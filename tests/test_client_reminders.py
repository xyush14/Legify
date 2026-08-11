"""Client hearing reminders — the promises this feature must not break.

Everything here is about a message going to a THIRD PARTY on the strength of a
consent the advocate recorded. So the tests are not about happy paths; they are
about the four ways this feature could damage a lawyer:

  1. Messaging a client who never consented.
  2. Telling a client the wrong date, or a message with a hole in it.
  3. Messaging the same client twice about one hearing.
  4. Reporting "reminded" for a client who was never told.

Storage is exercised against the REAL SQLite backend (a tmp_path database), not a
mock, because the double-send guard IS a database index — asserting it against a
fake would prove nothing about the constraint that actually stops the second
message.
"""

from __future__ import annotations

import importlib
import sqlite3
from unittest import mock

import pytest

from headnote.reminders import copy as rcopy


# ─────────────────────────────────────────────── fixtures


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """The reminder log on a throwaway SQLite file, with Supabase off."""
    import headnote.config as cfg
    from headnote.reminders import storage as rstore

    db = tmp_path / "rem.db"
    monkeypatch.setattr(cfg, "KANOON_CACHE_PATH", db)
    monkeypatch.setattr(rstore, "KANOON_CACHE_PATH", db, raising=False)
    monkeypatch.setattr(rstore, "_use_sb", lambda: False)
    return rstore


@pytest.fixture()
def svc(store, monkeypatch):
    from headnote.reminders import service as rsvc
    monkeypatch.setenv("WA_PROVIDER", "meta")
    monkeypatch.setenv("WA_ACCESS_TOKEN", "t")
    monkeypatch.setenv("WA_PHONE_NUMBER_ID", "p")
    monkeypatch.setattr(rsvc, "rstore", store)
    return rsvc


def matter(cid, *, name="रामप्रसाद", mobile="9425012345", consent=True,
           cnr="MP07010272252017", date="13/08/2026", court="जिला न्यायालय ग्वालियर",
           court_no="79", time="10:30 am"):
    return {
        "id": cid, "cnr": cnr, "case_title": "State vs X", "court_name": court,
        "case_number": "6345", "case_year": "2017", "next_hearing_date": date,
        "case_json": {"client": {"name": name, "mobile": mobile, "consent": consent},
                      "prep": {"court_no": court_no, "time": time}},
    }


def _due(svc, cases, **kw):
    with mock.patch.object(svc.cases_storage, "list_cases", return_value=cases):
        return svc.due(user_id="u1", hearing_iso="2026-08-13",
                       advocate_name="विष्णु", advocate_phone="+919425000000", **kw)


def _send(svc, cases, ids, **kw):
    with mock.patch.object(svc.cases_storage, "list_cases", return_value=cases):
        return svc.send_batch(user_id="u1", hearing_iso="2026-08-13", case_ids=ids,
                              advocate_name="विष्णु", advocate_phone="+919425000000", **kw)


# ═══════════════════════════════════ 1. consent


def test_no_consent_is_never_sent_however_hard_the_caller_asks(svc):
    """The tickbox the matters screen has shown since the diary shipped is a hard
    gate in the code, not a hint. A caller naming the matter explicitly still
    cannot get a message to a client who did not agree."""
    cases = [matter("c1", consent=False)]
    sent = []
    with mock.patch("headnote.whatsapp.client.send_template",
                    side_effect=lambda *a, **k: sent.append(a) or {"messages": [{"id": "x"}]}):
        r = _send(svc, cases, ["c1"])
    assert r["sent"] == 0
    assert sent == [], "a non-consenting client was messaged"
    assert "consent" in r["results"][0]["reason"].lower()


def test_consent_as_it_stood_is_recorded_with_the_send(svc, store):
    """Consent can be unticked later. The log must say what was true when we sent,
    which is the only version that matters if it is ever questioned."""
    with mock.patch("headnote.whatsapp.client.send_template",
                    return_value={"messages": [{"id": "wamid.1"}]}):
        _send(svc, [matter("c1")], ["c1"])
    row = store.history_for_matter(user_id="u1", case_id="c1")[0]
    assert row["consent_at_send"] is True
    assert row["to_phone"] == "+919425012345"


# ═══════════════════════════════════ 2. the message


def test_message_carries_the_matter_s_own_date_and_court(svc):
    e = _due(svc, [matter("c1")])["entries"][0]
    assert "13/08/2026" in e["message"]
    assert "गुरुवार" in e["message"], "the weekday is the check on a mistyped date"
    assert "जिला न्यायालय ग्वालियर" in e["message"]
    assert "79" in e["message"], "the court room from the cause list"
    assert "10:30 am" in e["message"]


def test_no_placeholder_ever_reaches_a_client(svc):
    for e in _due(svc, [matter("c1"), matter("c2", name="Ramesh")])["entries"]:
        assert "{{" not in e["message"] and "}}" not in e["message"]


def test_a_message_with_a_hole_in_it_is_refused_not_sent(svc):
    """Meta rejects a blank placeholder, but the reason this is checked on our side
    is the other case: a message reading "listed in  on " would be worse than no
    message, and must never leave."""
    cases = [matter("c1")]
    with mock.patch.object(rcopy, "missing_vars", return_value=[4]):
        with mock.patch("headnote.whatsapp.client.send_template") as snd:
            r = _send(svc, cases, ["c1"])
    assert snd.call_count == 0
    assert r["sent"] == 0 and r["failed"] == 1
    assert "blank" in r["results"][0]["reason"].lower()


def test_the_words_are_never_taken_from_the_request(svc):
    """The browser chooses WHO and WHICH LANGUAGE. It cannot supply the text, the
    date or the number — those are rebuilt server-side from the stored matter, so
    a tampered or merely stale payload cannot change what a client is told."""
    captured = {}

    def grab(to, tpl, lang, variables, provider=None):
        captured["to"], captured["v"] = to, variables
        return {"messages": [{"id": "x"}]}

    with mock.patch("headnote.whatsapp.client.send_template", side_effect=grab):
        _send(svc, [matter("c1")], ["c1"])
    assert captured["to"] == "+919425012345"
    assert captured["v"][4].startswith("13/08/2026")


# ═══════════════════════════════════ 3. one message per hearing


def test_the_same_client_cannot_be_told_twice_about_one_hearing(svc):
    cases = [matter("c1")]
    with mock.patch("headnote.whatsapp.client.send_template",
                    return_value={"messages": [{"id": "x"}]}) as snd:
        first = _send(svc, cases, ["c1"])
        second = _send(svc, cases, ["c1"])
    assert first["sent"] == 1
    assert second["sent"] == 0
    assert snd.call_count == 1, "the provider was called a second time"
    assert "already" in second["results"][0]["reason"].lower()


def test_the_guard_is_the_database_not_a_prior_read(svc, store):
    """Two clicks in the same instant must not both get through. A read-then-write
    check in the service layer would let them; a unique index cannot."""
    kw = dict(user_id="u1", case_id="c1", hearing_date="2026-08-13",
              to_phone="+919425012345", channel=store.CH_TEMPLATE)
    assert store.record(**kw) is not None
    assert store.record(**kw) is None


def test_a_different_hearing_of_the_same_matter_is_still_remindable(svc, store):
    kw = dict(user_id="u1", case_id="c1", to_phone="+91942501234",
              channel=store.CH_TEMPLATE)
    assert store.record(hearing_date="2026-08-13", **kw) is not None
    assert store.record(hearing_date="2026-09-02", **kw) is not None


# ═══════════════════════════════════ 4. never claim a send that did not happen


def test_a_provider_refusal_is_reported_and_the_slot_released(svc, store):
    """The row is claimed BEFORE the provider is called, so a refusal must flip it
    to failed. Left as 'sent' it would tell the lawyer a client was reminded who
    was not, AND lock that client out of a retry."""
    from headnote.whatsapp.providers import WAClientError
    cases = [matter("c1")]
    with mock.patch("headnote.whatsapp.client.send_template",
                    side_effect=WAClientError(400, "template not approved")):
        r = _send(svc, cases, ["c1"])
    assert r["sent"] == 0 and r["failed"] == 1
    row = store.history_for_matter(user_id="u1", case_id="c1")[0]
    assert row["status"] == store.FAILED and row["error"]
    assert "c1" not in store.sent_dates_for(user_id="u1", case_ids=["c1"],
                                            hearing_date="2026-08-13")
    # …and the retry then works.
    with mock.patch("headnote.whatsapp.client.send_template",
                    return_value={"messages": [{"id": "x"}]}):
        assert _send(svc, cases, ["c1"])["sent"] == 1


def test_one_client_failing_does_not_abandon_the_rest(svc):
    from headnote.whatsapp.providers import WAClientError
    cases = [matter("c1"), matter("c2", mobile="9812345678"),
             matter("c3", mobile="9811111111")]
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise WAClientError(500, "upstream")
        return {"messages": [{"id": "x"}]}

    with mock.patch("headnote.whatsapp.client.send_template", side_effect=flaky):
        r = _send(svc, cases, ["c1", "c2", "c3"])
    assert r["sent"] == 2 and r["failed"] == 1
    assert len(r["results"]) == 3, "every client's outcome is reported by name"


def test_nothing_is_sent_when_no_lane_is_live(svc, monkeypatch):
    """Without an approved template there is no legal way to start a conversation.
    The batch must refuse up front rather than spend a credit per client failing."""
    monkeypatch.delenv("WA_ACCESS_TOKEN", raising=False)
    import headnote.reminders.service as m
    importlib.reload(m)
    monkeypatch.setattr(m, "rstore", svc.rstore)
    with mock.patch("headnote.whatsapp.client.send_template") as snd:
        with mock.patch.object(m.cases_storage, "list_cases", return_value=[matter("c1")]):
            r = m.send_batch(user_id="u1", hearing_iso="2026-08-13", case_ids=["c1"],
                             advocate_name="V", advocate_phone="+919425000000")
    assert snd.call_count == 0
    assert r["sent"] == 0 and r["blocked_reason"]
    importlib.reload(m)


def test_no_callback_number_blocks_the_batch_once_not_every_row(svc):
    """The advocate's own missing number is one fact about the whole send. Reported
    per row it buried the client-level gaps that genuinely differ."""
    cases = [matter("c1"), matter("c2", mobile="9812345678")]
    with mock.patch.object(svc.cases_storage, "list_cases", return_value=cases):
        d = svc.due(user_id="u1", hearing_iso="2026-08-13",
                    advocate_name="विष्णु", advocate_phone="")
    assert d["can_send"] is False and "office number" in d["blocked_reason"]
    assert all(e["sendable"] for e in d["entries"]), \
        "a missing office number must not read as a per-client problem"
    with mock.patch("headnote.whatsapp.client.send_template") as snd:
        with mock.patch.object(svc.cases_storage, "list_cases", return_value=cases):
            r = svc.send_batch(user_id="u1", hearing_iso="2026-08-13",
                               case_ids=["c1", "c2"], advocate_name="विष्णु",
                               advocate_phone="")
    assert snd.call_count == 0 and r["sent"] == 0


# ═══════════════════════════════════ nothing disappears


def test_every_matter_on_the_day_is_reported_with_a_reason(svc):
    """A row that vanished because the client has no number would leave the lawyer
    believing that client was told."""
    cases = [matter("c1"),
             matter("c2", consent=False),
             matter("c3", mobile=""),
             matter("c4", mobile="94250"),
             {"id": "c5", "cnr": "DY9", "case_title": "T", "court_name": "X",
              "case_number": "9", "case_year": "2026",
              "next_hearing_date": "13/08/2026", "case_json": {}}]
    d = _due(svc, cases)
    assert d["counts"]["total"] == 5
    assert len(d["entries"]) == 5
    assert d["counts"]["sendable"] == 1
    assert all(e["blocker"] and e["fix"] for e in d["entries"] if not e["sendable"])
    kinds = {e["blocker"] for e in d["entries"]}
    assert {"no_consent", "no_phone", "no_details"} <= kinds


def test_a_short_number_is_refused_rather_than_dialled_hopefully(svc):
    e = [x for x in _due(svc, [matter("c1", mobile="94250")])["entries"]][0]
    assert not e["sendable"] and e["blocker"] == "no_phone"


def test_sendable_rows_come_first(svc):
    d = _due(svc, [matter("c1", consent=False), matter("c2", mobile="9812345678")])
    assert d["entries"][0]["sendable"] is True


# ═══════════════════════════════════ where the date came from


def test_a_court_confirmed_date_is_distinguished_from_a_typed_one(svc):
    """Most production matters carry a date read off a photographed cause list. The
    lawyer must see which is which before he tells a client to travel."""
    court = _due(svc, [matter("c1")])["entries"][0]
    assert court["date_source"]["kind"] == "causelist"
    own = _due(svc, [matter("c2", cnr="DY555D37A73195")])["entries"][0]
    assert own["date_source"]["kind"] == "own"
    assert "not court-confirmed" in own["date_source"]["label"]


# ═══════════════════════════════════ language


def test_the_client_s_own_script_picks_the_language(svc):
    hi = _due(svc, [matter("c1", name="रामप्रसाद")])["entries"][0]
    assert hi["lang"] == "hi" and "नमस्ते" in hi["message"]
    en = _due(svc, [matter("c2", name="Ramesh Patel", court="District Court")])["entries"][0]
    assert en["lang"] == "en" and "Namaste" in en["message"]


def test_an_unsupported_script_falls_to_english_never_hindi(svc):
    """A Hindi reminder to a Tamil client is worse than an English one he can have
    read to him. This is the same rule the drafting glossary follows."""
    e = _due(svc, [matter("c1", name="முருகன்", court="District Court, Madurai")])["entries"][0]
    assert e["lang"] == "en"
    assert "नमस्ते" not in e["message"]


def test_the_lawyer_can_override_the_language(svc):
    e = _due(svc, [matter("c1", name="Ramesh")], lang="mr")["entries"][0]
    assert e["lang"] == "mr" and "नमस्कार" in e["message"]
    assert e["lang_needs_signoff"] is True, \
        "wording no advocate in that state has read must be flagged as such"


# ═══════════════════════════════════ the template contract


def test_the_body_and_the_variable_builder_cannot_drift_apart():
    """The body registered with Meta and the values we send are two halves of one
    contract. If someone rewords a body and forgets a placeholder, the send fails
    at Meta with a code nobody recognises — so it fails here instead."""
    for lang in rcopy.SUPPORTED:
        body = rcopy.body(lang)
        for i in range(1, rcopy.VAR_COUNT + 1):
            assert "{{%d}}" % i in body, f"{lang} body is missing {{{{{i}}}}}"
        assert "{{%d}}" % (rcopy.VAR_COUNT + 1) not in body


@pytest.mark.parametrize("lang", rcopy.SUPPORTED)
def test_every_body_obeys_meta_s_own_rules(lang):
    """Meta rejects a template body that starts or ends with a placeholder, or that
    puts two of them side by side. Catching that here beats a rejected submission."""
    import re
    body = rcopy.body(lang).strip()
    assert not body.startswith("{{"), f"{lang}: body starts with a placeholder"
    assert not body.endswith("}}"), f"{lang}: body ends with a placeholder"
    assert not re.search(r"\}\}[\s,.]*\{\{", body), f"{lang}: adjacent placeholders"


def test_a_provider_that_cannot_do_templates_says_so_clearly(monkeypatch):
    """Twilio issues one Content SID per language rather than a template name.
    Handing it a name must produce an error that says what to set, not a 400."""
    from headnote.whatsapp.providers import twilio, WAClientError
    with pytest.raises(WAClientError) as ex:
        twilio.send_template("+919425012345", "hearing_reminder", "hi", ["a"] * 7)
    assert "Content SID" in str(ex.value)


def test_meta_send_template_posts_the_shape_meta_expects(monkeypatch):
    from headnote.whatsapp.providers import meta
    monkeypatch.setenv("WA_ACCESS_TOKEN", "t")
    monkeypatch.setenv("WA_PHONE_NUMBER_ID", "p")
    seen = {}

    class R:
        ok, status_code = True, 200
        def json(self): return {"messages": [{"id": "wamid.1"}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(json or {})
        return R()

    monkeypatch.setattr(meta.requests, "post", fake_post)
    meta.send_template("+919425012345", "hearing_reminder", "hi", [str(i) for i in range(7)])
    assert seen["type"] == "template"
    assert seen["to"] == "919425012345", "Meta wants the number without a +"
    assert seen["template"]["language"] == {"code": "hi"}
    params = seen["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == [str(i) for i in range(7)], \
        "variables must stay in order — they map to {{1}}..{{7}} positionally"


# ═══════════════════════════════════ phone handling


@pytest.mark.parametrize("raw,want", [
    ("9425012345", "+919425012345"),
    ("+91 94250 12345", "+919425012345"),
    ("919425012345", "+919425012345"),
    ("94250 12345", "+919425012345"),
    # A leading zero is an ordinary way to write an Indian mobile. It used to
    # produce "+09425012345" — not a number anywhere — which then PASSED the length
    # check and would have been handed to the provider as a real send.
    ("094250-12345", "+919425012345"),
    ("0919425012345", "+919425012345"),
    ("", ""),
])
def test_indian_numbers_normalise_the_same_way_as_the_daily_list(raw, want):
    """Follows headnote/cases/daily_send.py::_norm_phone — one typed number has to
    reach the same place from the daily list and from a reminder."""
    from headnote.reminders import service as rsvc
    assert rsvc.norm_phone(raw) == want


def test_a_number_that_normalisation_gave_up_on_is_never_dialled():
    """No country code starts with 0, so "+0…" means the parse failed. Refusing it
    costs nothing; sending it costs a message credit and reaches nobody."""
    from headnote.reminders import service as rsvc
    assert rsvc.plausible("+09425012345") is False
    assert rsvc.plausible("+919425012345") is True


# ═══════════════════════════════════ the Home banner


def test_the_home_summary_counts_without_composing_messages(svc):
    """/api/home renders one line from this. Building 40 messages to display a
    number would slow the most-loaded call in the product for nothing."""
    cases = [matter("c1"), matter("c2", consent=False), matter("c3", mobile="")]
    with mock.patch.object(rcopy, "render", side_effect=AssertionError("composed a message")):
        s = svc.summary(user_id="u1", hearing_iso="2026-08-13", cases=cases)
    assert s == {"date": "2026-08-13", "total": 3, "pending": 1, "blocked": 2, "already": 0}


def test_the_summary_stops_offering_clients_already_reminded(svc, store):
    cases = [matter("c1"), matter("c2", mobile="9812345678")]
    with mock.patch("headnote.whatsapp.client.send_template",
                    return_value={"messages": [{"id": "x"}]}):
        _send(svc, cases, ["c1"])
    s = svc.summary(user_id="u1", hearing_iso="2026-08-13", cases=cases)
    assert s["pending"] == 1 and s["already"] == 1


def test_home_still_loads_when_the_reminder_summary_breaks(monkeypatch):
    """A banner must never take the board down with it. Driven as a real request,
    because what is under test is the route's own except-clause."""
    from fastapi.testclient import TestClient
    from headnote.api.app import app
    from headnote.api import notesheets as ns
    from headnote.entitlements import CurrentUser, require_beta

    monkeypatch.setattr(ns.reminder_service, "summary",
                        mock.Mock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(ns.cases_storage, "list_cases", lambda **kw: [])
    app.dependency_overrides[require_beta] = lambda: CurrentUser(
        id="00000000-0000-0000-0000-000000000009", email="t@t.local",
        role="authenticated", raw_claims={})
    try:
        r = TestClient(app).get("/api/home")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["counts"]["remind"] == 0
        assert body["remind"]["unavailable"] is True, \
            "the screen must be told the count is unknown, not shown a false zero"
    finally:
        app.dependency_overrides.pop(require_beta, None)


# ═══════════════════════════════════ the log survives a missing migration


def test_a_missing_table_falls_back_instead_of_failing_the_send(tmp_path, monkeypatch):
    """Migration 014 is applied by hand, so between deploying and running it the
    table does not exist. Reminders must still work — and reads and writes must go
    to the SAME store, or the lawyer sees an empty history and can double-send."""
    import headnote.config as cfg
    from headnote.reminders import storage as rstore

    monkeypatch.setattr(cfg, "KANOON_CACHE_PATH", tmp_path / "fb.db")
    monkeypatch.setattr(rstore, "KANOON_CACHE_PATH", tmp_path / "fb.db", raising=False)
    monkeypatch.setattr(rstore._supabase, "_enabled", lambda: True)
    monkeypatch.setattr(rstore, "_pg_probed", False)
    monkeypatch.setattr(rstore, "_pg_absent", False)
    monkeypatch.setattr(rstore._supabase, "_send",
                        mock.Mock(side_effect=RuntimeError(
                            "PGRST205 Could not find the table 'public.client_reminders'")))

    row = rstore.record(user_id="u1", case_id="c1", hearing_date="2026-08-13",
                        to_phone="+919425012345", channel=rstore.CH_TEMPLATE)
    assert row is not None, "a missing migration must not lose the send record"
    assert rstore._use_sb() is False, "the process must switch to the local store"
    # And the guard still holds in the store the write actually went to.
    assert rstore.record(user_id="u1", case_id="c1", hearing_date="2026-08-13",
                         to_phone="+919425012345", channel=rstore.CH_TEMPLATE) is None
    assert "c1" in rstore.sent_dates_for(user_id="u1", case_ids=["c1"],
                                         hearing_date="2026-08-13")


def test_the_sqlite_guard_matches_the_postgres_index(tmp_path, monkeypatch):
    """The partial unique index is scoped to status='sent' in BOTH stores, so a dev
    run cannot pass while production would reject, or vice versa."""
    import headnote.config as cfg
    from headnote.reminders import storage as rstore
    db = tmp_path / "idx.db"
    monkeypatch.setattr(cfg, "KANOON_CACHE_PATH", db)
    monkeypatch.setattr(rstore, "KANOON_CACHE_PATH", db, raising=False)
    monkeypatch.setattr(rstore, "_use_sb", lambda: False)
    rstore.record(user_id="u", case_id="c", hearing_date="2026-08-13",
                  to_phone="+91", channel="x")
    with sqlite3.connect(db) as c:
        sql = c.execute(
            "SELECT sql FROM sqlite_master WHERE name='idx_cr_once'").fetchone()[0]
    assert "status = 'sent'" in sql

    mig = (__import__("pathlib").Path(__file__).resolve().parents[1]
           / "migrations" / "014_client_reminders.sql").read_text()
    assert "where status = 'sent'" in mig
    assert "user_id, case_id, hearing_date" in mig
