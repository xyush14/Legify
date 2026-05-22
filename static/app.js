/* =============================================================================
 * Headnote app · vanilla JS, no framework
 *
 * One file, three views: Research, Browse, Drafting (placeholder).
 *
 * Research auto-detects the user's intent from the input:
 *   - >1800 chars + paragraph breaks  → Headnote (Cri.L.J. format generation)
 *   - <80 chars, no sentence punctuation → Digest (topic research)
 *   - default                          → Situation (facts → ranked precedents)
 *
 * The user can override via the mode chip if detection is wrong.
 * ========================================================================== */
(() => {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const ce = (tag, opts = {}) => {
    const el = document.createElement(tag);
    if (opts.cls) el.className = opts.cls;
    if (opts.text != null) el.textContent = opts.text;
    if (opts.html != null) el.innerHTML = opts.html;
    if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) el.setAttribute(k, v);
    if (opts.children) opts.children.forEach(c => c && el.appendChild(c));
    return el;
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));

  // -------------------------------------------------------------- state
  const HISTORY_MAX = 12;
  const VIEW_TOGGLE_KEY = 'headnote.viewmode.v1';   // headnote | table

  // Per-user scoping for any state that contains user content.
  // Research history was previously stored under a SHARED key
  // ('headnote.history.v2'), so any user signing in on a shared browser
  // saw the previous user's queries — a real data isolation bug. Now we
  // namespace by Supabase user.id and clear the legacy shared key on first
  // load. A logged-out browser uses an 'anon' bucket that's wiped on sign-in.
  const LEGACY_HISTORY_KEY = 'headnote.history.v2';
  function historyKey() {
    const uid = (window.headnoteAuth && window.headnoteAuth.userId && window.headnoteAuth.userId()) || 'anon';
    return `headnote.history.v3.${uid}`;
  }
  // One-time migration: wipe the old shared key so it can't leak across users.
  try { localStorage.removeItem(LEGACY_HISTORY_KEY); } catch (e) {}

  const state = {
    activeView: 'research',
    mode: 'hidden',         // ranking mode: hidden | famous | mixed
    style: 'practitioner',  // output style: practitioner | journal
    deepMode: false,
    jurisdiction: '',
    lastResult: null,       // { autoMode, parsed, meta, query }
    resultView: localStorage.getItem(VIEW_TOGGLE_KEY) || 'cards',
  };

  // -------------------------------------------------------------- toasts
  function toast(msg, kind = 'info', ms = 2400) {
    const t = ce('div', { cls: `toast toast--${kind}`, text: msg });
    $('#toasts').appendChild(t);
    setTimeout(() => {
      t.style.transition = 'opacity .25s';
      t.style.opacity = '0';
      setTimeout(() => t.remove(), 280);
    }, ms);
  }

  // -------------------------------------------------------------- API
  function friendlyError(status, errText) {
    if (status === 401) return 'sign in to continue.';
    if (status === 502 || status === 504) {
      return 'request took too long. opus + the full corpus can exceed the request budget on the free tier. try without deep mode, or narrow your query.';
    }
    if (status === 503) return 'a backend dependency is down (likely IK token / anthropic key not set). check the server config.';
    if (status === 429) return 'rate-limited. wait 30 seconds and try again.';
    if (status === 0)   return 'network error or request was cancelled.';
    return errText || `HTTP ${status}`;
  }

  // Pull the Supabase access token from auth.js (which exposes window.headnoteAuth).
  // Returns {} if no session — server will 401 on gated endpoints.
  async function authHeaders() {
    if (window.headnoteAuth && typeof window.headnoteAuth.getAccessToken === 'function') {
      try {
        const token = await window.headnoteAuth.getAccessToken();
        if (token) return { 'Authorization': `Bearer ${token}` };
      } catch (e) { /* fall through */ }
    }
    return {};
  }

  // Detect quota/lock 402 responses and surface the upgrade modal.
  // Returns true if it handled the response (caller should bail out).
  function handleEntitlementError(status, data) {
    if (status !== 402) return false;
    const d = (data && data.detail) || {};
    if (window.showUpgradeModal) {
      window.showUpgradeModal(d);
    } else {
      toast(d.message || 'upgrade required.', 'error', 5000);
    }
    return true;
  }

  async function post(path, body) {
    let r;
    try {
      const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) };
      r = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body) });
    } catch (e) {
      throw new Error(friendlyError(0, e.message));
    }
    const data = await r.json().catch(() => ({}));
    if (handleEntitlementError(r.status, data)) {
      throw new Error((data.detail && data.detail.message) || 'upgrade required');
    }
    if (!r.ok) throw new Error(friendlyError(r.status, data.error || (data.detail && data.detail.message)));
    return data;
  }
  async function getJson(path) {
    const headers = await authHeaders();
    const r = await fetch(path, { headers });
    const data = await r.json().catch(() => ({}));
    if (handleEntitlementError(r.status, data)) {
      throw new Error((data.detail && data.detail.message) || 'upgrade required');
    }
    if (!r.ok) throw new Error(data.error || (data.detail && data.detail.message) || `HTTP ${r.status}`);
    return data;
  }

  // -------------------------------------------------------------- view router
  function switchView(view) {
    state.activeView = view;
    $$('.view').forEach(el => el.classList.toggle('is-active', el.dataset.view === view));
    $$('.navitem').forEach(el => el.classList.toggle('is-active', el.dataset.view === view));
    // Keep mobile bottom nav in sync
    $$('.botnav__item[data-view]').forEach(el => el.classList.toggle('is-active', el.dataset.view === view));
    // Close drawer if open
    closeDrawer();
    // Scroll to top on view switch (mobile UX)
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  // -------------------------------------------------------------- mobile drawer
  function openDrawer() {
    const sb = $('#sidebar'); const bd = $('#drawer-backdrop');
    if (!sb || !bd) return;
    sb.classList.add('is-open');
    bd.hidden = false;
    requestAnimationFrame(() => bd.classList.add('is-open'));
    document.body.style.overflow = 'hidden';
  }
  function closeDrawer() {
    const sb = $('#sidebar'); const bd = $('#drawer-backdrop');
    if (!sb || !bd) return;
    sb.classList.remove('is-open');
    bd.classList.remove('is-open');
    setTimeout(() => { bd.hidden = true; }, 220);
    document.body.style.overflow = '';
  }
  function toggleDrawer() {
    const sb = $('#sidebar');
    if (!sb) return;
    if (sb.classList.contains('is-open')) closeDrawer(); else openDrawer();
  }

  // Wire mobile chrome handlers — called from boot() once DOM is ready.
  function wireMobileChrome() {
    const menuBtn = $('#mobnav-menu');
    if (menuBtn) menuBtn.addEventListener('click', toggleDrawer);
    const backdrop = $('#drawer-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeDrawer);
    $$('.botnav__item[data-view]').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });
    const newChat = $('#mobnav-newchat');
    if (newChat) newChat.addEventListener('click', () => {
      switchView('research');
      createNewChat();
    });
    const acctBtn = $('#botnav-account');
    if (acctBtn) acctBtn.addEventListener('click', () => {
      // Open the drawer to expose sign-out + user info
      openDrawer();
    });
    // Close drawer on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDrawer();
    });
  }

  // -------------------------------------------------------------- input intent
  function detectIntent(text) {
    const t = (text || '').trim();
    if (!t) return 'situation';
    // Headnote: long judgment-like text with multiple paragraphs
    if (t.length > 1800 && (t.match(/\n\s*\n/g) || []).length >= 1) return 'headnote';
    if (t.length > 3000) return 'headnote';
    // Digest: short doctrinal phrase, no sentence punctuation
    const sentenceMarks = (t.match(/[.?!।]/g) || []).length;
    if (t.length < 80 && sentenceMarks === 0) return 'digest';
    return 'situation';
  }

  function describeMode(intent) {
    if (intent === 'headnote') return 'detected: long judgment text → cri.l.j. headnote';
    if (intent === 'digest')   return 'detected: short doctrinal phrase → research digest';
    return 'detected: factual situation → ranked precedents';
  }

  // -------------------------------------------------------------- chats / history
  // Multi-conversation research:
  //   chats[]  — array of { id, title, query, result, meta, autoMode, ts }
  //   Each chat = a saved research session. New chats are created via the
  //   "+ New chat" button or implicitly on submit when no active chat.
  //   Backed by per-user localStorage so accounts are isolated.
  //
  // The legacy flat-string history (HISTORY_KEY) was kept for backwards
  // compatibility above but is now derived from chats[] for rendering.
  const CHATS_MAX = 30;
  function chatsKey() {
    const uid = (window.headnoteAuth && window.headnoteAuth.userId && window.headnoteAuth.userId()) || 'anon';
    return `headnote.chats.v1.${uid}`;
  }
  function readChats() {
    try { return JSON.parse(localStorage.getItem(chatsKey()) || '[]'); }
    catch { return []; }
  }
  function writeChats(arr) {
    try { localStorage.setItem(chatsKey(), JSON.stringify(arr.slice(0, CHATS_MAX))); } catch {}
  }
  function uuid() {
    return 'c_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  }
  function chatTitle(query) {
    const t = (query || '').trim().split('\n')[0];
    return t.length > 48 ? t.slice(0, 45) + '…' : (t || 'untitled chat');
  }
  function createNewChat() {
    // Don't clutter the sidebar with multiple empty chats — if the user
    // hit "new chat" without typing, reuse the existing empty one.
    let chats = readChats();
    const empty = chats.find(c => !c.query);
    if (empty) {
      state.currentChatId = empty.id;
    } else {
      const c = { id: uuid(), title: '', query: '', result: null, meta: null, autoMode: null, ts: Date.now() };
      chats.unshift(c);
      writeChats(chats);
      state.currentChatId = c.id;
    }
    state.lastResult = null;
    const target = $('#results'); if (target) target.innerHTML = '';
    const input  = $('#situation-input'); if (input) input.value = '';
    renderHistory();
    if (input) input.focus();
  }
  function saveCurrentChat(query, result, meta, autoMode) {
    let chats = readChats();
    if (!state.currentChatId) state.currentChatId = uuid();
    let c = chats.find(x => x.id === state.currentChatId);
    if (!c) {
      c = { id: state.currentChatId, title: '', query: '', result: null, meta: null, autoMode: null, ts: Date.now() };
      chats.unshift(c);
    } else {
      // Move to top
      chats = chats.filter(x => x.id !== c.id);
      chats.unshift(c);
    }
    c.query    = query;
    c.result   = result;
    c.meta     = meta;
    c.autoMode = autoMode;
    c.title    = chatTitle(query);
    c.ts       = Date.now();
    writeChats(chats);
    renderHistory();
  }
  function loadChat(chatId) {
    const c = readChats().find(x => x.id === chatId);
    if (!c) return;
    state.currentChatId = c.id;
    const input = $('#situation-input');
    if (input) input.value = c.query || '';
    if (c.result) {
      state.lastResult = { autoMode: c.autoMode, parsed: c.result, meta: c.meta || {}, query: c.query };
      renderResearchResult();
    } else {
      state.lastResult = null;
      const target = $('#results'); if (target) target.innerHTML = '';
    }
    renderHistory();
    closeDrawer();
    switchView('research');
  }
  function deleteChat(chatId) {
    const chats = readChats().filter(c => c.id !== chatId);
    writeChats(chats);
    if (state.currentChatId === chatId) {
      state.currentChatId = null;
      state.lastResult = null;
      const target = $('#results'); if (target) target.innerHTML = '';
      const input  = $('#situation-input'); if (input) input.value = '';
    }
    renderHistory();
  }

  // Back-compat shims — existing code calls readHistory() and pushHistory(text).
  // We derive the flat string list from chats[] so any caller that still
  // expects a string array keeps working.
  function readHistory() {
    return readChats().map(c => c.query).filter(Boolean);
  }
  function pushHistory(text) {
    // Submitting a new query: ensure there's an active chat to attach to.
    if (!text || !text.trim()) return;
    if (!state.currentChatId) state.currentChatId = uuid();
  }
  function renderHistory() {
    const wrap = $('#history');
    if (!wrap) return;
    wrap.innerHTML = '';

    // "+ New chat" CTA at the top
    const newBtn = ce('button', { cls: 'history-newchat', text: '+ new chat' });
    newBtn.addEventListener('click', createNewChat);
    wrap.appendChild(newBtn);

    const chats = readChats().filter(c => c.query); // hide empty placeholder chats
    if (!chats.length) {
      wrap.appendChild(ce('div', { cls: 'history-empty', text: 'no chats yet — start by asking a question' }));
      return;
    }
    chats.forEach(c => {
      const row = ce('div', { cls: 'history-row' + (c.id === state.currentChatId ? ' history-row--active' : '') });
      const b = ce('button', {
        cls: 'history-item',
        text: c.title || chatTitle(c.query),
        attrs: { title: c.query, role: 'listitem' },
      });
      b.addEventListener('click', () => loadChat(c.id));
      const del = ce('button', { cls: 'history-del', text: '×', attrs: { 'aria-label': 'Delete chat' } });
      del.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm('Delete this chat?')) deleteChat(c.id);
      });
      row.appendChild(b);
      row.appendChild(del);
      wrap.appendChild(row);
    });
  }

  // -------------------------------------------------------------- composer chips
  function setMode(m) {
    state.mode = m;
    $$('.composer__chips .chip[data-mode]').forEach(c => c.classList.toggle('is-active', c.dataset.mode === m));
  }
  function setStyle(s) {
    state.style = s;
    $$('.composer__chips .chip[data-style]').forEach(c => c.classList.toggle('is-active', c.dataset.style === s));
  }
  function updateModeDisplay() {
    const q = $('#situation-input').value;
    const intent = detectIntent(q);
    const el = $('#mode-display');
    if (!q.trim()) { el.textContent = ''; return; }
    el.textContent = describeMode(intent);
  }

  // -------------------------------------------------------------- result rendering
  function renderResearching(text, isLoading) {
    return ce('div', {
      cls: 'researching' + (isLoading ? ' is-loading' : ''),
      children: [
        ce('div', { cls: 'researching__label', text: 'researching' }),
        ce('div', { cls: 'researching__line', children: [
          ce('div', { cls: 'researching__text', text: isLoading ? 'preparing focused sub-queries…' : (text || '—') }),
        ]}),
      ],
    });
  }

  // Progressive stage indicator. Updates as the request progresses.
  // Each call to advanceStage(n) marks stage n as done and the next as active.
  function renderStagesPanel(stages) {
    const wrap = ce('div', { cls: 'stages' });
    wrap.appendChild(ce('div', { cls: 'stages__label', text: 'progress' }));
    stages.forEach((label, i) => {
      wrap.appendChild(ce('div', {
        cls: `stage ${i === 0 ? 'stage--active' : ''}`,
        attrs: { 'data-stage': String(i) },
        children: [
          ce('div', { cls: 'stage__icon' }),
          ce('div', { cls: 'stage__label', text: label }),
        ],
      }));
    });
    return wrap;
  }
  function advanceStage(panel, doneIndex, activateNext = true) {
    if (!panel) return;
    const stages = panel.querySelectorAll('.stage');
    if (doneIndex >= 0 && doneIndex < stages.length) {
      stages[doneIndex].classList.remove('stage--active');
      stages[doneIndex].classList.add('stage--done');
    }
    if (activateNext && doneIndex + 1 < stages.length) {
      stages[doneIndex + 1].classList.add('stage--active');
    }
  }

  function renderBilingualStrip(originalHindi, englishQuery) {
    return ce('div', {
      cls: 'bilingual',
      children: [
        ce('div', { cls: 'bilingual__line', children: [
          ce('div', { cls: 'bilingual__label', text: 'आपकी क्वेरी' }),
          ce('div', { cls: 'bilingual__text', text: originalHindi }),
        ]}),
        ce('div', { cls: 'bilingual__line', children: [
          ce('div', { cls: 'bilingual__label', text: 'translated' }),
          ce('div', { cls: 'bilingual__english', text: englishQuery }),
        ]}),
      ],
    });
  }

  function renderLoadingCards(n = 3) {
    const wrap = ce('div', { cls: 'loading-cards' });
    for (let i = 0; i < n; i++) {
      wrap.appendChild(ce('div', { cls: 'skeleton-card', children: [
        ce('div', { cls: 'skeleton-line skeleton-line--title' }),
        ce('div', { cls: 'skeleton-line skeleton-line--short' }),
        ce('div', { cls: 'skeleton-line' }),
        ce('div', { cls: 'skeleton-line skeleton-line--med' }),
      ]}));
    }
    return wrap;
  }

  function renderError(msg) {
    return ce('div', { cls: 'error-card', text: msg });
  }

  // ---- helpers shared between card + table renderers ----
  function fameBadge(case_) {
    const fi = case_.fame_indicator || '';
    if (fi === 'obscure') return ce('span', { cls: 'badge badge--obscure', text: '⟡ obscure' });
    if (fi === 'famous')  return ce('span', { cls: 'badge badge--famous',  text: 'leading authority' });
    if (fi === 'lesser-known') return ce('span', { cls: 'badge', text: 'lesser-known' });
    if (fi === 'curated') return ce('span', { cls: 'badge', text: 'curated' });
    return null;
  }

  // Outcome badge — derived from the case's disposition. Green for outcomes
  // that favour the accused (acquittal, quashed, bail-granted), red for
  // adverse outcomes (conviction, bail-denied), neutral for the rest.
  const OUTCOME_BUCKETS = {
    'acquittal':    { cls: 'badge--outcome-good',    label: 'acquittal' },
    'quashed':      { cls: 'badge--outcome-good',    label: 'quashed' },
    'bail-granted': { cls: 'badge--outcome-good',    label: 'bail granted' },
    'dismissed':    { cls: 'badge--outcome-neutral', label: 'dismissed' },
    'conviction':   { cls: 'badge--outcome-bad',     label: 'conviction' },
    'bail-denied':  { cls: 'badge--outcome-bad',     label: 'bail denied' },
    'remand':       { cls: 'badge--outcome-neutral', label: 'remand' },
    'other':        null,
  };
  function outcomeBadge(case_) {
    const o = (case_.outcome || '').toLowerCase();
    const spec = OUTCOME_BUCKETS[o];
    if (!spec) return null;
    return ce('span', { cls: `badge ${spec.cls}`, text: spec.label });
  }

  // Normalise a case object from the situation schema (practitioner_notes or
  // journal_headnote nested) into the flat fields the renderer wants.
  function normaliseCase(c) {
    const pn = c.practitioner_notes || {};
    const jh = c.journal_headnote || {};
    return {
      // identifiers
      case_id: c.case_id,
      title: c.title || c.case_title || c.case_id || 'untitled',
      citation: c.citation || '',
      court: c.court || '',
      year: c.year || '',
      bench: c.bench || jh.per_judge_attribution || '',
      // deep-links / provenance
      kanoon_url: c.kanoon_url,
      kanoon_paragraph_url: c.kanoon_paragraph_url,
      kanoon_doc_id: c.kanoon_doc_id,
      fame_indicator: c.fame_indicator,
      source: c.source,
      // body — the differentiator and the substance
      fact_match: c.relevance_explanation || c.fact_match || pn.one_line_topic || '',
      one_line_topic: pn.one_line_topic || '',
      ratio: jh.ratio || pn.gist || c.ratio || c.holding || '',
      negative_carve_out: jh.negative_carve_out || '',
      catchword_chain: jh.catchword_chain || '',
      statute_index: jh.statute_index || '',
      quotable_phrase: pn.quotable_phrase || c.quotable_phrase || '',
      paragraph_anchor: c.paragraph_anchor || jh.paragraph_anchor || '',
      cross_refs: pn.cross_refs || c.cross_refs || [],
      bns_note: c.bns_note || '',
      outcome: c.outcome || '',
    };
  }
  function verifiedBadge() {
    return ce('span', { cls: 'badge badge--verified', text: 'verified' });
  }
  function judgmentLink(case_) {
    if (!case_.kanoon_url) return null;
    const label = case_.citation || case_.case_id || 'open on indian kanoon';
    return ce('a', {
      cls: 'judgment-link',
      text: label + ' ↗',
      attrs: { href: case_.kanoon_paragraph_url || case_.kanoon_url, target: '_blank', rel: 'noopener' },
    });
  }
  function metaBits(case_) {
    const bits = [];
    if (case_.court) bits.push(case_.court);
    if (case_.year)  bits.push(String(case_.year));
    if (case_.bench) bits.push(case_.bench);
    return bits;
  }

  function renderCaseCard(raw, idx) {
    const c = normaliseCase(raw);
    const head = ce('div', { cls: 'case-card__head' });
    const titleEl = ce('div', { cls: 'case-card__title' });
    if (c.kanoon_url) {
      titleEl.appendChild(ce('a', { text: c.title, attrs: { href: c.kanoon_url, target: '_blank', rel: 'noopener' } }));
      titleEl.appendChild(ce('span', { cls: 'ext-arrow', text: '↗' }));
    } else {
      titleEl.appendChild(document.createTextNode(c.title));
    }
    head.appendChild(titleEl);
    head.appendChild(ce('div', { cls: 'case-card__meta mono', text: `#${idx + 1}` }));

    // Meta line: court · year · bench · citation
    const metaLine = ce('div', { cls: 'case-card__meta mono' });
    metaBits(c).forEach(b => metaLine.appendChild(ce('span', { text: b })));
    if (c.citation) metaLine.appendChild(ce('span', { text: c.citation }));

    // Catchword chain (journal style only) — shows above the body
    const preBody = [];
    if (c.statute_index) {
      preBody.push(ce('div', { cls: 'headnote-block__catchwords', text: c.statute_index }));
    }
    if (c.catchword_chain) {
      preBody.push(ce('div', { cls: 'headnote-block__catchwords', text: c.catchword_chain }));
    }

    const rows = [];

    // Fact-match row — THE differentiator, navy tint
    if (c.fact_match) {
      rows.push(ce('div', { cls: 'case-card__row case-card__row--factmatch', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'fact match' }),
        ce('div', { cls: 'case-card__rowtext', text: c.fact_match }),
      ]}));
    }

    // Ratio (holding compressed)
    if (c.ratio) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'ratio' }),
        ce('div', { cls: 'case-card__rowtext', text: c.ratio }),
      ]}));
    }

    // Negative carve-out — journal style; warn-coloured to signal limitation
    if (c.negative_carve_out) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'carve-out' }),
        ce('div', { cls: 'case-card__rowtext', text: c.negative_carve_out }),
      ]}));
    }

    // Quotable phrase
    if (c.quotable_phrase) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'quote' }),
        ce('div', { cls: 'case-card__rowtext', text: '“' + c.quotable_phrase + '”' }),
      ]}));
    }

    // Paragraph anchor → deep link
    if (c.paragraph_anchor) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'paragraph' }),
        ce('div', { cls: 'case-card__rowtext', children: [
          c.kanoon_paragraph_url
            ? ce('a', { cls: 'judgment-link', text: c.paragraph_anchor + ' ↗', attrs: { href: c.kanoon_paragraph_url, target: '_blank', rel: 'noopener' } })
            : document.createTextNode(c.paragraph_anchor),
        ]}),
      ]}));
    }

    // Cross-refs (practitioner style)
    if (c.cross_refs && c.cross_refs.length) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'cited' }),
        ce('div', { cls: 'case-card__rowtext mono', text: c.cross_refs.join(' · ') }),
      ]}));
    }

    // BNS / BNSS mapping note (helps the lawyer translate IPC→BNS)
    if (c.bns_note) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'bns' }),
        ce('div', { cls: 'case-card__rowtext', text: c.bns_note }),
      ]}));
    }

    const badges = ce('div', { cls: 'case-card__badges' });
    const ob = outcomeBadge(c); if (ob) badges.appendChild(ob);
    const fb = fameBadge(c);    if (fb) badges.appendChild(fb);
    badges.appendChild(verifiedBadge());
    const j = judgmentLink(c);  if (j) badges.appendChild(j);

    // Hindi toggle button (per-card back-translation of ratio + quote)
    const hindiBtn = ce('button', { cls: 'btn--ghost', text: 'हिंदी में दिखाएँ' });
    hindiBtn.addEventListener('click', () => toggleCardHindi(hindiBtn, c, rows));
    badges.appendChild(hindiBtn);

    return ce('div', { cls: 'case-card', children: [head, metaLine, ...preBody, ...rows, badges] });
  }

  // ---- Per-card Hindi back-translation (lazy) ----
  const hindiCache = new Map();   // case_id -> { ratio, quote, fact_match }
  async function toggleCardHindi(btn, c, rows) {
    const cid = c.case_id || c.title;
    if (btn.classList.contains('is-active')) {
      // Restore English — re-render is the easiest; just refresh the page render
      btn.classList.remove('is-active');
      btn.textContent = 'हिंदी में दिखाएँ';
      renderResearchResult();
      return;
    }
    btn.classList.add('is-active');
    btn.textContent = 'translating…';
    btn.disabled = true;
    try {
      let cached = hindiCache.get(cid);
      if (!cached) {
        const payload = {
          ratio: c.ratio || '',
          fact_match: c.fact_match || '',
          quotable_phrase: c.quotable_phrase || '',
        };
        const resp = await post('/api/translate', { payload });
        cached = resp.result || {};
        hindiCache.set(cid, cached);
      }
      // Mutate the displayed rows to show Hindi
      rows.forEach(row => {
        const label = row.querySelector('.case-card__rowlabel').textContent;
        const text = row.querySelector('.case-card__rowtext');
        if (label === 'ratio' && cached.ratio) text.textContent = cached.ratio;
        else if (label === 'fact match' && cached.fact_match) text.textContent = cached.fact_match;
        else if (label === 'quote' && cached.quotable_phrase) text.textContent = '“' + cached.quotable_phrase + '”';
      });
      btn.textContent = 'show in english';
      btn.disabled = false;
    } catch (err) {
      btn.classList.remove('is-active');
      btn.textContent = 'हिंदी में दिखाएँ';
      btn.disabled = false;
      toast('hindi translation failed: ' + (err.message || 'unknown'), 'error');
    }
  }

  function renderCasesAsCards(cases) {
    const list = ce('div', { cls: 'results' });
    cases.forEach((c, i) => list.appendChild(renderCaseCard(c, i)));
    return list;
  }

  function renderCasesAsTable(cases) {
    const wrap = ce('div', { cls: 'comparison-table-wrap' });
    const table = ce('table', { cls: 'comparison-table' });
    const thead = ce('thead', { children: [
      ce('tr', { children: [
        ce('th', { text: 'case / authority' }),
        ce('th', { text: 'court / year' }),
        ce('th', { text: 'ratio' }),
        ce('th', { cls: 'fact-match-col', text: 'fact match' }),
        ce('th', { text: 'paragraph' }),
      ]}),
    ]});
    const tbody = ce('tbody');
    cases.forEach((raw) => {
      const c = normaliseCase(raw);
      const titleCell = ce('td');
      const titleEl = ce('span', { cls: 'ct-title' });
      if (c.kanoon_url) {
        titleEl.appendChild(ce('a', { text: c.title, attrs: { href: c.kanoon_url, target: '_blank', rel: 'noopener' } }));
      } else {
        titleEl.appendChild(document.createTextNode(c.title));
      }
      titleCell.appendChild(titleEl);
      if (c.citation) titleCell.appendChild(ce('span', { cls: 'ct-citation', text: c.citation }));

      const courtCell = ce('td', { text: [c.court, c.year, c.bench].filter(Boolean).join(' · ') || '—' });
      const ratioCell = ce('td', { text: c.ratio || '—' });
      const factCell  = ce('td', { cls: 'fact-match', text: c.fact_match || '—' });
      const paraCell  = ce('td');
      if (c.paragraph_anchor && c.kanoon_paragraph_url) {
        paraCell.appendChild(ce('a', { cls: 'judgment-link', text: c.paragraph_anchor + ' ↗', attrs: { href: c.kanoon_paragraph_url, target: '_blank', rel: 'noopener' } }));
      } else if (c.paragraph_anchor) {
        paraCell.textContent = c.paragraph_anchor;
      } else {
        paraCell.textContent = '—';
      }

      tbody.appendChild(ce('tr', { children: [titleCell, courtCell, ratioCell, factCell, paraCell] }));
    });
    table.appendChild(thead); table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderResultsHeader(count, showToggle) {
    const head = ce('div', { cls: 'results-header' });
    head.appendChild(ce('div', { cls: 'results-header__count', text: `${count} precedent${count === 1 ? '' : 's'} returned` }));
    if (showToggle) {
      const wrap = ce('div', { cls: 'view-toggle' });
      const cardBtn = ce('button', { cls: 'view-toggle__btn' + (state.resultView === 'cards' ? ' is-active' : ''), text: 'cards' });
      const tableBtn = ce('button', { cls: 'view-toggle__btn' + (state.resultView === 'table' ? ' is-active' : ''), text: 'table' });
      cardBtn.addEventListener('click', () => { state.resultView = 'cards'; localStorage.setItem(VIEW_TOGGLE_KEY, 'cards'); renderResearchResult(); });
      tableBtn.addEventListener('click', () => { state.resultView = 'table'; localStorage.setItem(VIEW_TOGGLE_KEY, 'table'); renderResearchResult(); });
      wrap.appendChild(cardBtn); wrap.appendChild(tableBtn);
      head.appendChild(wrap);
    }
    return head;
  }

  // ---- digest + headnote views ----
  function renderDigest(parsed) {
    const wrap = ce('div', { cls: 'results' });
    const sections = parsed.sections || parsed.subtopics || [];
    if (!sections.length) {
      wrap.appendChild(ce('div', { cls: 'empty', children: [
        ce('h2', { text: 'no digest sections returned' }),
        ce('p', { text: 'try rephrasing the topic — be specific about the doctrine and statute.' }),
      ]}));
      return wrap;
    }
    sections.forEach(s => {
      const block = ce('div', { cls: 'digest-block', children: [
        ce('div', { cls: 'digest-subhead', text: s.subhead || s.title || '—' }),
        ce('div', { cls: 'digest-text', text: s.summary || s.discussion || s.text || '' }),
      ]});
      const cases = (s.leading_cases || s.cases || []).filter(Boolean);
      if (cases.length) {
        block.appendChild(ce('div', {
          cls: 'digest-cases',
          text: 'leading authority: ' + cases.map(c => typeof c === 'string' ? c : (c.case_id || c.title || '?')).join(' · '),
        }));
      }
      wrap.appendChild(block);
    });
    return wrap;
  }

  function renderHeadnotes(parsed) {
    const wrap = ce('div', { cls: 'results' });
    const list = parsed.headnotes || [];
    if (!list.length) {
      wrap.appendChild(ce('div', { cls: 'empty', children: [
        ce('h2', { text: 'no headnotes produced' }),
        ce('p', { text: 'the judgment may have been too short or unstructured for Opus to extract distinct points of law.' }),
      ]}));
      return wrap;
    }
    list.forEach(hn => {
      const block = ce('div', { cls: 'headnote-block' });
      if (hn.letter) block.appendChild(ce('span', { cls: 'headnote-block__letter', text: '(' + hn.letter + ')' }));
      if (hn.catchwords) block.appendChild(ce('div', { cls: 'headnote-block__catchwords', text: hn.catchwords }));
      if (hn.ratio) block.appendChild(ce('div', { cls: 'headnote-block__ratio', text: hn.ratio }));
      if (hn.quotable_phrase) block.appendChild(ce('div', { cls: 'headnote-block__quote', text: '“' + hn.quotable_phrase + '”' }));
      if (hn.cases_referred && hn.cases_referred.length) {
        block.appendChild(ce('div', { cls: 'headnote-block__cases', text: 'cases referred: ' + hn.cases_referred.join(' · ') }));
      }
      wrap.appendChild(block);
    });
    return wrap;
  }

  // -------------------------------------------------------------- main result render
  function renderResearchResult() {
    const r = state.lastResult;
    const target = $('#results');
    target.innerHTML = '';
    if (!r) return;

    const { autoMode, parsed, meta, query } = r;

    // 1. researching panel (Situation mode only — other modes don't need it)
    if (autoMode === 'situation' && meta && (meta.researching || meta.english_query)) {
      target.appendChild(renderResearching(meta.researching, false));
    }

    // 2. Hindi bilingual strip
    if (meta && meta.input_script === 'devanagari' && meta.original_query) {
      target.appendChild(renderBilingualStrip(meta.original_query, meta.english_query || query));
    }

    // 3. body — depends on mode
    if (autoMode === 'situation') {
      const cases = (parsed && parsed.cases) || [];
      if (!cases.length) {
        target.appendChild(ce('div', { cls: 'empty', children: [
          ce('h2', { text: 'no cases survived verification' }),
          ce('p', { text: 'every candidate was either fabricated or unverifiable. try rephrasing with more specific statute references.' }),
        ]}));
        return;
      }
      target.appendChild(renderResultsHeader(cases.length, true));
      target.appendChild(state.resultView === 'table' ? renderCasesAsTable(cases) : renderCasesAsCards(cases));
    } else if (autoMode === 'digest') {
      target.appendChild(renderDigest(parsed));
    } else if (autoMode === 'headnote') {
      target.appendChild(renderHeadnotes(parsed));
    }
  }

  // -------------------------------------------------------------- submit
  async function submitResearch() {
    const input = $('#situation-input').value.trim();
    if (!input) { toast('type something first', 'error'); return; }
    const btn = $('#submit-btn');
    btn.disabled = true; btn.querySelector('.btn__label').textContent = 'thinking…';

    const intent = detectIntent(input);
    const target = $('#results');
    target.innerHTML = '';

    // Progressive stage indicator — paced timers approximate the backend phases.
    // Real events would need server-sent events; this is a reasonable UX proxy.
    let stagePanel = null;
    const isHindi = /[ऀ-ॿ]/.test(input);
    const stages = intent === 'situation' ? [
      ...(isHindi ? ['translating hindi → english'] : []),
      'searching 42k case corpus',
      'analysing with claude',
      'verifying citations',
    ] : intent === 'headnote' ? [
      'reading the judgment',
      'extracting points of law',
      'generating cri.l.j. headnote',
      'verifying with haiku',
    ] : [
      'reading the topic',
      'sweeping curated authority',
      'generating digest',
    ];
    stagePanel = renderStagesPanel(stages);
    target.appendChild(stagePanel);

    // Pacing now matches the new pipeline (shallow refine + parallel IK fetches):
    //   - corpus search: <5s (HF + semantic + curated; IK only if pool thin)
    //   - claude analysis: ~10-15s
    //   - verification: <1s
    // 'verifying citations' never advances via timer — replaced when results arrive.
    const situationDelays = isHindi
      ? [3500, 8000, 18000]   // translate done at 3.5s, search done at 8s, claude active until results
      : [5000, 16000];        // search done at 5s, claude active until results
    const defaultDelays = stages.slice(0, -1).map((_, i) => 4500 * (i + 1));
    const stageDelays = intent === 'situation' ? situationDelays : defaultDelays;
    const timers = stageDelays.map((delay, i) =>
      setTimeout(() => advanceStage(stagePanel, i, true), delay)
    );
    const stopStageTimers = () => timers.forEach(clearTimeout);

    target.appendChild(renderLoadingCards(intent === 'headnote' ? 2 : 3));

    pushHistory(input);
    // Jurisdiction input was removed from the composer in v0.4; keep this
    // null-safe so the field is simply blank when the chip isn't rendered.
    state.jurisdiction = $('#jurisdiction-input')?.value?.trim() || '';
    state.deepMode = $('#deep-mode').checked;

    // For situation mode, fire decomposition in parallel — non-blocking.
    let decompPromise = null;
    if (intent === 'situation') {
      decompPromise = post('/api/decompose', { query: input }).catch(() => null);
    }

    // Abort after 3 min so the user gets a clear message instead of an endless spinner.
    // Sonnet w/ extended thinking + IK doc fetch + verification can legitimately
    // take 30-90s on uncached queries; 90s was too tight and aborted real work.
    const abortCtrl = new AbortController();
    const abortTimer = setTimeout(() => abortCtrl.abort(), 180000);

    try {
      let resp;
      if (intent === 'situation') {
        const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) };
        const raw = await fetch('/api/situation', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            situation: input,
            style: state.style,
            deep_mode: state.deepMode,
            mode: state.mode,
            jurisdiction: state.jurisdiction || null,
          }),
          signal: abortCtrl.signal,
        });
        clearTimeout(abortTimer);
        const data = await raw.json().catch(() => ({}));
        if (handleEntitlementError(raw.status, data)) throw new Error((data.detail && data.detail.message) || 'upgrade required');
        if (!raw.ok) throw new Error(friendlyError(raw.status, data.error || (data.detail && data.detail.message)));
        resp = data;
      } else if (intent === 'digest') {
        resp = await post('/api/digest', { topic: input, deep_mode: state.deepMode });
      } else {
        resp = await post('/api/headnote', { judgment_text: input });
      }

      // Resolve decomposition (best-effort enrichment)
      let decomp = null;
      if (decompPromise) {
        try { decomp = await decompPromise; } catch { decomp = null; }
      }
      const meta = Object.assign({}, resp.meta || {}, decomp && decomp.decomposition ? {
        researching: decomp.decomposition.user_facing_summary,
        decomposition: decomp.decomposition,
      } : {});

      state.lastResult = {
        autoMode: intent,
        parsed: resp.result || {},
        meta,
        query: input,
      };
      renderResearchResult();
      // Persist this Q&A into the active chat (per-user, localStorage).
      saveCurrentChat(input, resp.result || {}, meta, intent);
    } catch (err) {
      clearTimeout(abortTimer);
      target.innerHTML = '';
      const msg = err.name === 'AbortError'
        ? 'query took over 3 minutes — try a more specific statute reference (e.g. "S.302 IPC self-defence" instead of "murder"), or just retry — the next attempt will hit the prompt cache and be ~3× faster.'
        : (err.message || 'request failed');
      target.appendChild(renderError(msg));
    } finally {
      clearTimeout(abortTimer);
      stopStageTimers();
      btn.disabled = false;
      btn.querySelector('.btn__label').textContent = 'research';
    }
  }

  // -------------------------------------------------------------- Browse
  async function submitBrowse() {
    const q = $('#browse-input').value.trim();
    if (!q) { toast('type a query first', 'error'); return; }

    const params = new URLSearchParams({ q });
    const fields = {
      court:      $('#browse-court').value,
      year_from:  $('#browse-year-from').value,
      year_to:    $('#browse-year-to').value,
      judge:      $('#browse-judge') && $('#browse-judge').value,
      statute:    $('#browse-statute') && $('#browse-statute').value,
      sort:       $('#browse-sort') && $('#browse-sort').value,
    };
    Object.entries(fields).forEach(([k, v]) => { if (v) params.set(k, v); });

    const target = $('#browse-results');
    target.innerHTML = '';
    target.appendChild(renderLoadingCards(4));

    const btn = $('#browse-submit');
    btn.disabled = true; btn.querySelector('.btn__label').textContent = 'searching…';

    try {
      const data = await getJson(`/api/browse/search?${params}`);
      target.innerHTML = '';

      const hits = data.hits || [];
      const source = data.source || 'ik';
      const headerLine = source === 'curated-fallback'
        ? `${hits.length} curated matches · ik offline (admin: set INDIAN_KANOON_TOKEN)`
        : `${data.found || hits.length + ' hits'}`;
      target.appendChild(ce('div', { cls: 'browse-meta', text: headerLine }));
      if (data.note) {
        target.appendChild(ce('div', { cls: 'browse-note', text: data.note }));
      }
      if (data.input_script === 'devanagari') {
        target.appendChild(renderBilingualStrip(data.original_query || q, data.english_query));
      }
      if (!hits.length) {
        target.appendChild(ce('div', { cls: 'empty', children: [
          ce('h2', { text: 'no judgments matched' }),
          ce('p', { text: 'broaden your filters or try different keywords. fewer constraints = more results.' }),
        ]}));
        return;
      }
      hits.forEach(h => target.appendChild(renderBrowseItem(h, q)));
    } catch (err) {
      target.innerHTML = '';
      target.appendChild(renderError(err.message || 'browse failed'));
    } finally {
      btn.disabled = false; btn.querySelector('.btn__label').textContent = 'search';
    }
  }

  function renderBrowseItem(hit, originalQuery) {
    const titleA = ce('a', { text: hit.title, attrs: { href: hit.kanoon_url, target: '_blank', rel: 'noopener' } });
    const titleEl = ce('div', { cls: 'browse-item__title' });
    titleEl.appendChild(titleA);

    const meta = ce('div', { cls: 'browse-item__meta mono' });
    if (hit.court) meta.appendChild(ce('span', { text: hit.court }));
    if (hit.publishdate) meta.appendChild(ce('span', { text: hit.publishdate }));
    if (typeof hit.numcitedby === 'number') meta.appendChild(ce('span', { text: hit.numcitedby + ' citations' }));

    const fame = ce('div', { cls: 'case-card__badges' });
    const fb = fameBadge({ fame_indicator: hit.fame_indicator });
    if (fb) fame.appendChild(fb);

    const headline = ce('div', { cls: 'browse-item__headline', html: hit.headline || '' });

    const actions = ce('div', { cls: 'browse-item__actions' });
    const openBtn = ce('a', { cls: 'browse-item__action', text: 'open on ik ↗', attrs: { href: hit.kanoon_url, target: '_blank', rel: 'noopener' } });
    const findBtn = ce('button', { cls: 'browse-item__action', text: 'find cases like this' });
    findBtn.addEventListener('click', () => {
      switchView('research');
      $('#situation-input').value = `find precedents factually similar to: ${hit.title}. ${originalQuery || ''}`;
      updateModeDisplay();
      $('#situation-input').focus();
    });
    actions.appendChild(openBtn);
    actions.appendChild(findBtn);

    return ce('div', { cls: 'browse-item', children: [titleEl, meta, fame, headline, actions] });
  }

  // -------------------------------------------------------------- boot
  function attachEvents() {
    // Sidebar nav
    $$('.navitem').forEach(b => {
      if (b.disabled) return;
      b.addEventListener('click', () => switchView(b.dataset.view));
    });

    // Drafting tiles — "soon" tiles show a wait-list toast; "live" tiles
    // (marked with data-href) navigate to the working drafter. Live tiles
    // open in the SAME tab so the back button returns to the drafting
    // home naturally; on mobile this is the right behaviour.
    $$('.draft-tile').forEach(tile => {
      tile.addEventListener('click', () => {
        const name = tile.querySelector('.draft-tile__name')?.textContent?.trim() || 'this draft';
        const href = tile.dataset.href;
        if (href) {
          window.location.href = href;
          return;
        }
        toast(`"${name}" — coming soon. We're building each flow deeply.`, 'info', 3000);
      });
    });

    // Drafting search — filter tiles by name + statute-hint substring.
    // Lightweight (no fuzzy match yet), runs on every keyup. At 10 tiles
    // this is instant; revisit if the list grows past ~40 tiles.
    const searchInput = document.getElementById('draft-search-input');
    const searchClear = document.getElementById('draft-search-clear');
    const draftEmpty = document.getElementById('draft-empty');
    const draftGrid = document.getElementById('draft-grid');

    function applyDraftFilter(q) {
      const needle = (q || '').toLowerCase().trim();
      let visible = 0;
      $$('.draft-tile').forEach(tile => {
        const name = (tile.querySelector('.draft-tile__name')?.textContent || '').toLowerCase();
        const sub  = (tile.querySelector('.draft-tile__sub')?.textContent  || '').toLowerCase();
        const matches = !needle || name.includes(needle) || sub.includes(needle);
        tile.dataset.hidden = matches ? 'false' : 'true';
        if (matches) visible++;
      });
      if (draftEmpty) draftEmpty.hidden = visible !== 0;
      if (draftGrid)  draftGrid.hidden = visible === 0;
      if (searchClear) searchClear.hidden = !needle;
    }

    if (searchInput) {
      searchInput.addEventListener('input', e => applyDraftFilter(e.target.value));
      // Escape clears (faster than reaching for the × button)
      searchInput.addEventListener('keydown', e => {
        if (e.key === 'Escape' && searchInput.value) {
          searchInput.value = '';
          applyDraftFilter('');
          e.preventDefault();
        }
      });
    }
    if (searchClear) {
      searchClear.addEventListener('click', () => {
        searchInput.value = '';
        applyDraftFilter('');
        searchInput.focus();
      });
    }

    // Mode + style chips
    $$('.composer__chips .chip[data-mode]').forEach(c => {
      c.addEventListener('click', () => setMode(c.dataset.mode));
    });
    $$('.composer__chips .chip[data-style]').forEach(c => {
      c.addEventListener('click', () => setStyle(c.dataset.style));
    });

    // Submit handlers
    $('#submit-btn').addEventListener('click', submitResearch);
    $('#situation-input').addEventListener('input', updateModeDisplay);
    $('#situation-input').addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submitResearch();
    });

    $('#browse-submit').addEventListener('click', submitBrowse);
    $('#browse-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submitBrowse();
    });
  }

  function boot() {
    attachEvents();
    wireMobileChrome();
    renderHistory();
    updateModeDisplay();
    setMode('hidden');
    setStyle('practitioner');
    // Auth auto-inits on every page that loads auth.js (see the IIFE at
    // the bottom of static/auth.js). This call is kept as a no-op safety
    // net for old browser caches that haven't picked up the new auth.js yet.
    if (typeof initAuth === 'function' && !window.__headnote_auth_booted) {
      window.__headnote_auth_booted = true;
      initAuth();
    }

    // Re-render any per-user UI (history list, drafts, chat threads)
    // whenever the user signs in / out / switches accounts. Until this
    // hook existed, history stayed showing the previous user's queries.
    if (window.headnoteAuth && typeof window.headnoteAuth.onAuthChange === 'function') {
      window.headnoteAuth.onAuthChange(() => {
        renderHistory();
        loadUserState();
      });
    }

    // Load user state (plan + usage) after auth resolves. We poll briefly
    // because initAuth is async and we don't want to race with the JWT.
    setTimeout(loadUserState, 1500);

    // Post-payment celebration. Flag set by /payment-success.html on
    // successful upgrade. Fires once, then is cleared. Doesn't depend
    // on /api/me — works even if the meter is briefly stale.
    showUpgradeCelebrationIfPending();
  }

  // Show a one-time celebration toast when the user has just completed a
  // payment. The flag is set by static/payment-success.html via localStorage.
  // We clear it immediately so it never fires twice.
  function showUpgradeCelebrationIfPending() {
    let raw = null;
    try { raw = localStorage.getItem('headnote.justUpgraded'); } catch {}
    if (!raw) return;
    try { localStorage.removeItem('headnote.justUpgraded'); } catch {}
    let data; try { data = JSON.parse(raw); } catch { return; }
    if (!data || !data.plan) return;
    // Stale flags (>10 min old) are ignored.
    if (data.at && Date.now() - data.at > 10 * 60 * 1000) return;

    const planName = data.display_name || (data.plan[0].toUpperCase() + data.plan.slice(1));
    const banner = document.createElement('div');
    banner.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);background:linear-gradient(135deg,#0c0c0a,#2a221a);color:#fdfcf9;padding:14px 22px;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,0.25);z-index:9999;display:flex;gap:14px;align-items:center;font-family:Geist,Inter,system-ui,sans-serif;border:1px solid #c9a96e;animation:upBan 0.4s cubic-bezier(0.16,1,0.3,1)';
    banner.innerHTML = `
      <style>@keyframes upBan { from { transform:translateX(-50%) translateY(-20px); opacity:0 } to { transform:translateX(-50%) translateY(0); opacity:1 } }</style>
      <div style="width:32px;height:32px;border-radius:50%;background:#c9a96e;color:#0c0c0a;font-size:18px;display:grid;place-items:center;font-weight:700">✓</div>
      <div>
        <div style="font-size:14px;font-weight:600;letter-spacing:-0.01em;">You're now on the <span style="color:#c9a96e">${planName}</span> plan</div>
        <div style="font-size:12px;color:#b8b0a4;margin-top:2px;">Every feature unlocked — start drafting</div>
      </div>
      <button onclick="this.parentElement.remove()" style="background:transparent;border:none;color:#8a857a;font-size:18px;cursor:pointer;padding:0 4px">×</button>
    `;
    document.body.appendChild(banner);
    setTimeout(() => { if (banner.parentElement) banner.remove(); }, 8000);
    // Refresh /api/me so the sidebar plan card immediately shows the new plan.
    setTimeout(loadUserState, 600);
  }

  // ------------------------------------------------------------- /api/me state
  let userState = null;

  async function loadUserState() {
    if (!window.headnoteAuth) return;
    try {
      const token = await window.headnoteAuth.getAccessToken();
      if (!token) return;  // not signed in yet
      const r = await fetch('/api/me', { headers: { 'Authorization': `Bearer ${token}` } });
      if (!r.ok) return;
      userState = await r.json();
      renderPlanBadge();
      renderPlanCard();   // sidebar upgrade card
      renderUsageBar();
    } catch (e) { /* silent */ }
  }

  // Sidebar plan-card: morphs based on current plan.
  // - demo  → "Demo · Upgrade for unlimited" → /pricing
  // - paid  → "Monthly · Manage" → /pricing (where they can cancel/upgrade)
  // - founder → "Founder · Unlimited access" — no upgrade button
  function renderPlanCard() {
    if (!userState) return;
    const card  = document.getElementById('sidebar-plan-card');
    const label = document.getElementById('sidebar-plan-label');
    const sub   = document.getElementById('sidebar-plan-sub');
    const arrow = document.getElementById('sidebar-plan-arrow');
    if (!card || !label || !sub) return;

    const s = userState.subscription || {};
    const plan = s.plan || 'demo';
    const display = s.display_name || 'Demo';
    card.style.display = 'block';

    if (plan === 'founder') {
      label.textContent = 'Founder · ∞';
      sub.textContent = 'Unlimited access — thank you for building with us';
      arrow.style.display = 'none';
      card.href = '#';
      card.style.cursor = 'default';
      card.onclick = (e) => e.preventDefault();
    } else if (plan === 'demo') {
      label.textContent = 'Demo plan';
      sub.textContent = 'Upgrade for unlimited drafts & research →';
      arrow.style.display = '';
      card.href = '/pricing';
    } else {
      // weekly / monthly / yearly
      label.textContent = display + ' active';
      const ends = s.period_end ? new Date(s.period_end).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' }) : '';
      sub.textContent = ends ? ('Active until ' + ends + ' · Manage →') : 'Manage subscription →';
      arrow.style.display = '';
      card.href = '/pricing';
    }
  }

  function renderPlanBadge() {
    if (!userState) return;
    let el = document.getElementById('plan-badge');
    const sub = userState.subscription || {};
    const label = sub.display_name || 'Demo';
    if (!el) {
      const sidebar = document.querySelector('.sidebar') || document.body;
      el = ce('div', { attrs: { id: 'plan-badge' }, cls: 'plan-badge' });
      sidebar.appendChild(el);
    }
    el.innerHTML = `<span class="plan-badge__label">${esc(label)}</span>
                    <a href="/pricing" class="plan-badge__upgrade">upgrade →</a>`;
    if (sub.plan === 'yearly' || sub.plan === 'founder') el.querySelector('.plan-badge__upgrade').style.display = 'none';
  }

  function renderUsageBar() {
    if (!userState) return;
    const limits = userState.limits || {};
    const ds = limits.deep_search || {};
    const dr = limits.draft || {};
    let el = document.getElementById('usage-bar');
    if (!el) {
      const sidebar = document.querySelector('.sidebar') || document.body;
      el = ce('div', { attrs: { id: 'usage-bar' }, cls: 'usage-bar' });
      sidebar.appendChild(el);
    }
    const fmt = (m) => {
      if (m.limit == null) return `${m.used || 0} used`;
      return `${m.used || 0} / ${m.limit}`;
    };
    el.innerHTML = `
      <div class="usage-row"><span>Deep search</span><span>${fmt(ds)}</span></div>
      <div class="usage-row"><span>Drafts</span><span>${fmt(dr)}</span></div>
    `;
  }

  // ------------------------------------------------------------- upgrade modal
  window.showUpgradeModal = function (detail) {
    detail = detail || {};
    const code = detail.code || 'quota_exceeded';
    const feature = detail.feature || 'this feature';
    const currentPlan = detail.plan || 'Demo';
    const upgradeTo = detail.upgrade_to || 'monthly';
    const message = detail.message || 'Upgrade to continue.';

    // Build the modal once, reuse it after
    let modal = document.getElementById('upgrade-modal');
    if (!modal) {
      modal = ce('div', { attrs: { id: 'upgrade-modal', role: 'dialog', 'aria-modal': 'true' }, cls: 'upgrade-modal' });
      modal.innerHTML = `
        <div class="upgrade-modal__backdrop" data-close="1"></div>
        <div class="upgrade-modal__card">
          <button class="upgrade-modal__close" data-close="1" aria-label="Close">×</button>
          <div class="upgrade-modal__icon">⚡</div>
          <h2 class="upgrade-modal__title"></h2>
          <p class="upgrade-modal__msg"></p>
          <div class="upgrade-modal__plan"></div>
          <a class="upgrade-modal__cta" href="/pricing">See all plans →</a>
        </div>
      `;
      document.body.appendChild(modal);
      modal.addEventListener('click', (e) => {
        if (e.target.dataset.close) modal.classList.remove('is-open');
      });
    }
    const title = code === 'feature_locked'
      ? 'Unlock this feature'
      : `You've hit your limit`;
    const planCopy = ({
      weekly:  { name: 'Weekly Trial', price: '₹120', tag: '7-day trial' },
      monthly: { name: 'Monthly',     price: '₹499/mo', tag: 'Most popular' },
      yearly:  { name: 'Yearly',       price: '₹4,999/yr', tag: 'Best value' },
    })[upgradeTo] || { name: 'Pro', price: '', tag: '' };

    modal.querySelector('.upgrade-modal__title').textContent = title;
    modal.querySelector('.upgrade-modal__msg').textContent = message;
    modal.querySelector('.upgrade-modal__plan').innerHTML = `
      <div class="upgrade-modal__plan-name">${esc(planCopy.name)} <span>${esc(planCopy.tag)}</span></div>
      <div class="upgrade-modal__plan-price">${esc(planCopy.price)}</div>
    `;
    modal.classList.add('is-open');
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
