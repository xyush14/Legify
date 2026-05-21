/**
 * Headnote — Auth module
 * Google OAuth via Supabase + onboarding flow (name, phone, referral).
 *
 * Flow
 * ----
 * 1. Overlay is visible by default in HTML (CSS hides .shell until body.auth-ready).
 *    This prevents a flash of the app before we know if the user is signed in.
 * 2. initAuth() runs on boot:
 *    - If Supabase isn't configured → reveal app (dev mode).
 *    - If session exists + onboarding done → reveal app.
 *    - If session exists but onboarding missing → show onboarding modal.
 *    - If no session → keep login modal visible.
 * 3. After successful auth + onboarding → body.auth-ready added, overlay fades out.
 */

/* ------------------------------------------------------------------ state */

let _sb = null;
let currentUser = null;
const _authChangeListeners = [];

/* ------------------------------------------------------------------ boot */

async function initAuth() {
  // Loud opening banner so the user can scroll past unrelated console
  // noise (Supabase, fastembed warnings, etc) to find auth output.
  console.log('%c[auth] === Headnote auth init ===', 'background:#000;color:#fff;padding:2px 6px');
  console.log('[auth] page url:', window.location.href);
  console.log('[auth] hash:', window.location.hash || '(empty)');
  console.log('[auth] search:', window.location.search || '(empty)');

  // -- Hard timeout safety net --
  // If anything in this function hangs for more than 8 seconds, force
  // the login modal so the user can at least retry instead of staring
  // at "checking sign-in…" forever.
  const _watchdog = setTimeout(() => {
    console.error('[auth] initAuth watchdog fired — forcing login modal after 8s');
    _showLoginModal();
    _showAuthError('Sign-in check is taking longer than expected. You can sign in again.');
  }, 8000);

  function _cancelWatchdog() { clearTimeout(_watchdog); }

  // -- Surface OAuth errors that come back as ?error= or #error= in the URL --
  _surfaceOAuthErrorFromUrl();

  // Fetch public Supabase config from backend — with explicit timeout so
  // a flaky network doesn't keep the page in 'checking' forever.
  let cfg = {};
  try {
    cfg = await _fetchWithTimeout('/api/config', 5000);
  } catch (e) {
    console.error('[auth] /api/config fetch failed:', e);
  }

  if (!cfg.supabase_url || !cfg.supabase_anon_key) {
    console.log('[auth] Supabase not configured — auth skipped (dev mode)');
    _cancelWatchdog();
    _revealApp();
    return;
  }

  // Wait for the Supabase CDN script to load (defer-loaded; usually ready
  // by the time we get here but be defensive).
  if (!window.supabase || !window.supabase.createClient) {
    await _waitFor(() => window.supabase && window.supabase.createClient, 3000);
  }
  if (!window.supabase) {
    console.error('[auth] Supabase CDN failed to load');
    _cancelWatchdog();
    _showLoginModal();   // at least show the login UI; user can refresh
    _showAuthError('Auth library failed to load. Please refresh the page.');
    return;
  }

  // Be explicit about auth persistence — defaults should be these values
  // but pinning them here means a Supabase JS upgrade can't accidentally
  // change behaviour without us noticing. Without persistSession+storage,
  // a page refresh logs the user out (no localStorage write on OAuth
  // success). Some browser privacy modes also disable storage by default;
  // we explicitly point at localStorage so a setup mismatch surfaces in
  // the console rather than silently dropping the session.
  _sb = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: (typeof window !== 'undefined' && window.localStorage) || undefined,
      // NOTE: deliberately leaving storageKey at the Supabase default
      // (sb-<project-ref>-auth-token) so existing signed-in users don't
      // get logged out by a key rename. If we ever need to namespace,
      // do it with a one-time migration that reads the old key first.
    },
  });

  // Diagnostic: confirm storage is writable so a private-mode browser
  // surfaces loudly rather than silently looking signed-out on refresh.
  try {
    const testKey = '__headnote_storage_test__';
    window.localStorage.setItem(testKey, '1');
    window.localStorage.removeItem(testKey);
  } catch (e) {
    console.error('[auth] localStorage not writable — sessions will not persist:', e);
    _showAuthError('Your browser is blocking storage. Disable private/incognito mode or allow cookies for this site.');
  }

  // React to sign-in / sign-out events. This handler fires with the
  // INITIAL_SESSION event right after createClient, so it does the same
  // job as the manual getSession() below — but Supabase delivers the
  // session here without the extra round-trip that getSession() is
  // taking 5+ seconds on. Either path can reveal the app.
  _sb.auth.onAuthStateChange(async (_event, session) => {
    console.log('[auth] Auth state changed. Event:', _event,
                'has session:', !!session, 'user:', session?.user?.email);
    const prevUserId = currentUser?.id || null;
    if (session?.user) {
      currentUser = session.user;
      // CRITICAL: the user_profiles row fetch can hang for 5-10s on
      // a cold Supabase region or under RLS-policy load. Without a
      // timeout here, the user sees the loading state until forever.
      // Fail-OPEN: better to flash the onboarding modal once than
      // trap a signed-in user.
      let done = false;
      try {
        done = await _withTimeout(
          _isOnboardingDone(session.user.id),
          4000,
          'isOnboardingDone(onAuthStateChange)',
        );
      } catch (e) {
        console.error('[auth] onboarding check timed out — assuming done:', e.message);
        done = true;
      }
      _cancelWatchdog();
      if (done) {
        _revealApp();
      } else {
        _showOnboardingModal(session.user);
      }
    } else {
      currentUser = null;
      _cancelWatchdog();
      _showLoginModal();
    }
    // Notify subscribers (app.js) so per-user state (history, drafts list,
    // chat threads) can be re-scoped to the new user — or cleared on signout.
    const newUserId = currentUser?.id || null;
    if (prevUserId !== newUserId) {
      _authChangeListeners.forEach(fn => {
        try { fn(currentUser); } catch (e) { console.error('[auth] listener err:', e); }
      });
    }
  });

  // Diagnostic: dump everything we know about the Supabase auth state
  // at this point. If sessions are being lost on refresh, the answer is
  // usually visible right here: either localStorage is empty (storage
  // not being written on OAuth success) or getSession() throws (cookies
  // disabled, SDK mismatch).
  try {
    const allKeys = Object.keys(window.localStorage || {});
    const sbKeys = allKeys.filter(k => k.startsWith('sb-') || k.includes('supabase'));
    console.log('[auth] localStorage sb-* keys:', sbKeys);
    sbKeys.forEach(k => {
      const v = window.localStorage.getItem(k);
      console.log(`[auth]   ${k}: ${(v || '').slice(0, 120)}...`);
    });
  } catch (e) {
    console.error('[auth] localStorage dump failed:', e);
  }

  // Note: we deliberately do NOT also call getSession() here.
  // onAuthStateChange above fires with INITIAL_SESSION + the stored
  // session right after createClient, so it covers the page-load case
  // already. Adding a second getSession() call here was both redundant
  // AND the actual culprit for the 'checking sign-in…' freeze — that
  // call was timing out at 5s while the onAuthStateChange handler had
  // already successfully fetched the session.
  //
  // The watchdog at the top of initAuth is still the safety net: if
  // onAuthStateChange somehow doesn't fire within 8s, the user gets
  // the login modal back instead of staying stuck.
}

// ----- helpers used by initAuth -----

async function _fetchWithTimeout(url, timeoutMs) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

function _withTimeout(promise, timeoutMs, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(
      () => reject(new Error(`${label} timed out after ${timeoutMs}ms`)),
      timeoutMs,
    )),
  ]);
}

/* ------------------------------------------------------------------ public helpers */

/** Diagnostic — call from DevTools console to see exactly what state
 *  auth is in. Returns a string + dumps to console.
 *
 *      headnoteAuthDebug()
 */
window.headnoteAuthDebug = function () {
  const out = ['=== Headnote auth state ==='];
  out.push('href: ' + window.location.href);
  out.push('hash: ' + (window.location.hash || '(empty)'));
  out.push('search: ' + (window.location.search || '(empty)'));
  out.push('_sb client present: ' + !!_sb);
  out.push('currentUser: ' + (currentUser ? currentUser.email || currentUser.id : 'null'));
  try {
    const all = Object.keys(window.localStorage || {});
    const sbKeys = all.filter(k => k.startsWith('sb-') || k.includes('supabase'));
    out.push('localStorage all keys count: ' + all.length);
    out.push('localStorage sb-* keys: ' + JSON.stringify(sbKeys));
    sbKeys.forEach(k => {
      const v = window.localStorage.getItem(k);
      out.push(`  ${k} (${(v || '').length} chars): ${(v || '').slice(0, 200)}…`);
    });
  } catch (e) {
    out.push('localStorage error: ' + e.message);
  }
  if (_sb) {
    _sb.auth.getSession().then(({ data, error }) => {
      console.log('[auth-debug] getSession returned:', {
        hasSession: !!data?.session,
        userId: data?.session?.user?.id,
        error: error?.message,
      });
    }).catch(e => console.error('[auth-debug] getSession threw:', e));
  }
  const msg = out.join('\n');
  console.log(msg);
  return msg;
};

/** Get the current Supabase JWT (use as Bearer in protected API calls). */
async function getAuthToken() {
  if (!_sb) return null;
  try {
    const { data: { session } } = await _sb.auth.getSession();
    return session?.access_token || null;
  } catch (e) {
    return null;
  }
}

async function signOut() {
  if (!_sb) return;
  await _sb.auth.signOut();
  // onAuthStateChange will trigger login modal
}

/* ------------------------------------------------------------------ public API
 * Exposed on window.headnoteAuth so app.js / pricing page / admin page
 * can grab the access token to attach to API calls. Keep this small and
 * stable — every fetch in the app depends on it.
 */
window.headnoteAuth = {
  getAccessToken: getAuthToken,
  getUser:        () => currentUser,
  userId:         () => currentUser?.id || null,
  signOut:        signOut,
  // Subscribe to sign-in / sign-out / user-switch events.
  // Callback receives the new user object (or null when signed out).
  // Returns an unsubscribe function.
  onAuthChange:   (fn) => {
    if (typeof fn !== 'function') return () => {};
    _authChangeListeners.push(fn);
    // Fire once with current state so subscribers don't need separate init
    try { fn(currentUser); } catch (e) { console.error('[auth] init listener err:', e); }
    return () => {
      const i = _authChangeListeners.indexOf(fn);
      if (i >= 0) _authChangeListeners.splice(i, 1);
    };
  },
};

/* ------------------------------------------------------------------ click handlers (called from HTML) */

async function signInWithGoogle() {
  if (!_sb) return;
  _setGoogleBtnLoading(true);
  try {
    // Use the current origin + /app as the post-auth redirect.
    // Note: this URL MUST be in Supabase Dashboard -> Authentication -> URL Configuration -> Redirect URLs
    // allowlist. If it isn't, Supabase silently falls back to the "Site URL" setting
    // (default localhost:3000) and the OAuth flow lands on a broken page.
    const redirectUrl = window.location.origin + '/app';
    console.log('[auth] Starting Google OAuth.');
    console.log('[auth] redirectTo:', redirectUrl);
    console.log('[auth] If this lands on localhost or anywhere unexpected,');
    console.log('[auth]   add this URL to Supabase Dashboard -> Authentication -> URL Configuration -> Redirect URLs');

    const { data, error } = await _sb.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: redirectUrl,
        // Force consent + offline access so we always get a fresh refresh token + complete profile.
        queryParams: { access_type: 'offline', prompt: 'consent' },
      },
    });
    console.log('[auth] signInWithOAuth returned:', { data, error });
    if (error) {
      console.error('[auth] OAuth error:', error);
      _setGoogleBtnLoading(false);
      _showAuthError('Sign-in failed: ' + error.message);
    }
    // On success, the page redirects; loading state persists until then.
  } catch (e) {
    console.error('[auth] OAuth exception:', e);
    _setGoogleBtnLoading(false);
    _showAuthError('Sign-in error: ' + e.message);
  }
}

async function submitOnboarding() {
  const name    = document.getElementById('onboard-name')?.value?.trim();
  const rawPhone = document.getElementById('onboard-phone')?.value?.replace(/\D/g, '');
  const referral = document.getElementById('onboard-referral')?.value?.trim();

  console.log('[auth] Onboarding submit. Name:', name, 'Phone:', rawPhone, 'Referral:', referral);

  if (!name) return _markFieldError('onboard-name', 'Please enter your name');
  if (!rawPhone || rawPhone.length !== 10) {
    return _markFieldError('onboard-phone', 'Enter a valid 10-digit number');
  }

  const btn = document.getElementById('onboard-submit-btn');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span>Saving…</span>';

  try {
    console.log('[auth] Saving onboarding to database...');
    await _saveOnboarding(name, '+91' + rawPhone, referral || null);
    console.log('[auth] Onboarding saved. Revealing app.');
    _revealApp();
  } catch (e) {
    console.error('[auth] Onboarding save failed:', e);
    btn.disabled = false;
    btn.innerHTML = orig;
    _showAuthError('Could not save profile: ' + e.message);
  }
}

/* ------------------------------------------------------------------ Supabase data layer */

async function _isOnboardingDone(userId) {
  if (!_sb) return true;
  try {
    const { data } = await _sb
      .from('user_profiles')
      .select('onboarding_complete')
      .eq('id', userId)
      .maybeSingle();
    return data?.onboarding_complete === true;
  } catch (_) {
    return false;
  }
}

async function _saveOnboarding(name, phone, referralCode) {
  if (!_sb || !currentUser) throw new Error('Not authenticated');
  const { error } = await _sb.from('user_profiles').upsert({
    id: currentUser.id,
    name,
    phone,
    referral_code: referralCode,
    onboarding_complete: true,
  });
  if (error) throw error;
}

/* ------------------------------------------------------------------ overlay state machine */

function _showLoginModal() {
  const login   = document.getElementById('login-modal');
  const onboard = document.getElementById('onboarding-modal');
  const loading = document.getElementById('auth-loading');
  if (login)   login.style.display   = '';
  if (onboard) onboard.style.display = 'none';
  if (loading) loading.style.display = 'none';
  document.getElementById('auth-overlay')?.classList.remove('is-hidden');
  document.body.classList.remove('auth-ready');
}

function _showOnboardingModal(user) {
  const login   = document.getElementById('login-modal');
  const onboard = document.getElementById('onboarding-modal');
  const loading = document.getElementById('auth-loading');
  if (login)   login.style.display   = 'none';
  if (onboard) onboard.style.display = '';
  if (loading) loading.style.display = 'none';

  // Pre-fill name + greeting from Google profile
  // Try multiple possible field locations for the name
  let googleName = (
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    user?.identities?.[0]?.identity_data?.full_name ||
    user?.identities?.[0]?.identity_data?.name ||
    ''
  ).trim();

  console.log('[auth] Attempting name extraction. user_metadata:', user?.user_metadata);
  console.log('[auth] Google name extracted:', googleName);

  // Fallback: use email name if no Google name found
  if (!googleName && user?.email) {
    googleName = user.email.split('@')[0];
    console.log('[auth] Using email-based fallback name:', googleName);
  }

  const firstName = googleName.split(' ')[0] || '';
  const greet = document.getElementById('onboard-greeting');
  if (greet && firstName) {
    greet.innerHTML = `, <span class="auth-welcome-name">${_escapeHtml(firstName)}</span>`;
  }
  const nameInput = document.getElementById('onboard-name');
  if (nameInput && googleName && !nameInput.value) nameInput.value = googleName;

  document.getElementById('auth-overlay')?.classList.remove('is-hidden');
  document.body.classList.remove('auth-ready');
}

/** Hide overlay and unlock app shell. */
function _revealApp() {
  document.body.classList.add('auth-ready');
  document.getElementById('auth-overlay')?.classList.add('is-hidden');
  // Remove the overlay from the DOM after the fade so it can't trap focus
  setTimeout(() => {
    document.getElementById('auth-overlay')?.remove();
  }, 350);
  // Populate the sidebar user card if we know who's signed in.
  _renderSidebarUser(currentUser);

  // If the user was bounced here from /draft/template/... or /draft/smart
  // by a 401, send them back to where they were now that they're signed in.
  try {
    const retTo = window.localStorage.getItem('headnote.returnTo');
    if (retTo && retTo !== window.location.pathname && retTo.startsWith('/')) {
      window.localStorage.removeItem('headnote.returnTo');
      // Small delay so the auth-ready transition completes first
      setTimeout(() => { window.location.href = retTo; }, 250);
    }
  } catch (e) { /* localStorage might be blocked — non-fatal */ }
}

/** Populate the sidebar footer with the signed-in user's name + avatar. */
function _renderSidebarUser(user) {
  const card = document.getElementById('sidebar-user');
  if (!card) return;
  if (!user) {
    card.hidden = true;
    return;
  }
  // Name: prefer the onboarded profile if we already have it via
  // user_metadata, otherwise fall back to the Google full name, then to
  // the email local-part.
  const name = (
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    user?.identities?.[0]?.identity_data?.full_name ||
    (user?.email ? user.email.split('@')[0] : '')
  ).trim();

  const nameEl = document.getElementById('sidebar-user-name');
  if (nameEl) nameEl.textContent = name || 'Signed in';

  // Avatar: Google profile picture if available, otherwise the first
  // letter of the name as a coloured initial.
  const avatarUrl = (
    user?.user_metadata?.avatar_url ||
    user?.user_metadata?.picture ||
    user?.identities?.[0]?.identity_data?.avatar_url ||
    ''
  );
  const avatarEl = document.getElementById('sidebar-user-avatar');
  if (avatarEl) {
    if (avatarUrl) {
      avatarEl.innerHTML = `<img src="${avatarUrl}" alt="" referrerpolicy="no-referrer" />`;
    } else {
      const initial = (name || 'U').trim().charAt(0).toUpperCase();
      avatarEl.textContent = initial;
    }
  }
  card.hidden = false;
}

/* ------------------------------------------------------------------ UI helpers */

function _setGoogleBtnLoading(loading) {
  const btn = document.getElementById('google-signin-btn');
  if (!btn) return;
  btn.disabled = loading;
  const label = btn.querySelector('.btn-google__label');
  if (label) label.textContent = loading ? 'Signing in…' : 'Continue with Google';
}

function _showAuthError(msg) {
  const el = document.getElementById('auth-error');
  if (el) { el.textContent = msg; el.style.display = ''; }
}

function _markFieldError(fieldId, msg) {
  const el = document.getElementById(fieldId);
  if (!el) return;
  el.classList.add('auth-form__input--error');
  el.focus();
  let err = el.parentElement.querySelector('.auth-field-error');
  if (!err) {
    err = document.createElement('span');
    err.className = 'auth-field-error';
    el.parentElement.appendChild(err);
  }
  err.textContent = msg;
  el.addEventListener('input', () => {
    el.classList.remove('auth-form__input--error');
    err.textContent = '';
  }, { once: true });
}

function _escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

/**
 * Pull OAuth errors out of the URL (?error=... or #error_code=...) and
 * surface them as a readable message on the login modal. This is what
 * makes the bad_oauth_state / redirect_uri_mismatch failure visible
 * instead of leaving the user staring at a blank app.
 */
function _surfaceOAuthErrorFromUrl() {
  try {
    const hash = (window.location.hash || '').replace(/^#/, '');
    const hashParams = new URLSearchParams(hash);
    const queryParams = new URLSearchParams(window.location.search || '');

    const errorCode = hashParams.get('error_code') || queryParams.get('error_code') || queryParams.get('error');
    const errorDesc =
      hashParams.get('error_description') ||
      queryParams.get('error_description') ||
      hashParams.get('error') ||
      '';

    if (!errorCode && !errorDesc) return;

    const pretty = decodeURIComponent((errorDesc || errorCode || '').replace(/\+/g, ' '));
    console.error('[auth] OAuth landed with error:', { errorCode, errorDesc: pretty });

    // Show the login modal with the error visible
    const login   = document.getElementById('login-modal');
    const onboard = document.getElementById('onboarding-modal');
    if (login)   login.style.display   = '';
    if (onboard) onboard.style.display = 'none';
    document.getElementById('auth-overlay')?.classList.remove('is-hidden');
    document.body.classList.remove('auth-ready');

    let hint = '';
    if (/bad_oauth_state|state.*not.*found|state.*expired/i.test(errorCode + ' ' + pretty)) {
      hint = ' (Supabase redirected to the wrong domain. The Site URL or Redirect URLs allowlist in Supabase Dashboard must include this app\'s URL.)';
    }
    _showAuthError('Sign-in failed: ' + pretty + hint);

    // Clean the URL so a refresh doesn't re-trigger the message
    if (window.history && window.history.replaceState) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  } catch (e) {
    console.error('[auth] _surfaceOAuthErrorFromUrl failed:', e);
  }
}

function _waitFor(cond, timeoutMs) {
  return new Promise(resolve => {
    const start = Date.now();
    const check = () => {
      if (cond()) return resolve(true);
      if (Date.now() - start > timeoutMs) return resolve(false);
      setTimeout(check, 50);
    };
    check();
  });
}
