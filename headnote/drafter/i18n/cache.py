"""Verified-string cache — the deterministic, advocate-approved half of the
regional pipeline.

A cache is one JSON file per language at i18n/verified/strings_<lang>.json:

    {
      "meta": {"lang": "mr", "verified_by": null, "updated": "..."},
      "strings": {
        "<source Hindi string>": {"t": "<target string>", "v": false, "k": "boilerplate"}
      }
    }

  * "t"  — the translation.
  * "v"  — verified: false = machine draft (shows the "verify before filing"
           label); true = a jurisdiction advocate signed off. The feedback loop
           flips this without any code change.
  * "k"  — "boilerplate" (reusable court language) | "facts" (demo seed).

Lookups are keyed by the exact rendered Hindi text run. The render layer
(render.py) substitutes hits from here and runtime-translates the misses, so
the advocate loop is pure data: correct a string → flip "v" → it's live.
"""
from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent / "verified"

# ---- machine (write-back) cache ------------------------------------------
# Unverified runtime translations. Distinct from the advocate-verified cache:
# once a string is translated by the LLM we persist it here so the NEXT render
# of the same paragraph (≈80% of a draft is repeated boilerplate) is an instant,
# free lookup instead of another API call. Lives in-memory for the process +
# best-effort atomic file persistence so it survives across requests/restarts.
_MDIR = Path(__file__).resolve().parent / "machine"
_mem: dict[str, dict[str, str]] = {}
_locks: dict[str, threading.Lock] = {}
_loaded: set[str] = set()


def _mlock(lang: str) -> threading.Lock:
    return _locks.setdefault(lang, threading.Lock())


def _mload(lang: str) -> dict:
    if lang not in _loaded:
        p = _MDIR / f"{lang}.json"
        try:
            _mem[lang] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception as e:
            log.warning("[i18n] machine cache load failed for %s: %s", lang, e)
            _mem[lang] = {}
        _loaded.add(lang)
    return _mem.setdefault(lang, {})


def machine_lookup(text: str, lang: str) -> str | None:
    """Return a previously-translated string, or None."""
    return _mload(lang).get(text.strip()) or None


def machine_store_many(pairs: dict[str, str], lang: str) -> None:
    """Add {source: translation} pairs and persist once (atomic write)."""
    d = _mload(lang)
    changed = False
    for src, tgt in pairs.items():
        k = (src or "").strip()
        if k and tgt and tgt != k and d.get(k) != tgt:
            d[k] = tgt
            changed = True
    if not changed:
        return
    with _mlock(lang):
        try:
            _MDIR.mkdir(parents=True, exist_ok=True)
            tmp = _MDIR / f".{lang}.tmp"
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(_MDIR / f"{lang}.json")
        except Exception as e:  # in-memory cache still works if disk is read-only
            log.warning("[i18n] machine cache persist failed for %s: %s", lang, e)


def _path(lang: str) -> Path:
    return _DIR / f"strings_{lang}.json"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    p = _path(lang)
    if not p.exists():
        return {"meta": {"lang": lang}, "strings": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # never let a bad cache file break rendering
        log.warning("[i18n] cache load failed for %s: %s", lang, e)
        return {"meta": {"lang": lang}, "strings": {}}


def lookup(text: str, lang: str) -> tuple[str, bool] | None:
    """Return (translation, verified) for a source string, or None on miss."""
    entry = _load(lang).get("strings", {}).get(text.strip())
    if not entry:
        return None
    return entry.get("t", ""), bool(entry.get("v"))


def all_verified(lang: str) -> bool:
    """True iff every cached string for `lang` is advocate-verified (drives the
    'file-ready' vs 'machine draft' badge on a rendered doc)."""
    strings = _load(lang).get("strings", {})
    return bool(strings) and all(v.get("v") for v in strings.values())


def stats(lang: str) -> dict:
    strings = _load(lang).get("strings", {})
    verified = sum(1 for v in strings.values() if v.get("v"))
    return {"total": len(strings), "verified": verified,
            "boilerplate": sum(1 for v in strings.values() if v.get("k") == "boilerplate")}
