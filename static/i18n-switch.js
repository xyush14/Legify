/* Shared regional-language switch for single-render drafting pages.
 *
 * A "single-render" page rebuilds its document HTML on demand and drops it into
 * one container (e.g. #doc-page). This helper adds Marathi (and later bn/gu) to
 * such a page WITHOUT re-implementing rendering: when a regional language is
 * chosen it takes the page's freshly-rendered HINDI HTML, POSTs it to
 * /api/draft/regionalize, and paints the returned regional HTML.
 *
 * Usage on a page:
 *   HeadnoteI18n.attach({
 *     select:      document.getElementById('lang-select'),  // the <select>
 *     docEl:       () => document.getElementById('doc-page'),
 *     renderHindi: () => renderHi(state.answers),           // returns HI html string
 *     onBase:      (lang) => { state.lang = lang; onChange(); }, // hi/en: page's own path
 *     authHeaders: async () => ({...}),                     // optional
 *   });
 *
 * hi/en are handled entirely by the page (onBase). Only mr/bn/gu are routed
 * through the backend here. The page's own render stays the source of truth.
 */
(function (global) {
  var REGIONAL = { mr: 1, bn: 1, gu: 1 };

  async function attach(cfg) {
    var sel = cfg.select;
    if (!sel) return;
    var lastReq = 0;

    async function regionalize(lang) {
      var docEl = cfg.docEl();
      if (!docEl) return;
      // 1) render the page's Hindi document as the source text
      var hindiHtml = cfg.renderHindi();
      docEl.innerHTML = hindiHtml;                 // show Hindi immediately
      // 2) show a lightweight "translating" hint
      var myReq = ++lastReq;
      docEl.setAttribute('data-i18n-busy', '1');
      try {
        var headers = { 'Content-Type': 'application/json' };
        if (cfg.authHeaders) Object.assign(headers, await cfg.authHeaders());
        var r = await fetch('/api/draft/regionalize', {
          method: 'POST', headers,
          body: JSON.stringify({ html: hindiHtml, lang: lang }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        var data = await r.json();
        if (myReq !== lastReq) return;             // user switched again mid-flight
        docEl.innerHTML = data.document || hindiHtml;
      } catch (e) {
        if (myReq !== lastReq) return;
        // Graceful: leave the Hindi document on screen; never blank the canvas.
        if (global.toast) global.toast('Marathi translation unavailable right now — showing Hindi', 'warn', 3000);
      } finally {
        docEl.removeAttribute('data-i18n-busy');
      }
    }

    sel.addEventListener('change', function (e) {
      var lang = e.target.value;
      if (REGIONAL[lang]) {
        // Chrome/UI follows Hindi for regional scripts (Devanagari etc.)
        if (cfg.onBaseChrome) cfg.onBaseChrome('hi');
        regionalize(lang);
      } else {
        lastReq++;                                 // cancel any in-flight regional paint
        cfg.onBase(lang);                          // hi/en: page's native path
      }
    });
  }

  global.HeadnoteI18n = { attach: attach };
})(window);
