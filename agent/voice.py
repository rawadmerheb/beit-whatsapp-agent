# -*- coding: utf-8 -*-
"""
Voice handling: speech-to-text (incoming WhatsApp voice notes) and
text-to-speech (outgoing voice replies).

- STT uses local faster-whisper -- no API key, runs on CPU, handles
  Arabic/French/English (and the code-switching common in Lebanese speech)
  reasonably well. First run downloads the model (~150-500MB depending on
  size) from Hugging Face, so it needs internet the first time.
- TTS uses edge-tts (Microsoft's free neural voices, no API key) --
  including native Lebanese Arabic voices (ar-LB-*).
- ffmpeg (already required on the host) handles audio format conversion:
  WhatsApp voice notes arrive as audio/ogg (opus) and need to become WAV
  for Whisper; outgoing WhatsApp replies are converted to ogg/opus so
  WhatsApp renders them as a native-looking playable voice note; browser
  chat replies stay as plain .mp3, which every browser plays natively.
"""

import os
import re
import subprocess
import uuid

import edge_tts
from faster_whisper import WhisperModel

_model = None


def get_model():
    global _model
    if _model is None:
        size = os.getenv("WHISPER_MODEL_SIZE", "small")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model


def transcribe(input_audio_path):
    """Returns (text, detected_language_code)."""
    wav_path = input_audio_path + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_audio_path, "-ar", "16000", "-ac", "1", wav_path],
        check=True, capture_output=True,
    )
    try:
        segments, info = get_model().transcribe(wav_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, info.language
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


ARABIC_RE = re.compile(r"[؀-ۿ]")
FRENCH_HINT_RE = re.compile(
    r"\b(le|la|les|des|est|vous|bonjour|merci|appartement)\b", re.IGNORECASE
)

# Pick from https://github.com/rany2/edge-tts `edge-tts --list-voices` for
# more options. ar-LB is a native Lebanese Arabic voice.
VOICE_MAP = {
    "ar": "ar-LB-LailaNeural",
    "fr": "fr-FR-DeniseNeural",
    "en": "en-US-AriaNeural",
}


def pick_voice(text):
    if ARABIC_RE.search(text):
        return VOICE_MAP["ar"]
    if FRENCH_HINT_RE.search(text):
        return VOICE_MAP["fr"]
    return VOICE_MAP["en"]


async def synthesize(text, out_dir):
    """Generate a spoken reply and return the path to an .ogg (opus) file
    ready to send as a WhatsApp voice note."""
    voice = pick_voice(text)
    stem = uuid.uuid4().hex
    mp3_path = os.path.join(out_dir, f"{stem}.mp3")
    ogg_path = os.path.join(out_dir, f"{stem}.ogg")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)

    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "32k", ogg_path],
        check=True, capture_output=True,
    )
    os.remove(mp3_path)
    return ogg_path


async def synthesize_mp3(text, out_dir):
    """Same idea as synthesize(), but returns the .mp3 directly instead of
    converting to .ogg/opus. Used for the browser chat's voice replies --
    mp3 plays natively in every major browser (unlike ogg/opus, which
    Safari doesn't reliably support), so no conversion step is needed."""
    voice = pick_voice(text)
    stem = uuid.uuid4().hex
    mp3_path = os.path.join(out_dir, f"{stem}.mp3")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)
    return mp3_path
