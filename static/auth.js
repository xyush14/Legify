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

/* ------------------------------------------------------------------ boot */

async function initAuth() {
  // Fetch public Supabase config from backend
  let cfg = {};
  try {
    cfg = await fetch('/api/config').then(r => r.json());
  } catch (_) { /* network blip — fall through */ }

  if (!cfg.supabase_url || !cfg.supabase_anon_key) {
    console.log('[auth] Supabase not configured — auth skipped (dev mode)');
    _revealApp();
    return;
  }

  // Wait for the Supabase CDN script to load (it has defer; runs before this
  // but during a hard reload it can momentarily not be on window yet).
  if (!window.supabase || !window.supabase.createClient) {
    await _waitFor(() => window.supabase && window.supabase.createClient, 3000);
  }
  if (!window.supabase) {
    console.error('[auth] Supabase CDN failed to load');
    _showAuthError('Could not load auth. Please refresh.');
    return;
  }

  _sb = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  // React to sign-in / sign-out events (Google OAuth redirect comes through here)
  _sb.auth.onAuthStateChange(async (_event, session) => {
    console.log('[auth] Auth state changed. Event:', _event, 'Session:', session);
    if (session?.user) {
      console.log('[auth] User logged in:', JSON.stringify(session.user, null, 2));
      currentUser = session.user;
      const done = await _isOnboardingDone(session.user.id);
      if (done) {
        _revealApp();
      } else {
        _showOnboardingModal(session.user);
      }
    } else {
      currentUser = null;
      _showLoginModal();
    }
  });

  // Initial session check (returning user)
  const { data: { session } } = await _sb.auth.getSession();
  console.log('[auth] Initial session check. Session:', session);
  if (session?.user) {
    console.log('[auth] Returning user found:', JSON.stringify(session.user, null, 2));
    currentUser = session.user;
    const done = await _isOnboardingDone(session.user.id);
    if (done) {
      _revealApp();
    } else {
      _showOnboardingModal(session.user);
    }
  }
  // else: login modal already visible (default state)
}

/* ------------------------------------------------------------------ public helpers */

/** Get the current Supabase JWT (use as Bearer in protected API calls). */
async function getAuthToken() {
  if (!_sb) return null;
  const { data: { session } } = await _sb.auth.getSession();
  return session?.access_token || null;
}

async function signOut() {
  if (!_sb) return;
  await _sb.auth.signOut();
  // onAuthStateChange will trigger login modal
}

/* ------------------------------------------------------------------ click handlers (called from HTML) */

async function signInWithGoogle() {
  if (!_sb) return;
  _setGoogleBtnLoading(true);
  try {
    const redirectUrl = window.location.origin + '/app';
    console.log('[auth] Starting Google OAuth, redirect to:', redirectUrl);
    const { error } = await _sb.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: redirectUrl },
    });
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
  if (login)   login.style.display   = '';
  if (onboard) onboard.style.display = 'none';
  document.getElementById('auth-overlay')?.classList.remove('is-hidden');
  document.body.classList.remove('auth-ready');
}

function _showOnboardingModal(user) {
  const login   = document.getElementById('login-modal');
  const onboard = document.getElementById('onboarding-modal');
  if (login)   login.style.display   = 'none';
  if (onboard) onboard.style.display = '';

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
