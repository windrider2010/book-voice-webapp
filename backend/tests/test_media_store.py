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
