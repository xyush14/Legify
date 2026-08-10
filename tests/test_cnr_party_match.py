"""Linking a diary matter by party name.

Most of a district advocate's matters are typed off a photographed cause list,
so they carry no CNR and their dates can never move on their own. Bulk linking
matched on case number ALONE — and a photographed case number is exactly the
field most likely to be mangled, while the party name is usually legible.

Matching on the name recovers those matters. The danger runs the other way: a
wrong link rewrites a matter's identity. So the bar is deliberately high, the
candidate must be unique in the docket, and nothing is written until the lawyer
ticks it.

NOTE ON THE NAMES BELOW: every name here is invented. This repository is public,
and real party names are the litigants in real criminal matters — they must
never be committed. The shapes are what the tests care about (shared first name,
shared surname, honorifics, "State of ... Vs", a short form), not the people.
"""
import pytest

from headnote.api.cases import _party_match, _party_tokens


def match(a: str, b: str) -> bool:
    return _party_match(_party_tokens(a), _party_tokens(b))


class TestTokens:
    def test_drops_cause_title_noise(self):
        # "State of M.P. Vs" identifies nobody — matching on it would link every
        # State prosecution in the docket to every other one.
        assert _party_tokens("State of M.P. Vs Testnama Kaalpanik") == {"testnama", "kaalpanik"}

    def test_drops_honorifics_and_and_others(self):
        assert _party_tokens("Smt. Udaharan Namuna & Ors") == {"udaharan", "namuna"}

    def test_keeps_devanagari(self):
        assert "उदाहरण" in _party_tokens("उदाहरण विरुद्ध नमूना")

    def test_bare_numbers_are_not_identity(self):
        assert _party_tokens("6345 2017") == set()

    def test_handles_none_and_empty(self):
        assert _party_tokens(None, "", "  ") == set()


class TestMatches:
    @pytest.mark.parametrize("a,b", [
        # the same title, punctuated differently by the court
        ("Pratham Vs Dwitiya Namuna", "Pratham v. Dwitiya Namuna & Anr"),
        ("Tritiya Misaal Urf Chautha Misaal", "Tritiya Misaal Urf Chautha Misaal"),
        # the diary holds only the client; the court holds the full cause title
        ("Testnama Kaalpanik", "State of M.P. Vs Testnama Kaalpanik"),
        ("Dwitiya Namuna", "Smt. Dwitiya Namuna vs Pratham"),
    ])
    def test_recovers_the_same_matter(self, a, b):
        assert match(a, b) is True


class TestNonMatches:
    @pytest.mark.parametrize("a,b", [
        ("Panchvaan Alpha", "Panchvaan Beta"),      # shared first name only
        ("Chhatha Kaalpanik", "Satvaan Kaalpanik"),  # shared surname only
        ("Aathvaa", "Aathvaan Namuna"),              # one word is never enough
        # Two different clients of the same lawyer, both prosecuted by the State.
        ("State of MP Vs Navvaan Alpha", "State of MP Vs Dasvaan Beta"),
    ])
    def test_refuses_a_weak_name(self, a, b):
        assert match(a, b) is False

    def test_empty_never_matches(self):
        assert match("", "Pratham Vs Dwitiya Namuna") is False
        assert match("Pratham Vs Dwitiya Namuna", "") is False

    def test_noise_only_never_matches(self):
        # Otherwise every State prosecution links to the first one in the docket.
        assert match("State of M.P.", "State of M.P.") is False


def test_a_short_form_is_offered_not_applied():
    """A two-word name fully contained in a longer one is genuinely ambiguous.

    It is offered, because the alternative is that the matter stays unlinked
    forever and its dates never update. It is safe to offer because the endpoint
    writes nothing: the lawyer sees both names side by side and ticks. The UI
    must therefore NOT pre-tick a party-name match — see the `matched_by` field
    and the un-ticked checkbox it drives.
    """
    assert match("Navvaan Alpha", "Navvaan Alpha Gyarvaan Baarvaan Terah") is True


def test_match_is_symmetric():
    a, b = "Testnama Kaalpanik", "State of M.P. Vs Testnama Kaalpanik"
    assert match(a, b) == match(b, a)


def test_no_real_party_names_are_committed():
    """A tripwire, not a formality.

    These tests were first written against names lifted from a live Home screen.
    The repo is public; publishing the parties to real criminal matters is a
    privacy breach that no later history rewrite can undo. If someone pastes
    production data in here again, this fails.
    """
    import hashlib
    import pathlib
    import re

    # The names are stored as hashes, never in clear: a guard that spells out
    # what it forbids publishes exactly the thing it exists to protect (and
    # fails against itself). Same reason tests/test_access_lists.py hashes.
    FORBIDDEN = {
        "eab83cf6a7d8cfe6", "6f60d5c815f63b5c", "155b58fd4346d2e5",
        "89fba1cfe8cc5297", "2a7970f241c70150", "500cf3a35edb5d48",
        "edb05b6899f3c114", "67530b9793ba0113",
    }
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    words = re.findall(r"[A-Za-z]+", src)
    seen = set()
    for i, w in enumerate(words):
        for phrase in (w, " ".join(words[i:i + 2])):
            h = hashlib.sha256(phrase.lower().encode()).hexdigest()[:16]
            if h in FORBIDDEN:
                seen.add(h)
    assert not seen, (
        f"{len(seen)} real party name(s) from production data are in this file — "
        "replace them with invented names; this repo is public")
