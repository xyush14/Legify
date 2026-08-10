# Headnote drafter — app catalogue & variable spec

*What the app offers (prioritised by Vishnu ji's actual filing volume + daily need),
and — the core promise — exactly **how little the lawyer has to type**. Everything
not listed as a "variable" is FIXED: the canonical header, the para skeleton, the
boilerplate language, the grounds, the sections, the format — all reproduced verbatim
from his filings. The lawyer changes only the case-specific variables below.*

---

## 0. North-star (noted, design later)

The tiered catalogue below is the *launch* surface. The real ambition is a **universal
drafter** — any application type, any court, on the same canonical header + framework
engine (not a fixed list). Tier 1/2 are the proven first set; the architecture
(canonical header + per-court framing + per-type skeleton + field schema) is built to
generalise to "any draft." Revisit the universal design after the bail family ships.

## A. The catalogue — what the app shows

Volume = count in his 1,197-doc corpus. Status: ✅ built · ⟳ built, needs canonical-header refit · ▢ to build.

### Tier 1 — daily drivers (build first)
| Type | Section (BNSS ← CrPC) | Court | Vol. | Status |
|---|---|---|---|---|
| **Regular bail** | §483 ← 439 | Sessions | **208** | ⟳ (next — same treatment) |
| **Cheque bounce — complaint (+ defence)** | §138 NI Act | JMFC | **120** | ✅ canonical + bilingual |
| **Magistrate bail** | §480 ← 437 | JMFC | 71 | ▢ (shares bail engine) |
| **Anticipatory bail** | §482 ← 438 | Sessions/HC | 56 | ⟳ refit |
| **Discharge** | §250/262 ← 227/239 | Sessions/JMFC | 42 | ⟳ refit |

### Tier 2 — frequent
| Type | Section | Court | Vol. | Status |
|---|---|---|---|---|
| Reply / जवाब | — | any | 37 | ▢ |
| Criminal revision | §438–442 ← 397–401 | Sessions/HC | 29 | ▢ |
| Criminal appeal (conviction) | §415 ← 374 | Sessions/HC | 21 | ⟳ refit |
| Maintenance | §144 ← 125 | Family | 19 | ⟳ refit |
| Domestic violence | §12 PWDVA | JMFC | 19 | ▢ |
| Quashing | §528 ← 482 | HC | 8 | ▢ |

### Tier 3 — companions & quick wins
| Type | Note |
|---|---|
| **Vakalatnama** | ⟳ — attaches to every matter |
| **§145 evidence affidavit** | companion to §138 complaint |
| **Rajnesh assets-&-liabilities affidavit** | mandatory companion to maintenance / DV §20 |
| **§479 undertrial-release** | NEW BNSS lever, formulaic (custody-days arithmetic) — high value |
| **§430/389 suspension of sentence** | companion to a conviction appeal |
| **Delay condonation §5 Limitation** | auto-offered when an appeal/revision is time-barred |
| **Affidavit (शपथपत्र) · adjournment · index/list of documents** | procedural attachments |

---

## B. The seamless-experience promise (how little they type)

1. **Header once per matter** — court, case no., party descriptors, advocate, place. Reused
   across every document in that case (bail + vakalatnama + affidavit share it).
2. **OCR auto-fill** — photo of the FIR / cheque + return memo / impugned order →
   auto-fills the FIR/cheque/order variables (the lawyer just confirms).
3. **Toggles, not typing, for conditional grounds** — e.g. "applicant is a woman",
   "co-accused bailed", "trial delayed", "offence ≤ 7 yrs", "company cheque" → the right
   verbatim ground/para switches on. The lawyer picks, doesn't write.
4. **Auto-computed values** — custody days (arrest→today), the §138 15-day expiry + cause-
   of-action date (from notice date), double-the-cheque compensation, the Zeba-Khan bail
   disclosure table — all derived, never typed.
5. **Everything else is fixed** — skeleton, boilerplate, grounds, sections (BNSS-first,
   keyed to FIR date), format. Bilingual at one toggle (हिन्दी ⇄ English).

The target: **a typical draft = header (mostly OCR) + 1 facts narrative + a few toggles.**

---

## C. Per-type variables (what the lawyer changes)

**Common header block (every type — fill once, mostly OCR):** court/bench + city · case
type/no./year · party 1 descriptor (name · parentage पुत्र/पुत्री/पत्नी श्री · age ·
occupation · address · district) · party 2 / State (PS or opposite party) · advocate name
(+ enrolment) · place · date.

Then, per type, ONLY:

- **Regular / Magistrate bail §483/480:** FIR no · PS · district · offence sections · arrest
  date *(→ custody auto-calc)* · prior-bail history (where/when rejected) · facts narrative
  *(OCR/voice)* · co-accused parity (name + status) · **toggles:** woman/sick/minor ·
  breadwinner · ≤7yr (Arnesh) · trial-delay · no-antecedents · investigation-complete.
  *(HC adds the auto-built prior-bail / co-accused / cross-case tables + Zeba-Khan affidavit.)*
- **Anticipatory bail §482:** FIR no · PS · district · sections · apprehension reason · facts
  narrative · co-accused parity · toggles: ≤7yr · breadwinner · no-antecedents.
- **Cheque §138 complaint:** the debt (relationship · what/amount/dates) · cheque (no · bank/
  branch · amount · date) · presentation bank · dishonour (date · reason) · notice (date ·
  mode) · service/known date *(→ 15-day + cause-of-action auto-calc)* · **toggle:** company
  (§141 — company name + signatory role).  *(Defence variant: which limb fails — notice/debt/
  limitation.)*
- **Discharge §239/227:** crime no · PS · offence sections · accused name(s) (singular/plural) ·
  the complainant's allegation · defence facts narrative · **toggles:** no-demand · family-
  member-principle · no-prima-facie.
- **Maintenance §144:** marriage date/place · children (names/ages) · dowry/cruelty/desertion
  narrative · respondent occupation + income · petitioner income (if any) · amount sought.
  *(Auto-attaches the Rajnesh assets affidavit + interim-maintenance app.)*
- **Appeal §415:** convicting court · trial case no · conviction date · sections convicted ·
  sentence · prosecution-facts narrative · grounds-of-appeal narrative · **toggles:** in-custody
  (jail) · fine-deposited · circumstantial (→ Sarda panchsheel) · clean-image.
- **Revision §438-442:** the impugned order (court · date · what it decided) · why it's
  revisable (intermediate, not interlocutory) · grounds narrative.
- **DV §12:** marriage/relationship · shared-household facts · §3 acts narrative (with dates) ·
  reliefs wanted **(toggles:** protection §18 · residence §19 · monetary §20 · custody §21 ·
  compensation §22 · interim §23).
- **Quashing §528:** the impugned FIR/charge-sheet + stage · Bhajan Lal category (toggle: no-
  ingredients / absurd / mala-fide / settlement) · grounds narrative.
- **Vakalatnama:** party role · opposite party · advocate (name + enrolment + address). (Rest fixed.)

---

*Source of truth for every skeleton & boilerplate = Vishnu ji's filed corpus (the mirror),
validated by `application-frameworks.md` (structure) + `legal-frameworks.md` (law). Citations
stay out of the body (cite-at-hearing, verified:false) unless he files them verbatim.*
