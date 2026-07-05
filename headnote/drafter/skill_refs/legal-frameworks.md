# Legal frameworks — the controlling tests, judgments & section map

The **reasoning layer** behind every template. A draft's grounds are only as good
as the legal test they satisfy. This file is the distilled, **research-verified**
knowledge a drafter must reason from. Citations here are **real and pinpoint-checked
against Indian Kanoon / SCC** — but they remain `verified: false` for *document-body*
use until Vishnu ji confirms each is **apposite** to the matter (non-negotiable rule
#2). They may be used freely for *reasoning* and in the flagged cite-at-hearing list.

> Hallucinated case law is now **judicial misconduct** in India (SC, 27 Feb 2026;
> Bombay HC ₹50k costs; ITAT Bengaluru recall). This is *why* citations never enter a
> body unverified. The whole architecture exists to make that impossible by construction.

---

## 0. BNSS ↔ CrPC section map + the THREE inversions that kill an LLM draft

Map by **function, not arithmetic** — BNSS did not renumber sequentially.

| Function | BNSS | CrPC | Note |
|---|---|---|---|
| Bail (non-bailable) — Sessions/HC | **§483** | §439 | unfettered |
| Bail — Magistrate | **§480** | §437 | barred for death/life (woman/minor/sick proviso) |
| Anticipatory (pre-arrest) | **§482** | §438 | Sessions/HC only |
| Remand / **default bail** | **§187** | §167 | 60/90-day clock |
| Undertrial max-detention | **§479** | §436A | NEW levers (see §4) |
| Arrest-restraint / notice | **§35** | §41/§41A | Arnesh Kumar machinery |
| FIR | **§173** | §154 | ⚠ inversion |
| Charge-sheet / police report | **§193** | §173 | ⚠ inversion |
| Cognizance | §210 | §190 | |
| **Quashing / inherent powers** | **§528** | §482 | ⚠ inversion |
| Appeal from conviction | **§415** | §374 | |
| Appeal from acquittal | §419 | §378 | |
| Suspension of sentence | **§430** | §389 | |
| Revision (HC) | **§442** | §401 | Sessions §438–440 band — verify |
| Maintenance | **§144** | §125 | ⚠ "§144" now = maintenance, NOT prohibitory orders (that's §163) |
| Discharge — Sessions / Magistrate | **§250 / §262** | §227 / §239 | |

**The three silent killers** (an LLM trained pre-2024 emits the *old* meaning):
1. **§482** — CrPC = quashing; **BNSS §482 = anticipatory bail**. Quashing → **§528**.
2. **§173** — CrPC = charge-sheet; **BNSS §173 = FIR**. Charge-sheet → **§193**.
3. **§438** — CrPC = anticipatory bail; BNSS §438 sits in the revision band.

**Which code applies** (BNSS §531 savings): keyed to **FIR date** — FIR before 1 Jul 2024
→ CrPC procedure; on/after → BNSS. Convention: **lead BNSS, CrPC in brackets**
(`धारा 483 बी.एन.एस.एस. (439 दं.प्र.सं.)`). Substantive offence follows the FIR's code
(IPC→BNS: 302→103, 420→318, 376→64). *Gating question for any builder: "FIR date?"*

---

## 1. BAIL — the master reasoning chain

**Step 1 — classify the matter (Satender Kumar Antil v. CBI, (2022) 10 SCC 51).**
This is the *first* thing a bail drafter does; the category dictates which arguments matter.
- **A** — ≤7 yr (not B/D): graduated process (summons→bailable warrant→NBW); lean on
  **Arnesh Kumar** + cooperation + "no custody needed"; often *no bail app needed* if
  not-arrested-in-investigation + cooperated.
- **B** — death / life / >7 yr: decide on **merits** (triple test + factors below).
- **C** — B + **special-act twin conditions** (NDPS §37, PMLA §45, UAPA §43-D(5)): the
  draft is *dead on arrival* if it doesn't confront the embargo.
- **D** — economic offences (no special act): gravity-weighed but **not dispositive**
  (Sanjay Chandra).

**Step 2 — the foundational presumption.** "Bail is the rule, jail the exception"
(Art 21) — **Sanjay Chandra v. CBI, (2012) 1 SCC 40**: bail is to secure attendance,
**not** to punish pre-trial, even in economic offences.

**Step 3 — the two overlapping tests every regular-bail ground must serve:**
- **Triple test** (risk) — **P. Chidambaram v. ED, (2019) 9 SCC 24**: (a) flight risk,
  (b) tampering with evidence, (c) influencing witnesses. *(Deploy for the triple-test
  proposition; do NOT over-read it as pro-bail in PMLA — its facts were conservative.)*
- **Multi-factor checklist** — **Prasanta Kumar Sarkar v. Ashis Chatterjee, (2010) 14
  SCC 496** = **the structural spine of the grounds section**: prima-facie case · nature
  & gravity · severity of punishment · flight risk · character/standing/means · likelihood
  of repetition · apprehension of influencing witnesses · justice being thwarted.
  *Each `यहकि` ground should neutralise one limb of the triple test or one Sarkar factor.*

**Step 4 — overlays that can win independently of merits:**
- **Default / statutory bail** (§187 BNSS / §167(2) CrPC) — **merits-INDEPENDENT**; accrues
  on prosecution's failure to file charge-sheet in **60 days** (≤10 yr) / **90 days**
  (death/life/≥10 yr). **Indefeasible & a fundamental right** — *Bikramjit Singh v. State
  of Punjab, (2020) 12 SCC 327*; pro-liberty computation *Rakesh Kumar Paul v. State of
  Assam, (2017) 15 SCC 67*; **must be availed before challan filed** *Uday Mohanlal Acharya
  v. State of Maharashtra, (2001) 5 SCC 453*. **Time-critical; gravity is irrelevant.**
- **Arrest-necessity** — **Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273**: for ≤7-yr
  offences arrest is **not automatic**; §41A/§35 notice instead; non-compliance *entitles*
  to bail. *(This is the citation Vishnu files verbatim in the §482 ≤7-yr ground — confirmed
  correct.)*
- **Trial delay / prolonged custody (Art 21)** — **Union of India v. K.A. Najeeb, (2021) 3
  SCC 713**: a constitutional court can grant bail **despite a special-statute embargo** when
  Art-21 speedy-trial is breached. Plead exact remand date + witnesses examined/pending +
  realistic trial timeline.
- **§479 BNSS undertrial release** (see §4) — formulaic, near-automatic.

**Anticipatory bail (§482/438):** *Gurbaksh Singh Sibbia v. State of Punjab, (1980) 2 SCC
565* (liberal, no judge-made fetters) · *Sushila Aggarwal v. State (NCT Delhi), (2020) 5
SCC 1* (NOT time-bound; continues till trial end) · *Siddharam Mhetre, (2011) 1 SCC 694*
(factor-list; implication "to injure/humiliate"). Grounds pivot from custody → **apprehension
of arrest + no custodial interrogation needed + cooperation**. *(Antil + Arnesh = verbatim in
Vishnu's real §482 filing.)*

**Conditions must not be onerous** — *Moti Ram v. State of M.P., (1978) 4 SCC 47* (own-bond;
surety to reflect means; no out-of-district bar). Use in surety-modification apps.

**What gets bail REFUSED (drafting traps):** wrong forum (death/life before Magistrate);
boilerplate that ignores the triple test; a successive app that hides the earlier rejection /
pleads no change of circumstance; parity asserted without **role-equivalence**; not confronting
a special-act twin condition; sleeping on default bail; overstated/false grounds; suppressing
other FIRs or higher-court rejections.

---

## 2. MAINTENANCE §144/§125 — Rajnesh is now mandatory law

**★ Rajnesh v. Neha, (2021) 2 SCC 324** — binding nationwide; a maintenance template is
*incomplete* without these:
1. **Affidavit of Assets & Liabilities — MANDATORY for both parties**, in the prescribed
   format (separate **urban** & **rural/agrarian** annexures). Non/false disclosure → adverse
   inference / strike-off defence / perjury. → **ship it as a companion document.**
2. **Maintenance from DATE OF APPLICATION** (not order). → prayer must say so.
3. **Disclose prior maintenance proceedings; amounts already awarded are ADJUSTED/set-off**,
   not stacked. → a mandatory disclosure paragraph in every fresh petition.
4. **Quantum criteria** (holistic, no fixed formula): matrimonial-home standard of living ·
   reasonable needs · wife's qualifications/employment & sacrifices · husband's income/assets/
   liabilities/other dependants · children's costs. (25% of net salary is *illustrative* —
   *Kalyan Dey Chowdhury, (2017) 14 SCC 200* — never plead as a rule.)

Supporting: "unable to maintain herself" ≠ destitute, judged vs matrimonial standard, an
earning wife still qualifies if income inadequate — *Chaturbhuj v. Sita Bai, (2008) 2 SCC
316*. Summary, expeditious, prevents vagrancy; able-bodied husband must earn — *Bhuwan Mohan
Singh v. Meena, (2015) 6 SCC 353*. Dignity, no arbitrary cuts — *Shamima Farooqui v. Shahid
Khan, (2015) 5 SCC 705*. §125 available to a divorced Muslim woman — *Mohd. Abdul Samad v.
State of Telangana* (2024; pull reportable before body use).

---

## 3. APPEAL §415/§374 & DISCHARGE §250-262/§227-239

**Appeal vs conviction:** first appeal = **full re-appreciation** of evidence; "two reasonable
views → the one favouring the accused" — *Chandrappa v. State of Karnataka, (2007) 4 SCC 415*.
Grounds: faulty appreciation · benefit of doubt · **material contradictions/improvements** in
PW testimony (§148 BSA / §181 BNSS) · hostile witness (not wholly effaced; *falsus in uno* not
a rule in India) · circumstantial-chain attack.
- **★ Sharad Birdhichand Sarda v. State of Maharashtra, (1984) 4 SCC 116 — the five
  "panchsheel" of circumstantial evidence** (reproduce verbatim in any circumstantial appeal):
  (1) circumstances **fully established** ("must/should", not "may"); (2) consistent **only**
  with guilt; (3) conclusive nature & tendency; (4) **exclude every hypothesis** but guilt;
  (5) **chain so complete** as to leave no reasonable ground consistent with innocence.
- **Suspension of sentence pending appeal §430/§389:** higher than ordinary bail —
  presumption of innocence gone; must show a **"fair chance of acquittal" / something gross on
  the face of the record**; heinous offences need detailed reasons. A *separate* application.

**Discharge — the test is "GRAVE SUSPICION", not proof, not a mini-trial:**
- *Union of India v. Prafulla Kumar Samal, (1979) 3 SCC 4* (locus classicus, 4 principles):
  judge may **sift & weigh** for the *limited* purpose of a prima-facie case; **grave suspicion
  → frame charge**; suspicion-not-grave / two equal views → **discharge**; judge is **not a mere
  post office** but must **not** hold a mini-trial. Reaffirmed *Sajjan Kumar v. CBI, (2010) 9
  SCC 368*, *P. Vijayan v. State of Kerala, (2010) 2 SCC 398*, *State of Bihar v. Ramesh Singh,
  (1977) 4 SCC 39*.
- **Draft a discharge by showing the materials, TAKEN AT FACE VALUE, do not disclose the
  INGREDIENTS** of the offence — *never* argue credibility/contradictions (that's trial).
- **498A omnibus relatives:** general/omnibus allegations against in-laws without specific role
  = no prima-facie case / abuse of process — **Kahkashan Kausar v. State of Bihar, (2022) 6 SCC
  599**; *Geeta Mehrotra v. State of U.P., (2012) 10 SCC 741*. *(Backs discharge_239's
  family_member_principle ground.)* Alt vehicle for relatives = quashing §528/§482.

---

## 4. NEW BNSS levers worth dedicated builders

- **§479 BNSS — undertrial max-detention release** (replaces §436A; **retrospective**, SC 23
  Aug 2024): release on bond at **½** of max sentence (ordinary) or **⅓** (first-time offender,
  never previously convicted). **Excluded:** death/life offences; **multiple pending cases**.
  Jail Superintendent has an affirmative duty to apply. → **formulaic (custody-days arithmetic)
  + retrospective backlog = ideal deterministic builder.**
- **Default bail §187** — its own time-critical builder (compute the 60/90-day lapse).
- **Staggered police custody** across first 40/60 days (not only first 15) — remand-stage drafting.

---

## 5. The "best drafter" thesis (validated by the research)

Three properties, in priority order:
1. **Zero hallucination by construction** — the model writes **neither facts nor citations**
   into the body. Facts ← OCR/structured input only; citations ← verified library + advocate
   sign-off. The model only *assembles reviewed, genericised grounds* into a *real-filing
   skeleton*. (Exactly Headnote's architecture; misconduct ruling makes this existential.)
2. **Fidelity to a real practitioner's filed templates** — layout, idiom, cause-title, Kruti
   Dev, Legal-page geometry lifted from Vishnu's actual `.docx`. **This is the moat** — what
   makes a Bhopal clerk unable to tell a human didn't type it. Form-banks (courtbook) have the
   headings but not the idiom; raw LLMs have neither + hallucinate.
3. **Correct, current sections keyed to FIR date** — hard BNSS↔CrPC lookup (NOT model recall),
   guarding the §482/§528, §173/§193, §438 inversions.

**Per-type, a winning draft = real skeleton (fidelity) × grounds mapped 1:1 to the controlling
test above (correctness) × zero invented facts/cites (safety) × right section for the FIR date
(currency) × the law-mandated companions (Rajnesh affidavit; verification; affidavit;
vakalatnama).**

---

## 6. §138 NI ACT — cheque dishonour (his corpus #2; heavily DEFENCE-side)

**The offence completes only when ALL of a strict timeline is met** — the timeline IS the case:
cheque drawn for a **legally enforceable debt** → presented within **3 months** (validity) → returned
unpaid (funds insufficient/exceeds arrangement) → payee sends **written demand notice within 30 days
of receiving the return memo** → drawer **fails to pay within 15 days of receiving notice** → offence
complete on day 16 → **complaint within 1 month** of cause of action (§142). Tried **summarily** before
JMFC; complainant's evidence on **affidavit §145**. Jurisdiction = **payee's bank branch** (§142(2),
post-2015 amendment; *Bridgestone India v. Inderpal Singh* (2016) 2 SCC 75). For a **company** cheque,
arraign the company **AND** the signatory/director under **§141** (omitting the company is fatal).

**Presumption §139 + §118(a):** once signature admitted/proved, the court **must** presume the cheque
was for discharge of a debt; burden shifts to the **accused** to rebut on **preponderance of
probabilities** (*Rangappa v. Sri Mohan* (2010) 11 SCC 441; how to rebut: *Basalingappa v. Mudibasappa*
(2019) 5 SCC 418; voluntarily-signed blank cheque still attracts §139: *Bir Singh v. Mukesh Kumar*
(2019) 4 SCC 197).

**DEFENCE side (what Vishnu actually files — his "138" corpus is accused-side):** the strongest *paper*
defences attack **maintainability** and can be fatal/quashable early — (a) **notice not validly served**
[but counter: deemed service if correctly addressed + RPAD — *C.C. Alavi Haji v. Palapetty Muhammed*
(2007) 6 SCC 555; *N. Parameswaran Unni* (2017) 5 SCC 737; bald "I didn't receive it" fails]; (b) notice
**defective** (amount ≠ cheque amount / premature / >30 days after memo); (c) complaint **premature**
(<16 days) or **time-barred** (>1 month, no condonation); (d) **no legally enforceable debt** (security
cheque where debt not yet due — *Sripati Singh* 2021 SCC OnLine SC 1002; time-barred debt — but §25(3)
Contract Act may revive). Debt/§139-rebuttal are **trial** defences (cross-examination, §313), not
threshold wins. There is **no §245 discharge** in a §138 summons-case — the threshold vehicle is
**quashing §528/§482** (HC) (Magistrate cannot recall his summoning order — *Adalat Prasad*). §147 =
**compoundable** at any stage (the realistic exit). §143A interim comp (≤20%, prospective — *G.J. Raja*);
§148 appeal deposit (≥20%, retrospective — *Surinder Singh Deswal*).
**Two templates needed:** payee's complaint (with §145 affidavit + the timeline auto-computed) AND the
accused-side defence pack. **A date-calculator (memo → notice → 15-day → 1-month) is the killer feature.**

## 7. QUASHING §528/§482 (HC inherent power)

Sparingly, "rarest of rare", **no mini-trial / no evidence-weighing** (*R.P. Kapur* AIR 1960 SC 866).
**★ State of Haryana v. Bhajan Lal, 1992 Supp (1) SCC 335 — the SEVEN categories** (para 102): a draft
must **name the category** invoked. Most-used: (1)/(3) allegations taken at **face value don't make out
the offence**; (5) **absurd / inherently improbable**; (7) **mala fide / counterblast** with ulterior
motive. Never argue contradictions/credibility (barred — para 103).
**On settlement** (distinct from §320 compounding — reaches even non-compoundable offences): *Gian Singh
v. State of Punjab* (2012) 10 SCC 303 → *Narinder Singh* (2014) 6 SCC 466 → *Parbatbhai Aahir* (2017) 9
SCC 641. **CAN quash:** predominantly **civil/commercial** or **matrimonial/family** disputes genuinely
settled, conviction remote. **CANNOT:** heinous (murder/rape/dacoity), **economic offences** with public
dimension, special-statute/PC-Act, public-servant offences. **498A relatives:** omnibus allegations with
no specific role = quash (*Kahkashan Kausar* (2022) 6 SCC 599; *Geeta Mehrotra* (2012) 10 SCC 741).
**Vehicle:** M.Cr.C./एम.सी.आर.सी. at HC; **implead the complainant** (Respondent 2); annex FIR copy +
settlement affidavit; interim prayer to stay investigation/trial.

## 8. CRIMINAL REVISION §438-442/§397-401

Supervisory only — **legality/propriety/correctness/regularity**, NOT a re-appreciation of evidence /
appeal substitute (interfere only if perverse / no evidence / misreading). **Two bars a draft must clear
up front:** (a) **§397(2)/§438(2)** — NO revision against a **purely interlocutory** order; framing-of-
charge & refusing-discharge are **"intermediate"** orders and ARE revisable (*Amar Nath* (1977) 4 SCC
137; *Madhu Limaye* (1977) 4 SCC 551); (b) **§397(3)/§438(3)** — **one revision only** (Sessions OR HC,
not both); after a Sessions revision, use **§528/§482 inherent power** (not a 2nd revision). **Cannot**
convert acquittal→conviction (§401(3)/§442(3) — file appeal against acquittal instead). Charge test:
*Amit Kapoor v. Ramesh Chander* (2012) 9 SCC 460 ("uncontroverted allegations prima facie establish the
offence?"). Limitation **90 days** (+ §12 copy-time exclusion; §5 condonation). Big district category:
**revision of §125/§144 maintenance orders**. Plead WHY the order is revisable (intermediate, not
interlocutory) or it's dismissed at the threshold.

## 9. CATEGORY-C BAIL — special-act embargoes (a draft dies if it ignores the twin conditions)

The ordinary triple-test is **not enough**; the draft must affirmatively satisfy/defeat the embargo.
- **NDPS §37** — twin conditions (PP heard + court satisfied "reasonable grounds to believe **not guilty
  AND not likely to re-offend**"). **FIRST plead the quantity bracket** — small/intermediate **escape §37
  entirely** (ordinary bail); only **commercial** triggers it (*State of Kerala v. Rajesh* (2020) 12 SCC
  122; "reasonable grounds" = more than prima facie — *Shiv Shanker Kesari* (2007) 7 SCC 798). Excise
  §67 confessions — *Tofan Singh* (2021) 4 SCC 1. Attack §42/§50/§52A-sampling compliance.
- **UAPA §43-D(5)** — single negative bar: no bail if accusation **"prima facie true"** on the case
  diary, read as a **totality, at face value** (*NIA v. Watali* (2019) 5 SCC 1 — do NOT argue
  inadmissibility). Win by: (a) **ingredients absent** even at face value — membership needs **intent /
  overt act**, not mere association (*Thwaha Fasal* (2021) 5 SCC 446; low probative value — *Vernon
  Gonsalves* 2023); (b) **Article-21 long-delay** — constitutional court grants bail despite §43-D(5)
  (*K.A. Najeeb* (2021) 3 SCC 713; *Sheikh Javed Iqbal* 2024 — Watali is not a precedent to deny bail on
  delay).
- **PMLA §45** — twin conditions, upheld *Vijay Madanlal Choudhary* 2022 SCC OnLine SC 929 (Nikesh
  Tarachand Shah is **spent**). **Lead with the §45 proviso** if available (woman / sick-infirm / <₹1
  crore — discretionary relaxation; "woman" not limited to vulnerable — *K. Kavitha* 2024). Attack
  existence of **"proceeds of crime"**. Article-21 delay reads INTO §45 — *Manish Sisodia* 2024 INSC 595;
  *V. Senthil Balaji* 2024 INSC 739.
- **SC/ST Act §18/§18-A** — bars **anticipatory** bail only (regular bail unaffected). Anticipatory still
  lies where **no prima facie case** under the Act (no caste-nexus / counterblast) — *Prathvi Raj Chauhan*
  (2020) 4 SCC 727. **POCSO** — no twin-condition bar; §29/§30 presumptions operate only after foundational
  facts; "romantic/consensual near-majority" is a recurrent bail ground.

## 10. DOMESTIC VIOLENCE §12 PWDVA + FAMILY

**§12 PWDVA** — **civil reliefs via a criminal (JMFC) forum** (*Kunapareddy* (2016) 11 SCC 774 — amendable;
**§468 CrPC limitation does NOT bar** — *Kamatchi* (2022) 4 SCC 424). Only a **woman** is the "aggrieved
person"; respondents **include female relatives** — **"adult male" struck down** *Hiral Harsora* (2016) 10
SCC 165 (bare Act still misprints "adult male" — always apply Harsora + plead each relative's **specific
role** to survive an omnibus/quash attack). **Shared household §2(s)+§17:** broad, can include in-laws'
property — *Satish Chander Ahuja* (2021) 1 SCC 414 (**overruled** *S.R. Batra*); but plead **both limbs**
(respondent-owned/joint-family **AND** she resided there). Live-in = four-factor test *D. Velusamy* (2010)
10 SCC 469. Right to reside not tied to actual residence; DIR not mandatory — *Prabha Tyagi* 2022. **Plead
§3 acts head-by-head with dates** (physical/sexual/verbal-emotional/**economic** — the under-used hook for
§20). **Reliefs:** protection §18, residence §19, monetary/maintenance §20 (**Rajnesh affidavit applies +
from date of application**), custody §21, compensation §22, **interim/ex-parte §23 on affidavit** (always
plead). His idiom: **व्यथित** / **प्रत्यर्थीगण**, structured like his maintenance petition.
**Family:** §9 HMA restitution — petitioner proves withdrawal, burden shifts to respondent to show
**"reasonable excuse"**; constitutional (*Saroj Rani* (1984) 4 SCC 90; validity re-referred — verify).
§13 divorce — **mental cruelty** illustratives *Samar Ghosh* (2007) 4 SCC 511; **irretrievable breakdown
is NOT a trial-court ground** (route through "cruelty" — *Naveen Kohli*; only SC via Art 142 — *Shilpa
Sailesh*). §13B mutual consent — 6-month wait waivable (*Amardeep Singh*).

## Verified citation ledger (real, pinpoint-checked — `verified: false` for body until Vishnu confirms apposite)

Bail: Satender Kumar Antil (2022) 10 SCC 51 · Arnesh Kumar (2014) 8 SCC 273 · Sushila Aggarwal
(2020) 5 SCC 1 · Gurbaksh Singh Sibbia (1980) 2 SCC 565 · Siddharam Mhetre (2011) 1 SCC 694 ·
P. Chidambaram (2019) 9 SCC 24 · Sanjay Chandra (2012) 1 SCC 40 · Prasanta Kumar Sarkar (2010)
14 SCC 496 · Moti Ram (1978) 4 SCC 47 · K.A. Najeeb (2021) 3 SCC 713 · Bikramjit Singh (2020)
12 SCC 327 · Rakesh Kumar Paul (2017) 15 SCC 67 · Uday Mohanlal Acharya (2001) 5 SCC 453.
Maintenance: Rajnesh v. Neha (2021) 2 SCC 324 · Chaturbhuj v. Sita Bai (2008) 2 SCC 316 ·
Bhuwan Mohan Singh (2015) 6 SCC 353 · Shamima Farooqui (2015) 5 SCC 705 · Kalyan Dey Chowdhury
(2017) 14 SCC 200.
Appeal: Sharad Birdhichand Sarda (1984) 4 SCC 116 · Chandrappa (2007) 4 SCC 415.
Discharge/498A: Prafulla Kumar Samal (1979) 3 SCC 4 · Sajjan Kumar (2010) 9 SCC 368 · P.
Vijayan (2010) 2 SCC 398 · Ramesh Singh (1977) 4 SCC 39 · Kahkashan Kausar (2022) 6 SCC 599 ·
Geeta Mehrotra (2012) 10 SCC 741.
§138 NI: K. Bhaskaran (1999) 7 SCC 510 · Dashrath Rupsingh (2014) 9 SCC 129 · Bridgestone India (2016) 2
SCC 75 · MSR Leathers (2013) 1 SCC 177 · C.C. Alavi Haji (2007) 6 SCC 555 · N. Parameswaran Unni (2017)
5 SCC 737 · Rangappa v. Sri Mohan (2010) 11 SCC 441 · Basalingappa (2019) 5 SCC 418 · Bir Singh (2019) 4
SCC 197 · Meters & Instruments (2018) 1 SCC 560 · In re Expeditious Trial (2021) 16 SCC 116 · A.C.
Narayanan (2014) 11 SCC 790 · G.J. Raja (2019) 8 SCC 535 · Surinder Singh Deswal (2019) 11 SCC 341 ·
Sripati Singh 2021 SCC OnLine SC 1002.
Quashing §528/§482: R.P. Kapur AIR 1960 SC 866 · Bhajan Lal 1992 Supp (1) SCC 335 · Gian Singh (2012) 10
SCC 303 · Narinder Singh (2014) 6 SCC 466 · Parbatbhai Aahir (2017) 9 SCC 641. Revision: Amar Nath (1977)
4 SCC 137 · Madhu Limaye (1977) 4 SCC 551 · V.C. Shukla 1980 Supp SCC 92 · Amit Kapoor (2012) 9 SCC 460.
Category-C bail: Satender Antil (2022) 10 SCC 51 · NDPS §37 — State of Kerala v. Rajesh (2020) 12 SCC 122,
Shiv Shanker Kesari (2007) 7 SCC 798, Tofan Singh (2021) 4 SCC 1 · UAPA §43-D(5) — Watali (2019) 5 SCC 1,
Najeeb (2021) 3 SCC 713, Thwaha Fasal (2021) 5 SCC 446, Vernon 2023 SCC OnLine SC 885, Sheikh Javed Iqbal
2024 SCC OnLine SC 1755 · PMLA §45 — Vijay Madanlal 2022 SCC OnLine SC 929, Nikesh Tarachand Shah (2018)
11 SCC 1 [spent], Manish Sisodia 2024 INSC 595, V. Senthil Balaji 2024 INSC 739 · SC/ST §18-A — Prathvi
Raj Chauhan (2020) 4 SCC 727.
DV/family: Hiral Harsora (2016) 10 SCC 165 · S.R. Batra (2007) 3 SCC 169 [overruled] · Satish Chander
Ahuja (2021) 1 SCC 414 · D. Velusamy (2010) 10 SCC 469 · Prabha Tyagi 2022 LiveLaw(SC) 474 · Kunapareddy
(2016) 11 SCC 774 · Kamatchi (2022) 4 SCC 424 · Saroj Rani (1984) 4 SCC 90 · Samar Ghosh (2007) 4 SCC 511
· Naveen Kohli (2006) 4 SCC 558.
*Pull reportable before any body use:* Mohd. Abdul Samad (2024) · Chandrappa & Kalyan Dey (parallel cite)
· Bridgestone/G.J. Raja/Surinder Deswal SCC pinpoints · Vernon & Sisodia SCC vol · K. Kavitha neutral cite
· S.M.S. Pharmaceuticals (2005) 8 SCC 89 · Indra Sarma (2013) 15 SCC 755 · Shilpa Sailesh (2023) 14 SCC
231 · Amardeep Singh (2017) 8 SCC 746 — none fabricated; each needs Vishnu's apposite-confirmation per rule #2.
