# Docker build so ffmpeg (needed for voice notes) is guaranteed present,
# regardless of hosting provider. Works on Render, Railway, Fly.io, or any
# other Docker-based host.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the faster-whisper speech-to-text model at BUILD time,
# baking it into the image, instead of leaving it to download the first
# time someone actually sends a voice message. Without this, the very
# first voice request after each deploy silently triggers a ~150MB model
# download from Hugging Face on Render's shared free-tier CPU/bandwidth --
# slow enough that it can feel broken or time out, while plain text
# messages (which never touch Whisper) keep working fine the whole time.
# That mismatch -- "text works, voice doesn't" -- is exactly this. Keep
# this ARG in sync with the WHISPER_MODEL_SIZE env var you actually set in
# Render, so the size baked in here matches the size requested at runtime.
ARG WHISPER_MODEL_SIZE=base
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"

COPY . .

# Render (and most hosts) inject $PORT; default to 10000 for local `docker run`.
ENV PORT=10000
EXPOSE 10000

# Single worker (keeps one copy of the Whisper model in memory -- important
# on a free/small instance), multiple threads to still handle concurrent
# requests, generous timeout for slower voice-note round trips.
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
