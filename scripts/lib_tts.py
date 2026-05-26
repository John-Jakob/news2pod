"""ElevenLabs Text-to-Speech."""
from __future__ import annotations
import os
from pathlib import Path
import requests

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def tts_to_mp3(text: str, voice_id: str, out_path: Path, model: str = "eleven_multilingual_v2") -> Path:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY ist nicht gesetzt.")

    url = ELEVENLABS_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    r = requests.post(url, json=payload, headers=headers, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs-Fehler {r.status_code}: {r.text[:500]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return out_path
