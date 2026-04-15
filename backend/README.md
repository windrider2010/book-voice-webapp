# Backend

FastAPI backend for the Book Voice web app.

Core endpoints:

- `POST /api/ocr`
- `POST /api/read`
- `POST /api/read/jobs`
- `GET /api/read/jobs/{request_id}`
- `GET /media/audio/{request_id}`
- `GET /healthz`

Diagnostics:

- `python scripts/run_fixture_pipeline.py`
- Runs `tests/ocr_voice_test.png` through the real OCR + Kokoro TTS stack.
- Saves `.txt`, `.wav`, and timing `.json` outputs under `backend/var/diagnostics/`.
