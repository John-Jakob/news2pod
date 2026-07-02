"""Audio-Pipeline: Skript in Chunks aufteilen, je TTS-Call (WAV), mit Silence concatenieren, loudnorm, final als MP3."""
from __future__ import annotations
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lib_tts import synthesize

CHUNK_MARKER = "==="
SAMPLE_RATE = 44100


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg nicht gefunden. Bitte installieren (brew install ffmpeg / apt install ffmpeg).")
    return path


def split_script(script: str) -> list[str]:
    chunks = [c.strip() for c in script.split(CHUNK_MARKER)]
    chunks = [c for c in chunks if c]
    return chunks or [script.strip()]


def _make_silence_wav(ffmpeg: str, dst: Path, seconds: float) -> None:
    """Mono-WAV mit Stille der gewünschten Länge."""
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
         "-t", f"{seconds:.3f}",
         "-c:a", "pcm_s16le",
         str(dst)],
        check=True,
    )


def _normalize_to_wav(ffmpeg: str, src: Path, dst: Path) -> None:
    """Wandelt einen TTS-Chunk in normiertes WAV (mono, 44.1 kHz, 16-bit) um.
    Sprache ist mono; das spart ~1/3 Dateigröße gegenüber Stereo.
    Akzeptiert MP3/WAV/PCM-Inputs. Bei reinem PCM brauchen wir extra-Argumente."""
    is_raw_pcm = src.suffix == ".pcm"
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    if is_raw_pcm:
        cmd += ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1"]
    cmd += ["-i", str(src),
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-c:a", "pcm_s16le",
            str(dst)]
    subprocess.run(cmd, check=True)


def _concat_and_encode(ffmpeg: str, parts: list[Path], silence: Path,
                       out_path: Path, target_lufs: float) -> None:
    """WAV-Concat via concat-Demuxer (sample-exakt, kein Frame-Drop), dann MP3 mit loudnorm."""
    list_file = out_path.parent / ".concat.txt"
    interleaved: list[Path] = []
    for i, p in enumerate(parts):
        interleaved.append(p)
        if i < len(parts) - 1:
            interleaved.append(silence)
    list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in interleaved), encoding="utf-8")
    af = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-af", af,
         "-c:a", "libmp3lame", "-b:a", "64k", "-ar", str(SAMPLE_RATE), "-ac", "1",
         str(out_path)],
        check=True,
    )
    list_file.unlink(missing_ok=True)


def synthesize_episode(script: str, topic: dict, out_path: Path,
                       gap_seconds: float = 0.7, target_lufs: float = -16.0) -> Path:
    """Synthesizes a multi-chunk episode and writes the final normalized MP3 to out_path.

    Verwendet pro Chunk eine TTS-Anfrage im WAV-Format (kein MP3-Frame-Padding),
    konkateniert dann sample-exakt mit Silence-WAV und encodiert erst am Ende nach MP3.
    """
    ffmpeg = _ffmpeg()
    chunks = split_script(script)
    print(f"      Chunks: {len(chunks)} (Pause {gap_seconds}s, Loudness {target_lufs} LUFS, WAV-Pipeline)", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="news2pod-") as tmpd:
        tmp = Path(tmpd)
        wavs: list[Path] = []
        provider = (topic.get("tts_provider") or ("openai" if topic.get("voice") else "elevenlabs")).lower()
        for i, chunk in enumerate(chunks):
            # OpenAI liefert echtes WAV; ElevenLabs liefert rohes PCM, das wir als .pcm speichern.
            if provider == "elevenlabs":
                raw = tmp / f"chunk_{i:02d}.pcm"
                raw.write_bytes(synthesize(chunk, topic, response_format="wav"))
            else:
                raw = tmp / f"chunk_{i:02d}_raw.wav"
                raw.write_bytes(synthesize(chunk, topic, response_format="wav"))
            normalized = tmp / f"chunk_{i:02d}.wav"
            _normalize_to_wav(ffmpeg, raw, normalized)
            wavs.append(normalized)
        silence = tmp / "silence.wav"
        _make_silence_wav(ffmpeg, silence, gap_seconds)
        _concat_and_encode(ffmpeg, wavs, silence, out_path, target_lufs)
    return out_path
