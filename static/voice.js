/* =============================================================================
 * HeadnoteVoice — shared voice engine for the drafting surfaces.
 *
 * Single source of truth for speech-to-text and text-to-speech across
 * /draft/smart (the hands-free conversational drafter) and
 * /draft/template/* (per-field dictation). Loaded the same way as auth.js:
 *     <script src="/static/voice.js?v=YYYYMMDDx"></script>
 *
 * It exposes window.HeadnoteVoice with three concerns:
 *
 *   1. dictate()  — robust speech-to-text with a DUAL path:
 *        • Web Speech API (SpeechRecognition) when available — free, real-time.
 *        • MediaRecorder → POST /api/draft/transcribe (Groq Whisper) fallback
 *          for every browser without usable SpeechRecognition (Firefox, many
 *          in-app webviews, flaky Safari). Whisper handles Hindi + Hinglish.
 *      The proven pattern is lifted from static/draft-discharge.html and
 *      generalised so both pages share one implementation.
 *
 *   2. speak()/shutUp() — text-to-speech read-back via speechSynthesis, with
 *      hi-IN / en-IN voice selection and long-text chunking. Powers the
 *      hands-free "the assistant talks back" experience. shutUp() is barge-in.
 *
 *   3. ensureMicPermission() — pre-warm the mic on a user gesture so the
 *      hands-free loop can auto-open the mic later without being blocked.
 *
 * The module is DOM-agnostic: callers drive their own button/orb visuals from
 * the onState callback, and own the conversation orchestration. Audio is never
 * stored client-side; the Whisper endpoint never persists it server-side.
 * ===========================================================================*/
(function () {
  'use strict';

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  var HAS_NATIVE = !!SR;
  var HAS_RECORDER = !!(window.MediaRecorder && navigator.mediaDevices &&
                        navigator.mediaDevices.getUserMedia);
  var HAS_TTS = ('speechSynthesis' in window) &&
                ('SpeechSynthesisUtterance' in window);

  // -------------------------------------------------------------- language
  function srLang(lang) { return lang === 'en' ? 'en-IN' : 'hi-IN'; }
  function whisperLang(lang) { return lang === 'en' ? 'en' : 'hi'; }

  // ---------------------------------------------------------------- errors
  // Pull a human message out of FastAPI's {detail: ...} error shape.
  function extractErr(obj) {
    if (!obj) return '';
    var d = obj.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length && d[0] && d[0].msg) return d[0].msg;
    if (obj.message) return obj.message;
    return '';
  }

  // ============================================================ TEXT-TO-SPEECH
  var _voices = [];
  function loadVoices() { try { _voices = window.speechSynthesis.getVoices() || []; } catch (e) { _voices = []; } }
  if (HAS_TTS) {
    loadVoices();
    try { window.speechSynthesis.onvoiceschanged = loadVoices; } catch (e) {}
  }

  function pickVoice(lang) {
    if (!_voices.length) loadVoices();
    var want = srLang(lang);                 // 'hi-IN' | 'en-IN'
    var pre = lang === 'en' ? 'en' : 'hi';
    return _voices.find(function (v) { return v.lang === want; }) ||
           _voices.find(function (v) { return v.lang && v.lang.toLowerCase().indexOf(pre) === 0; }) ||
           _voices.find(function (v) { return v.lang && v.lang.toLowerCase().indexOf('en') === 0; }) ||
           null;
  }

  // Chrome silently truncates utterances longer than ~15s. Split on sentence
  // boundaries (Devanagari danda + western punctuation) and queue each chunk.
  function chunkText(text) {
    var parts = String(text).split(/(?<=[।.!?;])\s+/).filter(Boolean);
    var out = [], cur = '';
    for (var i = 0; i < parts.length; i++) {
      if ((cur + ' ' + parts[i]).length > 180 && cur) { out.push(cur); cur = parts[i]; }
      else { cur = cur ? cur + ' ' + parts[i] : parts[i]; }
    }
    if (cur) out.push(cur);
    return out.length ? out : [String(text)];
  }

  var _speaking = false;

  function speak(text, opts) {
    opts = opts || {};
    var onEnd = opts.onEnd || function () {};
    if (!HAS_TTS || !text || opts.muted) { _speaking = false; onEnd(); return null; }
    try { window.speechSynthesis.cancel(); } catch (e) {}
    var lang = opts.lang || 'hi';
    var voice = pickVoice(lang);
    var chunks = chunkText(text);
    var idx = 0;
    _speaking = true;
    function next() {
      if (idx >= chunks.length) { _speaking = false; onEnd(); return; }
      var u = new SpeechSynthesisUtterance(chunks[idx++]);
      if (voice) u.voice = voice;
      u.lang = srLang(lang);
      u.rate = opts.rate || 1.0;
      u.pitch = opts.pitch || 1.0;
      u.onend = next;
      u.onerror = function () { _speaking = false; onEnd(); };   // never strand the loop
      try { window.speechSynthesis.speak(u); }
      catch (e) { _speaking = false; onEnd(); }
    }
    next();
    return true;
  }

  function shutUp() {
    _speaking = false;
    if (!HAS_TTS) return;
    try { window.speechSynthesis.cancel(); } catch (e) {}
  }

  function isSpeaking() {
    return _speaking || (HAS_TTS && (function () { try { return window.speechSynthesis.speaking; } catch (e) { return false; } })());
  }

  // ================================================================ MIC PERMS
  // Request mic access on a user gesture and immediately release it. Returns
  // true if granted. Pre-warming means the hands-free loop's later
  // auto-getUserMedia is not treated as a fresh prompt.
  function ensureMicPermission() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.resolve(false);
    return navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); return true; })
      .catch(function () { return false; });
  }

  // ================================================================== VAD
  // Lightweight energy-based silence detector for the Whisper (recorder) path
  // in hands-free turns: end the turn after a stretch of silence once the
  // lawyer has actually spoken. Native SpeechRecognition does this itself, so
  // VAD is only used on the fallback path.
  function startVad(stream, opts) {
    var AC = window.AudioContext || window.webkitAudioContext;
    var onSilence = opts.onSilence || function () {};
    if (!AC) return { stop: function () {} };          // no WebAudio → manual/maxMs only
    var ctx, raf, stopped = false;
    var threshold = opts.threshold || 0.018;
    var silenceMs = opts.silenceMs || 1800;
    var minSpeechMs = opts.minSpeechMs || 350;
    try {
      ctx = new AC();
      var src = ctx.createMediaStreamSource(stream);
      var analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      var buf = new Uint8Array(analyser.fftSize);
      var speechMs = 0, silentSince = 0, last = performance.now();
      var tick = function () {
        if (stopped) return;
        var now = performance.now();
        var dt = now - last; last = now;
        analyser.getByteTimeDomainData(buf);
        var sum = 0;
        for (var i = 0; i < buf.length; i++) { var v = (buf[i] - 128) / 128; sum += v * v; }
        var rms = Math.sqrt(sum / buf.length);
        if (rms > threshold) { speechMs += dt; silentSince = 0; }
        else if (speechMs > minSpeechMs) { silentSince += dt; if (silentSince >= silenceMs) { stop(); onSilence(); return; } }
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    } catch (e) { return { stop: function () {} }; }
    function stop() {
      if (stopped) return;
      stopped = true;
      if (raf) cancelAnimationFrame(raf);
      try { if (ctx && ctx.state !== 'closed') ctx.close(); } catch (e) {}
    }
    return { stop: stop };
  }

  // ============================================================ SPEECH-TO-TEXT
  // dictate(opts) → handle. opts:
  //   lang           'hi' | 'en'
  //   mode           'continuous' (append phrases until stop) | 'turn' (one
  //                  utterance; auto-ends on silence/end-of-speech)
  //   getAuthHeaders async () => { Authorization } (recorder path only)
  //   onInterim(t)   live partial text (native path)
  //   onFinal(t)     a finalised chunk — per-phrase (continuous) or once (turn)
  //   onState(s)     'listening' | 'processing' | 'stopped'
  //   onError(k,m)   k: denied|no-speech|network|auth|unsupported|transcribe|generic
  //   silenceMs/maxMs  turn-mode tuning (defaults 1800 / 30000)
  // handle: { stop(), isActive() }
  function dictate(opts) {
    opts = opts || {};
    var lang = opts.lang || 'hi';
    var mode = opts.mode || 'continuous';
    var isTurn = mode === 'turn';
    var onInterim = opts.onInterim || function () {};
    var onFinal = opts.onFinal || function () {};
    var onState = opts.onState || function () {};
    var onError = opts.onError || function () {};
    var getAuthHeaders = opts.getAuthHeaders || function () { return Promise.resolve({}); };
    var silenceMs = opts.silenceMs || 1800;
    var maxMs = opts.maxMs || 30000;

    var active = true;
    var done = false;
    var rec = null;             // SpeechRecognition instance
    var recorder = null;        // MediaRecorder
    var stream = null;
    var vad = null;
    var maxTimer = null;

    function finish() {
      if (done) return; done = true; active = false;
      if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
      onState('stopped');
    }

    // ---- Native Web Speech path -----------------------------------------
    function startNative() {
      rec = new SR();
      rec.lang = srLang(lang);
      rec.continuous = !isTurn;            // turn = single utterance, ends itself
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      var finalT = '';
      rec.onresult = function (e) {
        var interim = '';
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var t = e.results[i][0].transcript || '';
          if (e.results[i].isFinal) {
            if (isTurn) { finalT += (finalT ? ' ' : '') + t.trim(); }
            else { var c = t.trim(); if (c) onFinal(c); }   // continuous → emit each phrase
          } else { interim += t; }
        }
        if (interim) onInterim(interim.trim());
        else if (isTurn) onInterim(finalT);
      };
      rec.onerror = function (e) {
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') onError('denied', e.error);
        else if (e.error === 'no-speech') { /* allow restart / quiet end */ }
        else if (e.error === 'network') onError('network', e.error);
        else if (e.error === 'aborted') { /* user stop */ }
        else onError('generic', e.error || 'voice error');
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed' || e.error === 'network') {
          active = false;
        }
      };
      rec.onend = function () {
        if (isTurn) {
          var t = finalT.trim();
          finish();
          if (t) onFinal(t);
          return;
        }
        // continuous: keep the session alive until the caller stops it.
        if (active) { try { rec.start(); } catch (e) { finish(); } }
        else finish();
      };
      onState('listening');
      try { rec.start(); } catch (e) { onError('generic', 'could not start'); finish(); }
      if (isTurn) maxTimer = setTimeout(function () { try { rec.stop(); } catch (e) {} }, maxMs);
    }

    // ---- MediaRecorder → Whisper fallback path --------------------------
    function startRecorder() {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        if (!active) { s.getTracks().forEach(function (t) { t.stop(); }); return; }
        stream = s;
        var mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
          .find(function (m) { return window.MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m); }) || '';
        recorder = mime ? new MediaRecorder(s, { mimeType: mime }) : new MediaRecorder(s);
        var chunks = [];
        recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        recorder.onstop = function () {
          if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); }
          if (vad) { vad.stop(); vad = null; }
          var blob = new Blob(chunks, { type: (recorder && recorder.mimeType) || 'audio/webm' });
          if (!blob.size) { finish(); return; }
          transcribe(blob);
        };
        recorder.start();
        onState('listening');
        if (isTurn) {
          vad = startVad(s, { silenceMs: silenceMs, onSilence: function () { stopRecorder(); } });
          maxTimer = setTimeout(stopRecorder, maxMs);
        }
      }).catch(function () {
        onError('denied', 'mic permission denied');
        finish();
      });
    }

    function transcribe(blob) {
      onState('processing');
      getAuthHeaders().then(function (headers) {
        var fd = new FormData();
        fd.append('file', blob, 'voice.webm');
        return fetch('/api/draft/transcribe?language=' + whisperLang(lang), {
          method: 'POST', headers: headers || {}, body: fd,
        });
      }).then(function (r) {
        if (r.status === 401) { onError('auth', '401'); finish(); return null; }
        if (!r.ok) {
          return r.json().catch(function () { return {}; }).then(function (err) {
            throw new Error(extractErr(err) || ('HTTP ' + r.status));
          });
        }
        return r.json();
      }).then(function (data) {
        if (data && typeof data.text === 'string' && data.text.trim()) {
          var txt = data.text.trim();
          onInterim(txt);
          onFinal(txt);
        }
        finish();
      }).catch(function (e) {
        onError('transcribe', (e && e.message) || 'transcription failed');
        finish();
      });
    }

    function stopRecorder() {
      if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
      if (vad) { vad.stop(); vad = null; }
      if (recorder && recorder.state !== 'inactive') { try { recorder.stop(); } catch (e) {} }
    }

    // ---- start -----------------------------------------------------------
    if (HAS_NATIVE) startNative();
    else if (HAS_RECORDER) startRecorder();
    else { onError('unsupported', 'voice not supported in this browser'); finish(); }

    return {
      isActive: function () { return active && !done; },
      stop: function () {
        active = false;
        if (rec) { try { rec.stop(); } catch (e) {} }
        if (recorder) stopRecorder();
        // native turn/continuous resolve via onend; recorder via onstop.
        // If neither engine is running (already errored), make sure we settle.
        if (!rec && !recorder) finish();
      },
    };
  }

  window.HeadnoteVoice = {
    hasNativeSTT: HAS_NATIVE,
    hasRecorder: HAS_RECORDER,
    hasTTS: HAS_TTS,
    supported: HAS_NATIVE || HAS_RECORDER,
    dictate: dictate,
    speak: speak,
    shutUp: shutUp,
    isSpeaking: isSpeaking,
    ensureMicPermission: ensureMicPermission,
    pickVoice: pickVoice,
  };
})();
