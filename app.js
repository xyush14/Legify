/* =========================================================================
   Criminal Law AI — frontend logic
   Vanilla JS, no framework. State kept in module scope.
   ========================================================================= */

(() => {
  'use strict';

  // ---------- DOM helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const ce = (tag, opts = {}) => {
    const el = document.createElement(tag);
    if (opts.cls) el.className = opts.cls;
    if (opts.text != null) el.textContent = opts.text;
    if (opts.html != null) el.innerHTML = opts.html;
    if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) el.setAttribute(k, v);
    if (opts.children) opts.children.forEach((c) => c && el.appendChild(c));
    return el;
  };

  // Lightweight HTML escape (we generally use textContent)
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- Config ----------
  const EXAMPLES = {
    situationInput:
      'My client received a cheque dishonour notice but the notice was sent to a wrong address. ' +
      'Bank dishonour happened in Mumbai. Complainant filed the complaint in Delhi where he received the cheque. ' +
      'What are the precedents on territorial jurisdiction and validity of notice?',
    digestInput:
      'Five golden principles of circumstantial evidence — when can conviction be sustained ' +
      'on circumstantial evidence alone?',
  };

  const HISTORY_KEY = 'criminallawai.history.v1';
  const HISTORY_MAX = 30;

  // ---------- State ----------
  let currentMode = 'situation';
  let lastResult = null; // { mode, rawJson, parsed, container }

  // Stable snapshots of the ORIGINAL English result, keyed by mode.
  // These persist across re-renders (which is exactly what was broken before:
  // toggling Hindi rebuilt the result and overwrote "originalEnglish" with the
  // Hindi version, so the English button had nothing to restore to).
  const ORIGINAL = { situation: null, digest: null, headnote: null };
  // Current language per mode: 'en' | 'hi'
  const LANG = { situation: 'en', digest: 'en', headnote: 'en' };

  function setOriginal(mode, result) {
    ORIGINAL[mode] = JSON.parse(JSON.stringify(result));
    LANG[mode] = 'en';
  }

  // ---------- Toast ----------
  function toast(msg, kind = 'info', ms = 2400) {
    const t = ce('div', { cls: `toast toast--${kind}`, text: msg });
    $('#toasts').appendChild(t);
    setTimeout(() => {
      t.style.transition = 'opacity .25s';
      t.style.opacity = '0';
      setTimeout(() => t.remove(), 280);
    }, ms);
  }

  // ---------- API ----------
  async function api(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  async function apiGet(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  // ---------- Modes ----------
  function switchMode(mode) {
    currentMode = mode;
    $$('.mode').forEach((b) => {
      const active = b.dataset.mode === mode;
      b.classList.toggle('mode--active', active);
      b.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    $$('.panel').forEach((p) => {
      p.hidden = p.dataset.panel !== mode;
    });
    // Focus the textarea of the active mode
    const ta = $(`[data-panel="${mode}"] textarea`);
    if (ta) setTimeout(() => ta.focus(), 50);
  }

  $$('.mode').forEach((b) => b.addEventListener('click', () => switchMode(b.dataset.mode)));

  // ---------- Examples ----------
  $$('[data-action="example"]').forEach((b) => {
    b.addEventListener('click', () => {
      const ta = $('#' + b.dataset.target);
      if (!ta) return;
      const ex = EXAMPLES[b.dataset.target];
      if (ex) {
        ta.value = ex;
        ta.dispatchEvent(new Event('input'));
        ta.focus();
      }
    });
  });

  // ---------- Char count ----------
  function bindCharCount(textareaId, displayId, max) {
    const ta = $('#' + textareaId);
    const out = $('#' + displayId);
    if (!ta || !out) return;
    const update = () => {
      const len = ta.value.length;
      out.textContent = `${len.toLocaleString()} / ${max.toLocaleString()}`;
      out.style.color = len > max * 0.9 ? 'var(--warning)' : '';
    };
    ta.addEventListener('input', update);
    update();
  }
  bindCharCount('situationInput', 'situationCount', 8000);
  bindCharCount('digestInput', 'digestCount', 2000);
  bindCharCount('headnoteInput', 'headnoteCount', 80000);

  // ---------- Keyboard shortcuts ----------
  $$('.composer textarea').forEach((ta) => {
    ta.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        const panel = ta.closest('.panel').dataset.panel;
        const submitBtn = $(`#${panel}Submit`);
        if (submitBtn && !submitBtn.disabled) submitBtn.click();
      }
    });
  });

  // ---------- Renderers ----------

  function renderMetaStrip(meta) {
    const pill = (txt, cls) => ce('span', { cls: `meta-strip__pill ${cls || ''}`, text: txt });
    const strip = ce('div', { cls: 'meta-strip' });

    strip.appendChild(pill(`⏱ ${meta.elapsed_seconds}s`));
    if (meta.cache_read_input_tokens > 0) {
      strip.appendChild(pill(`Cache hit: ${meta.cache_read_input_tokens.toLocaleString()} tokens`, 'meta-strip__pill--cache'));
    } else if (meta.cache_creation_input_tokens > 0) {
      strip.appendChild(pill(`Cache write: ${meta.cache_creation_input_tokens.toLocaleString()} tokens`, 'meta-strip__pill--write'));
    }
    if (meta.input_tokens > 0) {
      strip.appendChild(pill(`${meta.input_tokens.toLocaleString()} new in / ${meta.output_tokens.toLocaleString()} out`));
    }
    if (meta.free) {
      strip.appendChild(ce('span', { cls: 'meta-strip__cost', text: 'Free · Google Translate' }));
    } else {
      strip.appendChild(ce('span', {
        cls: 'meta-strip__cost',
        text: `≈ $${meta.cost_usd.toFixed(4)} (₹${meta.cost_inr.toFixed(2)})`,
      }));
    }
    return strip;
  }

  function renderConfidence(level) {
    const cls = `confidence confidence--${level}`;
    const map = { high: '🟢 High match', medium: '🟡 Medium match', low: '🔴 Low match' };
    return ce('span', { cls, text: map[level] || level });
  }

  function renderJournalHeadnote(hn, letter) {
    if (!hn) return ce('div', { cls: 'state', text: 'No journal headnote.' });
    const wrap = ce('div', { cls: 'headnote' });
    const inner = ce('span');
    if (letter) inner.appendChild(ce('span', { cls: 'headnote__letter', text: `(${letter})` }));
    if (hn.statute_index) {
      inner.appendChild(document.createTextNode(' '));
      inner.appendChild(ce('span', { cls: 'headnote__statute', text: hn.statute_index }));
    }
    if (hn.catchword_chain) {
      inner.appendChild(document.createTextNode(' — '));
      inner.appendChild(ce('span', { cls: 'headnote__catchwords', text: hn.catchword_chain }));
    }
    if (hn.ratio) {
      inner.appendChild(document.createTextNode(' — '));
      inner.appendChild(ce('span', { cls: 'headnote__ratio', text: hn.ratio }));
    }
    if (hn.negative_carve_out) {
      inner.appendChild(document.createTextNode(' — '));
      inner.appendChild(ce('span', { cls: 'headnote__carve-out', text: hn.negative_carve_out }));
    }
    if (hn.per_judge_attribution) {
      inner.appendChild(document.createTextNode(' '));
      inner.appendChild(ce('span', { cls: 'headnote__per-judge', text: hn.per_judge_attribution }));
    }
    if (hn.paragraph_anchor) {
      inner.appendChild(document.createTextNode(' '));
      inner.appendChild(ce('span', { cls: 'headnote__anchor', text: hn.paragraph_anchor }));
    }
    wrap.appendChild(inner);
    return wrap;
  }

  function renderPractitionerNotes(pn) {
    if (!pn) return ce('div', { cls: 'state', text: 'No practitioner notes.' });
    const wrap = ce('div', { cls: 'pnotes' });
    if (pn.one_line_topic) wrap.appendChild(ce('div', { cls: 'pnotes__topic', text: pn.one_line_topic }));
    if (pn.gist) wrap.appendChild(ce('div', { cls: 'pnotes__gist', text: pn.gist }));
    if (pn.quotable_phrase) wrap.appendChild(ce('blockquote', { cls: 'pnotes__quote', text: '"' + pn.quotable_phrase + '"' }));
    if (Array.isArray(pn.cross_refs) && pn.cross_refs.length) {
      const refs = ce('div', { cls: 'pnotes__refs' });
      refs.appendChild(ce('strong', { text: 'Cross-refs:' }));
      pn.cross_refs.forEach((r) => refs.appendChild(ce('span', { text: r })));
      wrap.appendChild(refs);
    }
    return wrap;
  }

  function caseActions(caseObj, container) {
    const actions = ce('div', { cls: 'case-card__actions' });

    const copyBtn = ce('button', { cls: 'iconbtn', attrs: { 'aria-label': 'Copy', title: 'Copy this case' } });
    copyBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    copyBtn.addEventListener('click', () => copyToClipboard(caseToText(caseObj)));

    const shareBtn = ce('button', { cls: 'iconbtn', attrs: { 'aria-label': 'Share via WhatsApp', title: 'Share via WhatsApp' } });
    shareBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>';
    shareBtn.addEventListener('click', () => shareViaWhatsapp(caseToText(caseObj)));

    actions.appendChild(copyBtn);
    actions.appendChild(shareBtn);
    return actions;
  }

  function caseToText(c) {
    const lines = [];
    lines.push(c.title);
    if (c.citation) lines.push(c.citation);
    if (c.court) lines.push(`${c.court}${c.year ? ' · ' + c.year : ''}`);
    lines.push('');
    if (c.journal_headnote) {
      const h = c.journal_headnote;
      const parts = [];
      if (h.statute_index) parts.push(h.statute_index);
      if (h.catchword_chain) parts.push(h.catchword_chain);
      if (h.ratio) parts.push(h.ratio);
      if (h.negative_carve_out) parts.push(h.negative_carve_out);
      lines.push(parts.join(' — '));
      const tail = [h.per_judge_attribution, h.paragraph_anchor].filter(Boolean).join(' ');
      if (tail) lines.push(tail);
    }
    if (c.practitioner_notes) {
      const p = c.practitioner_notes;
      if (p.one_line_topic) lines.push(`Topic: ${p.one_line_topic}`);
      if (p.gist) lines.push(p.gist);
      if (p.quotable_phrase) lines.push(`"${p.quotable_phrase}"`);
      if (p.cross_refs?.length) lines.push(`Cross-refs: ${p.cross_refs.join(' · ')}`);
    }
    if (c.relevance_explanation) {
      lines.push('');
      lines.push(`Why it matches: ${c.relevance_explanation}`);
    }
    if (c.bns_note) lines.push(`BNS note: ${c.bns_note}`);
    return lines.join('\n');
  }

  function copyToClipboard(text) {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard', 'success')).catch(() => toast('Copy failed', 'error'));
    } else {
      const ta = ce('textarea'); ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy'); ta.remove();
      toast('Copied to clipboard', 'success');
    }
  }

  function shareViaWhatsapp(text) {
    const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
  }

  // ---------- Render Mode 1: Situation results ----------
  function renderSituation(data) {
    const root = $('#situationResults');
    root.innerHTML = '';
    root.appendChild(renderMetaStrip(data.meta));
    root.appendChild(renderLanguageBar('situation', data));

    const result = data.result || {};
    const cases = result.cases || [];

    const headerRow = ce('div', { cls: 'meta-strip', attrs: { style: 'background:transparent;border:0;padding:.25rem 0' } });
    headerRow.appendChild(renderConfidence(result.confidence || 'unknown'));
    headerRow.appendChild(ce('span', { text: `${cases.length} case${cases.length === 1 ? '' : 's'}` }));
    if ((data.dropped_hallucinations || []).length) {
      headerRow.appendChild(ce('span', { cls: 'meta-strip__pill meta-strip__pill--write', text: `Dropped ${data.dropped_hallucinations.length} hallucinated` }));
    }
    root.appendChild(headerRow);

    if (!cases.length) {
      root.appendChild(ce('div', {
        cls: 'state',
        children: [
          ce('h3', { cls: 'state__title', text: 'No strong matches in the corpus' }),
          ce('p', {
            cls: 'state__body',
            text: result.no_match_reason ||
              'The 42-case curated corpus does not contain genuinely relevant cases for this situation. A production system would have 50,000+ cases.',
          }),
        ],
      }));
      attachLanguageAndFeedback(root, 'situation', data);
      return;
    }

    cases.forEach((c, i) => {
      const card = ce('article', { cls: 'case-card case-card--with-rank', attrs: { 'data-rank': i + 1 } });
      card.appendChild(caseActions(c, card));

      const header = ce('header', { cls: 'case-card__header' });
      header.appendChild(ce('h2', { cls: 'case-card__title case-card__title--italic', text: c.title || '' }));
      const cite = [];
      if (c.court) cite.push(c.court);
      if (c.year) cite.push(c.year);
      if (c.citation) cite.push(c.citation);
      header.appendChild(ce('div', { cls: 'case-card__cite', text: cite.join(' · ') }));
      card.appendChild(header);

      if (c.journal_headnote) card.appendChild(renderJournalHeadnote(c.journal_headnote));
      if (c.practitioner_notes) card.appendChild(renderPractitionerNotes(c.practitioner_notes));

      if (c.relevance_explanation) {
        card.appendChild(ce('div', {
          cls: 'match-reason',
          html: `<strong>Why this matches your situation:</strong> ${esc(c.relevance_explanation)}`,
        }));
      }
      if (c.bns_note) {
        card.appendChild(ce('div', {
          cls: 'bns-note',
          html: `<span><strong>BNS / BNSS note:</strong> ${esc(c.bns_note)}</span>`,
        }));
      }
      root.appendChild(card);
    });

    root.appendChild(renderFeedbackBar('situation'));
  }

  // ---------- Render Mode 2: Digest ----------
  function renderDigest(data) {
    const root = $('#digestResults');
    root.innerHTML = '';
    root.appendChild(renderMetaStrip(data.meta));
    root.appendChild(renderLanguageBar('digest', data));

    const result = data.result || {};

    const headerRow = ce('div', { cls: 'meta-strip', attrs: { style: 'background:transparent;border:0;padding:.25rem 0' } });
    headerRow.appendChild(renderConfidence(result.confidence || 'unknown'));
    if (result.topic) headerRow.appendChild(ce('span', { text: result.topic, attrs: { style: 'font-style:italic' } }));
    root.appendChild(headerRow);

    const subTopics = result.sub_topics || [];
    if (!subTopics.length) {
      root.appendChild(ce('div', {
        cls: 'state',
        children: [
          ce('h3', { cls: 'state__title', text: 'No matching cases' }),
          ce('p', { cls: 'state__body', text: 'Try a different topic phrasing or expand the corpus.' }),
        ],
      }));
    } else {
      subTopics.forEach((sub) => {
        const block = ce('section', { cls: 'subtopic' });
        block.appendChild(ce('h3', { cls: 'subtopic__heading', text: sub.heading || '' }));
        const list = ce('div', { cls: 'subtopic__cases' });
        (sub.cases || []).forEach((c) => {
          const card = ce('article', { cls: 'case-card' });
          card.appendChild(caseActions(c, card));
          card.appendChild(ce('h4', {
            cls: 'case-card__title case-card__title--italic',
            text: c.title || '',
          }));
          card.appendChild(ce('div', {
            cls: 'case-card__cite',
            text: [c.year, c.citation].filter(Boolean).join(' · '),
          }));
          if (c.gist) card.appendChild(ce('div', { cls: 'pnotes__gist', text: c.gist, attrs: { style: 'margin-top:.5rem' } }));
          if (c.quotable_phrase) card.appendChild(ce('blockquote', { cls: 'pnotes__quote', text: '"' + c.quotable_phrase + '"' }));
          if (c.cross_refs?.length) {
            const refs = ce('div', { cls: 'pnotes__refs' });
            refs.appendChild(ce('strong', { text: 'Cross-refs:' }));
            c.cross_refs.forEach((r) => refs.appendChild(ce('span', { text: r })));
            card.appendChild(refs);
          }
          list.appendChild(card);
        });
        block.appendChild(list);
        root.appendChild(block);
      });
    }

    if (result.summary_takeaway) {
      root.appendChild(ce('div', {
        cls: 'takeaway',
        html: `<strong>Takeaway:</strong> ${esc(result.summary_takeaway)}`,
      }));
    }

    root.appendChild(renderFeedbackBar('digest'));
  }

  // ---------- Render Mode 3: Headnote ----------
  function renderHeadnote(data) {
    const root = $('#headnoteResults');
    root.innerHTML = '';
    root.appendChild(renderMetaStrip(data.meta));
    root.appendChild(renderLanguageBar('headnote', data));

    const result = data.result || {};
    const meta = result.case_metadata || {};

    if (meta.title) {
      const card = ce('article', { cls: 'case-card' });
      card.appendChild(ce('h2', { cls: 'case-card__title case-card__title--italic', text: meta.title }));
      const subBits = [meta.court, meta.bench, meta.date_of_decision && `D/- ${meta.date_of_decision}`].filter(Boolean);
      card.appendChild(ce('div', { cls: 'case-card__cite', text: subBits.join(' · ') }));
      if (meta.appeal_number) {
        card.appendChild(ce('div', { cls: 'case-card__cite', text: meta.appeal_number, attrs: { style: 'margin-top:2px' } }));
      }
      root.appendChild(card);
    }

    const headnotes = result.headnotes || [];
    headnotes.forEach((hn, i) => {
      const card = ce('article', { cls: 'case-card' });
      card.appendChild(caseActions({ title: `Headnote (${hn.letter || String.fromCharCode(65 + i)})`, journal_headnote: hn.journal_headnote, practitioner_notes: hn.practitioner_notes }, card));

      const tabs = ce('div', { cls: 'tabs', attrs: { role: 'tablist' } });
      const journalTab = ce('button', { cls: 'tab tab--active', text: '📜 Journal headnote', attrs: { role: 'tab' } });
      const practTab = ce('button', { cls: 'tab', text: '📝 Practitioner notes', attrs: { role: 'tab' } });
      tabs.append(journalTab, practTab);
      card.appendChild(tabs);

      const jp = ce('div', { cls: 'tab-panel' });
      jp.appendChild(renderJournalHeadnote(hn.journal_headnote, hn.letter));
      const pp = ce('div', { cls: 'tab-panel', attrs: { hidden: '' } });
      pp.appendChild(renderPractitionerNotes(hn.practitioner_notes));
      card.appendChild(jp);
      card.appendChild(pp);

      journalTab.addEventListener('click', () => {
        journalTab.classList.add('tab--active'); practTab.classList.remove('tab--active');
        jp.hidden = false; pp.hidden = true;
      });
      practTab.addEventListener('click', () => {
        practTab.classList.add('tab--active'); journalTab.classList.remove('tab--active');
        pp.hidden = false; jp.hidden = true;
      });

      root.appendChild(card);
    });

    const refs = result.cases_referred || [];
    if (refs.length) {
      const card = ce('article', { cls: 'case-card' });
      card.appendChild(ce('h3', { cls: 'subtopic__heading', text: 'Cases referred', attrs: { style: 'border:0;padding:0;margin:0 0 .5rem' } }));
      const list = ce('div', { cls: 'refs-list' });
      refs.forEach((r) => {
        const badge = { followed: '🟢', distinguished: '🟡', overruled: '🔴', referred: '⚪' }[r.treatment] || '⚪';
        const item = ce('div', { cls: 'ref-item' });
        item.appendChild(ce('span', { cls: 'ref-item__badge', text: badge }));
        item.appendChild(ce('span', { text: r.citation || '' }));
        if (r.treatment) item.appendChild(ce('span', { cls: 'ref-item__treatment', text: r.treatment }));
        list.appendChild(item);
      });
      card.appendChild(list);
      root.appendChild(card);
    }

    root.appendChild(renderFeedbackBar('headnote'));
  }

  // ---------- Language switcher (TOP of results) ----------
  // Renders a prominent EN/HI toggle right after the meta strip.
  // Reads ORIGINAL[mode] (stable across re-renders) so toggling back to
  // English always works.
  function renderLanguageBar(mode, data) {
    const bar = ce('div', { cls: 'lang-bar' });

    const left = ce('div', { cls: 'lang-bar__left' });
    left.appendChild(ce('span', { cls: 'lang-bar__label', text: 'View in:' }));
    const switcher = ce('div', { cls: 'lang-switch', attrs: { role: 'tablist', 'aria-label': 'Language' } });
    const enBtn = ce('button', {
      cls: 'lang-switch__btn' + (LANG[mode] === 'en' ? ' lang-switch__btn--active' : ''),
      text: 'English',
      attrs: { type: 'button', role: 'tab', 'aria-selected': LANG[mode] === 'en' ? 'true' : 'false' },
    });
    const hiBtn = ce('button', {
      cls: 'lang-switch__btn' + (LANG[mode] === 'hi' ? ' lang-switch__btn--active' : ''),
      text: 'हिन्दी',
      attrs: { type: 'button', role: 'tab', 'aria-selected': LANG[mode] === 'hi' ? 'true' : 'false' },
    });
    switcher.append(enBtn, hiBtn);
    left.appendChild(switcher);
    bar.appendChild(left);

    if (LANG[mode] === 'hi') {
      const badge = ce('span', { cls: 'lang-bar__badge', text: 'अनुवादित' });
      bar.appendChild(badge);
    }

    const right = ce('div', { cls: 'lang-bar__right' });
    const copyAllBtn = ce('button', { cls: 'btn btn--ghost btn--sm', text: '📋 Copy' });
    copyAllBtn.addEventListener('click', () => {
      const root = document.getElementById(`${mode}Results`);
      copyToClipboard(root.innerText);
    });
    const printBtn = ce('button', { cls: 'btn btn--ghost btn--sm', text: '🖨 Print' });
    printBtn.addEventListener('click', () => window.print());
    right.append(copyAllBtn, printBtn);
    bar.appendChild(right);

    // English: restore original snapshot
    enBtn.addEventListener('click', () => {
      if (LANG[mode] === 'en') return;
      data.result = JSON.parse(JSON.stringify(ORIGINAL[mode]));
      LANG[mode] = 'en';
      rerender(mode, data);
    });

    // Hindi: translate then re-render
    hiBtn.addEventListener('click', async () => {
      if (LANG[mode] === 'hi') return;
      enBtn.disabled = true;
      hiBtn.disabled = true;
      hiBtn.classList.add('lang-switch__btn--loading');
      hiBtn.textContent = 'अनुवाद हो रहा है…';
      try {
        const tr = await api('/api/translate', {
          payload: ORIGINAL[mode],     // ALWAYS translate from the stable English snapshot
          target_language: 'hi',
        });
        data.result = tr.result;
        LANG[mode] = 'hi';
        rerender(mode, data);
        toast('Translated to हिन्दी', 'success');
      } catch (e) {
        hiBtn.classList.remove('lang-switch__btn--loading');
        hiBtn.textContent = 'हिन्दी';
        enBtn.disabled = false;
        hiBtn.disabled = false;
        toast(`Translation failed: ${e.message}`, 'error');
        // Show inline error so it's not just a fleeting toast
        const root = document.getElementById(`${mode}Results`);
        const err = ce('div', {
          cls: 'state state--error',
          children: [
            ce('h3', { cls: 'state__title', text: 'Translation failed' }),
            ce('p', { cls: 'state__body', text: e.message }),
          ],
        });
        bar.after(err);
        setTimeout(() => err.remove(), 6000);
      }
    });

    return bar;
  }

  // ---------- Feedback (separate, at bottom) ----------
  function renderFeedbackBar(mode) {
    const bar = ce('div', { cls: 'feedback' });
    bar.appendChild(ce('div', { cls: 'feedback__title', text: 'Was this useful?' }));

    const fbRow = ce('div', { cls: 'feedback__buttons' });
    const upBtn = ce('button', { cls: 'btn btn--soft btn--sm', text: '👍 Useful' });
    const downBtn = ce('button', { cls: 'btn btn--soft btn--sm', text: '👎 Not useful' });
    fbRow.append(upBtn, downBtn);
    bar.appendChild(fbRow);

    const correction = ce('textarea', {
      cls: 'feedback__correction',
      attrs: { rows: '3', placeholder: 'Optional comment — what was wrong, what should have been returned?' },
    });
    bar.appendChild(correction);

    const submitFeedback = async (rating) => {
      const inputText = $(`#${mode}Input`)?.value || '';
      try {
        await api('/api/feedback', {
          mode,
          input_text: inputText,
          output_json: JSON.stringify(ORIGINAL[mode]),
          rating,
          correction: correction.value,
          lawyer_handle: localStorage.getItem('lawyer_handle') || '',
        });
        toast('Thanks — feedback saved', 'success');
      } catch (e) {
        toast(`Feedback failed: ${e.message}`, 'error');
      }
    };
    upBtn.addEventListener('click', () => submitFeedback(1));
    downBtn.addEventListener('click', () => submitFeedback(-1));

    return bar;
  }

  function rerender(mode, data) {
    if (mode === 'situation') renderSituation(data);
    else if (mode === 'digest') renderDigest(data);
    else if (mode === 'headnote') renderHeadnote(data);
  }

  // ---------- Submit handlers ----------
  async function submitSituation() {
    const input = $('#situationInput').value.trim();
    if (input.length < 10) return toast('Please describe your situation in more detail', 'error');
    const style = document.querySelector('input[name="style"]:checked').value;

    const btn = $('#situationSubmit');
    setLoading(btn, true);
    showSkeleton('#situationResults');
    try {
      const data = await api('/api/situation', { situation: input, style });
      pushHistory({ mode: 'situation', input, style, ts: Date.now() });
      setOriginal('situation', data.result);
      renderSituation(data);
    } catch (e) {
      showError('#situationResults', e.message);
    } finally {
      setLoading(btn, false);
    }
  }

  async function submitDigest() {
    const input = $('#digestInput').value.trim();
    if (input.length < 5) return toast('Please type a longer topic query', 'error');

    const btn = $('#digestSubmit');
    setLoading(btn, true);
    showSkeleton('#digestResults');
    try {
      const data = await api('/api/digest', { topic: input });
      pushHistory({ mode: 'digest', input, ts: Date.now() });
      setOriginal('digest', data.result);
      renderDigest(data);
    } catch (e) {
      showError('#digestResults', e.message);
    } finally {
      setLoading(btn, false);
    }
  }

  async function submitHeadnote() {
    const input = $('#headnoteInput').value.trim();
    if (input.length < 200) return toast('Please paste a longer judgment text', 'error');

    const btn = $('#headnoteSubmit');
    setLoading(btn, true);
    showSkeleton('#headnoteResults');
    try {
      const data = await api('/api/headnote', { judgment_text: input });
      pushHistory({ mode: 'headnote', input: input.slice(0, 200) + '…', ts: Date.now() });
      setOriginal('headnote', data.result);
      renderHeadnote(data);
    } catch (e) {
      showError('#headnoteResults', e.message);
    } finally {
      setLoading(btn, false);
    }
  }

  $('#situationSubmit').addEventListener('click', submitSituation);
  $('#digestSubmit').addEventListener('click', submitDigest);
  $('#headnoteSubmit').addEventListener('click', submitHeadnote);

  function setLoading(btn, on) {
    if (!btn) return;
    btn.classList.toggle('btn--loading', on);
    btn.disabled = on;
  }

  function showSkeleton(sel) {
    const root = $(sel);
    root.innerHTML = `
      <div class="case-card">
        <div class="skeleton skeleton--title"></div>
        <div class="skeleton skeleton--line"></div>
        <div class="skeleton skeleton--line"></div>
        <div class="skeleton skeleton--line skeleton--short"></div>
      </div>
      <div class="case-card">
        <div class="skeleton skeleton--title"></div>
        <div class="skeleton skeleton--line"></div>
        <div class="skeleton skeleton--line skeleton--short"></div>
      </div>
    `;
  }

  function showError(sel, msg) {
    const root = $(sel);
    root.innerHTML = '';
    root.appendChild(ce('div', {
      cls: 'state state--error',
      children: [
        ce('h3', { cls: 'state__title', text: 'Something went wrong' }),
        ce('p', { cls: 'state__body', text: msg }),
      ],
    }));
  }

  // ---------- Drawers ----------
  function openDrawer(id) {
    const d = document.getElementById(id);
    if (!d) return;
    d.hidden = false;
    document.body.style.overflow = 'hidden';
    d.querySelector('button')?.focus();
  }
  function closeDrawer(id) {
    const d = document.getElementById(id);
    if (!d) return;
    d.hidden = true;
    document.body.style.overflow = '';
  }

  $('#corpusBtn').addEventListener('click', () => { loadCorpus(); openDrawer('corpusDrawer'); });
  $('#historyBtn').addEventListener('click', () => { renderHistory(); openDrawer('historyDrawer'); });
  $('#aboutBtn').addEventListener('click', () => openDrawer('aboutDrawer'));
  $('#footerAbout')?.addEventListener('click', (e) => { e.preventDefault(); openDrawer('aboutDrawer'); });

  $$('.drawer').forEach((d) => {
    d.addEventListener('click', (e) => {
      if (e.target === d) closeDrawer(d.id);
    });
    d.querySelectorAll('[data-close-drawer]').forEach((b) => b.addEventListener('click', () => closeDrawer(d.id)));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $$('.drawer').forEach((d) => { if (!d.hidden) closeDrawer(d.id); });
    }
  });

  // ---------- Corpus drawer ----------
  let corpusCache = null;

  async function loadCorpus() {
    if (corpusCache) return renderCorpusList(corpusCache);
    const list = $('#corpusList');
    list.innerHTML = '<div class="skeleton skeleton--line"></div><div class="skeleton skeleton--line"></div><div class="skeleton skeleton--line skeleton--short"></div>';
    try {
      const data = await apiGet('/api/corpus');
      corpusCache = data.cases;
      renderCorpusList(corpusCache);
    } catch (e) {
      list.innerHTML = `<p class="state state--error">Could not load corpus: ${esc(e.message)}</p>`;
    }
  }

  function renderCorpusList(cases) {
    const list = $('#corpusList');
    list.innerHTML = '';
    cases.forEach((c) => {
      const item = ce('button', { cls: 'corpus-item', attrs: { type: 'button' } });
      item.appendChild(ce('div', { cls: 'corpus-item__title', text: c.title }));
      item.appendChild(ce('div', { cls: 'corpus-item__meta', text: `${c.court} · ${c.year}` }));
      if (c.topics?.length) {
        const topics = ce('div', { cls: 'corpus-item__topics' });
        c.topics.forEach((t) => topics.appendChild(ce('span', { text: t })));
        item.appendChild(topics);
      }
      list.appendChild(item);
    });
  }

  $('#corpusSearch').addEventListener('input', (e) => {
    if (!corpusCache) return;
    const q = e.target.value.toLowerCase().trim();
    if (!q) return renderCorpusList(corpusCache);
    const filtered = corpusCache.filter((c) =>
      (c.title?.toLowerCase().includes(q)) ||
      (String(c.year).includes(q)) ||
      (c.topics?.some((t) => t.toLowerCase().includes(q)))
    );
    renderCorpusList(filtered);
  });

  // ---------- History ----------
  function pushHistory(item) {
    let arr = [];
    try { arr = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch {}
    arr.unshift(item);
    if (arr.length > HISTORY_MAX) arr = arr.slice(0, HISTORY_MAX);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(arr));
  }

  function renderHistory() {
    const list = $('#historyList');
    let arr = [];
    try { arr = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch {}
    list.innerHTML = '';
    if (!arr.length) {
      list.innerHTML = '<p class="state state__body">No recent searches yet. Run a query to see it here.</p>';
      return;
    }
    arr.forEach((it) => {
      const btn = ce('button', { cls: 'corpus-item', attrs: { type: 'button' } });
      const date = new Date(it.ts).toLocaleString();
      btn.appendChild(ce('div', { cls: 'corpus-item__title', text: it.input.slice(0, 80) + (it.input.length > 80 ? '…' : '') }));
      btn.appendChild(ce('div', { cls: 'corpus-item__meta', text: `${it.mode} · ${date}` }));
      btn.addEventListener('click', () => {
        switchMode(it.mode);
        const ta = $(`#${it.mode}Input`);
        if (ta) ta.value = it.input;
        ta?.dispatchEvent(new Event('input'));
        if (it.mode === 'situation' && it.style) {
          $(`input[name="style"][value="${it.style}"]`)?.click();
        }
        closeDrawer('historyDrawer');
        ta?.focus();
      });
      list.appendChild(btn);
    });
  }

  $('#historyClear').addEventListener('click', () => {
    if (confirm('Clear all search history?')) {
      localStorage.removeItem(HISTORY_KEY);
      renderHistory();
      toast('History cleared', 'success');
    }
  });

  // ---------- Init ----------
  switchMode('situation');

  // Set lawyer handle if URL contains ?u=NAME (for sharing testing URLs to specific lawyers)
  const params = new URLSearchParams(location.search);
  if (params.get('u')) {
    localStorage.setItem('lawyer_handle', params.get('u'));
  }
})();
