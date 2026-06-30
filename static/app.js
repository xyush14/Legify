/* =============================================================================
 * Headnote app · vanilla JS, no framework
 *
 * One file, three views: Research, Browse, Drafting (placeholder).
 *
 * Research auto-detects the user's intent from the input:
 *   - >1800 chars + paragraph breaks  → Headnote (Cri.L.J. format generation)
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
      return 'the server took too long to respond. this can happen when the AI provider is under heavy load. please retry — the second attempt is usually much faster (cached prompts).';
    }
    if (status === 503) {
      // The backend returns specific actionable messages for 503 (Bedrock
      // marketplace, no Anthropic credits, rate limit, Bedrock model
      // misconfig, etc.). Surface them instead of a generic message — the
      // lawyer can act on "AWS Bedrock isn't ready yet — go to AWS
      // Console..." but not on "backend dependency is down".
      if (errText && errText.trim()) return errText;
      return 'a backend dependency is down (likely IK token / anthropic key not set). check the server config.';
    }
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
  async function patchJson(path, body) {
    const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) };
    const r = await fetch(path, { method: 'PATCH', headers, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (handleEntitlementError(r.status, data)) {
      throw new Error((data.detail && data.detail.message) || 'upgrade required');
    }
    if (!r.ok) throw new Error(friendlyError(r.status, data.error || (data.detail && data.detail.message)));
    return data;
  }
  async function delJson(path) {
    const headers = await authHeaders();
    const r = await fetch(path, { method: 'DELETE', headers });
    const data = await r.json().catch(() => ({}));
    if (handleEntitlementError(r.status, data)) {
      throw new Error((data.detail && data.detail.message) || 'upgrade required');
    }
    if (!r.ok) throw new Error(friendlyError(r.status, data.error || (data.detail && data.detail.message)));
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
    // Lazy-render the saved-case-law library on entry (always re-fetch so it
    // reflects saves/unsaves made in the research view this session).
    if (view === 'saved') renderSavedView();
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
    // Everything else is a situation → ranked precedents. Short queries are
    // treated as a situation too (no separate "digest" mode).
    return 'situation';
  }

  function describeMode(intent) {
    if (intent === 'headnote') return 'detected: long judgment text → cri.l.j. headnote';
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

  // -------------------------------------------------------------- saved case-law
  // A lawyer's personal library of kept research hits. Unlike chat history
  // (localStorage-only), saved cases live server-side in Supabase so they
  // follow the account across devices. We snapshot the FULL case object on
  // save, so each card re-renders identically here with zero LLM cost.
  //
  // savedIds mirrors the server set so every result card can show the right
  // ☆/★ toggle state synchronously. It's loaded on boot + on auth change, and
  // kept in sync on every save/unsave.
  const savedIds = new Set();

  async function loadSavedIds() {
    try {
      const data = await getJson('/api/saved-caselaw');
      savedIds.clear();
      (data.items || []).forEach(it => it.case_id && savedIds.add(it.case_id));
    } catch (e) {
      // Not signed in / offline — leave the set empty. onAuthChange retries.
      savedIds.clear();
    }
    refreshSaveButtons();
  }

  function isSaved(caseId) { return !!caseId && savedIds.has(caseId); }
  function saveBtnLabel(saved) { return saved ? '★ saved' : '☆ save'; }

  // Re-sync every save button currently in the DOM (research cards + saved view)
  // to the live savedIds set.
  function refreshSaveButtons() {
    $$('.case-save-btn[data-case-id]').forEach(btn => {
      const saved = isSaved(btn.dataset.caseId);
      btn.classList.toggle('is-saved', saved);
      btn.textContent = saveBtnLabel(saved);
    });
  }

  function isSignedIn() {
    return !!(window.headnoteAuth && window.headnoteAuth.userId && window.headnoteAuth.userId());
  }

  // Save / unsave one case. `raw` is the original (un-normalised) case object
  // from the API response — we store it verbatim so the snapshot re-renders
  // through the same normaliseCase() path.
  async function toggleSave(raw, btn) {
    const caseId = (raw && raw.case_id) || '';
    if (!caseId) { toast('cannot save — this result has no stable id', 'error'); return; }
    if (!isSignedIn()) { toast('sign in to save case-law', 'error', 3200); return; }

    const wasSaved = isSaved(caseId);
    btn.disabled = true;
    try {
      if (wasSaved) {
        await delJson('/api/saved-caselaw/' + encodeURIComponent(caseId));
        savedIds.delete(caseId);
        toast('removed from saved', 'info');
      } else {
        await post('/api/saved-caselaw', {
          case_id: caseId,
          case_json: raw,
          source_query: (state.lastResult && state.lastResult.query) || '',
        });
        savedIds.add(caseId);
        toast('saved to your library', 'success');
      }
    } catch (e) {
      toast('could not update saved: ' + (e.message || 'unknown'), 'error', 4000);
    } finally {
      btn.disabled = false;
      refreshSaveButtons();
      // If the user just unsaved from within the library, drop the card.
      if (state.activeView === 'saved' && wasSaved) renderSavedView();
    }
  }

  // Build the save toggle for a card's badge row.
  function buildSaveButton(raw, caseId) {
    const saved = isSaved(caseId);
    const btn = ce('button', {
      cls: 'btn--ghost case-save-btn' + (saved ? ' is-saved' : ''),
      text: saveBtnLabel(saved),
      attrs: { type: 'button', 'data-case-id': caseId || '', title: 'Save this case to your library' },
    });
    btn.addEventListener('click', () => toggleSave(raw, btn));
    return btn;
  }

  // ---- Saved view (the library) ----
  async function renderSavedView() {
    const target = $('#saved-results');
    if (!target) return;
    target.innerHTML = '';
    target.appendChild(ce('div', { cls: 'saved-loading mono', text: 'loading your saved case-law…' }));

    if (!isSignedIn()) {
      target.innerHTML = '';
      target.appendChild(ce('div', { cls: 'empty', children: [
        ce('h2', { text: 'sign in to see your saved case-law' }),
        ce('p', { text: 'saved precedents follow your account across devices.' }),
      ]}));
      return;
    }

    let items = [];
    try {
      const data = await getJson('/api/saved-caselaw');
      items = data.items || [];
      // Keep the toggle-state set authoritative with what the server returned.
      savedIds.clear();
      items.forEach(it => it.case_id && savedIds.add(it.case_id));
    } catch (e) {
      target.innerHTML = '';
      target.appendChild(ce('div', { cls: 'empty', children: [
        ce('h2', { text: 'could not load saved case-law' }),
        ce('p', { text: (e.message || 'please try again in a moment.') }),
      ]}));
      return;
    }

    target.innerHTML = '';
    if (!items.length) {
      target.appendChild(ce('div', { cls: 'empty', children: [
        ce('h2', { text: 'no saved case-law yet' }),
        ce('p', { text: 'run a research query, then hit ☆ save on any result worth keeping — it lands here, exactly as found.' }),
      ]}));
      return;
    }

    const header = ce('div', { cls: 'results-header' });
    header.appendChild(ce('div', { cls: 'results-header__count mono',
      text: items.length + (items.length === 1 ? ' saved case' : ' saved cases') }));
    target.appendChild(header);
    items.forEach((it, i) => target.appendChild(renderSavedCard(it, i)));
  }

  function renderSavedCard(item, idx) {
    const wrap = ce('div', { cls: 'saved-card' });
    // The exact research card, re-rendered from the stored snapshot. Its own
    // save button shows ★ saved and unsaving it removes it from the library.
    wrap.appendChild(renderCaseCard(item.case_json || {}, idx));
    // The situation it was saved from — reminds the lawyer why they kept it.
    if (item.source_query) {
      wrap.appendChild(ce('div', { cls: 'saved-card__context mono',
        text: 'saved from: ' + item.source_query }));
    }
    wrap.appendChild(renderNoteEditor(item));
    return wrap;
  }

  // Per-case personal note, edited inline and persisted via PATCH.
  function renderNoteEditor(item) {
    const box = ce('div', { cls: 'saved-note' });
    box.appendChild(ce('div', { cls: 'saved-note__label mono', text: 'your note' }));
    const ta = ce('textarea', { cls: 'saved-note__input', attrs: {
      rows: '2', placeholder: 'why this matters — e.g. "use for the bail argument, para 14"',
    }});
    ta.value = item.note || '';
    const saveBtn = ce('button', { cls: 'btn--ghost saved-note__save', text: 'save note' });
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'saving…';
      try {
        await patchJson('/api/saved-caselaw/' + encodeURIComponent(item.case_id), { note: ta.value });
        item.note = ta.value.trim();
        saveBtn.textContent = 'saved ✓';
      } catch (e) {
        saveBtn.textContent = 'save note';
        toast('could not save note: ' + (e.message || 'unknown'), 'error');
      } finally {
        saveBtn.disabled = false;
      }
    });
    // Reset the confirmation label once the user edits again.
    ta.addEventListener('input', () => { saveBtn.textContent = 'save note'; });
    box.appendChild(ta);
    box.appendChild(saveBtn);
    return box;
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
    const md = c.match_dimensions || {};
    // Internal viewer URL — for HF cases, every card gets a real link
    // to our in-app /case/<doc_id> viewer (replaces the broken
    // "Search Indian Kanoon" fallback). IK cases keep their existing
    // kanoon_url; curated cases also get the viewer.
    const cid = c.case_id || '';
    const internalUrl = cid ? '/case/' + encodeURIComponent(cid) : null;
    return {
      // identifiers
      case_id: cid,
      title: c.title || c.case_title || c.case_id || 'untitled',
      // Prefer the court-accepted neutral/SCR citation when we matched this
      // case to our official Supreme Court corpus.
      citation: c.official_citation || c.citation || '',
      court: c.court || '',
      year: c.year || '',
      bench: c.bench || jh.per_judge_attribution || '',
      // deep-links / provenance
      kanoon_url: c.kanoon_url,
      kanoon_paragraph_url: c.kanoon_paragraph_url,
      kanoon_doc_id: c.kanoon_doc_id,
      internal_url: internalUrl,                  // NEW — /case/<doc_id>
      // Official Supreme Court open-data copy, cross-resolved from the IK hit.
      official_doc_id: c.official_doc_id || '',
      official_pdf_url: c.official_pdf_url || (c.official_doc_id ? '/api/judgment/pdf/' + c.official_doc_id : ''),
      official_citation: c.official_citation || '',
      is_official_copy: !!c.is_official_copy,
      // "Reported in" — every reporter this judgment appears in (SCC/AIR/…),
      // plus the free court-issued neutral citation (shown apart from the
      // paid reporters). Parsed from IK; falls back to nothing when unreported.
      citations_all: Array.isArray(c.citations_all) ? c.citations_all : [],
      neutral_citation: c.neutral_citation || c.official_citation || '',
      fame_indicator: c.fame_indicator,
      source: c.source,
      source_language: c.source_language || (c.source && String(c.source).startsWith('hf') ? null : 'en'),
      // body — NEW schema (stinger + held_line + court_quote)
      stinger_sentence: c.stinger_sentence || '',
      held_line: c.held_line || c.holding || jh.ratio || pn.gist || c.ratio || '',
      court_quote: c.court_quote || pn.quotable_phrase || c.quotable_phrase || '',
      negative_carve_out: c.negative_carve_out || jh.negative_carve_out || '',
      // match precision (4 dimensions)
      match_dimensions: {
        statute_match:  md.statute_match  || '',
        doctrine_match: md.doctrine_match || '',
        fact_match:     md.fact_match     || '',
        outcome_match:  md.outcome_match  || '',
      },
      // Legacy fields kept for back-compat during transition
      fact_match: c.relevance_explanation || c.fact_match || pn.one_line_topic || '',
      one_line_topic: pn.one_line_topic || '',
      ratio: jh.ratio || pn.gist || c.ratio || c.holding || '',
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
  // A citation is "neutral" (free, court-issued) rather than a paid reporter
  // when it carries the SC/HC neutral form or the official S.C.R. report:
  //   2022 INSC 690 · [2024] 10 S.C.R. 108 · 2023:MPHC-JBP:18421
  function isNeutralCite(s) {
    // INSC has no word boundary in the compact official form "2008INSC1281",
    // so match it bare — no paid reporter name contains "INSC".
    return /INSC/i.test(s)
        || /\bS\.?\s*C\.?\s*R\.?\b/i.test(s)
        || /^\s*\[?\d{4}\]?\s*:/.test(s);   // HC neutral form YYYY:COURT:NUMBER
  }
  // Real SC judgments are reported in 50+ places — SCC and AIR alongside dozens
  // of obscure regional reporters (KER LT, ORISSA LR, MAH LJ …). A lawyer only
  // ever cites the recognised national reporters, so rank those to the front
  // and collapse the rest behind a "+N more". Lower rank = shown first; 90 = the
  // regional long tail that stays hidden until expanded.
  function reporterRank(s) {
    if (/SCC\s*OnLine/i.test(s)) return 2;
    if (/SCC\s*\(?\s*CRI/i.test(s)) return 7;
    if (/\bSCC\b/i.test(s)) return 1;
    if (/\bAIR\b.*\bSCW\b/i.test(s)) return 5;
    if (/\bAIR\b.*SC\s*\(\s*CRI/i.test(s)) return 6;
    if (/\bAIR\b.*(SUPREME\s+COURT|\bSC\b)/i.test(s)) return 3;
    if (/\bAIR\b/i.test(s)) return 4;                              // AIR <State> — HC cases
    if (/CRI\.?\s*L\.?\s*J\.?|CRILJ|CRI\s+LJ/i.test(s)) return 8;
    if (/\bSCALE\b/i.test(s)) return 9;
    if (/\bJT\b/i.test(s)) return 10;
    return 90;
  }
  // Builds the "Reported in" row: the reporters a lawyer pastes into a pleading,
  // recognised national reporters first (primary highlighted), the free neutral
  // citation greyed apart, the regional long tail collapsed behind "+N more",
  // and a copy button for the clean citeable string. Returns null when the
  // judgment is unreported so the row simply doesn't appear (unchanged card).
  function buildReportedRow(c) {
    const seen = new Set();
    const all = [];
    (c.citations_all || []).forEach(s => {
      const v = String(s || '').trim();
      if (v && !seen.has(v)) { seen.add(v); all.push(v); }
    });
    const neutral = String(c.neutral_citation || '').trim();
    if (neutral && !seen.has(neutral)) { seen.add(neutral); all.push(neutral); }
    if (!all.length) return null;

    const primary = String(c.citation || '').trim();
    const neutrals  = all.filter(isNeutralCite);
    let   reporters = all.filter(s => !isNeutralCite(s));
    // Rank: the card's own primary citation always leads, then recognised
    // national reporters, then the regional tail (stable within each rank).
    reporters = reporters
      .map((s, i) => ({ s, i, r: (s === primary ? 0 : reporterRank(s)) }))
      .sort((a, b) => (a.r - b.r) || (a.i - b.i))
      .map(o => o.s);

    const MAJOR_CAP = 5;
    const major = reporters.filter(s => s === primary || reporterRank(s) < 90).slice(0, MAJOR_CAP);
    const extra = reporters.filter(s => !major.includes(s));
    // The clean string a lawyer pastes — recognised reporters + neutral.
    const copyStr = major.concat(neutrals).join(' : ');

    const cites = ce('div', { cls: 'cites' });
    let shown = 0;
    const addChip = (s, isPrimary) => {
      if (shown > 0) cites.appendChild(ce('span', { cls: 'cite-sep', text: ':' }));
      let cls = 'cite';
      if (isNeutralCite(s)) cls += ' cite--neutral';
      else if (isPrimary) cls += ' cite--primary';
      cites.appendChild(ce('span', { cls, text: s }));
      shown++;
    };
    major.forEach(s => addChip(s, s === primary || (!primary && s === major[0])));

    // "+N more" — reveals the regional reporters inline, then removes itself.
    if (extra.length) {
      const moreBtn = ce('button', {
        cls: 'cite-more', text: '+' + extra.length + ' more',
        attrs: { type: 'button', title: 'Show all reporters' },
      });
      moreBtn.addEventListener('click', () => {
        const sep = document.createDocumentFragment();
        extra.forEach(s => {
          sep.appendChild(ce('span', { cls: 'cite-sep', text: ':' }));
          sep.appendChild(ce('span', { cls: 'cite cite--minor', text: s }));
        });
        cites.insertBefore(sep, moreBtn);
        moreBtn.remove();
      });
      cites.appendChild(moreBtn);
    }

    // Neutral citation(s) trail, greyed apart from the paid reporters.
    neutrals.forEach(s => addChip(s, false));

    const copyBtn = ce('button', {
      cls: 'cite-copy', text: '⧉ copy',
      attrs: { type: 'button', title: 'Copy citation' },
    });
    copyBtn.addEventListener('click', () => {
      const done = () => {
        copyBtn.textContent = '✓ copied';
        copyBtn.classList.add('copied');
        setTimeout(() => { copyBtn.textContent = '⧉ copy'; copyBtn.classList.remove('copied'); }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(copyStr).then(done).catch(done);
      } else { done(); }
    });
    cites.appendChild(copyBtn);

    return ce('div', { cls: 'case-card__row case-card__row--reported', children: [
      ce('div', { cls: 'case-card__rowlabel', text: 'reported in' }),
      cites,
    ]});
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
    // Title link priority:
    //   1. IK pool-verified URL — opens authoritative judgment on IK
    //   2. Internal viewer /case/<doc_id> — for HF + curated cases
    //   3. Plain text (no link) if neither available
    if (c.kanoon_url) {
      titleEl.appendChild(ce('a', { text: c.title, attrs: { href: c.kanoon_url, target: '_blank', rel: 'noopener' } }));
      titleEl.appendChild(ce('span', { cls: 'ext-arrow', text: '↗' }));
    } else if (c.internal_url) {
      titleEl.appendChild(ce('a', { text: c.title, attrs: { href: c.internal_url, target: '_blank', rel: 'noopener', title: 'Read full judgment' } }));
      titleEl.appendChild(ce('span', { cls: 'ext-arrow', text: '→' }));
    } else {
      titleEl.appendChild(document.createTextNode(c.title || ''));
    }
    head.appendChild(titleEl);
    head.appendChild(ce('div', { cls: 'case-card__meta mono', text: `#${idx + 1}` }));

    // Meta line: court · year · bench · citation. When the full "Reported in"
    // row will render below, drop the single citation here so it isn't shown
    // twice.
    const hasReportedRow = (c.citations_all && c.citations_all.length) || c.neutral_citation;
    const metaLine = ce('div', { cls: 'case-card__meta mono' });
    metaBits(c).forEach(b => metaLine.appendChild(ce('span', { text: b })));
    if (c.citation && !hasReportedRow) metaLine.appendChild(ce('span', { text: c.citation }));

    // Catchword chain (journal style only) — shows above the body
    const preBody = [];
    if (c.statute_index) {
      preBody.push(ce('div', { cls: 'headnote-block__catchwords', text: c.statute_index }));
    }
    if (c.catchword_chain) {
      preBody.push(ce('div', { cls: 'headnote-block__catchwords', text: c.catchword_chain }));
    }

    const rows = [];

    // NEW ORDER (mirrors Cri.L.J. + the lawyer's 10-second triage):
    //   1. Stinger sentence   — "Why this helps your matter" (lawyer voice)
    //   2. HELD line          — binding ratio, paste-ready into petition
    //   3. Court quote        — verbatim ≤30 words, visually distinct
    //   4. Match precision    — 4-line ✓⚠✗ confirmation grid
    //   5. Negative carve-out — what the case does NOT decide
    //   6. BNS mapping        — IPC↔BNS reference for advocate
    //   7. Cross-refs         — related cases (low priority, last)

    // 1. Stinger — single sentence, headline tint
    const stingerText = c.stinger_sentence || c.fact_match;
    if (stingerText) {
      rows.push(ce('div', { cls: 'case-card__row case-card__row--factmatch', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'why' }),
        ce('div', { cls: 'case-card__rowtext', text: stingerText }),
      ]}));
    }

    // 2. HELD line — binding rule, with paragraph anchor appended
    // (Cri.L.J. convention: "HELD — [rule]. (Paras 14, 16-17)"). Showing the
    // anchor here guarantees the lawyer always sees the citable paragraph,
    // even on cards that have no verbatim quote.
    if (c.held_line || c.ratio) {
      let heldText = c.held_line || c.ratio;
      // Ensure HELD prefix is present for visual recognition
      heldText = /^HELD\s*[—:-]/i.test(heldText) ? heldText : ('HELD — ' + heldText);
      const heldCell = ce('div', { cls: 'case-card__rowtext', text: heldText });
      // Append the paragraph anchor if the quote row won't already show it,
      // or always — the anchor is the holding's citation pointer.
      if (c.paragraph_anchor) {
        heldCell.appendChild(ce('span', { cls: 'mono', text: '  ' + c.paragraph_anchor }));
      }
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'held' }),
        heldCell,
      ]}));
    }

    // 3. Court's words (verbatim) — moneyshot block
    const quoteText = c.court_quote || c.quotable_phrase;
    if (quoteText) {
      const quoteBlock = ce('div', { cls: 'case-card__rowtext' });
      quoteBlock.appendChild(ce('span', { text: '“' + quoteText + '”' }));
      // Anchor + copy button right after quote
      if (c.paragraph_anchor) {
        quoteBlock.appendChild(ce('span', { cls: 'mono', text: '   — ' + c.paragraph_anchor }));
      }
      rows.push(ce('div', { cls: 'case-card__row case-card__row--quote', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'quote' }),
        quoteBlock,
      ]}));
    }

    // 4. Match precision — 4 dimension confirmation lines
    const mdim = c.match_dimensions || {};
    const matchLines = [];
    if (mdim.statute_match)  matchLines.push('· statute  ' + mdim.statute_match);
    if (mdim.doctrine_match) matchLines.push('· doctrine ' + mdim.doctrine_match);
    if (mdim.fact_match)     matchLines.push('· facts    ' + mdim.fact_match);
    if (mdim.outcome_match)  matchLines.push('· outcome  ' + mdim.outcome_match);
    if (matchLines.length) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'match' }),
        ce('div', { cls: 'case-card__rowtext', text: matchLines.join('\n') }),
      ]}));
    }

    // 5. Negative carve-out — what case does NOT decide
    if (c.negative_carve_out) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'carve-out' }),
        ce('div', { cls: 'case-card__rowtext', text: c.negative_carve_out }),
      ]}));
    }

    // 6. BNS / BNSS mapping note (hide if placeholder)
    if (c.bns_note && !/pending|tbd|editorial review/i.test(c.bns_note)) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'bns' }),
        ce('div', { cls: 'case-card__rowtext', text: c.bns_note }),
      ]}));
    }

    // 7. Cross-refs (low priority, last)
    if (c.cross_refs && c.cross_refs.length) {
      rows.push(ce('div', { cls: 'case-card__row', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'cited' }),
        ce('div', { cls: 'case-card__rowtext mono', text: c.cross_refs.join(' · ') }),
      ]}));
    }

    // 8. "Reported in" — the full reporter list a lawyer pastes into a pleading,
    // joined the conventional way with " : ". Paid reporters (SCC/AIR/Cri.L.J./
    // SCALE) lead; the free court-issued neutral citation (INSC / S.C.R. / HC
    // neutral) is shown apart, greyed. One tap copies the whole string.
    const reportedRow = buildReportedRow(c);
    if (reportedRow) rows.push(reportedRow);

    const badges = ce('div', { cls: 'case-card__badges' });
    const ob = outcomeBadge(c); if (ob) badges.appendChild(ob);
    const fb = fameBadge(c);    if (fb) badges.appendChild(fb);
    badges.appendChild(verifiedBadge());
    // Official Supreme Court copy badge — this case was matched to our
    // court-accepted open-data corpus (neutral citation + signed PDF).
    if (c.is_official_copy) {
      badges.appendChild(ce('span', { cls: 'badge badge--official', text: '⚖ official SC copy' }));
    }
    const j = judgmentLink(c);  if (j) badges.appendChild(j);
    // Link to the official signed judgment copy, embedded in our in-app viewer.
    if (c.official_doc_id) {
      badges.appendChild(ce('a', {
        cls: 'judgment-link judgment-link--official',
        text: (c.official_citation ? c.official_citation + ' — ' : '') + 'official copy (PDF) ⚖',
        attrs: {
          href: '/case/' + encodeURIComponent(c.official_doc_id),
          target: '_blank', rel: 'noopener',
          title: 'Official Supreme Court judgment copy — court-accepted neutral citation',
        },
      }));
    }

    // Save / unsave to the lawyer's personal library (persists server-side).
    // We pass the original `raw` so the full situation-specific snapshot is
    // what gets stored and later re-rendered.
    badges.appendChild(buildSaveButton(raw, c.case_id));

    // Hindi toggle button (per-card back-translation of ratio + quote)
    const hindiBtn = ce('button', { cls: 'btn--ghost', text: 'हिंदी में दिखाएँ' });
    hindiBtn.addEventListener('click', () => toggleCardHindi(hindiBtn, c, rows));
    badges.appendChild(hindiBtn);

    return ce('div', { cls: 'case-card', children: [head, metaLine, ...preBody, ...rows, badges] });
  }

  // ---- Per-card Hindi back-translation (lazy) ----
  const hindiCache = new Map();   // case_id -> translation payload
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
      // CRITICAL RULE: verbatim court quotes are NEVER translated. If the
      // source is English, the quote stays in English in quotation marks.
      // If we translated it to Hindi, the lawyer might cite a Hindi line
      // that doesn't exist in the actual judgment — court-citation risk.
      // Only the EXPLANATORY layer (stinger, held_line, fact_match) is
      // translatable.
      let cached = hindiCache.get(cid);
      if (!cached) {
        const payload = {
          stinger:   c.stinger_sentence || '',
          held_line: c.held_line || '',
          ratio:     c.ratio || '',
          fact_match: c.fact_match || '',
          // INTENTIONALLY excluded:
          //   - quotable_phrase / court_quote — must stay verbatim
          //   - negative_carve_out — translate it OK, but keep English fallback
          carve_out: c.negative_carve_out || '',
        };
        const resp = await post('/api/translate', { payload });
        cached = resp.result || {};
        hindiCache.set(cid, cached);
      }
      // Mutate the displayed rows to show Hindi — but NEVER touch the quote row
      rows.forEach(row => {
        const labelEl = row.querySelector('.case-card__rowlabel');
        const textEl  = row.querySelector('.case-card__rowtext');
        if (!labelEl || !textEl) return;
        const label = labelEl.textContent;
        if (label === 'why' && (cached.stinger || cached.fact_match)) {
          textEl.textContent = cached.stinger || cached.fact_match;
        }
        else if (label === 'held' && (cached.held_line || cached.ratio)) {
          textEl.textContent = cached.held_line || cached.ratio;
        }
        else if (label === 'carve-out' && cached.carve_out) {
          textEl.textContent = cached.carve_out;
        }
        // 'quote' row intentionally skipped — verbatim never translated
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

  // Tier-1 of progressive research: paint REAL retrieved cases the moment
  // retrieval finishes — provisional "why" + the "Reported in" citations —
  // while the analysis (held/quote/match) streams in. Replaced wholesale by
  // renderResearchResult() once the final result arrives.
  function renderShellCards(shells, target, stagePanel) {
    if (!shells || !shells.length) return;
    target.innerHTML = '';
    if (stagePanel) advanceStage(stagePanel, 2, true);   // "searching" done → "preparing"
    target.appendChild(ce('div', { cls: 'researching', children: [
      ce('div', { cls: 'researching__label', text: 'found ' + shells.length + ' cases' }),
      ce('div', { cls: 'researching__line', children: [
        ce('div', { cls: 'researching__text', text: 'writing analysis…' }),
      ]}),
    ]}));
    const list = ce('div', { cls: 'results' });
    shells.forEach((s, i) => list.appendChild(renderShellCard(s, i)));
    target.appendChild(list);
  }

  function renderShellCard(s, idx) {
    const head = ce('div', { cls: 'case-card__head', children: [
      ce('div', { cls: 'case-card__title', text: s.title || 'untitled' }),
      ce('div', { cls: 'case-card__meta mono', text: '#' + (idx + 1) }),
    ]});
    const meta = ce('div', { cls: 'case-card__meta mono' });
    if (s.court) meta.appendChild(ce('span', { text: s.court }));
    if (s.year)  meta.appendChild(ce('span', { text: String(s.year) }));

    const rows = [];
    if (s.why_provisional) {
      rows.push(ce('div', { cls: 'case-card__row case-card__row--factmatch', children: [
        ce('div', { cls: 'case-card__rowlabel', text: 'why' }),
        ce('div', { cls: 'case-card__rowtext', text: s.why_provisional }),
      ]}));
    }
    rows.push(ce('div', { cls: 'case-card__row case-card__row--pending', children: [
      ce('div', { cls: 'case-card__rowlabel', text: 'held' }),
      ce('div', { cls: 'case-card__rowtext', children: [
        ce('span', { cls: 'analyzing', children: [
          ce('span', { cls: 'analyzing__dot' }),
          ce('span', { text: 'writing analysis…' }),
        ]}),
        ce('div', { cls: 'shimmer shimmer--w1' }),
        ce('div', { cls: 'shimmer shimmer--w2' }),
      ]}),
    ]}));

    const card = ce('div', { cls: 'case-card case-card--shell', children: [head, meta, ...rows] });
    const reported = buildReportedRow(s);
    if (reported) card.appendChild(reported);
    const badges = ce('div', { cls: 'case-card__badges', children: [verifiedBadge()] });
    const fb = fameBadge(s); if (fb) badges.appendChild(fb);
    card.appendChild(badges);
    return card;
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
      } else if (c.title) {
        // No pool-verified URL → IK search by title (manual lookup fallback)
        const searchUrl = 'https://indiankanoon.org/search/?formInput=' + encodeURIComponent(c.title);
        titleEl.appendChild(ce('a', { text: c.title, attrs: { href: searchUrl, target: '_blank', rel: 'noopener', title: 'Search Indian Kanoon' } }));
      } else {
        titleEl.appendChild(document.createTextNode(c.title || ''));
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

  // ---- headnote view ----
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
      // Support both flat (legacy) and nested (v2) schema
      const jh = hn.journal_headnote || {};
      const pn = hn.practitioner_notes || {};
      const block = ce('div', { cls: 'headnote-block' });

      if (hn.letter) block.appendChild(ce('span', { cls: 'headnote-block__letter', text: '(' + hn.letter + ')' }));

      // Journal headnote fields
      const statuteIdx = jh.statute_index || hn.statute_index || '';
      const catchwords = jh.catchword_chain || hn.catchwords || '';
      const ratio      = jh.ratio || hn.ratio || '';
      const carveOut   = jh.negative_carve_out || '';
      const paraAnchor = jh.paragraph_anchor || hn.paragraph_anchor || '';

      if (statuteIdx) block.appendChild(ce('div', { cls: 'headnote-block__statute', text: statuteIdx }));
      if (catchwords)  block.appendChild(ce('div', { cls: 'headnote-block__catchwords', text: catchwords }));
      if (ratio)       block.appendChild(ce('div', { cls: 'headnote-block__ratio', text: ratio }));
      if (carveOut)    block.appendChild(ce('div', { cls: 'headnote-block__carveout', text: '⚠ ' + carveOut }));
      if (paraAnchor)  block.appendChild(ce('div', { cls: 'headnote-block__anchor', text: paraAnchor }));

      // Practitioner notes
      const gist        = pn.gist || '';
      const quote       = pn.quotable_phrase || hn.quotable_phrase || '';
      const grounds     = pn.grounds || hn.grounds || [];
      const crossRefs   = pn.cross_refs || hn.cases_referred || [];

      if (gist)  block.appendChild(ce('div', { cls: 'headnote-block__gist', text: gist }));
      if (quote) block.appendChild(ce('div', { cls: 'headnote-block__quote', text: '“' + quote + '”' }));

      // Grounds — the petition-ready argument lines (new field)
      if (grounds.length) {
        const groundsWrap = ce('div', { cls: 'headnote-block__grounds' });
        groundsWrap.appendChild(ce('div', { cls: 'headnote-block__grounds-label', text: 'Grounds to use' }));
        grounds.forEach(g => {
          groundsWrap.appendChild(ce('div', { cls: 'headnote-block__ground', text: g }));
        });
        block.appendChild(groundsWrap);
      }

      if (crossRefs.length) {
        block.appendChild(ce('div', { cls: 'headnote-block__cases',
          text: 'cases referred: ' + crossRefs.join(' · ') }));
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
        // Still offer the personal-assist escape hatch — this is exactly
        // the situation where the lawyer needs us most.
        target.appendChild(renderAssistCta('research', query));
        return;
      }
      target.appendChild(renderResultsHeader(cases.length, true));
      target.appendChild(state.resultView === 'table' ? renderCasesAsTable(cases) : renderCasesAsCards(cases));
      // CTA after every successful research response — even when results
      // look good. Drives the 15-min personal-assist flow.
      target.appendChild(renderAssistCta('research', query));
    } else if (autoMode === 'headnote') {
      target.appendChild(renderHeadnotes(parsed));
      target.appendChild(renderAssistCta('research', query));
    }
  }

  // ---------------------------------------------------------------
  // Personal-assist CTA — the "Not satisfied? our team will help"
  // escape hatch that fires under every research response.
  //
  // Promise: case-law within 15 minutes (research mode) / template
  // uploaded within 2 hours (draft mode — same component, the draft
  // screen instantiates it with mode='draft' via a thin wrapper).
  // ---------------------------------------------------------------
  function renderAssistCta(mode, sourceContext) {
    const cfg = mode === 'draft' ? {
      eyebrow:  'Need a different template?',
      headline: "Tell us — we'll upload it within 2 hours.",
      sub:      "Free for paid users. Drop the template name + a one-line use case. Goes straight to the founder, not a queue.",
      placeholder: "e.g. 'POCSO bail at Sessions Court — need the standard High Court format with parity table'",
      submitLabel: "Send request",
      successMsg:  "Got it — we'll have it live within 2 hours.",
      endpoint: '/api/assist/draft',
    } : {
      eyebrow:  'Not satisfied with this response?',
      headline: "Let our team find the case-law for you, personally.",
      sub:      "We'll WhatsApp / email you three judgments with paragraph anchors within 15 minutes. Just describe what you need.",
      placeholder: "e.g. 'High Court bail under 304B IPC — co-accused already granted, parity ground'",
      submitLabel: "Get personal help",
      successMsg:  "Got it — our team will reach out within 15 minutes.",
      endpoint: '/api/assist/research',
    };

    const wrap = ce('div', { cls: 'assist-cta' });

    const head = ce('div', { cls: 'assist-cta__head' });
    head.appendChild(ce('div', { cls: 'assist-cta__eyebrow', text: cfg.eyebrow }));
    head.appendChild(ce('div', { cls: 'assist-cta__title',   text: cfg.headline }));
    head.appendChild(ce('div', { cls: 'assist-cta__sub',     text: cfg.sub }));
    wrap.appendChild(head);

    // Inline form (no modal — modals on mobile hide the keyboard handoff)
    const form = ce('div', { cls: 'assist-cta__form' });
    const ta = document.createElement('textarea');
    ta.className = 'assist-cta__input';
    ta.placeholder = cfg.placeholder;
    ta.rows = 3;
    form.appendChild(ta);

    const row = ce('div', { cls: 'assist-cta__row' });
    const sla = ce('span', { cls: 'assist-cta__sla',
      text: mode === 'draft' ? '⏱ 2-hour SLA · permanent upload' : '⏱ 15-minute SLA · WhatsApp + email' });
    const btn = document.createElement('button');
    btn.className = 'assist-cta__submit';
    btn.textContent = cfg.submitLabel;
    btn.addEventListener('click', async () => {
      const q = ta.value.trim();
      if (q.length < 3) { toast('Add a few words first', 'error'); ta.focus(); return; }
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = 'Sending…';
      try {
        await post(cfg.endpoint, { query: q, source_context: sourceContext || '' });
        wrap.classList.add('assist-cta--sent');
        wrap.innerHTML = '';
        const done = ce('div', { cls: 'assist-cta__done' });
        done.appendChild(ce('div', { cls: 'assist-cta__done-icon', text: '✓' }));
        done.appendChild(ce('div', { cls: 'assist-cta__done-msg', text: cfg.successMsg }));
        wrap.appendChild(done);
      } catch (e) {
        btn.disabled = false;
        btn.textContent = prev;
        toast('Could not send — ' + (e.message || 'try again'), 'error', 4000);
      }
    });
    row.appendChild(sla);
    row.appendChild(btn);
    form.appendChild(row);
    wrap.appendChild(form);

    return wrap;
  }
  // Expose so the drafting pages (different HTML host) can call it too.
  window.renderAssistCta = renderAssistCta;

  // -------------------------------------------------------------- submit
  // Progressive research. Hits /api/situation/stream, which emits real card
  // shells the instant retrieval finishes (before the 10-30s LLM call), then
  // the full result. Falls back to the classic /api/situation on ANY problem
  // (older server, proxy buffering, no ReadableStream, parse error) so the
  // proven path always backs it. Returns the same shape as /api/situation.
  async function researchSituation(body, headers, signal, stagePanel, target) {
    try {
      const r = await fetch('/api/situation/stream', { method: 'POST', headers, body, signal });
      if (!r.ok) {
        // Gate / server error arrives BEFORE the stream opens — treat as classic.
        const data = await r.json().catch(() => ({}));
        if (handleEntitlementError(r.status, data)) {
          const e = new Error((data.detail && data.detail.message) || 'upgrade required'); e.noFallback = true; throw e;
        }
        const e = new Error(friendlyError(r.status, data.error || (data.detail && data.detail.message))); e.noFallback = true; throw e;
      }
      if (!r.body || typeof r.body.getReader !== 'function') throw new Error('streaming unsupported');

      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '', finalResp = null, streamError = null;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          let evt; try { evt = JSON.parse(line); } catch (e) { continue; }
          if (evt.type === 'shells') {
            try { renderShellCards(evt.cases || [], target, stagePanel); } catch (e) { /* non-fatal */ }
          } else if (evt.type === 'result') {
            finalResp = { result: evt.result, raw: evt.raw, dropped_hallucinations: evt.dropped_hallucinations, meta: evt.meta };
          } else if (evt.type === 'error') {
            streamError = evt.message || 'stream error';
          }
        }
      }
      if (finalResp) return finalResp;
      throw new Error(streamError || 'stream ended without a result');
    } catch (err) {
      if (err.name === 'AbortError' || err.noFallback) throw err;
      console.warn('[research] streaming failed → classic fallback:', err && err.message);
      const r2 = await fetch('/api/situation', { method: 'POST', headers, body, signal });
      const data = await r2.json().catch(() => ({}));
      if (handleEntitlementError(r2.status, data)) throw new Error((data.detail && data.detail.message) || 'upgrade required');
      if (!r2.ok) throw new Error(friendlyError(r2.status, data.error || (data.detail && data.detail.message)));
      return data;
    }
  }

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
      'understanding the matter',
      'searching across 3.5 crore judgments',
      'reasoning through candidates',
      'preparing case cards',
    ] : [
      'reading the judgment',
      'extracting points of law',
      'generating cri.l.j. headnote',
      'verifying with haiku',
    ];
    stagePanel = renderStagesPanel(stages);
    target.appendChild(stagePanel);

    // Pacing matches the V3-default pipeline:
    //   - understanding (refine): ~8s
    //   - searching (retrieve): ~15-30s
    //   - reasoning (V3 main): 10-30s
    //   - preparing (verify + render): <2s
    // 'preparing case cards' never advances via timer — replaced when results arrive.
    const situationDelays = isHindi
      ? [3500, 10000, 28000, 45000]    // hindi translate + 4-stage situation
      : [8000, 25000, 45000];          // 3-stage situation pacing
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

    // Abort after 3 min. V3 (DeepSeek chat) is the default again — typical
    // 10-30s, realistic worst case ~90s with refine + retrieve. 180s gives a
    // generous buffer for the Groq fallback path without an endless spinner.
    const abortCtrl = new AbortController();
    const abortTimer = setTimeout(() => abortCtrl.abort(), 180000);

    try {
      let resp;
      if (intent === 'headnote') {
        resp = await post('/api/headnote', { judgment_text: input });
      } else {
        // Situation / ranked-precedents — progressive streaming (real card
        // shells the moment retrieval finishes, analysis streamed in), with a
        // clean fallback to the classic single-shot endpoint on any problem.
        const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) };
        const body = JSON.stringify({
          situation: input,
          style: state.style,
          deep_mode: state.deepMode,
          mode: state.mode,
          jurisdiction: state.jurisdiction || null,
        });
        resp = await researchSituation(body, headers, abortCtrl.signal, stagePanel, target);
        clearTimeout(abortTimer);
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
        ? 'query took over 3 minutes — the AI provider may be under load. please retry (second attempt is usually ~3× faster due to caching). tip: adding a specific section reference (e.g. "BNSS 482") narrows the search and speeds things up.'
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
      if (!b.dataset.view) return;   // plain <a> links (e.g. /sections) navigate natively
      b.addEventListener('click', () => switchView(b.dataset.view));
    });

    // ============================================================
    // DRAFTING HOME v2 — court-organised
    // ============================================================
    // Cards fetched from /api/draft/courts on first switch into the
    // drafting view; cached for the session. Tiles render as buttons
    // linking to /draft/court/{id} for browse and /draft/template/{id}
    // for procedural (cross-court) templates.
    let _courtCache = null;       // [{id, label_en, label_hi, count, templates: [...]}]
    let _flatTemplateCache = null; // flat list of all templates for cross-court search

    async function loadCourtData() {
      if (_courtCache) return _courtCache;
      try {
        const r = await fetch('/api/draft/courts');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        _courtCache = data.courts || [];
        _flatTemplateCache = _courtCache.flatMap(c => c.templates || []);
        return _courtCache;
      } catch (e) {
        console.warn('court data load failed:', e);
        return [];
      }
    }

    function renderCourtCards(courts) {
      const wrap = document.getElementById('draft-courts');
      if (!wrap) return;
      // The 5 main courts (procedural rendered separately below).
      const mainCourts = courts.filter(c => c.id !== 'procedural');
      wrap.innerHTML = mainCourts.map(c => {
        const empty = (c.count === 0);
        const sample = (c.templates && c.templates[0]) || null;
        const hint = sample
          ? `${c.count} templates · ${esc(sample.name_en)}…`
          : `${c.count} templates`;
        return `
          <${empty ? 'div' : 'a href="/draft/court/' + c.id + '"'}
             class="court-card ${empty ? 'court-card--empty' : ''}"
             role="listitem"
             ${empty ? 'aria-disabled="true"' : ''}>
            <div class="court-card__name">${esc(c.label_en)}</div>
            <div class="court-card__name-hi">${esc(c.label_hi)}</div>
            <div class="court-card__count">${empty ? 'coming soon' : (c.count + ' templates')}</div>
          </${empty ? 'div' : 'a'}>
        `;
      }).join('');
    }

    function renderProceduralRail(courts) {
      const wrap = document.getElementById('draft-procedural');
      if (!wrap) return;
      const proc = courts.find(c => c.id === 'procedural');
      if (!proc || !proc.templates || !proc.templates.length) {
        wrap.innerHTML = '';
        return;
      }
      wrap.innerHTML = proc.templates.map(t => `
        <a href="/draft/template/${esc(t.id)}" class="procedural-tile" role="listitem">
          <div class="procedural-tile__name">${esc(t.name_en)}</div>
          <div class="procedural-tile__sub">${esc(t.name_hi || '')}</div>
        </a>
      `).join('');
    }

    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
    }

    async function initDraftingHome() {
      const courts = await loadCourtData();
      renderCourtCards(courts);
      renderProceduralRail(courts);
      checkPersonaNudge();
    }

    // ============================================================
    // Persona nudge — show "Complete your bar profile" if user
    // hasn't filled in advocate_name + enrolment_number yet.
    // ============================================================
    async function checkPersonaNudge() {
      const nudge = document.getElementById('persona-nudge');
      if (!nudge) return;
      try {
        if (!window.headnoteAuth) return;
        await window.headnoteAuth.ready();
        const token = await window.headnoteAuth.getAccessToken();
        if (!token) return;  // not signed in — no nudge
        const r = await fetch('/api/lawyer-profile', {
          headers: { 'Authorization': 'Bearer ' + token },
        });
        if (!r.ok) return;
        const data = await r.json();
        nudge.hidden = !!data.complete;  // hide if profile already complete
      } catch (e) { /* silent */ }
    }

    // ============================================================
    // Search — cross-court flat search across all 35 templates.
    // ============================================================
    const searchInput = document.getElementById('draft-search-input');
    const searchClear = document.getElementById('draft-search-clear');
    const draftEmpty  = document.getElementById('draft-empty');
    const courtBrowse = document.getElementById('draft-court-browse');
    const searchResults = document.getElementById('draft-search-results');

    function renderSearchResults(needle) {
      if (!searchResults) return;
      const list = _flatTemplateCache || [];
      const matches = list.filter(t => {
        const hay = (t.name_en + ' ' + (t.name_hi||'') + ' ' + (t.description||''))
          .toLowerCase();
        return hay.includes(needle);
      });
      if (!matches.length) {
        searchResults.innerHTML = '';
        return false;
      }
      searchResults.innerHTML = matches.map(t => `
        <a href="/draft/template/${esc(t.id)}" class="draft-tile draft-tile--live" role="listitem">
          <div class="draft-tile__name">${esc(t.name_en)}</div>
          <div class="draft-tile__sub mono">${esc(t.court_label_en)} · ${esc((t.description||'').slice(0,60))}</div>
          <span class="draft-tile__badge draft-tile__badge--live">open</span>
        </a>
      `).join('');
      return true;
    }

    function applyDraftFilter(q) {
      const needle = (q || '').toLowerCase().trim();
      if (!needle) {
        // Show court browse, hide search results
        if (courtBrowse)   courtBrowse.hidden = false;
        if (searchResults) searchResults.hidden = true;
        if (draftEmpty)    draftEmpty.hidden = true;
        if (searchClear)   searchClear.hidden = true;
        return;
      }
      // Show search, hide court browse
      if (courtBrowse)   courtBrowse.hidden = true;
      const hadResults = renderSearchResults(needle);
      if (searchResults) searchResults.hidden = !hadResults;
      if (draftEmpty)    draftEmpty.hidden = hadResults;
      if (searchClear)   searchClear.hidden = false;
    }

    if (searchInput) {
      searchInput.addEventListener('input', e => applyDraftFilter(e.target.value));
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
        if (searchInput) { searchInput.value = ''; }
        applyDraftFilter('');
        if (searchInput) searchInput.focus();
      });
    }

    // Kick off the drafting home render. Idempotent — first switchView
    // into 'drafting' will see cached data on subsequent calls.
    initDraftingHome();

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
    // Prime the saved-case-law set so result cards show the right ☆/★ state.
    // Best-effort: resolves once the auth token is ready, else stays empty and
    // the onAuthChange hook below refreshes it on sign-in.
    loadSavedIds();
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
        // Saved library is per-account — reload it (and refresh card toggles)
        // whenever the user signs in / out / switches accounts.
        loadSavedIds();
        if (state.activeView === 'saved') renderSavedView();
      });
    }

    // Load user state (plan + usage) after auth resolves. We poll briefly
    // because initAuth is async and we don't want to race with the JWT.
    setTimeout(loadUserState, 1500);

    // Post-payment celebration. Flag set by /payment-success.html on
    // successful upgrade. Fires once, then is cleared. Doesn't depend
    // on /api/me — works even if the meter is briefly stale.
    showUpgradeCelebrationIfPending();

    // Honour an initial view from the URL hash, e.g. /app#drafting. This is
    // what lets the draft editor pages (draft-bail / draft-template /
    // draft-court) send the user BACK to the drafting home instead of
    // research — they link to /app#drafting. Default stays research.
    const _hashView = (location.hash || '').replace(/^#/, '').trim();
    if (['research', 'browse', 'drafting', 'account', 'saved'].includes(_hashView)) {
      switchView(_hashView);
    }
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
      monthly: { name: 'Monthly',     price: '₹599/mo', tag: 'Most popular' },
      yearly:  { name: 'Yearly',       price: '₹5,999/yr', tag: 'Best value' },
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
