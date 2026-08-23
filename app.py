# -*- coding: utf-8 -*-
"""
WhatsApp webhook for the Lebanese Real Estate AI agent.

Flow per incoming message (Twilio -> POST /whatsapp):
  1. If it's a voice note, download it (authenticated with your Twilio
     credentials) and transcribe it locally with faster-whisper.
  2. Send the (transcribed or typed) text to Claude, which can call the
     `search_properties` tool (Arkan Estate first, public portals as a
     fallback) via agent/claude_client.py.
  3. Reply with text. If the incoming message was a voice note, ALSO
     synthesize a spoken reply (matching the detected language) and attach
     it as a WhatsApp voice note.

Run locally with `python app.py`, expose it publicly (see README), and point
your Twilio WhatsApp Sandbox's "when a message comes in" webhook at
`<public-url>/whatsapp`.
"""

import os

from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
import requests  # noqa: E402
from flask import Flask, request, send_from_directory  # noqa: E402
from twilio.twiml.messaging_response import MessagingResponse  # noqa: E402

from agent.claude_client import ask_agent  # noqa: E402
from agent.voice import transcribe, synthesize  # noqa: E402

app = Flask(__name__)

TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
# Set once you know your public URL (see README) -- needed so Twilio can
# fetch the generated voice-reply audio file back from you. Falls back to
# Render's auto-provided RENDER_EXTERNAL_URL when hosted there, so you don't
# have to fill this in by hand after a Render deploy.
PUBLIC_BASE_URL = (
    os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")
).rstrip("/")

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "tmp_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Simple in-memory per-sender conversation history. Fine for a demo/small
# pilot; replace with Redis/a DB before handling many concurrent users or
# before you need history to survive a restart.
HISTORY = {}
HISTORY_TURNS_KEPT = 12


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    sender = request.form.get("From", "unknown")
    body = (request.form.get("Body") or "").strip()
    num_media = int(request.form.get("NumMedia", 0) or 0)

    is_voice_input = False
    user_text = body

    if num_media > 0:
        content_type = request.form.get("MediaContentType0", "")
        media_url = request.form.get("MediaUrl0")
        if media_url and content_type.startswith("audio"):
            is_voice_input = True
            local_path = os.path.join(
                AUDIO_DIR, f"in_{abs(hash(media_url))}.ogg"
            )
            r = requests.get(media_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=20)
            r.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(r.content)
            try:
                user_text, _lang = transcribe(local_path)
            finally:
                if os.path.exists(local_path):
                    os.remove(local_path)

    if not user_text:
        user_text = "(the message arrived empty -- ask the person to try again)"

    history = HISTORY.get(sender, [])
    reply_text, new_history = ask_agent(user_text, history)
    HISTORY[sender] = new_history[-HISTORY_TURNS_KEPT:]

    twiml = MessagingResponse()
    msg = twiml.message(reply_text)

    if is_voice_input:
        if not PUBLIC_BASE_URL:
            app.logger.warning(
                "PUBLIC_BASE_URL is not set -- skipping voice reply, sending text only."
            )
        else:
            try:
                ogg_path = asyncio.run(synthesize(reply_text, AUDIO_DIR))
                filename = os.path.basename(ogg_path)
                msg.media(f"{PUBLIC_BASE_URL}/audio/{filename}")
            except Exception:  # noqa: BLE001
                app.logger.exception("TTS failed, falling back to text-only reply")

    return str(twiml)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
