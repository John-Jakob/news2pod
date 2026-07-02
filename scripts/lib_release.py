"""Episoden-MP3s als GitHub-Release-Assets hosten (statt im Repo / auf Pages).

Release-Assets zählen nicht ins Pages-1-GB-Limit und blähen die Git-History
nicht auf. Tag-Schema: <slug>-<date>, Asset-Name: <date>.mp3.
"""
from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p


def repo_slug() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo
    p = _run(["git", "remote", "get-url", "origin"])
    if p.returncode != 0:
        raise RuntimeError("Kein GITHUB_REPOSITORY gesetzt und kein git-Remote 'origin' gefunden.")
    m = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", p.stdout.strip())
    if not m:
        raise RuntimeError(f"Kann Repo nicht aus origin-URL ableiten: {p.stdout.strip()}")
    return m.group(1)


def upload_episode(slug: str, date: str, mp3_path: Path) -> str:
    """Lädt die MP3 als Release-Asset hoch und liefert die stabile Download-URL."""
    repo = repo_slug()
    tag = f"{slug}-{date}"
    if _run(["gh", "release", "view", tag, "--repo", repo]).returncode != 0:
        p = _run(["gh", "release", "create", tag, "--repo", repo,
                  "--title", f"{slug} {date}",
                  "--notes", f"Tagesfolge {date} für Topic '{slug}'.",
                  str(mp3_path)])
    else:
        p = _run(["gh", "release", "upload", tag, str(mp3_path),
                  "--repo", repo, "--clobber"])
    if p.returncode != 0:
        raise RuntimeError(f"Release-Upload fehlgeschlagen ({tag}): {p.stderr[:300]}")
    return f"https://github.com/{repo}/releases/download/{tag}/{mp3_path.name}"
