from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from time import perf_counter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.services.image_pipeline import normalize_uploaded_image
from app.services.ocr_service import PaddleOcrService
from app.services.tts_service import KokoroTtsService, synthesize_text_in_paragraphs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the real OCR + TTS pipeline against a fixture image and save the artifacts."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=BACKEND_DIR / "tests" / "ocr_voice_test.png",
        help="Image fixture to run through OCR and TTS.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_DIR / "var" / "diagnostics",
        help="Directory where text, wav, and JSON report files are written.",
    )
    parser.add_argument(
        "--lang-hint",
        default="bilingual",
        help="Language hint passed to OCR and TTS. Defaults to bilingual.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    fixture_path = args.fixture.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not fixture_path.is_file():
        raise FileNotFoundError(f"Fixture image not found: {fixture_path}")

    if os.name == "nt" and not settings.espeak_ng_path:
        default_espeak_dir = Path("C:/Program Files/eSpeak NG")
        if default_espeak_dir.exists():
            os.environ.setdefault("ESPEAK_NG_PATH", str(default_espeak_dir))

    request_id = f"fixture-{uuid.uuid4().hex[:8]}"
    raw_bytes = fixture_path.read_bytes()
    normalized = normalize_uploaded_image(
        raw_bytes,
        content_type="image/png",
        max_upload_bytes=settings.max_upload_bytes,
        image_max_side=settings.image_max_side,
    )

    ocr_service = PaddleOcrService(
        use_gpu=settings.paddle_use_gpu,
        enable_mkldnn=settings.paddle_enable_mkldnn,
        enable_hpi=settings.paddle_enable_hpi,
        cpu_threads=settings.paddle_cpu_threads,
    )
    tts_service = KokoroTtsService(
        default_en_voice=settings.default_en_voice,
        default_zh_voice=settings.default_zh_voice,
        device=settings.kokoro_device,
        speed=settings.kokoro_speed,
        espeak_ng_path=os.getenv("ESPEAK_NG_PATH") or settings.espeak_ng_path,
    )

    started = perf_counter()
    ocr_started = perf_counter()
    recognized = ocr_service.recognize(normalized.image, args.lang_hint)
    ocr_seconds = perf_counter() - ocr_started

    tts_started = perf_counter()
    audio = synthesize_text_in_paragraphs(tts_service, recognized.text, args.lang_hint)
    tts_seconds = perf_counter() - tts_started
    total_seconds = perf_counter() - started

    text_path = output_dir / f"{request_id}.txt"
    audio_path = output_dir / f"{request_id}.wav"
    report_path = output_dir / f"{request_id}.json"
    text_path.write_text(recognized.text, encoding="utf-8")
    audio_path.write_bytes(audio.audio_bytes)
    report_path.write_text(
        json.dumps(
            {
                "request_id": request_id,
                "fixture_path": str(fixture_path),
                "image_width": normalized.width,
                "image_height": normalized.height,
                "ocr_seconds": round(ocr_seconds, 3),
                "tts_seconds": round(tts_seconds, 3),
                "total_seconds": round(total_seconds, 3),
                "text_chars": len(recognized.text),
                "audio_bytes": len(audio.audio_bytes),
                "detected_scripts": recognized.detected_scripts,
                "text_path": str(text_path),
                "audio_path": str(audio_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"request_id={request_id}")
    print(f"fixture_path={fixture_path}")
    print(f"ocr_seconds={ocr_seconds:.3f}")
    print(f"tts_seconds={tts_seconds:.3f}")
    print(f"total_seconds={total_seconds:.3f}")
    print(f"text_chars={len(recognized.text)}")
    print(f"audio_bytes={len(audio.audio_bytes)}")
    print(f"text_path={text_path}")
    print(f"audio_path={audio_path}")
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
