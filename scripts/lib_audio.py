"""Audio-Pipeline: Skript in Chunks aufteilen, je TTS-Call, mit Silence concatenieren, loudnorm."""
from __future__ import annotations
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lib_tts import synthesize

CHUNK_MARKER = "==="


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg nicht gefunden. Bitte installieren (brew install ffmpeg / apt install ffmpeg).")
    return path


def split_script(script: str) -> list[str]:
    chunks = [c.strip() for c in script.split(CHUNK_MARKER)]
    chunks = [c for c in chunks if c]
    return chunks or [script.strip()]


def _make_silence(ffmpeg: str, dst: Path, seconds: float) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", f"{seconds:.3f}",
         "-c:a", "libmp3lame", "-b:a", "96k",
         str(dst)],
        check=True,
    )


def _concat_and_normalize(ffmpeg: str, parts: list[Path], silence: Path,
                          out_path: Path, target_lufs: float) -> None:
    """Concat parts interleaved with silence, then apply loudnorm in single pass."""
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
         "-c:a", "libmp3lame", "-b:a", "96k", "-ar", "44100", "-ac", "2",
         str(out_path)],
        check=True,
    )
    list_file.unlink(missing_ok=True)


def synthesize_episode(script: str, topic: dict, out_path: Path,
                       gap_seconds: float = 0.7, target_lufs: float = -16.0) -> Path:
    """Synthesizes a multi-chunk episode and writes the final normalized MP3 to out_path."""
    ffmpeg = _ffmpeg()
    chunks = split_script(script)
    print(f"      Chunks: {len(chunks)} (Pause {gap_seconds}s, Loudness {target_lufs} LUFS)", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="news2pod-") as tmpd:
        tmp = Path(tmpd)
        parts: list[Path] = []
        for i, chunk in enumerate(chunks):
            mp3 = tmp / f"chunk_{i:02d}.mp3"
            mp3.write_bytes(synthesize(chunk, topic))
            parts.append(mp3)
        silence = tmp / "silence.mp3"
        _make_silence(ffmpeg, silence, gap_seconds)
        _concat_and_normalize(ffmpeg, parts, silence, out_path, target_lufs)
    return out_path
