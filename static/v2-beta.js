/* ============================================================================
   v2-beta.js — the client half of the V2 private-beta gate.

   The SERVER is the real gate: every V2-only endpoint depends on require_beta
   and answers 403 {"code":"not_in_beta"} to anyone else. This file exists so a
   non-tester who guesses the URL sees a calm explanation instead of a page
   that loads and then fails on every request.

   Usage — first line of a V2 page's boot, before it fetches anything:

       if (!(await hnBetaGate())) return;

   Returns true  → carry on, the user is a tester.
   Returns false → the gate screen is on screen; the page must stop.

   Demo mode (?demo=1 or opening the file directly) skips the gate entirely so
   the pages stay reviewable without an account.
   ============================================================================ */
(function () {
  'use strict';

  /* Ask the Supabase client first: a stored access token expires after about an
     hour, and only the client refreshes it. Reading localStorage alone meant a
     tester who came back the next day was told "could not reach your account"
     — the gate failing closed on a perfectly valid session. The raw read stays
     as a fallback for pages that never loaded auth.js. */
  function storedToken() {
    try {
      for (const k of Object.keys(localStorage)) {
        if (k.includes('auth-token')) {
          const v = JSON.parse(localStorage.getItem(k));
          if (v && v.access_token) return v.access_token;
        }
      }
    } catch (e) {}
    return null;
  }

  async function token() {
    try {
      if (window.headnoteAuth && typeof window.headnoteAuth.getAccessToken === 'function') {
        const t = await window.headnoteAuth.getAccessToken();
        if (t) return t;
      }
    } catch (e) {}
    return storedToken();
  }

  function isDemo() {
    return /[?&]demo=1/.test(location.search) || location.protocol === 'file:';
  }

  function screen(title, body, ctaLabel, ctaHref) {
    document.body.innerHTML =
      '<div style="min-height:100vh;display:grid;place-items:center;padding:24px;' +
      'font-family:Geist,system-ui,sans-serif;background:#fff;color:#0c0c0a">' +
        '<div style="max-width:460px;text-align:center">' +
          '<div style="font-family:\'Geist Mono\',monospace;font-size:11px;letter-spacing:.12em;' +
          'text-transform:uppercase;color:#8a857a;margin-bottom:14px">Headnote</div>' +
          '<h1 style="font-size:21px;font-weight:600;letter-spacing:-.02em;margin:0 0 10px">' +
            title +
          '</h1>' +
          '<p style="font-size:14px;line-height:1.65;color:#5d5b54;margin:0 0 24px">' +
            body +
          '</p>' +
          '<a href="' + ctaHref + '" style="display:inline-block;background:#0c0c0a;color:#fff;' +
          'text-decoration:none;font-size:14px;font-weight:500;padding:11px 22px;border-radius:10px">' +
            ctaLabel +
          '</a>' +
        '</div>' +
      '</div>';
  }

  /**
   * Resolve whether this user may use the V2 surfaces.
   * Never throws — a network failure is treated as "not a tester" so we fail
   * closed rather than rendering an unfinished surface to the whole user base.
   */
  window.hnBetaGate = async function hnBetaGate() {
    if (isDemo()) return true;

    const t = await token();
    if (!t) {
      screen(
        'Sign in to continue',
        'Your chamber lives on your Headnote account, so only you can see it.',
        'Sign in', '/app'
      );
      return false;
    }

    let me = null;
    try {
      const r = await fetch('/api/me', { headers: { Authorization: 'Bearer ' + t } });
      if (r.ok) me = await r.json();
    } catch (e) {}

    if (!me) {
      // Was "Back to Headnote → /app". /app now forwards a signed-in session
      // straight back to /home, so that button looped the advocate through the
      // same failure with no way out. A dropped request on a congested cell —
      // the normal case for this user — needs a retry, not a redirect.
      screen(
        'Could not reach your account',
        'Your connection dropped while opening your chamber. Nothing in your ' +
        'account has changed.',
        'Try again', location.href
      );
      return false;
    }

    if (!me.beta) {
      // Only reachable if V2 has been deliberately switched off (V2_PUBLIC=0),
      // which is no longer the default. In that one state V2 is unavailable to
      // this user, so /app would loop and the previous interface genuinely is
      // the only place left to send them. This is the sole link to /app/v1 in
      // the product, and it exists because a dead end would be worse.
      screen(
        'The new chamber is not open for your account yet',
        'It is being tested with a small group of advocates first. Everything ' +
        'in your account keeps working as normal in the meantime.',
        'Open the previous version', '/app/v1'
      );
      return false;
    }

    return true;
  };
})();
