from __future__ import annotations

from types import SimpleNamespace

from app.services import tts_service
from app.services.tts_service import SynthesizedAudio


def test_kokoro_pipeline_uses_explicit_repo_and_zh_warmup(monkeypatch) -> None:
    tts_service._PIPELINES.clear()
    created: list[dict[str, object]] = []
    calls: list[tuple[str, str]] = []

    class FakePipeline:
        def __init__(self, *, lang_code: str, repo_id: str, device: str) -> None:
            created.append(
                {
                    "lang_code": lang_code,
                    "repo_id": repo_id,
                    "device": device,
                }
            )
            self.lang_code = lang_code

        def __call__(self, text: str, *, voice: str, speed: float):
            calls.append((self.lang_code, text))
            return [SimpleNamespace(audio=[0.0, 0.0])]

    monkeypatch.setitem(__import__("sys").modules, "kokoro", SimpleNamespace(KPipeline=FakePipeline))

    service = tts_service.KokoroTtsService(
        default_en_voice="af_heart",
        default_zh_voice="zf_xiaobei",
        device="cpu",
    )

    service.preload()

    assert created == [
        {"lang_code": "a", "repo_id": "hexgrad/Kokoro-82M", "device": "cpu"},
        {"lang_code": "z", "repo_id": "hexgrad/Kokoro-82M", "device": "cpu"},
    ]
    assert calls == [("a", "Hello."), ("z", "\u4f60\u597d\u3002")]


def test_synthesize_text_in_paragraphs_reports_progress_and_merges_audio() -> None:
    calls: list[str] = []
    progress_updates: list[tuple[int, int]] = []
    chunk_audio = tts_service._wave_bytes_from_chunks([[0.0, 0.0]], 24000)

    class FakeService:
        def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
            calls.append(text)
            return SynthesizedAudio(audio_bytes=chunk_audio, mime_type="audio/wav", sample_rate=24000)

    audio = tts_service.synthesize_text_in_paragraphs(
        FakeService(),
        "First paragraph.\n\nSecond paragraph.",
        progress_callback=lambda completed, total: progress_updates.append((completed, total)),
    )

    assert calls == ["First paragraph.", "Second paragraph."]
    assert progress_updates == [(0, 2), (1, 2), (2, 2)]
    assert len(audio.audio_bytes) > len(chunk_audio)
