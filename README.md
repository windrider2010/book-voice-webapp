# Book Voice Web App

An iPhone-first mobile web app for reading printed book pages aloud:

- Safari opens a thin web UI.
- The UI shows the rear camera preview, captures one frame, uploads it.
- FastAPI runs OCR with PaddleOCR.
- FastAPI turns the recognized text into speech with Kokoro.
- The phone plays the returned audio directly.

## Repo Layout

```text
book-voice-webapp/
  backend/   FastAPI API, OCR/TTS services, tests
  web/       Vue 3 + Vite mobile web app
```

## Local Development

### Backend

```powershell
cd C:\home\dev\book-voice-webapp
uv sync --project backend
uv run --directory backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The first real OCR/TTS request may download model assets required by PaddleOCR and Kokoro.

### Frontend

```powershell
cd C:\home\dev\book-voice-webapp\web
npm install
npm run dev
```

Vite proxies `/api`, `/media`, and `/healthz` to `http://localhost:8000`.

## Test

### Backend

```powershell
cd C:\home\dev\book-voice-webapp
uv run --directory backend pytest
```

### Frontend

```powershell
cd C:\home\dev\book-voice-webapp\web
npm test
```

## Production Notes

- The app must run behind HTTPS for iPhone Safari camera access.
- The backend serves the built `web/dist` directory in production for same-origin camera upload and audio playback.
- Uploaded images are validated and normalized entirely in memory; they are not persisted to disk.
- Audio files are cached on local disk with a TTL, a background cleanup loop, and an overall disk budget guard.
- `MAX_ACTIVE_READS=1` limits concurrent OCR+TTS jobs on CPU-first deployments.
- The Docker image is aligned for Oracle Ubuntu hosts running Linux containers: Node builds the Vue bundle in a separate stage, Python 3.12 runs the API, and the runtime image includes the Linux shared libraries commonly required by PaddleOCR/OpenCV and Kokoro/eSpeak.
- This stack is aligned for Oracle Ubuntu `arm64` and `x86_64` CPU hosts. `paddlepaddle` is resolved from Paddle's official CPU wheel index instead of PyPI so Linux `aarch64` builds can install the official ARM wheel in Docker.

## Docker On Oracle Ubuntu

Build:

```bash
docker build -t book-voice-webapp:latest .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env book-voice-webapp:latest
```

Recommended host checks on Oracle Ubuntu before deploy:

```bash
uname -m
docker --version
docker info
```

If `uname -m` returns `aarch64`, build and run the same image normally. The repo is configured to pull Paddle's ARM CPU wheel during image build.

## Server Deployment

This repo includes server-side deploy artifacts for an Oracle Ubuntu host:

- `docker-compose.yml` runs the app container on `127.0.0.1:8001`, persists generated audio in a named volume, and persists runtime model downloads in a cache volume.
- `deploy/nginx/book-voice-webapp.conf` is a host-level Nginx reverse-proxy config that terminates HTTPS and forwards traffic to the local Docker app.
- `deploy/systemd/book-voice-webapp.service` manages the Docker Compose stack under `systemd`.

Suggested server layout:

```bash
sudo mkdir -p /opt/book-voice-webapp
sudo chown $USER:$USER /opt/book-voice-webapp
```

Copy this repo to `/opt/book-voice-webapp`, then create `/opt/book-voice-webapp/.env` from `.env.example` and set at least:

```dotenv
APP_ENV=production
ALLOW_ORIGINS=https://your-domain.example
MAX_ACTIVE_READS=1
MAX_TEXT_CHARS=10000
MEDIA_TTL_SECONDS=3600
MEDIA_CLEANUP_INTERVAL_SECONDS=300
MEDIA_MAX_BYTES=536870912
KOKORO_DEVICE=cpu
PADDLE_USE_GPU=0
PADDLE_ENABLE_MKLDNN=0
PADDLE_ENABLE_HPI=0
PADDLE_CPU_THREADS=4
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
```

Install the Compose stack:

```bash
cd /opt/book-voice-webapp
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8001/healthz
```

Install Nginx:

```bash
sudo cp deploy/nginx/book-voice-webapp.conf /etc/nginx/sites-available/book-voice-webapp.conf
sudo ln -s /etc/nginx/sites-available/book-voice-webapp.conf /etc/nginx/sites-enabled/book-voice-webapp.conf
sudo nginx -t
sudo systemctl reload nginx
```

Update the placeholder domain and certificate paths in the Nginx config before enabling it.

Install the `systemd` unit:

```bash
sudo cp deploy/systemd/book-voice-webapp.service /etc/systemd/system/book-voice-webapp.service
sudo systemctl daemon-reload
sudo systemctl enable --now book-voice-webapp.service
sudo systemctl status book-voice-webapp.service
```
