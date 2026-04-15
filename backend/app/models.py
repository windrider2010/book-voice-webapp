from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OcrBlock(BaseModel):
    text: str
    confidence: float | None = None
    box: list[list[float]] = Field(default_factory=list)


class OcrResponse(BaseModel):
    request_id: str
    text: str
    blocks: list[OcrBlock]
    detected_scripts: list[str]


class ReadResponse(BaseModel):
    request_id: str
    text: str
    audio_url: str
    mime_type: str = "audio/wav"
    expires_at: str


class ReadJobAcceptedResponse(BaseModel):
    request_id: str
    status: Literal["queued", "processing", "completed", "failed"]


class ReadJobStatusResponse(BaseModel):
    request_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    stage: Literal["queued", "ocr", "tts", "completed", "failed"]
    text: str | None = None
    audio_url: str | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    paragraphs_total: int = 0
    paragraphs_completed: int = 0
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
