from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.services.media_store import MediaStore
from app.services.ocr_service import RecognizedBlock, RecognizedPage
from app.services.tts_service import SynthesizedAudio


class FakeOcrService:
    def recognize(self, image: Image.Image, lang_hint: str | None = None) -> RecognizedPage:
        return RecognizedPage(
            text="你好 world",
            blocks=[
                RecognizedBlock(text="你好", confidence=0.99, box=[[0, 0], [1, 0], [1, 1], [0, 1]]),
                RecognizedBlock(text="world", confidence=0.98, box=[[2, 2], [3, 2], [3, 3], [2, 3]]),
            ],
            detected_scripts=["cjk", "latin"],
        )


class FakeTtsService:
    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        return SynthesizedAudio(audio_bytes=b"RIFFfakewav", mime_type="audio/wav", sample_rate=24000)


def _make_client(tmp_path: Path, *, settings: Settings | None = None) -> TestClient:
    app = create_app(
        settings=settings,
        ocr_service=FakeOcrService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    return TestClient(app)


def _sample_image_bytes() -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (120, 60), color=(255, 255, 255))
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_ocr_endpoint_returns_text_and_blocks(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/ocr",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"lang_hint": "bilingual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "你好 world"
    assert payload["detected_scripts"] == ["cjk", "latin"]
    assert len(payload["blocks"]) == 2


def test_read_endpoint_rejects_image_and_text_together(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"text": "hello"},
    )
    assert response.status_code == 422
    assert "only one" in response.json()["detail"]


def test_read_endpoint_json_mode_returns_audio_url_and_text(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
        data={"lang_hint": "bilingual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "你好 world"
    assert payload["mime_type"] == "audio/wav"
    assert payload["audio_url"].endswith(f'/media/audio/{payload["request_id"]}')


def test_read_endpoint_stream_mode_returns_audio_and_link(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/api/read",
        data={"text": "hello", "response_mode": "stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["link"].startswith("<http://testserver/media/audio/")
    assert response.content == b"RIFFfakewav"


def test_audio_asset_endpoint_serves_cached_wav(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    read_response = client.post("/api/read", data={"text": "hello"})
    request_id = read_response.json()["request_id"]
    response = client.get(f"/media/audio/{request_id}")
    assert response.status_code == 200
    assert response.content == b"RIFFfakewav"


def test_read_endpoint_returns_busy_when_gate_is_full(tmp_path: Path) -> None:
    app = create_app(
        ocr_service=FakeOcrService(),
        tts_service=FakeTtsService(),
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    app.state.read_gate._active = 1
    client = TestClient(app)
    response = client.post("/api/read", data={"text": "hello"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_read_endpoint_rejects_overlong_text(tmp_path: Path) -> None:
    settings = Settings(max_text_chars=4)
    client = _make_client(tmp_path, settings=settings)
    response = client.post("/api/read", data={"text": "hello"})
    assert response.status_code == 422
    assert "character limit" in response.json()["detail"]
