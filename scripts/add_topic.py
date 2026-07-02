#!/usr/bin/env python3
"""Interaktiver Helper: Claude schlägt Quellen für ein neues Thema vor, du wählst per Nummer, YAML wird geschrieben.

Beispiel:
    ANTHROPIC_API_KEY=... python scripts/add_topic.py
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml
from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_config import TOPICS_DIR

DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"  # Adam, multilingual
MODEL = os.environ.get("NEWS2POD_MODEL", "claude-sonnet-5")


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[äöüß]", lambda m: {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}[m.group()], s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "topic"


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"{prompt}{hint}: ").strip()
    return val or default


def suggest_sources(description: str) -> list[dict]:
    client = Anthropic()
    prompt = f"""Schlage 12 bis 18 seriöse Online-Quellen vor, die regelmässig tagesaktuell und mit journalistischen Standards über folgendes Thema berichten:

THEMA: {description}

Anforderungen:
- Mischung aus deutschsprachigen und englischsprachigen Quellen.
- Nur etablierte Redaktionen mit Impressum (keine reinen Blogs, keine Aggregatoren wie Google News).
- Wenn ein Fachverband, ein Forschungsinstitut oder eine Behörde regelmäßig publiziert, gerne mit aufnehmen.

Antworte ausschliesslich mit einem JSON-Array ohne Markdown-Codefences. Jeder Eintrag ist ein Objekt {{"domain": "domain.tld", "name": "Anzeigename", "why": "kurze Begründung in einem Satz"}}.
"""
    response = client.messages.create(model=MODEL, max_tokens=4000,
                                       messages=[{"role": "user", "content": prompt}])
    raw = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--title")
    ap.add_argument("--description")
    args = ap.parse_args()

    description = args.description or ask("Worum soll der Podcast gehen? (1-2 Sätze)")
    if not description:
        print("Abgebrochen: keine Beschreibung.")
        return 1
    default_slug = slugify(description.split()[0] if description else "")
    slug = args.slug or ask("Slug (a-z, 0-9, -)", default_slug)
    title = args.title or ask("Anzeige-Titel", f"{slug.title()} Daily")

    target = TOPICS_DIR / f"{slug}.yaml"
    if target.exists() and ask(f"'{slug}.yaml' existiert. Überschreiben? (j/N)", "n").lower() not in ("j", "ja", "y"):
        return 0

    print("\nFrage Claude nach geeigneten Quellen…\n")
    try:
        suggestions = suggest_sources(description)
    except Exception as e:
        print(f"Konnte Quellen nicht laden: {e}", file=sys.stderr)
        return 1

    for i, s in enumerate(suggestions, 1):
        print(f"  [{i:2}] {s.get('domain',''):<30} {s.get('name',''):<28}  – {s.get('why','')}")

    sel = ask("\nNummern der Quellen (kommagetrennt) oder 'alle'", "alle")
    if sel.lower() in ("alle", "all", "a", "*"):
        picked = suggestions
    else:
        idxs = [int(x) for x in re.findall(r"\d+", sel)]
        picked = [suggestions[i - 1] for i in idxs if 1 <= i <= len(suggestions)]
    if not picked:
        print("Keine Quellen ausgewählt – Abbruch.")
        return 1

    research_prompt = ask("Forschungsleitfaden (Enter = generisch)", "") or \
        f"Recherchiere die wichtigsten tagesaktuellen Nachrichten zum Thema: {description}"

    voice_id = ask("ElevenLabs voice_id", DEFAULT_VOICE)
    minutes = int(ask("Ziel-Länge in Minuten", "5"))

    cfg = {
        "slug": slug,
        "title": title,
        "description": description,
        "language": "de",
        "voice_id": voice_id,
        "voice_model": "eleven_multilingual_v2",
        "target_minutes": minutes,
        "research_prompt": research_prompt,
        "preferred_sources": [s["domain"] for s in picked],
        "cover_image": "default-cover.png",
    }

    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    print(f"\nGeschrieben: {target}")
    print(f"Nächster Schritt: python scripts/build_podcast.py {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
