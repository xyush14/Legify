/**
 * Headnote — Analytics (PostHog, EU Cloud)
 * ----------------------------------------
 * One shared, self-initializing module loaded in the <head> of every
 * user-facing page. It boots PostHog, then exposes a tiny, stable helper
 * (window.hn) so the rest of the app can fire named funnel events without
 * caring about the SDK.
 *
 * Privacy (NON-NEGOTIABLE — our users are advocates handling client data):
 *   - EU-hosted (eu.i.posthog.com): data residency for DPDP.
 *   - maskAllInputs: every typed value (client facts, search queries, draft
 *     fields) is masked in session replay — it NEVER leaves the browser.
 *   - sensitive rendered text (generated drafts, research results) is masked
 *     via maskTextSelector. Add `ph-mask` / data-ph-mask to anything else
 *     that should be hidden in replay.
 *   - autocapture still records BUTTON / LINK labels (e.g. "Generate draft")
 *     — those are not client data and are what funnels need.
 *
 * The project token below is PostHog's PUBLIC, write-only key. It is designed
 * to be shipped in client code (it cannot read data) — safe to commit.
 *
 * Internal sessions (founders) are flagged is_internal:true at identify time
 * so you can exclude them in PostHog with one filter.
 */
(function () {
  'use strict';

  // ---- config -----------------------------------------------------------
  var PROJECT_TOKEN = 'phc_ydt7d7YqLZmuocWXaeZvJoppHnKV8wC2ZL75Zm8wuF2B';
  var API_HOST = 'https://eu.i.posthog.com';
  var UI_HOST  = 'https://eu.posthog.com';

  // Don't pollute production analytics with local dev sessions.
  var host = location.hostname;
  var IS_DEV = host === 'localhost' || host === '127.0.0.1' || host === '' ||
               host.endsWith('.local') || /^192\.168\./.test(host);
  // Flip to true in DevTools (localStorage._hn_analytics_dev='1') to test locally.
  var FORCE = false;
  try { FORCE = localStorage.getItem('_hn_analytics_dev') === '1'; } catch (e) {}

  // Founder emails — sessions get is_internal:true so they can be filtered out.
  var ADMIN_EMAILS = {
    '20pe3009@rgipt.ac.in': 1,
    'ayushshivhare02@gmail.com': 1,
    'kpal645@gmail.com': 1,
    'vishnushivhare25@gmail.com': 1,
  };

  // ---- public helper (always present, even if PostHog is disabled) -------
  // Safe no-ops when analytics is off (dev) so callers never need to guard.
  window.hn = {
    track: function (event, props) {
      try { if (window.posthog && window.posthog.capture) window.posthog.capture(event, props || {}); } catch (e) {}
    },
    identify: function (user, extra) {
      try {
        if (!user || !window.posthog || !window.posthog.identify) return;
        var meta = user.user_metadata || {};
        var email = (user.email || '').toLowerCase().trim();
        var props = {
          email: email,
          name: meta.full_name || meta.name || (email ? email.split('@')[0] : ''),
          is_internal: !!ADMIN_EMAILS[email],
        };
        if (extra) for (var k in extra) props[k] = extra[k];
        window.posthog.identify(user.id, props);
      } catch (e) {}
    },
    reset: function () {
      try { if (window.posthog && window.posthog.reset) window.posthog.reset(); } catch (e) {}
    },
    enabled: function () { return !IS_DEV || FORCE; },
  };

  if (IS_DEV && !FORCE) {
    // eslint-disable-next-line no-console
    console.log('[analytics] disabled on dev host (' + host + '). Set localStorage._hn_analytics_dev="1" to test.');
    return;
  }

  // ---- PostHog loader snippet (standard, async from CDN) -----------------
  !function (t, e) {
    var o, n, p, r;
    e.__SV || (window.posthog = e, e._i = [], e.init = function (i, s, a) {
      function g(t, e) { var o = e.split('.'); 2 == o.length && (t = t[o[0]], e = o[1]), t[e] = function () { t.push([e].concat(Array.prototype.slice.call(arguments, 0))); }; }
      (p = t.createElement('script')).type = 'text/javascript', p.crossOrigin = 'anonymous', p.async = !0, p.src = s.api_host.replace('.i.posthog.com', '-assets.i.posthog.com') + '/static/array.js',
      (r = t.getElementsByTagName('script')[0]).parentNode.insertBefore(p, r);
      var u = e; for (void 0 !== a ? u = e[a] = [] : a = 'posthog', u.people = u.people || [], u.toString = function (t) { var e = 'posthog'; return 'posthog' !== a && (e += '.' + a), t || (e += ' (stub)'), e; }, u.people.toString = function () { return u.toString(1) + '.people (stub)'; }, o = 'init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug getPageViewId captureTraceFeedback captureTraceMetric'.split(' '), n = 0; n < o.length; n++) g(u, o[n]); e._i.push([i, s, a]); }, e.__SV = 1);
  }(document, window.posthog || []);

  window.posthog.init(PROJECT_TOKEN, {
    api_host: API_HOST,
    ui_host: UI_HOST,
    // Only build person profiles once we know who someone is — anonymous
    // events are still captured (funnels from the landing page work), but we
    // don't pay for / store profiles on bot + bounce traffic.
    person_profiles: 'identified_only',
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: true,
    session_recording: {
      // Mask EVERY typed value — client facts, queries, draft fields.
      maskAllInputs: true,
      // Mask rendered sensitive text (generated drafts / research output).
      // Tag any other private region with class="ph-mask" or data-ph-mask.
      maskTextSelector: '.ph-mask, [data-ph-mask], .draft-output, .draft-result, .result-card, .editor, .doc-body, .answer, .judgment-text',
    },
    loaded: function (ph) {
      // If a session already knows the user (e.g. soft nav), re-identify is
      // cheap and idempotent. auth.js drives the real identify on sign-in.
      try {
        var u = window.headnoteAuth && window.headnoteAuth.getUser && window.headnoteAuth.getUser();
        if (u) window.hn.identify(u);
      } catch (e) {}
    },
  });
})();
