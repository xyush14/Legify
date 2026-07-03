"""Preserve-token masking shared by the NMT backends (Bhashini, Sarvam).

Neither NMT engine can be *instructed* to leave citations / section numbers /
statute short-forms alone, so we mask them out before translation and restore
them after:  mask → translate → unmask.

Preserved = section/crime/case numbers, dates, statute short-forms
(भा.द.वि. / दं.प्र.सं. / बी.एन.एस.एस.), and any Latin run (IPC, BNSS, discharge).
Sentinels are private-use-area chars an NMT model won't translate or drop.
"""
from __future__ import annotations

import re

_PRESERVE_RX = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4}"                       # dates 22/03/2024
    r"|\d+/\d+"                                       # 240/2021, 3/4
    r"|\d+[ऀ-ॿ]*"                           # 498ए, 239 (+ Devanagari matra)
    r"|भा\.द\.वि\.|दं\.प्र\.सं\.|बी\.एन\.एस\.एस\."   # statute short-forms (Devanagari)
    r"|[A-Za-z][A-Za-z.\-]*"                          # Latin runs: IPC, BNSS, discharge
)
_S0, _S1 = "\uE000", "\uE001"


def mask(text: str) -> tuple[str, list[str]]:
    toks: list[str] = []

    def sub(m: re.Match) -> str:
        toks.append(m.group(0))
        return f"{_S0}{len(toks) - 1}{_S1}"

    return _PRESERVE_RX.sub(sub, text), toks


def unmask(text: str, toks: list[str]) -> str:
    for i, t in enumerate(toks):
        text = text.replace(f"{_S0}{i}{_S1}", t)
    return text
