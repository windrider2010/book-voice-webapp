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
    def __init__(self, root_dir: Path, *, ttl_seconds: int, max_bytes: int | None = None) -> None:
        self.root_dir = root_dir
        self.ttl_seconds = ttl_seconds
        self.max_bytes = max_bytes if max_bytes and max_bytes > 0 else None
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def store_audio(self, *, request_id: str, audio_bytes: bytes, mime_type: str, text: str) -> MediaAsset:
        self.cleanup_expired()
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        created_at = datetime.now(UTC).isoformat()
        audio_path = self.root_dir / f"{request_id}.wav"
        metadata_path = self.root_dir / f"{request_id}.json"
        audio_path.write_bytes(audio_bytes)
        metadata_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mime_type": mime_type,
                    "created_at": created_at,
                    "expires_at": expires_at.isoformat(),
                    "size_bytes": len(audio_bytes),
                    "text": text,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if self.max_bytes is not None:
            self.cleanup_to_size_limit(protected_request_id=request_id)
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

    def cleanup_to_size_limit(self, *, protected_request_id: str | None = None) -> int:
        if self.max_bytes is None:
            return 0

        records = []
        total_bytes = 0
        for metadata_path in self.root_dir.glob("*.json"):
            audio_path = metadata_path.with_suffix(".wav")
            if not audio_path.exists():
                continue
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request_id = payload.get("request_id", metadata_path.stem)
            size_bytes = int(payload.get("size_bytes") or audio_path.stat().st_size)
            total_bytes += size_bytes
            records.append(
                {
                    "request_id": request_id,
                    "created_at": payload.get("created_at") or "",
                    "audio_path": audio_path,
                    "metadata_path": metadata_path,
                    "size_bytes": size_bytes,
                }
            )

        if total_bytes <= self.max_bytes:
            return 0

        removed = 0
        records.sort(key=lambda item: (item["request_id"] == protected_request_id, item["created_at"]))
        for record in records:
            if total_bytes <= self.max_bytes:
                break
            if record["request_id"] == protected_request_id:
                continue
            _unlink_if_exists(record["audio_path"])
            _unlink_if_exists(record["metadata_path"])
            total_bytes -= record["size_bytes"]
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
