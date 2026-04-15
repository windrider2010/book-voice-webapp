from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import get_settings
from app.models import HealthResponse, OcrBlock, OcrResponse, ReadResponse
from app.services.image_pipeline import ImageValidationError, normalize_uploaded_image
from app.services.media_store import MediaStore
from app.services.ocr_service import OcrService, PaddleOcrService
from app.services.tts_service import KokoroTtsService, TtsService

logger = logging.getLogger(__name__)


class ReadConcurrencyGate:
    def __init__(self, max_active: int) -> None:
        self._max_active = max_active
        self._lock = threading.Lock()
        self._active = 0

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self._max_active:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


def create_app(
    *,
    settings=None,
    ocr_service: OcrService | None = None,
    tts_service: TtsService | None = None,
    media_store: MediaStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.media_store.cleanup_expired()
        app.state.media_store.cleanup_to_size_limit()
        if app.state.settings.preload_models:
            await asyncio.to_thread(_preload_runtime_dependencies, app)
        cleanup_task = asyncio.create_task(_media_cleanup_loop(app))
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.ocr_service = ocr_service or PaddleOcrService(
        use_gpu=settings.paddle_use_gpu,
        enable_mkldnn=settings.paddle_enable_mkldnn,
        enable_hpi=settings.paddle_enable_hpi,
        cpu_threads=settings.paddle_cpu_threads,
    )
    app.state.tts_service = tts_service or KokoroTtsService(
        default_en_voice=settings.default_en_voice,
        default_zh_voice=settings.default_zh_voice,
        device=settings.kokoro_device,
        speed=settings.kokoro_speed,
        espeak_ng_path=settings.espeak_ng_path,
    )
    app.state.media_store = media_store or MediaStore(
        settings.media_root,
        ttl_seconds=settings.media_ttl_seconds,
        max_bytes=settings.media_max_bytes,
    )
    app.state.read_gate = ReadConcurrencyGate(settings.max_active_reads)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allow_origins) if settings.allow_origins != ("*",) else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/api/ocr", response_model=OcrResponse)
    async def run_ocr(image: UploadFile = File(...), lang_hint: str | None = Form(None)) -> OcrResponse:
        request_id = uuid.uuid4().hex
        normalized = await _read_and_normalize_upload(image, app)
        result = await asyncio.to_thread(app.state.ocr_service.recognize, normalized.image, lang_hint)
        return OcrResponse(
            request_id=request_id,
            text=result.text,
            blocks=[OcrBlock(text=block.text, confidence=block.confidence, box=block.box) for block in result.blocks],
            detected_scripts=result.detected_scripts,
        )

    @app.post("/api/read", response_model=ReadResponse)
    async def read_page(
        request: Request,
        image: UploadFile | None = File(None),
        text: str | None = Form(None),
        lang_hint: str | None = Form(None),
        response_mode: str = Form("json"),
    ) -> ReadResponse | StreamingResponse:
        response_mode = response_mode.strip().lower()
        if response_mode not in {"json", "stream"}:
            raise HTTPException(status_code=422, detail="response_mode must be either `json` or `stream`.")
        if image is None and not (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide either `image` or `text`.")
        if image is not None and (text or "").strip():
            raise HTTPException(status_code=422, detail="Provide only one of `image` or `text`, not both.")
        if not app.state.read_gate.try_acquire():
            raise HTTPException(
                status_code=503,
                detail="The OCR/TTS worker is busy. Retry shortly.",
                headers={"Retry-After": "5"},
            )

        try:
            request_id = uuid.uuid4().hex
            if image is not None:
                normalized = await _read_and_normalize_upload(image, app)
                recognized = await asyncio.to_thread(app.state.ocr_service.recognize, normalized.image, lang_hint)
                source_text = recognized.text
            else:
                source_text = (text or "").strip()

            if not source_text:
                raise HTTPException(status_code=422, detail="No readable text was produced from the submitted input.")
            if len(source_text) > settings.max_text_chars:
                raise HTTPException(
                    status_code=422,
                    detail=f"Text exceeds the {settings.max_text_chars} character limit.",
                )

            audio = await asyncio.to_thread(app.state.tts_service.synthesize_text, source_text, lang_hint)
            asset = app.state.media_store.store_audio(
                request_id=request_id,
                audio_bytes=audio.audio_bytes,
                mime_type=audio.mime_type,
                text=source_text,
            )
        finally:
            app.state.read_gate.release()

        audio_url = str(request.url_for("get_audio_asset", request_id=request_id))
        if response_mode == "stream":
            return StreamingResponse(
                iter([audio.audio_bytes]),
                media_type=audio.mime_type,
                headers={"Link": f'<{audio_url}>; rel="alternate"'},
            )
        return ReadResponse(
            request_id=request_id,
            text=source_text,
            audio_url=audio_url,
            mime_type=audio.mime_type,
            expires_at=asset.expires_at,
        )

    @app.get("/media/audio/{request_id}", name="get_audio_asset")
    async def get_audio_asset(request_id: str) -> FileResponse:
        asset = app.state.media_store.get_asset(request_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Audio asset not found or expired.")
        return FileResponse(asset.audio_path, media_type=asset.mime_type, filename=f"{request_id}.wav")

    _register_spa_routes(app)
    return app


async def _read_and_normalize_upload(upload: UploadFile, app: FastAPI):
    settings = app.state.settings
    raw_bytes = await upload.read()
    try:
        return normalize_uploaded_image(
            raw_bytes,
            content_type=upload.content_type,
            max_upload_bytes=settings.max_upload_bytes,
            image_max_side=settings.image_max_side,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _register_spa_routes(app: FastAPI) -> None:
    settings = app.state.settings
    index_path = settings.web_dist_dir / "index.html"

    @app.get("/", include_in_schema=False, response_model=None)
    async def root():
        if index_path.exists():
            return FileResponse(index_path)
        return JSONResponse({"message": "Frontend build not found. Build web/dist to serve the mobile app."})

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "media/", "healthz")):
            raise HTTPException(status_code=404)
        if not settings.web_dist_dir.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found.")
        candidate = settings.web_dist_dir / Path(full_path)
        if candidate.is_file():
            return FileResponse(candidate)
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404)


async def _media_cleanup_loop(app: FastAPI) -> None:
    interval = app.state.settings.media_cleanup_interval_seconds
    if interval <= 0:
        return
    while True:
        await asyncio.sleep(interval)
        try:
            app.state.media_store.cleanup_expired()
            app.state.media_store.cleanup_to_size_limit()
        except Exception:
            logger.exception("Background media cleanup failed")


def _preload_runtime_dependencies(app: FastAPI) -> None:
    ocr_service = app.state.ocr_service
    preload_ocr = getattr(ocr_service, "preload", None)
    if callable(preload_ocr):
        preload_ocr()

    tts_service = app.state.tts_service
    preload_tts = getattr(tts_service, "preload", None)
    if callable(preload_tts):
        preload_tts()


app = create_app()
