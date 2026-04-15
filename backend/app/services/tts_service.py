from __future__ import annotations

import io
import os
import sys
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.script_utils import SpeechSegment, split_text_by_script

_PIPELINE_LOCK = threading.Lock()
_PIPELINES: dict[tuple[str, str], Any] = {}
_DLL_DIRECTORY_LOCK = threading.Lock()
_DLL_DIRECTORY_PATHS: set[str] = set()
_DLL_DIRECTORY_HANDLES: list[Any] = []
_ESPEAK_DATA_DIR_NAME = "espeak-ng-data"
_KOKORO_REPO_ID = "hexgrad/Kokoro-82M"


@dataclass(slots=True)
class SynthesizedAudio:
    audio_bytes: bytes
    mime_type: str
    sample_rate: int


class TtsService(Protocol):
    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        """Convert text into speech audio."""

    def preload(self) -> None:
        """Warm runtime assets so the first user request is not a cold start."""


class KokoroTtsService:
    provider_name = "kokoro"
    mime_type = "audio/wav"
    sample_rate = 24000

    def __init__(
        self,
        *,
        default_en_voice: str,
        default_zh_voice: str,
        device: str = "cpu",
        speed: float = 1.0,
        espeak_ng_path: str | None = None,
    ) -> None:
        self._default_en_voice = default_en_voice
        self._default_zh_voice = default_zh_voice
        self._device = device
        self._speed = speed
        self._espeak_ng_path = espeak_ng_path

    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        cleaned = text.strip()
        if not cleaned:
            raise RuntimeError("Cannot synthesize empty text.")

        segments = split_text_by_script(cleaned)
        if not segments:
            default_script = "cjk" if (lang_hint or "").strip().lower() == "zh" else "latin"
            segments = [SpeechSegment(script=default_script, text=cleaned)]

        chunks: list[Any] = []
        for segment in segments:
            lang_code, voice = _language_for_segment(
                segment=segment,
                default_en_voice=self._default_en_voice,
                default_zh_voice=self._default_zh_voice,
            )
            pipeline = _get_pipeline(lang_code=lang_code, device=self._device, espeak_ng_path=self._espeak_ng_path)
            for result in pipeline(segment.text, voice=voice, speed=self._speed):
                audio = getattr(result, "audio", None)
                if audio is None and isinstance(result, tuple) and len(result) >= 3:
                    audio = result[2]
                if audio is not None:
                    chunks.append(audio)

        if not chunks:
            raise RuntimeError("Kokoro returned no audio chunks.")
        return SynthesizedAudio(
            audio_bytes=_wave_bytes_from_chunks(chunks, self.sample_rate),
            mime_type=self.mime_type,
            sample_rate=self.sample_rate,
        )

    def preload(self) -> None:
        warmups = [
            ("Hello.", "a", self._default_en_voice),
            ("\u4f60\u597d\u3002", "z", self._default_zh_voice),
        ]
        for text, lang_code, voice in warmups:
            pipeline = _get_pipeline(lang_code=lang_code, device=self._device, espeak_ng_path=self._espeak_ng_path)
            for _ in pipeline(text, voice=voice, speed=self._speed):
                pass


def _language_for_segment(
    *,
    segment: SpeechSegment,
    default_en_voice: str,
    default_zh_voice: str,
) -> tuple[str, str]:
    if segment.script == "cjk":
        return "z", default_zh_voice
    return "a", default_en_voice


def _get_pipeline(*, lang_code: str, device: str, espeak_ng_path: str | None) -> Any:
    key = (lang_code, device)
    with _PIPELINE_LOCK:
        existing = _PIPELINES.get(key)
        if existing is not None:
            return existing
        try:
            from kokoro import KPipeline
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Kokoro is unavailable. Run `uv sync --project backend` to install TTS dependencies."
            ) from exc
        if espeak_ng_path:
            _apply_explicit_espeak_override(espeak_ng_path)
        pipeline = KPipeline(lang_code=lang_code, repo_id=_KOKORO_REPO_ID, device=device)
        _PIPELINES[key] = pipeline
        return pipeline


def _platform_library_names() -> tuple[str, ...]:
    if os.name == "nt":
        return ("libespeak-ng.dll", "espeak-ng.dll")
    if sys.platform == "darwin":  # pragma: no cover
        return ("libespeak-ng.dylib", "espeak-ng.dylib")
    return ("libespeak-ng.so", "espeak-ng.so")


def _find_library(base_dir: Path) -> Path | None:
    for name in _platform_library_names():
        candidate = base_dir / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def _find_data_path(base_dir: Path) -> Path | None:
    candidate = base_dir / _ESPEAK_DATA_DIR_NAME
    if candidate.is_dir():
        return candidate.resolve()
    return None


def _resolve_explicit_espeak_paths(explicit_path: str) -> tuple[str, str]:
    raw = Path(str(explicit_path or "").strip()).expanduser()
    if not str(raw):
        raise RuntimeError("ESPEAK_NG_PATH is empty.")
    if not raw.exists():
        raise RuntimeError(f"ESPEAK_NG_PATH does not exist: {raw}")

    base_dir = raw if raw.is_dir() else raw.parent
    library_path: Path | None = None
    data_path: Path | None = None

    if raw.is_dir():
        if raw.name.lower() == _ESPEAK_DATA_DIR_NAME:
            library_path = _find_library(raw.parent)
            data_path = raw.resolve()
        else:
            library_path = _find_library(raw)
            data_path = _find_data_path(raw)
    else:
        lowered_name = raw.name.lower()
        if lowered_name in {name.lower() for name in _platform_library_names()}:
            library_path = raw.resolve()
        data_path = _find_data_path(base_dir)
        if lowered_name == _ESPEAK_DATA_DIR_NAME:
            data_path = raw.resolve()
            library_path = _find_library(base_dir)
        elif library_path is None:
            library_path = _find_library(base_dir)

    if library_path is None:
        raise RuntimeError(f"Unable to locate the eSpeak NG library next to: {raw}")
    if data_path is None:
        raise RuntimeError(f"Unable to locate `{_ESPEAK_DATA_DIR_NAME}` next to: {raw}")
    return str(library_path), str(data_path)


def _register_windows_dll_directory(directory: Path) -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    resolved = str(directory.resolve())
    with _DLL_DIRECTORY_LOCK:
        if resolved in _DLL_DIRECTORY_PATHS:
            return
        handle = os.add_dll_directory(resolved)
        _DLL_DIRECTORY_HANDLES.append(handle)
        _DLL_DIRECTORY_PATHS.add(resolved)


def _apply_explicit_espeak_override(explicit_path: str) -> None:
    library_path, data_path = _resolve_explicit_espeak_paths(explicit_path)
    try:
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Phonemizer eSpeak integration is unavailable.") from exc
    library_dir = Path(library_path).parent
    _register_windows_dll_directory(library_dir)
    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = library_path
    os.environ["PHONEMIZER_ESPEAK_DATA_PATH"] = data_path
    EspeakWrapper.set_library(library_path)
    EspeakWrapper.set_data_path(data_path)


def _float_to_pcm16(value: float) -> int:
    clipped = max(-1.0, min(1.0, float(value)))
    if clipped >= 1.0:
        return 32767
    if clipped <= -1.0:
        return -32768
    return int(round(clipped * 32767))


def _audio_chunk_to_pcm_bytes(chunk: Any) -> bytes:
    if hasattr(chunk, "tolist"):
        chunk = chunk.tolist()
    if isinstance(chunk, (bytes, bytearray)):
        return bytes(chunk)
    if not isinstance(chunk, (list, tuple)):
        raise RuntimeError(f"Unsupported Kokoro audio chunk type: {type(chunk)!r}")
    pcm = bytearray()
    for sample in chunk:
        pcm.extend(int(_float_to_pcm16(sample)).to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


def _wave_bytes_from_chunks(chunks: list[Any], sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for chunk in chunks:
            wav_file.writeframes(_audio_chunk_to_pcm_bytes(chunk))
    return buffer.getvalue()
