# Court format rules

Format is taken from Vishnu ji's real filed documents — these rules describe what
those documents already do, so authored grounds slot in without disturbing layout.

## ★ THE CANONICAL HEADER — pixel-exact, EVERY application (the "60% win")

Ayush's rule: the **first part of every application is a pixel-exact mirror** of
`legal_petition_template.docx`; only the variables change; then the body begins
point-wise. It is ONE shared component — `headnote/drafter/templates/_doc_header.py`
(`render_header`) — never re-typed per template. Decoded ground-truth spec:

- **Page:** A4 (210×297 mm) portrait; **margins 1.00″ (1440 tw) all four sides**.
- **Font:** **Mangal** (Unicode Devanagari) throughout (NOT Kruti Dev for this format).
- **Descriptor tab:** explicit LEFT tab at **4600 tw = 3.194″ = 81.1 mm** from the
  left margin — the wide gap before the party descriptor block.
- **Type scale:** court name **18pt BOLD underline**; everything else **13pt**.
- **Lines** (align / underline / space-after pt) — *alignment confirmed by Ayush 2026-06-23:*
  - side-line (`बन्दी/आवेदक की ओर से`) — **center** / underline / 2
  - court name — **CENTER** / underline+bold(18pt) / 3
  - case code (`एम.सी.आर.सी.– / <वर्ष>`) — **CENTER** / none / 5
  - petitioner — label `<X> ——` (underline, **left**) + TAB→81.1mm + descriptor
    lines (filled place-values underlined) / block space-after 4
  - `विरुद्ध / Versus` — **centered OVER the descriptor/name column** (sits between
    the two party NAME blocks — NOT page-centered) / none / 4
  - respondent — same as petitioner / block space-after 6
  - title (`<क्रम> <प्रकार> अन्तर्गत धारा <X> <अधिनियम>`) — **CENTER** / underline / 0

So: side-line, court, case, विरुद्ध (over name col) and title are centered; only the
two party blocks are label-left + tab-descriptor. Underline scope = **filled
place-values only** (follow this unless told otherwise).

**Spacing (Ayush — "keep lil space"):** the render opens the .docx's tight space-after
a touch for readability — approx **side 7 / court 9 / case 15 / petitioner 11 /
विरुद्ध 11 / respondent 15 / title 9 pt**, body line-height **~1.45** (descriptor
lines ~1.55). The .docx-fill output should match this roomier spacing, not the
original tight values.

**True pixel-exact FILING output = fill the .docx itself** (placeholder→value) +
append the body; the HTML render (`_doc_header.HEADER_CSS`) is the on-screen review mirror.

---

## Standard top-section — EVERY application (the uniform header) — *(superseded by the canonical header above; kept for the per-forum cause-title defaults)*

Reproduced from Vishnu Ji's filings; confirmed by him. Identical on every draft —
only the court line and case-type label change per forum. ~20% of drafting errors
come from an inconsistent top, so this is fixed and enforced.

1. **Side-line** — *centered*, small: who the draft is on behalf of —
   `बंदी की ओर से` / `आवेदक की ओर से`. In English **`बंदी` → "Applicant"**, never
   "Detenue" (habeas corpus excepted): "On behalf of the Applicant".
2. **Court name** — the single most prominent line, **centered**, in a font large
   enough to fill the line on its own. NO `justify`, NO stretched gaps between words.
   One line, page margins kept. Court text from the cause-title defaults below.
3. **Case-number line** — *centered*: case-type + number + year. Type per forum:
   `एम.सी.आर.सी.` (HC misc-criminal) · `प्रकरण क्रमांक` (Sessions/Magistrate) ·
   `रिट याचिका` (writ) · `अपील` / `पुनरीक्षण` as applicable.
4. **Cause-title** — applicant line, then `विरुद्ध`, then non-applicant line.
   Each party is a FULL descriptor (may run 2-3 lines): name + relationship
   (`पुत्र/पुत्री/पत्नी श्री …` = S/o, D/o, W/o) + age + occupation + residence.
   **Label at the extreme LEFT, descriptor block to its right** (wraps in column);
   `विरुद्ध` (EN "Versus") **centered** on its own line between the two parties:
   ```
   आवेदक/आवेदिका  ————————————————  <नाम>
                                       विरुद्ध
   अनावेदक        ————————————————  म.प्र. शासन
   ```

No other header line (no court address, no coram). Enforced centrally in
`headnote/drafter/compose.py::_generate_document` (mandatory header block that
overrides any per-spec header) + the bail/discharge/complaint canvases' CSS.

## MP district / sessions (`mp_district_krutidev`)  — the current default
- Font: **Kruti Dev 010** (legacy ASCII-mapped; not Unicode). Values are
  converted Unicode→Kruti Dev at fill time by `headnote/drafter/krutidev.py`.
- Page: **Legal, 8.5 × 14 in**. Margins (in): top 1.5, bottom 1.0, left 1.5
  (binding side), right 1.0.
- Cause title: `न्यायालय माननीय <court>, <city> (म.प्र.)` — bold, near top.
- Numbering: grounds open with `यह कि` (often written solid: `यहकि`).
- Blanks: fill-in gaps are **spaces**, never underscores (`_` renders as the
  vowel ऋ in Kruti Dev).
- Punctuation glyphs: `&` → dash (—), `]` → comma, `@` → slash (/),
  `%&` → ":-", `A` → danda (।). Handled by the converter.
- Sentence/abbreviation dots: `0` and `-` render as abbreviation marks
  (म0प्र0 = म.प्र.).

## High Court (MP, Gwalior bench)
- Same font/encoding. Cause title: `माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर`.
- HC bail (successive) additionally carries: an **index/annexure list**, a
  **prior-bail-history table**, a **crime-details table**, a **memo of appearance
  + affidavit**. These are structural tables kept verbatim from the filed doc.

## Cause-title defaults per tier (Hindi)
- magistrate: `न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, <city> (म.प्र.)`
- sessions: `न्यायालय माननीय सत्र न्यायाधीश महोदय, <city> (म.प्र.)`
- hc: `माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर`
- family: `न्यायालय माननीय प्रधान न्यायाधीश, कुटुम्ब न्यायालय, <city> (म.प्र.)`

These are editable fields with the above as defaults — the lawyer adjusts the
bench/city. Other states/courts get their own format id when added.
