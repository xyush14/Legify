/* Headnote V2 — shared navigation
 * ============================================================================
 * WHY THIS FILE EXISTS
 *
 * The four V2 screens (/home, /research, /draft, /draft-dna) each hide the
 * desktop sidebar at 720px and show a `.mtop` bar carrying only the wordmark
 * and one or two page-specific icons. That bar has NO links in it. So on a
 * phone — which is what a district advocate is actually holding, in a corridor,
 * between two boards — there was no way to get from Home to Research to Draft
 * at all. The only navigation in V2 lived in a sidebar that mobile deletes.
 *
 * This file is that navigation, in one place, for every V2 screen:
 *   - a bottom tab bar on phones (the primary navigation there),
 *   - a "More" sheet for the surfaces that don't earn a tab,
 *   - and, on desktop, the entries the V2 sidebars never had.
 *
 * That last part is not cosmetic. V1 (/app/v1) is no longer linked from
 * anywhere, and V1's sidebar was the ONLY route to the Document Vault, the
 * Recorder, the statute map and Settings/billing. Unlinking V1 without adding
 * them here would have quietly orphaned a paying user's documents and the page
 * where they manage their subscription.
 *
 * Written as one shared script rather than four copies of the same markup on
 * purpose: a nav that is duplicated four times is a nav that drifts, and the
 * V2 pages have already been bitten by exactly that (each page kept its own
 * copy of the readiness label map until the server started shipping it).
 *
 * No dependency on anything page-level. It does not call the host page's
 * helpers (go(), toast(), openPal()) because the four pages define different
 * subsets of them. Sign-out goes through window.headnoteAuth, which auth.js
 * puts on every V2 page.
 * ========================================================================== */
(function () {
  'use strict';

  if (window.__hnV2Nav) return;          // idempotent: safe to include twice
  window.__hnV2Nav = true;

  var BAR_H = 58;                        // keep in sync with .hnb height below

  /* The five things that earn a tab. Everything else lives behind More.
     `match` is the set of paths that light this tab up. */
  var TABS = [
    { id: 'home',     label: 'Home',     href: '/home',      match: ['/home'],
      icon: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>' },
    { id: 'research', label: 'Research', href: '/research',   match: ['/research'],
      icon: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3-3"/>' },
    { id: 'draft',    label: 'Draft',    href: '/draft',      match: ['/draft'],
      icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>' },
    { id: 'docs',     label: 'Docs',     href: '/documents',  match: ['/documents'],
      icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/>' },
    { id: 'more',     label: 'More',     href: null,          match: ['/draft-dna', '/recorder', '/sections', '/settings', '/diary', '/matters', '/cases'],
      icon: '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>' },
  ];

  /* Sliders, not a gear: at 19px on a thin stroke a gear's teeth collapse into a
     blob, and the first cut's simplified version read as a sun. */
  var SETTINGS_ICON =
    '<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2"/><circle cx="9" cy="16" r="2"/>';

  /* The More sheet. Deliberately does NOT repeat the four tabs, and
     deliberately does NOT list the matters diary — V2 Home IS the diary, and
     offering a second door to the same thing is how V1's eight cryptic doors
     happened. */
  var MORE = [
    { label: 'Draft DNA',  hint: 'Your own format, on every draft', href: '/draft-dna',
      icon: '<path d="M12 3v18"/><path d="M8 5.5v13"/><path d="M16 5.5v13"/><path d="M4.5 9v6"/><path d="M19.5 9v6"/>' },
    { label: 'Recorder',   hint: 'Client conversation to work product', href: '/recorder',
      icon: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>' },
    { label: 'IPC → BNS',  hint: 'Old section to new', href: '/sections',
      icon: '<path d="M4 19V5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2Zm0 0a2 2 0 0 1 2-2h13"/>' },
    { label: 'Settings',   hint: 'Account, plan and billing', href: '/settings',
      icon: SETTINGS_ICON },
  ];

  /* Entries the V2 sidebars are missing. The Chamber group (Home / Research /
     Draft) and Personalisation (Draft DNA) are already hand-written into each
     page, so this only adds what is genuinely absent. */
  var SIDEBAR_EXTRA = [
    { label: 'Documents', href: '/documents',
      icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/>' },
    { label: 'Recorder', href: '/recorder',
      icon: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>' },
    { label: 'IPC → BNS', href: '/sections',
      icon: '<path d="M4 19V5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2Zm0 0a2 2 0 0 1 2-2h13"/>' },
    { label: 'Settings', href: '/settings', icon: SETTINGS_ICON },
  ];

  function svg(paths, w) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' +
      (w || 1.6) + '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      paths + '</svg>';
  }

  var path = (location.pathname || '/').replace(/\/+$/, '') || '/';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------------------------------------------------------------- styles */
  var css = [
    /* --- the bar itself: phones only ------------------------------------ */
    '.hnb{display:none}',
    '.hnb-sheet,.hnb-back{display:none}',
    '@media(max-width:720px){',
    '.hnb{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:90;',
      'background:rgba(255,255,255,.94);backdrop-filter:blur(16px);',
      'border-top:1px solid var(--line);',
      /* iPhone home-bar: without this the tabs sit under the gesture area */
      'padding-bottom:env(safe-area-inset-bottom,0px)}',
    '.hnb__i{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;',
      'gap:3px;height:' + BAR_H + 'px;border:0;background:0;padding:0;cursor:pointer;',
      'color:var(--ink-4);font:inherit;text-decoration:none;-webkit-tap-highlight-color:transparent}',
    '.hnb__i svg{width:21px;height:21px;flex:none}',
    '.hnb__i span{font-size:10px;letter-spacing:.01em;line-height:1;font-weight:500}',
    /* active is near-black weight, not a colour — semantic colour on this app
       is reserved for ready / needs-attention / overdue */
    '.hnb__i.on{color:var(--ink)}',
    '.hnb__i.on span{font-weight:650}',
    '.hnb__i:active{background:var(--soft)}',

    /* --- keep the bar from sitting on top of the page ------------------- */
    /* Each page sets its own .wrap padding inside its own 720px query; this is
       one class-deep so it wins without touching four files. */
    'body.hn-mobnav .wrap{padding-bottom:' + (BAR_H + 26) + 'px}',
    /* Research and Draft dock a sticky composer at the bottom of a full-height
       chat. Sticky bottom is measured against the viewport, so the bar would
       land on top of the thing the advocate is typing into. */
    'body.hn-mobnav .pane-chat .cdock{bottom:calc(10px + ' + BAR_H + 'px + env(safe-area-inset-bottom,0px))}',
    'body.hn-mobnav .pane-chat{min-height:calc(100vh - 128px - ' + BAR_H + 'px)}',
    /* toasts, the floating beta chip and the drawer footer all live down here */
    'body.hn-mobnav .toasts{bottom:calc(20px + ' + BAR_H + 'px + env(safe-area-inset-bottom,0px))}',
    'body.hn-mobnav .flag{bottom:calc(6px + ' + BAR_H + 'px + env(safe-area-inset-bottom,0px))}',
    'body.hn-mobnav .jdrawer{bottom:calc(' + BAR_H + 'px + env(safe-area-inset-bottom,0px))}',

    /* --- the More sheet ------------------------------------------------- */
    '.hnb-back{position:fixed;inset:0;background:rgba(12,12,10,.28);z-index:95;',
      'opacity:0;transition:opacity .18s ease}',
    '.hnb-back.on{display:block;opacity:1}',
    '.hnb-sheet{position:fixed;left:0;right:0;bottom:0;z-index:96;background:var(--surface);',
      'border-top-left-radius:18px;border-top-right-radius:18px;',
      'box-shadow:0 -18px 50px -24px rgba(12,12,10,.4);',
      'padding:8px 12px calc(14px + env(safe-area-inset-bottom,0px));',
      'transform:translateY(102%);transition:transform .24s cubic-bezier(.32,.72,0,1)}',
    '.hnb-sheet.on{display:block;transform:translateY(0)}',
    '.hnb-grip{width:38px;height:4px;border-radius:99px;background:var(--line);margin:6px auto 12px}',
    '.hnb-who{display:flex;align-items:center;gap:10px;padding:2px 8px 12px;',
      'border-bottom:1px solid var(--line-2);margin-bottom:8px}',
    '.hnb-who .av{width:32px;height:32px;border-radius:9px;background:var(--ink);color:#fff;',
      'display:grid;place-items:center;font-size:13px;font-weight:600;flex:none}',
    '.hnb-who .u{font-size:13.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.hnb-who .r{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-4)}',
    '.hnb-row{display:flex;align-items:center;gap:12px;width:100%;text-align:left;border:0;background:0;',
      'padding:11px 8px;border-radius:11px;color:var(--ink);font:inherit;text-decoration:none;cursor:pointer}',
    '.hnb-row:active{background:var(--soft)}',
    '.hnb-row svg{width:19px;height:19px;flex:none;stroke:var(--ink-2)}',
    '.hnb-row>span{min-width:0}',
    '.hnb-row .l{display:block;font-size:14px;font-weight:500;line-height:1.25}',
    '.hnb-row .h{display:block;font-size:11.5px;color:var(--ink-4);line-height:1.3;margin-top:1px}',
    '.hnb-row.on{background:var(--soft)}.hnb-row.on .l{font-weight:650}',
    '.hnb-row--out{margin-top:6px;border-top:1px solid var(--line-2);border-radius:0;padding-top:14px;color:var(--ink-2)}',
    '}',

    /* --- desktop sidebar additions -------------------------------------- */
    /* These are <a>, and .navi was written for <button>. */
    '.sb a.navi{text-decoration:none}',
  ].join('');

  var style = document.createElement('style');
  style.id = 'hn-v2-nav-css';
  style.textContent = css;
  document.head.appendChild(style);

  /* ------------------------------------------------------------- the bar */
  function activeId() {
    for (var i = 0; i < TABS.length; i++) {
      if (TABS[i].match.indexOf(path) !== -1) return TABS[i].id;
    }
    return null;
  }

  var active = activeId();

  var bar = document.createElement('nav');
  bar.className = 'hnb';
  bar.setAttribute('aria-label', 'Main');
  bar.innerHTML = TABS.map(function (t) {
    var on = t.id === active ? ' on' : '';
    var cur = t.id === active ? ' aria-current="page"' : '';
    var body = svg(t.icon) + '<span>' + esc(t.label) + '</span>';
    return t.href
      ? '<a class="hnb__i' + on + '" href="' + t.href + '"' + cur + '>' + body + '</a>'
      : '<button type="button" class="hnb__i' + on + '" data-hnb-more="1" ' +
        'aria-haspopup="true" aria-expanded="false">' + body + '</button>';
  }).join('');

  /* ----------------------------------------------------------- More sheet */
  var back = document.createElement('div');
  back.className = 'hnb-back';

  var sheet = document.createElement('div');
  sheet.className = 'hnb-sheet';
  sheet.setAttribute('role', 'dialog');
  sheet.setAttribute('aria-label', 'More');
  sheet.innerHTML =
    '<div class="hnb-grip"></div>' +
    '<div class="hnb-who"><div class="av" id="hnb-av">·</div>' +
      '<div style="min-width:0"><div class="u" id="hnb-u">Signed in</div>' +
      '<div class="r" id="hnb-r">Headnote</div></div></div>' +
    MORE.map(function (m) {
      return '<a class="hnb-row' + (path === m.href ? ' on' : '') + '" href="' + m.href + '">' +
        svg(m.icon, 1.5) + '<span><span class="l">' + esc(m.label) + '</span>' +
        '<span class="h">' + esc(m.hint) + '</span></span></a>';
    }).join('') +
    '<button type="button" class="hnb-row hnb-row--out" data-hnb-signout="1">' +
      svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>', 1.5) +
      '<span class="l">Sign out</span></button>';

  function openMore() {
    back.classList.add('on');
    sheet.classList.add('on');
    bar.querySelector('[data-hnb-more]')?.setAttribute('aria-expanded', 'true');
  }
  function closeMore() {
    back.classList.remove('on');
    sheet.classList.remove('on');
    bar.querySelector('[data-hnb-more]')?.setAttribute('aria-expanded', 'false');
  }

  bar.addEventListener('click', function (e) {
    if (e.target.closest('[data-hnb-more]')) { e.preventDefault(); openMore(); }
  });
  back.addEventListener('click', closeMore);
  sheet.addEventListener('click', function (e) {
    if (e.target.closest('[data-hnb-signout]')) {
      e.preventDefault();
      closeMore();
      try { window.headnoteAuth?.signOut?.(); } catch (err) {}
      // Back to the door, which is where signing in happens.
      setTimeout(function () { location.href = '/app'; }, 150);
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeMore();
  });

  /* ------------------------------------------------- desktop sidebar tail */
  function extendSidebar() {
    var sb = document.querySelector('.sb');
    if (!sb || sb.querySelector('[data-hn-extra]')) return;
    // The spacer that pushes the user card to the bottom — insert above it so
    // these land under the page's own groups, not after the user card.
    var anchor = sb.querySelector('.grow');
    var frag = document.createElement('div');
    frag.setAttribute('data-hn-extra', '1');
    frag.style.marginTop = '16px';
    frag.innerHTML = '<div class="lbl">Chamber tools</div>' +
      SIDEBAR_EXTRA.map(function (s) {
        var on = path === s.href ? ' on' : '';
        return '<a class="navi' + on + '" href="' + s.href + '" title="' + esc(s.label) + '">' +
          svg(s.icon, 1.5) + '<span class="nvt">' + esc(s.label) + '</span></a>';
      }).join('');
    if (anchor) sb.insertBefore(frag, anchor); else sb.appendChild(frag);
  }

  /* --------------------------------------------------------------- who is it */
  function paintWho(user) {
    var name = (user && (user.user_metadata?.full_name || user.user_metadata?.name || user.email)) || '';
    var u = document.getElementById('hnb-u');
    var r = document.getElementById('hnb-r');
    var av = document.getElementById('hnb-av');
    var out = sheet.querySelector('[data-hnb-signout]');
    // Say one thing, not two. The first cut printed the placeholder "Signed in"
    // above "NOT SIGNED IN" — the header and the sub-line contradicting each
    // other on the same card.
    if (u) u.textContent = user ? (name || 'Signed in') : 'Not signed in';
    if (r) r.textContent = user ? 'Advocate' : 'Open a screen to sign in';
    if (av) av.textContent = (name.trim()[0] || '·').toUpperCase();
    // Nothing to sign out of.
    if (out) out.style.display = user ? '' : 'none';
  }

  function mount() {
    document.body.classList.add('hn-mobnav');
    document.body.appendChild(back);
    document.body.appendChild(sheet);
    document.body.appendChild(bar);
    extendSidebar();
    try {
      window.headnoteAuth?.onAuthChange?.(paintWho);
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
