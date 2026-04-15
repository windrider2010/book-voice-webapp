from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(slots=True)
class MediaAsset:
    request_id: str
    audio_path: Path
    metadata_path: Path
    mime_type: str
    expires_at: str
    text: str


class MediaStore:
    def __init__(self, root_dir: Path, *, ttl_seconds: int) -> None:
        self.root_dir = root_dir
        self.ttl_seconds = ttl_seconds
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def store_audio(self, *, request_id: str, audio_bytes: bytes, mime_type: str, text: str) -> MediaAsset:
        self.cleanup_expired()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        audio_path = self.root_dir / f"{request_id}.wav"
        metadata_path = self.root_dir / f"{request_id}.json"
        audio_path.write_bytes(audio_bytes)
        metadata_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mime_type": mime_type,
                    "expires_at": expires_at.isoformat(),
                    "text": text,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return MediaAsset(
            request_id=request_id,
            audio_path=audio_path,
            metadata_path=metadata_path,
            mime_type=mime_type,
            expires_at=expires_at.isoformat(),
            text=text,
        )

    def get_asset(self, request_id: str) -> MediaAsset | None:
        self.cleanup_expired()
        audio_path = self.root_dir / f"{request_id}.wav"
        metadata_path = self.root_dir / f"{request_id}.json"
        if not audio_path.exists() or not metadata_path.exists():
            return None
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        expires_at = payload.get("expires_at", "")
        if _is_expired(expires_at):
            _unlink_if_exists(audio_path)
            _unlink_if_exists(metadata_path)
            return None
        return MediaAsset(
            request_id=request_id,
            audio_path=audio_path,
            metadata_path=metadata_path,
            mime_type=payload.get("mime_type", "audio/wav"),
            expires_at=expires_at,
            text=payload.get("text", ""),
        )

    def cleanup_expired(self) -> int:
        removed = 0
        for metadata_path in self.root_dir.glob("*.json"):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not _is_expired(payload.get("expires_at", "")):
                continue
            audio_path = metadata_path.with_suffix(".wav")
            _unlink_if_exists(audio_path)
            _unlink_if_exists(metadata_path)
            removed += 1
        return removed


def _is_expired(expires_at: str) -> bool:
    if not expires_at:
        return True
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= datetime.now(UTC)


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()
