/* Statute quick-look — ⌘K from anywhere (including mid-draft).
 *
 * Self-contained: injects its own styles + overlay, binds Cmd/Ctrl+K, and
 * queries GET /api/mapping/lookup (the public, deterministic IPC↔BNS /
 * CrPC↔BNSS / Evidence↔BSA concordance — no LLM anywhere in this path).
 * Click or ↵ copies the new-code section so it can be pasted into a draft.
 *
 * Include with:  <script src="/static/statute-palette.js" defer></script>
 * Skips itself if the page already provides a ⌘K palette (element #pal),
 * e.g. /home (matter jump) and /research (its own statute palette).
 */
(function () {
  'use strict';
  if (document.getElementById('pal') || document.getElementById('hn-stpal')) return;

  var css = [
    '#hn-stpal{position:fixed;inset:0;background:rgba(12,12,10,.28);backdrop-filter:blur(3px);z-index:9999;display:none;align-items:flex-start;justify-content:center;padding-top:12vh;font-family:"Geist",-apple-system,"Segoe UI",sans-serif}',
    '#hn-stpal.on{display:flex}',
    '#hn-stpal .bx{width:min(600px,92vw);background:#fff;border:1px solid #e7e7e4;border-radius:14px;box-shadow:0 30px 70px -20px rgba(12,12,10,.4);overflow:hidden;color:#0c0c0a}',
    '#hn-stpal .in{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid #f1f1ef}',
    '#hn-stpal .in svg{width:17px;height:17px;stroke:#8a8a82;fill:none;stroke-width:1.8;flex:none}',
    '#hn-stpal input{border:0;outline:0;font-size:15px;width:100%;background:transparent;font-family:inherit;color:inherit}',
    '#hn-stpal .rs{max-height:380px;overflow:auto}',
    '#hn-stpal .r{display:flex;align-items:center;gap:12px;padding:11px 16px;cursor:pointer;width:100%;text-align:left;border:0;background:none;font-family:inherit;font-size:13px;color:inherit}',
    '#hn-stpal .r:hover{background:#fcfcfb}',
    '#hn-stpal .old{font-family:"Geist Mono",ui-monospace,monospace;font-size:12px;color:#4b4b48;min-width:92px}',
    '#hn-stpal .arr{color:#b8b6ae}',
    '#hn-stpal .new{font-family:"Geist Mono",ui-monospace,monospace;font-size:12px;font-weight:500;min-width:92px}',
    '#hn-stpal .tt{font-size:12.5px;color:#8a8a82;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '#hn-stpal .mt{padding:22px 16px;text-align:center;color:#8a8a82;font-size:13px}',
    '#hn-stpal .ft{padding:9px 16px;border-top:1px solid #f1f1ef;font-family:"Geist Mono",ui-monospace,monospace;font-size:10px;color:#b8b6ae}',
    '#hn-stpal .toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#0c0c0a;color:#fff;font-size:13px;font-weight:500;padding:10px 16px;border-radius:999px}'
  ].join('\n');

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  var wrap = document.createElement('div');
  wrap.id = 'hn-stpal';
  wrap.innerHTML =
    '<div class="bx">' +
    '<div class="in"><svg viewBox="0 0 24 24"><path d="M4 19V5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2Zm0 0a2 2 0 0 1 2-2h13"/></svg>' +
    '<input placeholder="Quick statute lookup — IPC 302, 420, anticipatory bail…"></div>' +
    '<div class="rs"><div class="mt">Type a section — old code or new.</div></div>' +
    '<div class="ft">&#8629; copies the new section &middot; esc closes &middot; government concordance, no AI</div></div>';
  document.body.appendChild(wrap);

  var input = wrap.querySelector('input');
  var box = wrap.querySelector('.rs');
  var timer = null, top = null;

  function open() { wrap.classList.add('on'); input.value = ''; paint(null); input.focus(); }
  function close() { wrap.classList.remove('on'); }
  function toast(m) {
    var t = document.createElement('div'); t.className = 'toast'; t.textContent = m;
    wrap.appendChild(t); setTimeout(function () { t.remove(); }, 2200);
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]; }); }

  function paint(d) {
    if (!d) { box.innerHTML = '<div class="mt">Type a section — old code or new. IPC 302 · 420 · ४२०</div>'; top = null; return; }
    var rs = d.results || [];
    if (!rs.length) { box.innerHTML = '<div class="mt">No mapping found.</div>'; top = null; return; }
    top = rs[0];
    box.innerHTML = rs.map(function (r) {
      var o = r.old || {}, n = r.new || {};
      return '<button class="r" data-new="' + esc((n.code || '') + ' ' + (n.section || '')) + '">' +
        '<span class="old">' + esc((o.code || '') + ' ' + (o.section || '')) + '</span><span class="arr">&rarr;</span>' +
        '<span class="new">' + esc(n.section ? (n.code + ' ' + n.section) : 'omitted') + '</span>' +
        '<span class="tt">' + esc(o.title || n.title || '') + '</span></button>';
    }).join('');
    [].forEach.call(box.querySelectorAll('.r'), function (b) {
      b.onclick = function () { copy(b.getAttribute('data-new')); };
    });
  }
  function copy(v) {
    v = (v || '').trim();
    if (!v) { toast('No successor section — it was omitted'); return; }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(v).then(function () { toast('Copied ' + v); }, function () { toast(v); });
    } else { toast(v); }
    close();
  }

  input.addEventListener('input', function () {
    clearTimeout(timer);
    var q = input.value.trim();
    if (!q) { paint(null); return; }
    timer = setTimeout(function () {
      fetch('/api/mapping/lookup?q=' + encodeURIComponent(q) + '&limit=6')
        .then(function (r) { return r.json(); })
        .then(paint)
        .catch(function () { box.innerHTML = '<div class="mt">Lookup failed — are you online?</div>'; });
    }, 180);
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && top) { var n = top.new || {}; copy((n.code || '') + ' ' + (n.section || '')); }
  });
  wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === 'k') {
      e.preventDefault();
      wrap.classList.contains('on') ? close() : open();
    }
    if (e.key === 'Escape') close();
  });
})();
