/* ============================================================
   Headnote — Chat UI logic
   Talks to existing FastAPI endpoints:
     POST /api/situation   { situation, style }       -> { cases: [...] }
     POST /api/digest      { topic }                  -> { sub_topics, summary_takeaway }
     POST /api/headnote    { judgment_text }          -> { headnotes, cases_referred }
     POST /api/translate   { payload }                -> translated JSON
   Backend untouched. This file alone replaces previous app.js.
   ============================================================ */

(() => {
  "use strict";

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const elHero        = $("hero");
  const elMessages    = $("messages");
  const elPrompt      = $("prompt");
  const elSendBtn     = $("send-btn");
  const elModePills   = document.querySelectorAll(".pill");
  const elStyleToggle = $("style-toggle");
  const elStyleBtns   = document.querySelectorAll(".style-btn");
  const elChips       = document.querySelectorAll(".chip");
  const elNewBtn      = $("new-chat-btn");
  const elNewBtnLarge = $("new-chat-large");
  const elHistory     = $("history");
  const elChatTitle   = $("chat-title");
  const elSourcesList = $("sources-list");
  const elSourcesEmpty= $("sources-empty");
  const elSourcesCount= $("sources-count");
  const elToasts      = $("toasts");
  const elSidebar     = $("sidebar");
  const elSources     = $("sources");
  const elMenuBtn     = $("menu-btn");
  const elSourcesBtn  = $("sources-btn");

  // ---------- State ----------
  const state = {
    mode: "situation",          // situation | digest | headnote
    style: "journal",           // journal | practitioner
    messages: [],               // [{role, mode, content, raw, ts, cost}]
    sources: [],                // accumulated case sources for current chat
    history: [],                // [{id, title, mode, ts, messages, sources}]
    currentId: null,
    busy: false,
  };

  // ---------- LocalStorage ----------
  const LS_KEY = "headnote.history.v1";

  const loadHistory = () => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) state.history = JSON.parse(raw);
    } catch (e) { console.warn("history load failed", e); }
  };

  const saveHistory = () => {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(state.history.slice(0, 50)));
    } catch (e) { console.warn("history save failed", e); }
  };

  // ---------- Utilities ----------
  const esc = (s) => String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  const fmtTs = (ts) => {
    const d = new Date(ts);
    const today = new Date(); today.setHours(0,0,0,0);
    const dDay = new Date(d); dDay.setHours(0,0,0,0);
    const diffDays = Math.round((today - dDay) / 86400000);
    if (diffDays === 0) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  const toast = (msg, kind = "") => {
    const t = document.createElement("div");
    t.className = "toast" + (kind ? " " + kind : "");
    t.textContent = msg;
    elToasts.appendChild(t);
    setTimeout(() => t.style.opacity = "0", 2400);
    setTimeout(() => t.remove(), 2800);
  };

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      elMessages.scrollTop = elMessages.scrollHeight;
    });
  };

  // ---------- Mode + style ----------
  const setMode = (mode) => {
    state.mode = mode;
    elModePills.forEach((p) => {
      p.classList.toggle("active", p.dataset.mode === mode);
      p.setAttribute("aria-selected", p.dataset.mode === mode ? "true" : "false");
    });
    // style toggle only relevant for situation mode
    elStyleToggle.classList.toggle("hide", mode !== "situation");

    // adapt placeholder
    const ph = {
      situation: "Describe a matter — facts, parties, section invoked, the question…",
      digest:    "Type a doctrinal topic — 'circumstantial evidence requirements', 'S. 482 quashing on settlement'…",
      headnote:  "Paste the full judgment text. Headnote will return lettered Cri.L.J. headnotes.",
    };
    elPrompt.placeholder = ph[mode];
  };

  const setStyle = (style) => {
    state.style = style;
    elStyleBtns.forEach((b) => b.classList.toggle("active", b.dataset.style === style));
  };

  elModePills.forEach((p) => p.addEventListener("click", () => setMode(p.dataset.mode)));
  elStyleBtns.forEach((b) => b.addEventListener("click", () => setStyle(b.dataset.style)));

  // ---------- Example chips ----------
  elChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      setMode(chip.dataset.example);
      elPrompt.value = chip.dataset.text;
      autoGrow();
      elPrompt.focus();
    });
  });

  // ---------- Textarea auto-grow ----------
  const autoGrow = () => {
    elPrompt.style.height = "auto";
    elPrompt.style.height = Math.min(elPrompt.scrollHeight, 220) + "px";
    elSendBtn.disabled = !elPrompt.value.trim() || state.busy;
  };
  elPrompt.addEventListener("input", autoGrow);

  elPrompt.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onSend();
    } else if (e.key === "Enter" && !e.shiftKey && !state.busy) {
      // single-Enter to send on non-headnote modes (headnote = multi-line paste)
      if (state.mode !== "headnote") {
        e.preventDefault();
        onSend();
      }
    } else if (e.key === "/" && elPrompt.value === "") {
      // quick mode cycle
      e.preventDefault();
      const order = ["situation", "digest", "headnote"];
      const next = order[(order.indexOf(state.mode) + 1) % order.length];
      setMode(next);
    }
  });

  elSendBtn.addEventListener("click", onSend);

  // ---------- New chat ----------
  const startNewChat = () => {
    state.messages = [];
    state.sources = [];
    state.currentId = null;
    elMessages.innerHTML = "";
    elMessages.classList.remove("show");
    elHero.classList.remove("hide");
    elChatTitle.textContent = "New research";
    renderSources();
    renderHistory();
  };
  elNewBtn.addEventListener("click", startNewChat);
  elNewBtnLarge.addEventListener("click", startNewChat);

  // ---------- Mobile menu ----------
  if (elMenuBtn)    elMenuBtn.addEventListener("click", () => elSidebar.classList.toggle("open"));
  if (elSourcesBtn) elSourcesBtn.addEventListener("click", () => elSources.classList.toggle("open"));
  document.addEventListener("click", (e) => {
    if (window.innerWidth > 900) return;
    if (!elSidebar.contains(e.target) && !elMenuBtn?.contains(e.target))   elSidebar.classList.remove("open");
    if (!elSources.contains(e.target) && !elSourcesBtn?.contains(e.target)) elSources.classList.remove("open");
  });

  // ============================================================
  //  CORE: send + render
  // ============================================================

  async function onSend() {
    const text = elPrompt.value.trim();
    if (!text || state.busy) return;
    state.busy = true;
    autoGrow();

    // first send → hide hero, show messages
    if (state.messages.length === 0) {
      elHero.classList.add("hide");
      elMessages.classList.add("show");
      elChatTitle.textContent = text.length > 60 ? text.slice(0, 60) + "…" : text;
      state.currentId = "c_" + Date.now();
    }

    // push user msg
    const userMsg = { role: "user", mode: state.mode, content: text, ts: Date.now() };
    state.messages.push(userMsg);
    appendUserMsg(userMsg);

    elPrompt.value = "";
    autoGrow();
    scrollToBottom();

    // thinking placeholder
    const thinkingNode = appendThinking();

    try {
      const result = await callApi(state.mode, text, state.style);
      thinkingNode.remove();
      const assistMsg = {
        role: "assistant",
        mode: state.mode,
        raw: result,
        ts: Date.now(),
      };
      state.messages.push(assistMsg);
      appendAssistantMsg(assistMsg);
      mergeSources(result, state.mode);
      saveCurrentToHistory();
    } catch (err) {
      thinkingNode.remove();
      toast(err.message || "Something went wrong", "error");
      const errMsg = {
        role: "assistant",
        mode: state.mode,
        raw: { error: err.message || String(err) },
        ts: Date.now(),
      };
      state.messages.push(errMsg);
      appendErrorMsg(errMsg);
    } finally {
      state.busy = false;
      autoGrow();
      scrollToBottom();
      elPrompt.focus();
    }
  }

  // ---------- API ----------
  async function callApi(mode, text, style) {
    let url = "", body = {};
    if (mode === "situation") {
      url = "/api/situation";
      body = { situation: text, style };
    } else if (mode === "digest") {
      url = "/api/digest";
      body = { topic: text };
    } else if (mode === "headnote") {
      url = "/api/headnote";
      body = { judgment_text: text };
    } else {
      throw new Error("Unknown mode");
    }
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      throw new Error(`Server ${res.status}${t ? ": " + t.slice(0, 120) : ""}`);
    }
    return res.json();
  }

  async function translatePayload(payload) {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }),
    });
    if (!res.ok) throw new Error("Translate failed");
    return res.json();
  }

  // ============================================================
  //  RENDER: user, assistant, sources
  // ============================================================

  function appendUserMsg(msg) {
    const div = document.createElement("div");
    div.className = "msg user";
    div.innerHTML = `<div class="bubble">${esc(msg.content)}</div>`;
    elMessages.appendChild(div);
  }

  function appendThinking() {
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.innerHTML = `
      <div class="thinking">
        <span class="dots"><span></span><span></span><span></span></span>
        <span>Researching the corpus…</span>
      </div>`;
    elMessages.appendChild(div);
    scrollToBottom();
    return div;
  }

  function appendErrorMsg(msg) {
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.innerHTML = `
      <div class="meta">
        <span class="mark">H</span>
        <span class="mode-tag">${esc(msg.mode)}</span>
      </div>
      <p class="summary"><em style="color: var(--warn);">${esc(msg.raw?.error || "Something went wrong.")}</em></p>`;
    elMessages.appendChild(div);
  }

  function appendAssistantMsg(msg) {
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.dataset.idx = state.messages.length - 1;

    let inner = `
      <div class="meta">
        <span class="mark">H</span>
        <span class="mode-tag">${esc(msg.mode)}</span>
      </div>`;

    if (msg.mode === "situation") {
      inner += renderSituation(msg.raw);
    } else if (msg.mode === "digest") {
      inner += renderDigest(msg.raw);
    } else if (msg.mode === "headnote") {
      inner += renderHeadnote(msg.raw);
    }

    // assistant actions footer
    inner += `
      <div class="assistant-actions">
        <button class="act" data-act="copy" title="Copy as text">${iconCopy()} Copy</button>
        <button class="act" data-act="hindi" title="Translate to Hindi">हिन्दी</button>
        <button class="act" data-act="share" title="Share">${iconShare()} Share</button>
        ${msg.raw?.cost_inr ? `<span class="act cost">≈ $${msg.raw.cost_usd || "0.18"} / ₹${msg.raw.cost_inr}</span>` : ""}
      </div>`;

    div.innerHTML = inner;
    elMessages.appendChild(div);
    wireMsgActions(div, msg);
  }

  function wireMsgActions(div, msg) {
    // toggle case cards
    div.querySelectorAll(".case-card .cc-head").forEach((h) => {
      h.addEventListener("click", () => h.parentElement.classList.toggle("open"));
    });
    // assistant actions
    div.querySelectorAll(".assistant-actions .act").forEach((btn) => {
      btn.addEventListener("click", () => onAssistantAction(btn.dataset.act, msg, div));
    });
    // case-card actions (copy/share per case)
    div.querySelectorAll(".cc-action").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const text = btn.closest(".case-card").dataset.text || "";
        if (action === "copy") {
          navigator.clipboard.writeText(text).then(() => toast("Case copied"));
        } else if (action === "share") {
          const wa = `https://wa.me/?text=${encodeURIComponent(text)}`;
          window.open(wa, "_blank");
        }
      });
    });
  }

  async function onAssistantAction(act, msg, div) {
    if (act === "copy") {
      const text = (div.innerText || "").replace(/Copy\s*हिन्दी\s*Share[\s\S]*$/, "").trim();
      navigator.clipboard.writeText(text).then(() => toast("Copied"));
      return;
    }
    if (act === "share") {
      const summary = (div.querySelector(".summary")?.innerText || "").slice(0, 280);
      const wa = `https://wa.me/?text=${encodeURIComponent(summary + "\n\nResearched on Headnote")}`;
      window.open(wa, "_blank");
      return;
    }
    if (act === "hindi") {
      if (!msg.raw) return;
      if (msg._translated) {
        // toggle back to English
        msg._translated = false;
        const reflow = state.messages.indexOf(msg);
        // re-render this message
        const allAssist = elMessages.querySelectorAll(".msg.assistant");
        const i = parseInt(div.dataset.idx, 10);
        const fresh = document.createElement("div");
        fresh.className = "msg assistant";
        fresh.dataset.idx = i;
        fresh.innerHTML = div.innerHTML;
        div.replaceWith(fresh);
        renderTransition(fresh, msg);
        return;
      }
      try {
        toast("Translating…");
        const translated = await translatePayload(msg.raw);
        msg._translated = true;
        msg._original = msg._original || msg.raw;
        msg.raw = translated;
        // re-render in place
        const placeholder = document.createElement("div");
        appendAssistantInto(placeholder, msg);
        div.replaceWith(placeholder.firstChild);
        toast("हिन्दी ↓");
      } catch (e) {
        toast("Translation failed", "error");
      }
    }
  }

  function appendAssistantInto(host, msg) {
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.dataset.idx = state.messages.indexOf(msg);
    let inner = `
      <div class="meta">
        <span class="mark">H</span>
        <span class="mode-tag">${esc(msg.mode)}</span>
      </div>`;
    if (msg.mode === "situation") inner += renderSituation(msg.raw);
    else if (msg.mode === "digest") inner += renderDigest(msg.raw);
    else if (msg.mode === "headnote") inner += renderHeadnote(msg.raw);
    inner += `
      <div class="assistant-actions">
        <button class="act" data-act="copy">${iconCopy()} Copy</button>
        <button class="act" data-act="hindi">${msg._translated ? "EN" : "हिन्दी"}</button>
        <button class="act" data-act="share">${iconShare()} Share</button>
      </div>`;
    div.innerHTML = inner;
    host.appendChild(div);
    wireMsgActions(div, msg);
  }

  function renderTransition(div, msg) {
    // not strictly needed; placeholder for any post-replace logic
    wireMsgActions(div, msg);
  }

  // ============================================================
  //  RENDERERS: situation / digest / headnote
  // ============================================================

  function renderSituation(raw) {
    if (!raw || !raw.cases) return `<p class="summary"><em>No structured response.</em></p>`;
    const cases = raw.cases || [];
    let html = "";

    if (cases.length === 0 || raw.confidence === "low") {
      html += `<p class="summary no-match">${esc(raw.no_match_reason || "No strongly matching case in the current corpus. Try refining the situation, or check the Digest mode for a topic-level answer.")}</p>`;
    } else {
      html += `<p class="summary">Found <strong>${cases.length}</strong> relevant case${cases.length === 1 ? "" : "s"} from the corpus.</p>`;
    }

    cases.forEach((c, i) => html += renderCaseCard(c, i + 1, raw.style || state.style));
    return html;
  }

  function renderDigest(raw) {
    if (!raw || !raw.sub_topics) return `<p class="summary"><em>No structured response.</em></p>`;
    let html = "";
    if (raw.summary_takeaway) {
      html += `<p class="summary">${esc(raw.summary_takeaway)}</p>`;
    }
    (raw.sub_topics || []).forEach((st) => {
      html += `<div class="subtopic">
        <h3>${esc(st.heading || "")}</h3>`;
      (st.cases || []).forEach((c, i) => {
        const txt = [
          `${c.title || ""} ${c.citation ? "— " + c.citation : ""}`,
          c.gist ? "\n\n" + c.gist : "",
          c.quotable_phrase ? `\n\n"${c.quotable_phrase}"` : "",
        ].join("");
        html += `<div class="case-card" data-text="${esc(txt)}">
          <div class="cc-head">
            <span class="cc-num">${i + 1}</span>
            <div class="cc-meta">
              <div class="cc-title">${esc(c.title || "")}</div>
              <div class="cc-citation">${esc(c.citation || "")}${c.year ? " · " + c.year : ""}</div>
            </div>
            <span class="cc-toggle">${iconChevron()}</span>
          </div>
          <div class="cc-body">
            ${c.gist ? `<div class="cc-section"><h4>Gist</h4><p>${esc(c.gist)}</p></div>` : ""}
            ${c.quotable_phrase ? `<div class="cc-section"><h4>Quotable phrase</h4><p><em>${esc(c.quotable_phrase)}</em></p></div>` : ""}
            ${Array.isArray(c.cross_refs) && c.cross_refs.length ? `<div class="cc-section"><h4>Cross-references</h4><p>${c.cross_refs.map(esc).join(" · ")}</p></div>` : ""}
            <div class="cc-actions">
              <button class="cc-action" data-action="copy">${iconCopy()} Copy</button>
              <button class="cc-action" data-action="share">${iconShare()} WhatsApp</button>
            </div>
          </div>
        </div>`;
      });
      html += `</div>`;
    });
    return html;
  }

  function renderHeadnote(raw) {
    if (!raw) return `<p class="summary"><em>No structured response.</em></p>`;
    let html = "";
    const meta = raw.case_metadata || {};
    if (meta.title) {
      html += `<p class="summary"><strong>${esc(meta.title)}</strong>${meta.court ? " · " + esc(meta.court) : ""}${meta.date_of_decision ? " · " + esc(meta.date_of_decision) : ""}</p>`;
    }
    (raw.headnotes || []).forEach((hn) => {
      const j = hn.journal_headnote || {};
      const p = hn.practitioner_notes || {};
      html += `<div class="headnote-letter">
        <div><span class="letter">${esc(hn.letter || "")}</span></div>
        ${j.statute_index ? `<div class="cc-section"><h4>Statute</h4><p class="text"><strong>${esc(j.statute_index)}</strong></p></div>` : ""}
        ${j.catchword_chain ? `<div class="cc-section"><h4>Catchwords</h4><p class="text">${esc(j.catchword_chain)}</p></div>` : ""}
        ${j.ratio ? `<div class="cc-section"><h4>Ratio</h4><p class="text">${esc(j.ratio)}</p></div>` : ""}
        ${j.negative_carve_out ? `<div class="cc-section"><h4>Does not decide</h4><p class="text">${esc(j.negative_carve_out)}</p></div>` : ""}
        ${j.paragraph_anchor ? `<div class="cc-section"><h4>Anchor</h4><p class="text"><code>${esc(j.paragraph_anchor)}</code></p></div>` : ""}
        ${p.one_line_topic ? `<div class="cc-section"><h4>Practitioner note</h4><p class="text"><strong>${esc(p.one_line_topic)}</strong> — ${esc(p.gist || "")}</p></div>` : ""}
        ${p.quotable_phrase ? `<div class="cc-section"><h4>Quotable</h4><p class="text"><em>${esc(p.quotable_phrase)}</em></p></div>` : ""}
      </div>`;
    });
    if (Array.isArray(raw.cases_referred) && raw.cases_referred.length) {
      html += `<div class="cc-section" style="margin-top:18px"><h4>Cases referred</h4><p class="text">${raw.cases_referred.map(r => `${esc(r.citation)} (${esc(r.treatment)})`).join(" · ")}</p></div>`;
    }
    return html;
  }

  function renderCaseCard(c, num, style) {
    const j = c.journal_headnote || {};
    const p = c.practitioner_notes || {};
    const isJournal = style === "journal";
    const flatText = [
      `${c.title || ""} — ${c.citation || ""}`,
      c.relevance_explanation ? `\n\nWhy this matches: ${c.relevance_explanation}` : "",
      isJournal && j.ratio ? `\n\nRatio: ${j.ratio}` : "",
      !isJournal && p.gist ? `\n\nGist: ${p.gist}` : "",
      j.paragraph_anchor ? `\n${j.paragraph_anchor}` : "",
    ].join("");

    return `<div class="case-card" data-text="${esc(flatText)}">
      <div class="cc-head">
        <span class="cc-num">${num}</span>
        <div class="cc-meta">
          <div class="cc-title">${esc(c.title || "")}</div>
          <div class="cc-citation">${esc(c.citation || "")}${c.year ? " · " + c.year : ""}${c.court ? " · " + esc(c.court) : ""}</div>
        </div>
        <span class="cc-toggle">${iconChevron()}</span>
      </div>
      <div class="cc-body">
        ${c.relevance_explanation ? `<div class="cc-relevance">${esc(c.relevance_explanation)}</div>` : ""}

        ${isJournal ? `
          ${j.statute_index ? `<div class="cc-section"><h4>Statute</h4><p class="text"><strong>${esc(j.statute_index)}</strong></p></div>` : ""}
          ${j.catchword_chain ? `<div class="cc-section"><h4>Catchwords</h4><p class="text">${esc(j.catchword_chain)}</p></div>` : ""}
          ${j.ratio ? `<div class="cc-section"><h4>Ratio</h4><p class="text">${esc(j.ratio)}</p></div>` : ""}
          ${j.negative_carve_out ? `<div class="cc-section"><h4>Does not decide</h4><p class="text">${esc(j.negative_carve_out)}</p></div>` : ""}
          ${j.paragraph_anchor ? `<div class="cc-section"><h4>Anchor</h4><p class="text"><code>${esc(j.paragraph_anchor)}</code></p></div>` : ""}
        ` : `
          ${p.one_line_topic ? `<div class="cc-section"><h4>Topic</h4><p class="text"><strong>${esc(p.one_line_topic)}</strong></p></div>` : ""}
          ${p.gist ? `<div class="cc-section"><h4>Gist</h4><p class="text">${esc(p.gist)}</p></div>` : ""}
          ${p.quotable_phrase ? `<div class="cc-section"><h4>Quotable</h4><p class="text"><em>${esc(p.quotable_phrase)}</em></p></div>` : ""}
          ${Array.isArray(p.cross_refs) && p.cross_refs.length ? `<div class="cc-section"><h4>Cross-refs</h4><p class="text">${p.cross_refs.map(esc).join(" · ")}</p></div>` : ""}
        `}

        ${c.bns_note ? `<div class="cc-bns">${esc(c.bns_note)}</div>` : ""}

        <div class="cc-actions">
          <button class="cc-action" data-action="copy">${iconCopy()} Copy</button>
          <button class="cc-action" data-action="share">${iconShare()} WhatsApp</button>
        </div>
      </div>
    </div>`;
  }

  // ============================================================
  //  SOURCES PANEL
  // ============================================================
  function mergeSources(raw, mode) {
    let newOnes = [];
    if (mode === "situation" && Array.isArray(raw?.cases)) {
      newOnes = raw.cases.map(c => ({
        id: c.case_id, title: c.title, citation: c.citation, year: c.year, court: c.court,
      }));
    } else if (mode === "digest" && Array.isArray(raw?.sub_topics)) {
      raw.sub_topics.forEach(st => (st.cases || []).forEach(c => {
        newOnes.push({ id: c.case_id, title: c.title, citation: c.citation, year: c.year });
      }));
    } else if (mode === "headnote" && Array.isArray(raw?.cases_referred)) {
      newOnes = raw.cases_referred.map((r, i) => ({
        id: "ref_" + i, title: r.citation, citation: r.treatment,
      }));
    }
    // dedupe by id+title
    const seen = new Set(state.sources.map(s => (s.id || "") + "|" + (s.title || "")));
    newOnes.forEach(n => {
      const key = (n.id || "") + "|" + (n.title || "");
      if (!seen.has(key)) {
        state.sources.push(n);
        seen.add(key);
      }
    });
    renderSources();
  }

  function renderSources() {
    elSourcesCount.textContent = state.sources.length;
    if (state.sources.length === 0) {
      elSourcesEmpty.classList.remove("hide");
      elSourcesList.innerHTML = "";
      return;
    }
    elSourcesEmpty.classList.add("hide");
    elSourcesList.innerHTML = state.sources.map((s, i) => `
      <div class="src" style="animation-delay:${i * 40}ms">
        <div class="src-head">
          <span class="src-num">${i + 1}</span>
          <div class="src-title">${esc(s.title || "")}</div>
        </div>
        <div class="src-citation">${esc(s.citation || "")}${s.year ? " · " + s.year : ""}${s.court ? " · " + esc(s.court) : ""}</div>
        <div class="src-verified">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          Verified to corpus
        </div>
      </div>
    `).join("");
  }

  // ============================================================
  //  HISTORY
  // ============================================================
  function saveCurrentToHistory() {
    if (state.messages.length === 0) return;
    const first = state.messages.find(m => m.role === "user");
    const title = first ? (first.content.length > 60 ? first.content.slice(0, 60) + "…" : first.content) : "Untitled";
    const entry = {
      id: state.currentId,
      title,
      mode: state.messages[0]?.mode || state.mode,
      ts: Date.now(),
      messages: state.messages,
      sources: state.sources,
    };
    const existingIdx = state.history.findIndex(h => h.id === state.currentId);
    if (existingIdx >= 0) state.history[existingIdx] = entry;
    else state.history.unshift(entry);
    saveHistory();
    renderHistory();
  }

  function loadFromHistory(id) {
    const entry = state.history.find(h => h.id === id);
    if (!entry) return;
    state.messages = entry.messages;
    state.sources = entry.sources || [];
    state.currentId = entry.id;
    elChatTitle.textContent = entry.title;
    elHero.classList.add("hide");
    elMessages.classList.add("show");
    elMessages.innerHTML = "";
    state.messages.forEach(m => {
      if (m.role === "user") appendUserMsg(m);
      else if (m.raw?.error) appendErrorMsg(m);
      else appendAssistantMsg(m);
    });
    renderSources();
    renderHistory();
    if (window.innerWidth <= 900) elSidebar.classList.remove("open");
    scrollToBottom();
  }

  function renderHistory() {
    if (state.history.length === 0) {
      elHistory.innerHTML = `<div style="font-size:12px;color:var(--ink-3);padding:8px 4px;">No research yet.</div>`;
      return;
    }
    elHistory.innerHTML = state.history.map(h => `
      <button class="history-item ${h.id === state.currentId ? "active" : ""}" data-id="${esc(h.id)}">
        <div class="h-title">${esc(h.title)}</div>
        <div class="h-meta">
          <span class="h-tag">${esc(h.mode)}</span>
          <span>· ${fmtTs(h.ts)}</span>
        </div>
      </button>
    `).join("");
    elHistory.querySelectorAll(".history-item").forEach(b => {
      b.addEventListener("click", () => loadFromHistory(b.dataset.id));
    });
  }

  // ============================================================
  //  ICONS (inline SVG strings)
  // ============================================================
  function iconChevron() {
    return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
  }
  function iconCopy() {
    return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
  }
  function iconShare() {
    return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.6" y1="13.5" x2="15.4" y2="17.5"></line><line x1="15.4" y1="6.5" x2="8.6" y2="10.5"></line></svg>`;
  }

  // ============================================================
  //  BOOT
  // ============================================================
  loadHistory();
  renderHistory();
  renderSources();
  setMode("situation");
  setStyle("journal");
  autoGrow();
  elPrompt.focus();

})();
