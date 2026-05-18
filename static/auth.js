/**
 * Headnote — Auth module
 * Google OAuth via Supabase + onboarding flow (name, phone, referral).
 *
 * Initialised by initAuth() called from app.js on load.
 * If Supabase is not configured (no env vars set), auth is skipped silently —
 * useful during local dev before Supabase is wired up.
 */

/* ------------------------------------------------------------------ state */

let _sb = null;          // Supabase client
let currentUser = null;  // currently signed-in user object (or null)

/* ------------------------------------------------------------------ boot */

async function initAuth() {
  // Fetch public config from backend (supabase_url + anon key are public — safe to expose)
  let cfg = {};
  try {
    cfg = await fetch('/api/config').then(r => r.json());
  } catch (_) { /* backend unreachable during first load — skip */ }

  if (!cfg.supabase_url || !cfg.supabase_anon_key) {
    console.log('[auth] Supabase not configured — auth skipped (dev mode)');
    return;
  }

  _sb = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  // React to sign-in / sign-out
  _sb.auth.onAuthStateChange(async (_event, session) => {
    if (session?.user) {
      currentUser = session.user;
      _hideLoginModal();
      const done = await _isOnboardingDone(session.user.id);
      if (!done) _showOnboardingModal(session.user);
    } else {
      currentUser = null;
      _showLoginModal();
    }
  });

  // Check existing session (page reload / returning user)
  const { data: { session } } = await _sb.auth.getSession();
  if (!session) {
    _showLoginModal();
  }
}

/* ------------------------------------------------------------------ public helpers */

/** Returns the Supabase JWT for the current session (use in API calls). */
async function getAuthToken() {
  if (!_sb) return null;
  const { data: { session } } = await _sb.auth.getSession();
  return session?.access_token || null;
}

/** Sign out and return to login modal. */
async function signOut() {
  if (!_sb) return;
  await _sb.auth.signOut();
}

/* ------------------------------------------------------------------ modal actions (called from HTML onclick) */

async function signInWithGoogle() {
  if (!_sb) return;
  _setGoogleBtnLoading(true);
  const { error } = await _sb.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + '/app' },
  });
  if (error) {
    _setGoogleBtnLoading(false);
    _showAuthError('Sign in failed: ' + error.message);
  }
  // On success the page redirects — loading state stays until redirect
}

async function submitOnboarding() {
  const name    = document.getElementById('onboard-name')?.value?.trim();
  const rawPhone = document.getElementById('onboard-phone')?.value?.replace(/\D/g, '');
  const referral = document.getElementById('onboard-referral')?.value?.trim();

  // Validate
  if (!name) return _markFieldError('onboard-name', 'Name is required');
  if (!rawPhone || rawPhone.length !== 10) return _markFieldError('onboard-phone', 'Enter a valid 10-digit number');

  const btn = document.getElementById('onboard-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  try {
    await _saveOnboarding(name, '+91' + rawPhone, referral || null);
    _hideOnboardingModal();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Get started →';
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

/* ------------------------------------------------------------------ modal UI helpers */

function _showLoginModal() {
  const overlay = document.getElementById('auth-overlay');
  const login   = document.getElementById('login-modal');
  const onboard = document.getElementById('onboarding-modal');
  if (!overlay) return;
  overlay.classList.add('is-visible');
  login.style.display   = '';
  onboard.style.display = 'none';
}

function _hideLoginModal() {
  // Only hide if onboarding isn't about to show
  const onboard = document.getElementById('onboarding-modal');
  if (onboard?.style.display === '') return; // onboarding is showing
  document.getElementById('auth-overlay')?.classList.remove('is-visible');
}

function _showOnboardingModal(user) {
  const overlay = document.getElementById('auth-overlay');
  const login   = document.getElementById('login-modal');
  const onboard = document.getElementById('onboarding-modal');
  if (!overlay) return;

  // Pre-fill name from Google profile if available
  const googleName = user?.user_metadata?.full_name || user?.user_metadata?.name || '';
  const nameInput = document.getElementById('onboard-name');
  if (nameInput && googleName) nameInput.value = googleName;

  overlay.classList.add('is-visible');
  login.style.display   = 'none';
  onboard.style.display = '';
}

function _hideOnboardingModal() {
  document.getElementById('auth-overlay')?.classList.remove('is-visible');
}

function _setGoogleBtnLoading(loading) {
  const btn = document.getElementById('google-signin-btn');
  if (!btn) return;
  btn.disabled = loading;
  btn.querySelector('.btn-google__label').textContent = loading ? 'Signing in…' : 'Continue with Google';
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
  // Show inline error below field
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
