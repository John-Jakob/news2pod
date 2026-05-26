"""Text-to-Speech mit austauschbaren Providern (OpenAI, ElevenLabs)."""
from __future__ import annotations
import os
from pathlib import Path
import requests

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"


def _elevenlabs(text: str, topic: dict, out_path: Path) -> Path:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY ist nicht gesetzt.")
    voice_id = topic.get("voice_id")
    if not voice_id:
        raise RuntimeError("topic.voice_id fehlt für tts_provider=elevenlabs.")
    model = topic.get("voice_model", "eleven_multilingual_v2")
    url = ELEVENLABS_URL.format(voice_id=voice_id)
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                            "style": 0.0, "use_speaker_boost": True},
    }
    r = requests.post(url, json=payload, headers=headers, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:500]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return out_path


def _openai(text: str, topic: dict, out_path: Path) -> Path:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt.")
    voice = topic.get("voice", "onyx")
    model = topic.get("tts_model", "gpt-4o-mini-tts")
    instructions = topic.get(
        "tts_instructions",
        "Sprich ruhig, klar und sachlich wie ein professioneller deutscher Nachrichten-Sprecher. "
        "Tempo moderat, kein Drama, deutliche Aussprache englischer Eigennamen.",
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }
    if model == "gpt-4o-mini-tts":
        payload["instructions"] = instructions
    r = requests.post(OPENAI_TTS_URL, json=payload, headers=headers, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI TTS {r.status_code}: {r.text[:500]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return out_path


PROVIDERS = {"openai": _openai, "elevenlabs": _elevenlabs}


def tts_to_mp3(text: str, topic: dict, out_path: Path) -> Path:
    provider = (topic.get("tts_provider")
                or ("openai" if topic.get("voice") else "elevenlabs")).lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Unbekannter tts_provider: {provider}")
    return PROVIDERS[provider](text, topic, out_path)
