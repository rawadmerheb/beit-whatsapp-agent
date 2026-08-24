# -*- coding: utf-8 -*-
"""
Web chat + WhatsApp webhook for the Lebanese Real Estate AI agent.

Two ways to reach the same agent:

  A) Browser chat window at "/" (chat.html) -- talks to POST /api/chat.
     No Twilio/WhatsApp needed at all; useful for testing or as a standalone
     "landing page" demo people can use directly from a link.
  B) WhatsApp, via Twilio -> POST /whatsapp (needs TWILIO_ACCOUNT_SID /
     TWILIO_AUTH_TOKEN and a Sandbox or real WhatsApp Sender configured).

Both paths share the same brain (agent/claude_client.py's ask_agent(), which
can call the `search_properties` tool -- Arkan Estate first, public portals
as a fallback) and the same voice pipeline (agent/voice.py): incoming voice
is transcribed with faster-whisper, and a voice reply is only synthesized
back when the incoming message was itself voice.

Run locally with `python app.py`, then open http://localhost:5000 for the
web chat, or expose it publicly (see README) and point your Twilio WhatsApp
Sandbox's "when a message comes in" webhook at `<public-url>/whatsapp`.
"""

import os
import uuid

from dotenv import load_dotenv

load_dotenv()

import asyncio  # noqa: E402
import requests  # noqa: E402
from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from twilio.twiml.messaging_response import MessagingResponse  # noqa: E402

from agent.claude_client import ask_agent  # noqa: E402
from agent.voice import synthesize, synthesize_mp3, transcribe  # noqa: E402

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Optional now that the web chat ("/") works without Twilio at all -- only
# needed for the WhatsApp path (POST /whatsapp). Left unset or blank, the
# web chat still works fine; the WhatsApp route just won't be reachable
# meaningfully until these are real values.
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
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
CHAT_HISTORY = {}  # same idea, keyed by the web chat's per-browser session_id
HISTORY_TURNS_KEPT = 12


@app.route("/")
def web_chat_page():
    """Serves the browser chat window -- text or voice, no WhatsApp needed."""
    return send_from_directory(BASE_DIR, "chat.html")


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Browser chat endpoint. Accepts multipart/form-data with a
    `session_id` (any string the page makes up, used only to keep that
    browser's conversation history separate from everyone else's) and
    either a `message` text field or an `audio` file field (a recorded
    voice clip -- any format ffmpeg can decode, e.g. the webm/opus a
    browser's MediaRecorder produces). Returns JSON: {reply, transcript,
    audio_url}. `audio_url` is only present when the input itself was
    voice, matching the WhatsApp behavior of replying by voice only when
    asked by voice.
    """
    session_id = (request.form.get("session_id") or "web-anon").strip()
    user_text = (request.form.get("message") or "").strip()
    is_voice_input = False

    audio_file = request.files.get("audio")
    if audio_file and audio_file.filename:
        is_voice_input = True
        # Keep the browser's file extension (chat.html always sends
        # "recording.webm") so ffmpeg has an explicit hint about the
        # container format instead of relying entirely on content-sniffing.
        ext = os.path.splitext(audio_file.filename)[1] or ".webm"
        local_path = os.path.join(AUDIO_DIR, f"web_in_{uuid.uuid4().hex}{ext}")
        audio_file.save(local_path)
        try:
            user_text, _lang = transcribe(local_path)
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    if not user_text:
        return jsonify({"error": "I didn't receive any text or audio -- try again."}), 400

    history = CHAT_HISTORY.get(session_id, [])
    reply_text, new_history = ask_agent(user_text, history)
    CHAT_HISTORY[session_id] = new_history[-HISTORY_TURNS_KEPT:]

    result = {"reply": reply_text, "transcript": user_text if is_voice_input else None}

    if is_voice_input:
        try:
            mp3_path = asyncio.run(synthesize_mp3(reply_text, AUDIO_DIR))
            result["audio_url"] = f"/audio/{os.path.basename(mp3_path)}"
        except Exception:  # noqa: BLE001
            app.logger.exception("TTS failed for web chat, replying with text only")

    return jsonify(result)


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
