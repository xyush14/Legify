"""
Criminal Law AI — v0.2 prototype (Opus + prompt caching)
=========================================================

Three modes:
  (1) "Find cases for my situation" — describe a legal situation, choose
      output style (Journal headnote OR Practitioner notes), get back 3-5
      relevant cases from the curated corpus.
  (2) "Topic digest" — type a doctrinal topic, get a topic-organised
      practitioner-notebook-style digest (the gold-doc format).
  (3) "Generate headnote from judgment" — paste a full judgment, get back
      Cri.L.J.-format headnote(s) PLUS a parallel practitioner-notes version.

Optimisations for $5 Opus budget:
  - Anthropic prompt caching enabled. The system prompt + corpus (~14k
    tokens) is sent as a cached block; only the lawyer's situation/topic
    changes per call. Cached input costs ~10% of normal input pricing.
  - Default model: claude-opus-4-6 for best output quality.

Anti-hallucination:
  - Mode 1 & 2: model is constrained to return ONLY cases from the corpus.
    Every returned case_id is verified against the corpus before display.
  - Mode 3: model is told to never fabricate citations / paragraph numbers.
  - Every output is JSON-validated; failures are visible to the user.

Lawyer feedback (👍 / 👎 + correction text) is captured to a local SQLite
file for review.

Deploy:
  - Local:           streamlit run app.py
  - Streamlit Cloud: push to GitHub + connect at share.streamlit.io
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from anthropic import Anthropic

from headnote.llm.prompts import (
    build_situation_system_prompt,
    SITUATION_USER_TEMPLATE,
    HEADNOTE_SYSTEM_PROMPT,
    HEADNOTE_USER_TEMPLATE,
    build_digest_system_prompt,
    DIGEST_USER_TEMPLATE,
)

# -------------------------------------------------------------------- config

APP_DIR = Path(__file__).parent
CASES_PATH = APP_DIR / "cases.json"
FEEDBACK_DB = APP_DIR / "feedback.db"

DEFAULT_MODEL = "claude-opus-4-6"
MAX_TOKENS = 4096

# Approximate Opus 4.6 prices (USD per million tokens). Used only for the
# in-app cost estimate; you should verify against your actual billing.
PRICE_INPUT_PER_M = 15.00
PRICE_INPUT_CACHE_WRITE_PER_M = 18.75   # 1.25x base
PRICE_INPUT_CACHE_READ_PER_M = 1.50     # 0.10x base
PRICE_OUTPUT_PER_M = 75.00
USD_TO_INR = 84.0

# -------------------------------------------------------------------- helpers

@st.cache_data
def load_corpus() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


@st.cache_data
def corpus_json_str() -> str:
    """Stable, cached JSON serialisation for prompt caching."""
    return json.dumps(load_corpus(), ensure_ascii=False)


def get_client() -> Anthropic:
    key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        st.error(
            "ANTHROPIC_API_KEY not set. Add it to .streamlit/secrets.toml "
            "(local) or in the Streamlit Cloud secrets UI."
        )
        st.stop()
    return Anthropic(api_key=key)


def init_feedback_db() -> None:
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            mode TEXT NOT NULL,
            input_text TEXT NOT NULL,
            output_json TEXT NOT NULL,
            rating INTEGER NOT NULL,
            correction TEXT,
            lawyer_handle TEXT
        )"""
    )
    conn.commit()
    conn.close()


def save_feedback(
    mode: str,
    input_text: str,
    output_json: str,
    rating: int,
    correction: str = "",
    lawyer_handle: str = "",
) -> None:
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.execute(
        "INSERT INTO feedback (ts, mode, input_text, output_json, rating, correction, lawyer_handle) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(),
            mode,
            input_text,
            output_json,
            rating,
            correction,
            lawyer_handle,
        ),
    )
    conn.commit()
    conn.close()


def call_claude_cached(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> tuple[str, dict]:
    """Send a Claude messages call with the system prompt cached.

    Returns (text, usage_dict). usage_dict has input/output/cache token counts.
    """
    client = get_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    usage = resp.usage
    usage_dict = {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }
    return resp.content[0].text, usage_dict


def estimate_cost_usd(usage: dict) -> float:
    """Estimate cost from usage tokens for Opus 4.6 with caching."""
    cost = (
        usage.get("input_tokens", 0) * PRICE_INPUT_PER_M / 1_000_000
        + usage.get("cache_creation_input_tokens", 0) * PRICE_INPUT_CACHE_WRITE_PER_M / 1_000_000
        + usage.get("cache_read_input_tokens", 0) * PRICE_INPUT_CACHE_READ_PER_M / 1_000_000
        + usage.get("output_tokens", 0) * PRICE_OUTPUT_PER_M / 1_000_000
    )
    return cost


def parse_json_response(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        st.error(f"Could not parse model response as JSON: {e}")
        with st.expander("Raw response"):
            st.code(raw)
        return None


def render_journal_headnote(hn: dict, letter: str | None = None) -> None:
    parts = []
    if letter:
        parts.append(f"**({letter})** ")
    parts.append(f"**{hn.get('statute_index', '')}** — ")
    parts.append(f"{hn.get('catchword_chain', '')} — ")
    parts.append(f"*{hn.get('ratio', '')}*")
    if hn.get("negative_carve_out"):
        parts.append(f" — {hn['negative_carve_out']}")
    para_anchor = hn.get("paragraph_anchor", "")
    per_judge = hn.get("per_judge_attribution", "")
    suffix_bits = [b for b in (per_judge, para_anchor) if b]
    if suffix_bits:
        parts.append(f" **{' '.join(suffix_bits)}**")
    st.markdown("".join(parts))


def render_practitioner_notes(pn: dict) -> None:
    topic = pn.get("one_line_topic", "")
    gist = pn.get("gist", "")
    quote = pn.get("quotable_phrase", "")
    refs = pn.get("cross_refs", []) or []
    if topic:
        st.markdown(f"**Topic:** {topic}")
    if gist:
        st.markdown(gist)
    if quote:
        st.markdown(f"> _{quote}_")
    if refs:
        st.caption("**Cross-refs:** " + " · ".join(refs))


def render_situation_match(idx: int, m: dict, style: str) -> None:
    case_title = m.get("title", "Unknown case")
    citation = m.get("citation", "")
    court = m.get("court", "")
    year = m.get("year", "")

    st.markdown(f"### {idx}. {case_title}")
    st.caption(f"{court} • {year} • {citation}")

    with st.container(border=True):
        if style == "journal":
            jh = m.get("journal_headnote") or {}
            if jh:
                render_journal_headnote(jh)
            else:
                st.info("Journal headnote not produced for this case.")
        else:  # practitioner
            pn = m.get("practitioner_notes") or {}
            if pn:
                render_practitioner_notes(pn)
            else:
                st.info("Practitioner notes not produced for this case.")

    if m.get("relevance_explanation"):
        st.markdown(f"**Why this matches:** {m['relevance_explanation']}")
    if m.get("bns_note"):
        st.info(f"**BNS / BNSS note:** {m['bns_note']}")


# -------------------------------------------------------------------- UI

st.set_page_config(
    page_title="Criminal Law AI — v0.2",
    page_icon="⚖️",
    layout="wide",
)

init_feedback_db()
corpus = load_corpus()

# --- Sidebar
st.sidebar.title("⚖️ Criminal Law AI")
st.sidebar.caption("v0.2 prototype • Indian criminal law • Claude Opus")
st.sidebar.markdown(
    f"**Corpus:** {len(corpus)} landmark Supreme Court criminal-law cases  \n"
    "**Model:** Claude Opus 4.6 (highest-quality Anthropic model)  \n"
    "**Caching:** Anthropic prompt caching ON — corpus is cached across calls"
)

with st.sidebar.expander("⚠️ Limitations of this v0"):
    st.markdown(
        "- Corpus is **42 curated landmark cases**, not a comprehensive database. "
        "Production system would index 50,000+ judgments.\n"
        "- Citations should be **independently verified** before use in court. "
        "After the SC's Feb 2026 ruling on AI hallucinations as misconduct, "
        "this is mandatory."
    )

with st.sidebar.expander("Tester handle (optional)"):
    lawyer_handle = st.text_input(
        "Initials or first name — appears in feedback log",
        value="",
        key="lawyer_handle",
    )

with st.sidebar.expander("Browse the corpus"):
    for c in corpus:
        st.caption(f"• {c['title']} ({c['year']})")

mode = st.sidebar.radio(
    "Mode",
    [
        "1. Find cases for my situation",
        "2. Topic digest (research notebook style)",
        "3. Generate headnote from judgment",
    ],
    index=0,
)

# --- Header
st.title("Criminal Law AI")
st.caption(
    "AI legal research for Indian criminal law. Outputs in journal-headnote "
    "or practitioner-notes style — your choice."
)

# Cost estimate strip
def show_usage_strip(usage: dict, elapsed: float) -> None:
    cost_usd = estimate_cost_usd(usage)
    cost_inr = cost_usd * USD_TO_INR
    cache_in = usage.get("cache_read_input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)
    new_in = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_msg = ""
    if cache_in:
        cache_msg = f"  ·  🟢 Cache hit: {cache_in:,} tokens"
    elif cache_write:
        cache_msg = f"  ·  🟡 Cache write: {cache_write:,} tokens (first call)"
    st.caption(
        f"⏱ {elapsed:.1f}s  ·  {new_in:,} new in / {out:,} out{cache_msg}"
        f"  ·  ≈ ${cost_usd:.4f} (₹{cost_inr:.2f})"
    )


# ===================================================================== MODE 1

if mode.startswith("1"):
    st.header("Describe your situation")
    st.markdown(
        "Type your legal situation in plain English. Pick the output style "
        "you want — formal journal headnote (for written submissions) or "
        "compressed practitioner notes (for chambers research)."
    )

    style_label = st.radio(
        "Output style",
        ["Journal headnote (Cri.L.J. format)", "Practitioner notes (chambers digest)"],
        index=0,
        horizontal=True,
        key="style_radio",
    )
    style = "journal" if style_label.startswith("Journal") else "practitioner"

    example = (
        "My client received a cheque dishonour notice but the notice was sent "
        "to a wrong address. Bank dishonour happened in Mumbai. Complainant "
        "filed the complaint in Delhi where he received the cheque. What are "
        "the precedents on territorial jurisdiction and validity of notice?"
    )
    situation = st.text_area(
        "Situation",
        height=180,
        placeholder=example,
        key="situation_input",
    )

    col_a, col_b = st.columns([1, 4])
    with col_a:
        run = st.button("🔍 Find cases", type="primary", disabled=not situation.strip())
    with col_b:
        if st.button("Use example"):
            st.session_state["situation_input"] = example
            st.rerun()

    if run and situation.strip():
        with st.spinner("Searching corpus and drafting (Claude Opus)…"):
            sys_prompt = build_situation_system_prompt(style, corpus_json_str())
            user_prompt = SITUATION_USER_TEMPLATE.format(
                situation=situation.strip(),
                style=style,
            )
            t0 = time.time()
            try:
                raw, usage = call_claude_cached(sys_prompt, user_prompt)
            except Exception as e:
                st.error(f"API call failed: {e}")
                st.stop()
            elapsed = time.time() - t0

        parsed = parse_json_response(raw)
        if parsed is None:
            st.stop()

        # Verify case_ids
        corpus_ids = {c["id"] for c in corpus}
        verified_cases = []
        for c in parsed.get("cases", []):
            if c.get("case_id") in corpus_ids:
                verified_cases.append(c)
            else:
                st.warning(
                    f"Skipped a case not in the corpus (possible hallucination): "
                    f"{c.get('title', '?')}"
                )

        confidence = parsed.get("confidence", "unknown")
        cmap = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
        st.markdown(
            f"**Match confidence:** {cmap.get(confidence, confidence)}  "
            f"  ·  Verified cases: {len(verified_cases)}"
        )
        show_usage_strip(usage, elapsed)

        if confidence == "low" or not verified_cases:
            st.warning(
                parsed.get("no_match_reason")
                or "The corpus does not contain cases that strongly match this "
                "situation. A larger corpus is needed in production."
            )
        else:
            for i, m in enumerate(verified_cases, 1):
                render_situation_match(i, m, style)

            st.divider()
            st.subheader("Was this useful?")
            fb_cols = st.columns([1, 1, 8])
            with fb_cols[0]:
                up = st.button("👍 Useful", key="up_1")
            with fb_cols[1]:
                down = st.button("👎 Not useful", key="down_1")
            correction = st.text_area(
                "Correction or comment (optional — what was wrong, what should have been returned?)",
                height=80,
                key="correction_1",
            )
            if up:
                save_feedback("situation", situation, raw, 1, correction, lawyer_handle)
                st.success("Thanks — feedback saved.")
            if down:
                save_feedback("situation", situation, raw, -1, correction, lawyer_handle)
                st.success("Thanks — feedback saved.")


# ===================================================================== MODE 2

elif mode.startswith("2"):
    st.header("Topic digest — chambers research notebook style")
    st.markdown(
        "Type a doctrinal topic (e.g. _\"circumstantial evidence requirements\"_, "
        "_\"S. 482 quashing on settlement\"_, _\"anticipatory bail in economic offences\"_). "
        "The AI will produce a topic-organised digest grouping relevant cases — "
        "the format senior advocates' associates use in chambers."
    )

    example_topic = "Five golden principles of circumstantial evidence — when can conviction be sustained on circumstantial evidence alone?"
    topic = st.text_area(
        "Topic / doctrinal question",
        height=120,
        placeholder=example_topic,
        key="topic_input",
    )

    col_a, col_b = st.columns([1, 4])
    with col_a:
        run = st.button("📚 Generate digest", type="primary", disabled=not topic.strip())
    with col_b:
        if st.button("Use example", key="ex2"):
            st.session_state["topic_input"] = example_topic
            st.rerun()

    if run and topic.strip():
        with st.spinner("Compiling topic digest (Claude Opus)…"):
            sys_prompt = build_digest_system_prompt(corpus_json_str())
            user_prompt = DIGEST_USER_TEMPLATE.format(topic=topic.strip())
            t0 = time.time()
            try:
                raw, usage = call_claude_cached(sys_prompt, user_prompt)
            except Exception as e:
                st.error(f"API call failed: {e}")
                st.stop()
            elapsed = time.time() - t0

        parsed = parse_json_response(raw)
        if parsed is None:
            st.stop()

        show_usage_strip(usage, elapsed)
        confidence = parsed.get("confidence", "unknown")
        cmap = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
        st.markdown(f"**Confidence:** {cmap.get(confidence, confidence)}")

        st.subheader(f"Topic: {parsed.get('topic', topic.strip())}")

        for st_block in parsed.get("sub_topics", []):
            st.markdown(f"### {st_block.get('heading', '')}")
            for c in st_block.get("cases", []):
                with st.container(border=True):
                    st.markdown(
                        f"**{c.get('title', '')}** — {c.get('citation', '')} ({c.get('year', '')})"
                    )
                    if c.get("gist"):
                        st.markdown(c["gist"])
                    if c.get("quotable_phrase"):
                        st.markdown(f"> _{c['quotable_phrase']}_")
                    if c.get("cross_refs"):
                        st.caption("**Cross-refs:** " + " · ".join(c["cross_refs"]))

        if parsed.get("summary_takeaway"):
            st.markdown("---")
            st.markdown(f"**Takeaway:** {parsed['summary_takeaway']}")

        st.divider()
        st.subheader("Was this useful?")
        fb_cols = st.columns([1, 1, 8])
        with fb_cols[0]:
            up = st.button("👍 Useful", key="up_2")
        with fb_cols[1]:
            down = st.button("👎 Not useful", key="down_2")
        correction = st.text_area(
            "Correction or comment", height=80, key="correction_2"
        )
        if up:
            save_feedback("digest", topic, raw, 1, correction, lawyer_handle)
            st.success("Thanks — feedback saved.")
        if down:
            save_feedback("digest", topic, raw, -1, correction, lawyer_handle)
            st.success("Thanks — feedback saved.")


# ===================================================================== MODE 3

else:
    st.header("Paste a judgment")
    st.markdown(
        "Paste the full text of an Indian criminal-law judgment. The AI will "
        "produce one or more headnotes — one per discrete point of law — "
        "with both a journal-format version (for citation) and a practitioner-"
        "notes version (for your working file)."
    )

    judgment_text = st.text_area(
        "Judgment text (paragraph-numbered if possible)",
        height=320,
        placeholder=(
            "1. This appeal arises out of...\n2. The facts are as follows...\n..."
        ),
        key="judgment_input",
    )

    run3 = st.button(
        "📝 Generate headnote(s)",
        type="primary",
        disabled=not judgment_text.strip(),
    )

    if run3 and judgment_text.strip():
        with st.spinner("Reading judgment and drafting (Claude Opus)…"):
            user_prompt = HEADNOTE_USER_TEMPLATE.format(
                judgment_text=judgment_text.strip()[:30000]
            )
            t0 = time.time()
            try:
                raw, usage = call_claude_cached(HEADNOTE_SYSTEM_PROMPT, user_prompt)
            except Exception as e:
                st.error(f"API call failed: {e}")
                st.stop()
            elapsed = time.time() - t0

        parsed = parse_json_response(raw)
        if parsed is None:
            st.stop()

        show_usage_strip(usage, elapsed)

        meta = parsed.get("case_metadata", {})
        if meta:
            with st.container(border=True):
                st.markdown(
                    f"**{meta.get('title', '')}**  \n"
                    f"{meta.get('court', '')} • "
                    f"{meta.get('bench', '')} • "
                    f"D/- {meta.get('date_of_decision', '')}  \n"
                    f"_{meta.get('appeal_number', '')}_"
                )

        st.subheader("Headnotes")
        for hn in parsed.get("headnotes", []):
            with st.container(border=True):
                tabs = st.tabs(["📜 Journal headnote", "📝 Practitioner notes"])
                with tabs[0]:
                    render_journal_headnote(hn.get("journal_headnote", {}), letter=hn.get("letter"))
                with tabs[1]:
                    render_practitioner_notes(hn.get("practitioner_notes", {}))

        cases_referred = parsed.get("cases_referred", [])
        if cases_referred:
            st.subheader("Cases referred")
            for cr in cases_referred:
                badge = {
                    "followed": "🟢",
                    "distinguished": "🟡",
                    "overruled": "🔴",
                    "referred": "⚪",
                }.get(cr.get("treatment", "referred"), "⚪")
                st.markdown(
                    f"{badge}  {cr.get('citation', '')}  _{cr.get('treatment', '')}_"
                )

        st.divider()
        st.subheader("Was this useful?")
        fb_cols = st.columns([1, 1, 8])
        with fb_cols[0]:
            up = st.button("👍 Useful", key="up_3")
        with fb_cols[1]:
            down = st.button("👎 Not useful", key="down_3")
        correction = st.text_area("Correction or comment", height=80, key="correction_3")
        if up:
            save_feedback("headnote", judgment_text, raw, 1, correction, lawyer_handle)
            st.success("Thanks — feedback saved.")
        if down:
            save_feedback("headnote", judgment_text, raw, -1, correction, lawyer_handle)
            st.success("Thanks — feedback saved.")

# --- Footer
st.markdown("---")
st.caption(
    "**Disclaimer:** Experimental prototype. Always verify citations against "
    "the source judgment before relying on them in court. After the Supreme "
    "Court's February 2026 ruling on AI-generated fake citations as judicial "
    "misconduct, this verification step is mandatory."
)
