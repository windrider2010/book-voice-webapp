from __future__ import annotations

import io
import threading
import time
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

    def preload(self) -> None:
        self.preloaded = True


class FakePreloadOcrService(FakeOcrService):
    def __init__(self) -> None:
        self.preloaded = False

    def preload(self) -> None:
        self.preloaded = True


class FakePreloadTtsService(FakeTtsService):
    def __init__(self) -> None:
        self.preloaded = False

    def preload(self) -> None:
        self.preloaded = True


class BlockingTtsService(FakeTtsService):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize_text(self, text: str, lang_hint: str | None = None) -> SynthesizedAudio:
        self.started.set()
        self.release.wait(timeout=1)
        return super().synthesize_text(text, lang_hint)


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


def _wait_for_job_completion(client: TestClient, request_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/read/jobs/{request_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for read job {request_id}")


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


def test_read_job_endpoint_returns_completed_status_and_audio_url(tmp_path: Path) -> None:
    with _make_client(tmp_path) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"lang_hint": "bilingual"},
        )
        assert start_response.status_code == 202
        request_id = start_response.json()["request_id"]

        payload = _wait_for_job_completion(client, request_id)
        assert payload["status"] == "completed"
        assert payload["stage"] == "completed"
        assert "world" in payload["text"]
        assert payload["mime_type"] == "audio/wav"
        assert payload["audio_url"].endswith(f"/media/audio/{request_id}")
        assert payload["paragraphs_total"] >= 1
        assert payload["paragraphs_completed"] == payload["paragraphs_total"]


def test_read_job_endpoint_surfaces_ocr_text_before_audio_completion(tmp_path: Path) -> None:
    blocking_tts = BlockingTtsService()
    app = create_app(
        ocr_service=FakeOcrService(),
        tts_service=blocking_tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )

    with TestClient(app) as client:
        start_response = client.post(
            "/api/read/jobs",
            files={"image": ("page.jpg", _sample_image_bytes(), "image/jpeg")},
            data={"lang_hint": "bilingual"},
        )
        assert start_response.status_code == 202
        request_id = start_response.json()["request_id"]
        assert blocking_tts.started.wait(timeout=1)

        status_response = client.get(f"/api/read/jobs/{request_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        assert payload["status"] == "processing"
        assert payload["stage"] == "tts"
        assert "world" in payload["text"]
        assert payload["paragraphs_total"] == 1
        assert payload["paragraphs_completed"] == 0

        blocking_tts.release.set()
        completed = _wait_for_job_completion(client, request_id)
        assert completed["status"] == "completed"


def test_read_job_endpoint_rejects_empty_input(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    start_response = client.post("/api/read/jobs", data={"text": "   "})
    assert start_response.status_code == 422


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


def test_app_preloads_runtime_dependencies_when_enabled(tmp_path: Path) -> None:
    ocr = FakePreloadOcrService()
    tts = FakePreloadTtsService()
    settings = Settings(preload_models=True)
    app = create_app(
        settings=settings,
        ocr_service=ocr,
        tts_service=tts,
        media_store=MediaStore(tmp_path / "media", ttl_seconds=3600),
    )
    with TestClient(app):
        pass
    assert ocr.preloaded is True
    assert tts.preloaded is True
