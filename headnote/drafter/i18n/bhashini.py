"""Bhashini (Digital India / MeitY ULCA) NMT client — the translation backend.

Two-step ULCA pipeline:
  1. getModelsPipeline  → discover the inference endpoint (callbackUrl), the
     per-language serviceId, and the inference auth header. Cached per
     source→target pair (it rarely changes).
  2. inference          → translate one text segment.

Because Bhashini is raw NMT (no system prompt, no glossary, no "keep this in
English" instruction), the legal-safety controls the LLM path did in-prompt are
done HERE by masking:

    mask preserved tokens  →  Bhashini translate  →  restore tokens

Preserved = section/crime/case numbers, dates, statute short-forms
(भा.द.वि. / दं.प्र.सं. / IPC / BNS …), and any Latin run (IPC, discharge, NI).
The court-term glossary is NOT enforceable through NMT — it guides the advocate
review that flips cache entries to verified, and an optional LLM post-edit.

Config (env):
    BHASHINI_USER_ID         ULCA userID
    BHASHINI_ULCA_API_KEY    ULCA apiKey (a.k.a. Bhashini API key)
    BHASHINI_PIPELINE_ID     default 64392f96daac500b55c543cd (MeitY common pipeline)
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

import httpx

log = logging.getLogger(__name__)

_CONFIG_URL = os.environ.get(
    "BHASHINI_CONFIG_URL",
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
)
_DEFAULT_PIPELINE = os.environ.get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")
_TIMEOUT = float(os.environ.get("BHASHINI_TIMEOUT", "30"))

# Tokens Bhashini must not touch. Order matters: dates & fractions before bare
# ints so "22/03/2024" and "3/4" aren't split.
_PRESERVE_RX = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4}"                       # dates 22/03/2024
    r"|\d+/\d+"                                       # 240/2021, 3/4
    r"|\d+[ऀ-ॿ]*"                          # 498ए, 239 (+ matra)
    r"|भा\.द\.वि\.|दं\.प्र\.सं\.|बी\.एन\.एस\.एस\."   # statute short-forms (Devanagari)
    r"|[A-Za-z][A-Za-z.\-]*"                          # Latin runs: IPC, BNSS, discharge
)
# Private-use sentinels NMT won't translate or drop.
_S0, _S1 = "\uE000", "\uE001"


class BhashiniError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("BHASHINI_USER_ID") and os.environ.get("BHASHINI_ULCA_API_KEY"))


def _mask(text: str) -> tuple[str, list[str]]:
    toks: list[str] = []

    def sub(m: re.Match) -> str:
        toks.append(m.group(0))
        return f"{_S0}{len(toks) - 1}{_S1}"

    return _PRESERVE_RX.sub(sub, text), toks


def _unmask(text: str, toks: list[str]) -> str:
    for i, t in enumerate(toks):
        text = text.replace(f"{_S0}{i}{_S1}", t)
    return text


@lru_cache(maxsize=32)
def _pipeline(src: str, tgt: str) -> tuple[str, str, str, str]:
    """Resolve (inference_url, auth_name, auth_value, service_id) for src→tgt.
    Cached — the ULCA config call is slow and stable."""
    user_id = os.environ.get("BHASHINI_USER_ID", "").strip()
    ulca_key = os.environ.get("BHASHINI_ULCA_API_KEY", "").strip()
    if not (user_id and ulca_key):
        raise BhashiniError("BHASHINI_USER_ID / BHASHINI_ULCA_API_KEY not set")

    body = {
        "pipelineTasks": [{
            "taskType": "translation",
            "config": {"language": {"sourceLanguage": src, "targetLanguage": tgt}},
        }],
        "pipelineRequestConfig": {"pipelineId": _DEFAULT_PIPELINE},
    }
    r = httpx.post(_CONFIG_URL, json=body, timeout=_TIMEOUT,
                   headers={"userID": user_id, "ulcaApiKey": ulca_key})
    r.raise_for_status()
    d = r.json()
    ep = d["pipelineInferenceAPIEndPoint"]
    url = ep["callbackUrl"]
    key = ep["inferenceApiKey"]  # {name, value}
    svc = d["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    return url, key["name"], key["value"], svc


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate one segment src→tgt via Bhashini, masking preserved tokens.
    Raises BhashiniError on any failure so the caller can fall back."""
    if not text or not text.strip() or source_lang == target_lang:
        return text
    masked, toks = _mask(text)
    try:
        url, auth_name, auth_value, service_id = _pipeline(source_lang, target_lang)
        body = {
            "pipelineTasks": [{
                "taskType": "translation",
                "config": {
                    "language": {"sourceLanguage": source_lang, "targetLanguage": target_lang},
                    "serviceId": service_id,
                },
            }],
            "inputData": {"input": [{"source": masked}]},
        }
        r = httpx.post(url, json=body, timeout=_TIMEOUT,
                       headers={auth_name: auth_value, "Content-Type": "application/json"})
        r.raise_for_status()
        out = r.json()["pipelineResponse"][0]["output"][0]["target"]
    except BhashiniError:
        raise
    except Exception as e:  # network / shape / auth
        raise BhashiniError(f"Bhashini translate failed: {type(e).__name__}: {e}") from e
    return _unmask(out, toks)
