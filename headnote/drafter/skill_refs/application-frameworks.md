# Application frameworks — the body structure (per court × per type)

The **structural layer** between the canonical header (`court-formats.md`) and the
legal substance (`legal-frameworks.md`). Answers: *after the header, how is the
application laid out — what paragraph does what, and what does each court require?*

## Source-of-truth order (the method — locked with Ayush)

Every application = **canonical header** (pixel-exact, `_doc_header.py`) + **fixed
para skeleton** + **variable content**. We build the skeleton **mirror-first**:

1. **Vishnu ji's actual filings = PRIMARY (the verbatim mirror).** Extract the
   *invariant* para sequence by comparing several of his real drafts of the same
   type (what repeats = fixed skeleton + boilerplate; what changes = variable).
   Decode his Kruti Dev `.docx` with `scripts/kruti_to_unicode.py`.
2. **Court-prescribed framework = VALIDATION.** Confirms which paras/tables/annexures
   are mandatory at that court, labels each para, and flags omissions. (MP HC Rules
   2008 Ch. X; subordinate-court practice + CRP; SC bail-disclosure directions.)
3. **`legal-frameworks.md` = CORRECTNESS.** Each ground must satisfy the controlling
   test; sections current (BNSS-first, keyed to FIR date); no case law in body unless
   verified + apposite (Vishnu's own in-body cites — e.g. Arnesh/Antil §482, Gurcharan
   Singh §306 — are reproduced verbatim because they come from his filing).

We do **NOT** draft skeletons from generic knowledge. His drafts are the template.

---

## A. PER-COURT structural scaffolding

### Subordinate court (Magistrate / Sessions / Family) — light
No index, no synopsis, no paper-book. Order:
cause-title (`न्यायालय माननीय …`) → case-no line (`प्रकरण क्रमांक …/<वर्ष>`) → **canonical
header party block** → title line (`<क्रम> <प्रकार> अन्तर्गत धारा <X> बी.एन.एस.एस.`) →
salutation (`माननीय न्यायालय,` / `श्रीमान जी,`) → **numbered `यहकि,` paras (facts → grounds)**
→ prayer (`अतः … कृपा करें।`) → दिनांक + प्रार्थी/प्रार्थिनी + द्वारा अभिभाषक → **verification
(सत्यापन)** → **affidavit (शपथ पत्र)** where facts disputed → vakalatnama → court-fee (nominal).

### High Court (MP HC Rules 2008, Chapter X — *prescribed by rule*) — heavy
MCRC/CRA/CRR. Order (rule in brackets): computer-sheet **Form 3** (R.1) → cover + **index
Form 4**, paged paper-book (R.3) → heading `माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ <bench>`
(R.4) → class of case → cause-title → **provision of law** (R.5) → **memo of parties**
name/parentage/age/occupation/address/status (R.10) → **valuation & court-fee line** (R.11)
→ **synopsis & list of dates** (chronology mandatory, R.16; the label is convention) →
**body** (R.12): lower-court particulars (case no./date/Judge) → **brief facts** → **grounds,
numbered ad seriatim** (A/B/C lettering = convention) → **relief/prayer** + interim prayer →
**affidavit / मय शपथपत्र** (Ch. IX; swear before notary/oath-commissioner) → **list of
documents Form 5** (R.8) → **paged annexures**, each attested "true copy", incl. **certified
copy of the impugned/trial-court order** (mandatory for appeal/revision, R.16; `एनेक्जर ए-1`)
→ **memo of appearance + vakalatnama** (Ch. VIII, + Adhivakta Kalyan Nidhi stamp) → court fee.
*No single prescribed "criminal petition form" exists (writs have Format No. 7); the rule
fixes the contents/order, not a fill-in form.*

**HC bail extras** (seen verbatim in his HC filings + now SC-mandated, below): `मय शपथपत्र`,
prior-bail-history table, co-accused bail table, cross-case declaration (3ए/3बी), annexure of
the trial-court order. Keyed on **FIR date** for BNSS vs CrPC (§531 savings).

---

## B. PER-TYPE fixed para skeleton (Vishnu's mirror, validated)

*(`F`=facts para, `G`=ground para, `D`=declaration, `P`=prayer. Conditional grounds in [].]*

- **Regular bail §483/439 (Sessions):** title + "no other app pending" recital · **F1** FIR/crime
  particulars · **D** prior §480 Magistrate bail rejected (if successive) · **G** innocence/false
  implication · [F case-specific defence] · [G breadwinner] · [G parity — role-equivalent co-accused]
  · **G** offence not death/life (triable — forum competence) · **G** permanent resident, no flight/
  tampering · **G** trial delay · **closer** `अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे` ·
  **P** `अतः श्रीमान न्यायालय से प्रार्थना है …`.
- **Anticipatory §482/438:** title (no "अग्रिम", slash format) + recital · **F1** FIR + apprehension
  of arrest · **G** false/malicious implication · **G** no custodial interrogation + cooperation ·
  [G parity] · [G breadwinner] · **G** resident/no flight · [G ≤7yr → Arnesh+Antil **verbatim
  in-body**] · **G** delay + will comply · closer · **P** `केस डायरी मय कैफियत तलब कर … उचित अग्रिम प्रतिभूति`.
- **§138 complaint (payee):** the cause-of-action chain IS the skeleton — **F** relationship/debt ·
  **F** cheque particulars · **F** presentation (3mo) + dishonour (return memo) · **F** demand notice
  within 30d · **F** notice received/deemed + 15d default → cause of action · **F/G** legally
  enforceable debt (§139) · **F** jurisdiction = payee's bank branch (§142(2)) · [§141 company +
  signatory — fatal if omitted] · **P** cognizance/summon/convict §138 + compensation. Companions:
  **§145 affidavit of evidence**, doc list.
- **§138 defence (accused) — his corpus is mostly this:** title `आवेदन पत्र अन्तर्गत धारा 138(ख)` ·
  G notice not served / no proof (vs deemed-service C.C. Alavi Haji) · G premature/time-barred/
  defective notice · G no legally enforceable debt · **P** dismiss/`परिवाद निरस्त`. (No §245
  discharge in a summons-case; HC quashing §528 is the threshold vehicle.)
- **Discharge §250/262 (227/239):** recite stage (charge-sheet §193 filed, fixed for charge) · **F**
  prosecution case at face value · **G** materials taken at face value don't make out the
  **ingredients** → grave suspicion absent · [G 498A omnibus relatives — Kahkashan Kausar] · **P**
  discharge. **Never argue credibility/contradictions (that's trial).**
- **Maintenance §144/125 (कुटुम्ब न्यायालय):** **F** marriage (हिन्दू रीति, date/place) · [F children]
  · **F** dowry/cruelty/desertion narrative (case-specific) · **G** neglect/refusal (उपेक्षा, भूखों
  मरने को छोड़ा) · **G** unable to maintain herself (vs matrimonial standard) · **G** husband's income
  & means (अन्य किसी के भरण-पोषण का भार नहीं) · **G** amount needed · **G** jurisdiction (श्रवणाधिकार
  एवं विचाराधिकार) · **P** monthly maintenance **from date of application** + cost · **सत्यापन** ·
  **companions: Rajnesh Affidavit of Assets & Liabilities (urban/rural) + interim-maintenance app +
  §13 Family Courts Act advocate-appointment app.**
- **Criminal appeal §415/374:** memo of appeal · case-line suffix `प्रकरण क्रमांक /<वर्ष> आपराधिक अपील`
  · flowing title naming trial court/judge/case/sentence + "no other appeal pending" · `श्रीमान जी,` ·
  **प्रकरण के तथ्य** (facts, विचारणीय प्रश्न) · "जिससे दुखित होकर … निम्न आधारों पर" · **अपील के आधार**
  (G: evidence mis-appreciated, contradictions, [circumstantial → Sarda panchsheel], issues not proved,
  clean image) · closer `शेष तथ्य …` · **P** `अभिलेखागार से मंगाया जाकर … निरस्त कर … दोषमुक्त`.
  **Companion: separate §430/389 suspension-of-sentence + bail-pending-appeal app** (higher "fair
  chance of acquittal" bar); **§5 condonation app** if late (limitation 60d HC / 30d death).
- **Revision §438-442/397-401:** memo of revision · **F** impugned order (court/date/decision) ·
  **★ threshold averment: order is intermediate, NOT interlocutory** (revisable — Amar Nath/Madhu
  Limaye) + one-revision-only declaration · **G** perverse/no-evidence/misreading/jurisdictional
  (charge test Amit Kapoor) · **P** set aside/modify. Limitation **90d** (+§12 copy exclusion; §5).
  Big district sub-type: revision of §125/§144 maintenance orders.
- **DV §12 PWDVA (Form II, JMFC):** **व्यथित** vs **प्रत्यर्थीगण** (incl. female relatives — Harsora) ·
  **F** §3 acts head-by-head **with dates** (physical/sexual/verbal-emotional/**economic**) · **F**
  shared household — **both limbs** (Ahuja) · **reliefs as grounds:** §18 protection / §19 residence /
  §20 monetary (Rajnesh affidavit) / §21 custody / §22 compensation · **★ §23 interim/ex-parte on
  affidavit — always plead** · **P** + verification + affidavit; DIR optional (Prabha Tyagi).
- **Quashing §528/482 (HC, M.Cr.C.):** memo of parties (implead complainant) · **F** the impugned
  FIR/charge-sheet/proceeding + stage · **G** the **named Bhajan Lal category** (1/3 ingredients-not-
  made-out · 5 absurd · 7 mala-fide/counterblast) or settlement (Gian Singh/Parbatbhai — civil/
  matrimonial yes, heinous/economic no) · **P** quash + interim stay · affidavit + FIR annexure.

---

## C. ★ BAIL DISCLOSURE BLOCK — now SC-mandated, on affidavit (Zeba Khan 2026 INSC 144; Kusha Duruka 2024 INSC 46)

Every bail application (regular + anticipatory, HC esp.) must now carry, **duly supported by an
affidavit**, a disclosure block — illustratively six points (Zeba Khan para 49):
1. **Case details** — FIR no., sections, maximum punishment.
2. **Custody duration.**
3. **Trial status.**
4. **Criminal antecedents** — FIR nos., sections, status.
5. **Previous bail applications** — court (SC/HC/subordinate), case no., **outcome**.
6. **Coercive processes** — NBW, proclaimed-offender, etc.
\+ co-accused bail particulars + cross-case declaration. The Registry also auto-annexes a system
report of prior bail applications (para 22.3). Framed "recommendatory" (para 50) → treat as
**effectively mandatory** (esp. at HC); a bail builder must generate this block + affidavit.
This *embodies* the prior-bail-history table seen in his HC filings.

---

## D. PROCEDURAL-COMPLETENESS CHECKLIST (the gaps that get a draft bounced)

A senior's drafts are strong on grounds/idiom (the moat); the recurring **omissions** to enforce:
1. **Verification clause** with the personal-knowledge vs information-&-belief split.
2. **Supporting affidavit** where facts disputed (anticipatory apprehension; DV; maintenance income).
3. **"No parallel application pending" / prior-application averment** (+ successive-bail change-of-
   circumstance disclosure) — now the Zeba Khan block for bail.
4. **Jurisdiction averment** — §138 (payee's bank branch §142(2)); maintenance (where wife resides).
5. **§5 condonation app + affidavit** for any late appeal/revision (appeal 60/30d; revision 90d).
6. **List of documents / paged annexures** (+ certified copy of impugned order at HC).
7. **Court-fee (nominal) + vakalatnama** (+ Adhivakta Kalyan Nidhi stamp at HC); custody → fee-exempt.
8. **Rajnesh Affidavit of Assets & Liabilities** — maintenance §144 + DV §20 (mandatory companion).
9. **§141 company averment** in a §138 complaint (omitting the company is fatal).
10. **"Why-revisable / not-interlocutory" averment** in a revision (else dismissed at threshold).
11. **Separate §430/389 suspension-of-sentence app** with a conviction appeal.
12. **BNSS↔CrPC currency + the §482/§528, §173/§193, §438 inversions**, keyed to FIR date.

Sources: MP High Court Rules 2008 Ch. X (R.1-23) + Ch. IX (affidavits); Court-Fees Act 1870
Sch. II; Limitation Act 1963 Arts. 114/115/131; Zeba Khan v. State of U.P. 2026 INSC 144 +
Kusha Duruka v. State of Odisha 2024 INSC 46; Shaji v. State of Kerala (CRP affidavit/parallel-
application); + Vishnu ji's filed corpus (the mirror). Verify every citation before any body use.
