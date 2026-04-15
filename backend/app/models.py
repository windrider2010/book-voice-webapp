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


class HealthResponse(BaseModel):
    status: Literal["ok"]
