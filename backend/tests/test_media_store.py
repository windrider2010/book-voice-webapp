from __future__ import annotations

import time
from pathlib import Path

from app.services.media_store import MediaStore


def test_media_store_cleans_up_expired_assets(tmp_path: Path) -> None:
    store = MediaStore(tmp_path / "media", ttl_seconds=0)
    asset = store.store_audio(request_id="abc123", audio_bytes=b"wav", mime_type="audio/wav", text="hello")
    time.sleep(0.01)
    removed = store.cleanup_expired()
    assert removed == 1
    assert not asset.audio_path.exists()
    assert store.get_asset("abc123") is None


def test_media_store_prunes_oldest_assets_when_over_size_limit(tmp_path: Path) -> None:
    store = MediaStore(tmp_path / "media", ttl_seconds=3600, max_bytes=8)
    first = store.store_audio(request_id="first", audio_bytes=b"12345", mime_type="audio/wav", text="one")
    second = store.store_audio(request_id="second", audio_bytes=b"67890", mime_type="audio/wav", text="two")
    assert not first.audio_path.exists()
    assert first.metadata_path.exists() is False
    assert second.audio_path.exists()
    assert store.get_asset("first") is None
    assert store.get_asset("second") is not None
