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

COPY . .

# Render (and most hosts) inject $PORT; default to 10000 for local `docker run`.
ENV PORT=10000
EXPOSE 10000

# Single worker (keeps one copy of the Whisper model in memory -- important
# on a free/small instance), multiple threads to still handle concurrent
# requests, generous timeout for slower voice-note round trips.
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
