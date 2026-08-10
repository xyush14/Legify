# Application taxonomy

## First: which FAMILY is it? (this decides the document's shape)

Everything in the table below is a **court filing** — it has a cause-title, an
opposing party and a prayer. Most of what an advocate writes is not. Before picking a
type, decide the family (`headnote/drafter/doctypes.py`), which follows from **who the
document is addressed to × what instrument it is**:

| Family | Addressed to | Shape |
|---|---|---|
| `court_filing` | a judge / tribunal | cause title · parties · विरुद्ध · grounds · prayer · सत्यापन |
| `authority_application` | police station, Collector/SDM/Tahsildar/RTO, Registrar, bank, employer | सेवा में · विषय · संदर्भ · महोदय · **prose** body · निवेदन · applicant signs · संलग्न |
| `notice` | the other side (or the State u/s 80 CPC) | advocate's block · addressee · on-instructions · numbered facts · demand · time limit · consequence |
| `affidavit` | nobody — sworn | deponent block · sworn paras · verification · attestation |
| `deed` | executed between parties | recitals · operative clause · covenants · schedule · **witnesses** |

A non-court family has **no court name, no case number, no विरुद्ध, no opposing party
and no court प्रार्थना**. Writing one into a cause-title produces a document the
advocate cannot send. Note that the same facts can support both — a seized vehicle can
be asked for at the थाना *and* moved before the Magistrate under BNSS §497/§503; draft
what the advocate asked for and flag the other.

## Court-filing types

Category → type → current section (BNSS, CrPC in brackets). `built` = template
shipped & gated; `phase1` = bail family being authored now; `planned` = later.

## Bail  *(≈ half of all filing volume — Phase 1 focus)*
| Type id | Name | Section (BNSS ← CrPC) | Court | Status |
|---|---|---|---|---|
| `regular_bail_439` | Regular bail — Sessions | 483 ← 439 | sessions | built |
| `regular_bail_hc_439` | Regular / successive bail — High Court | 483 ← 439 | hc | phase1 |
| `bail_437` | Bail — Magistrate | 480 ← 437 | magistrate | built |
| `anticipatory_bail_438` | Anticipatory bail | 482 ← 438 | sessions/hc | phase1 |

## Appeal / revision
| `revision` | Criminal revision | 438/442 ← 397/401 | sessions/hc | planned |
| `appeal` | Criminal appeal (conviction) | 415+ ← 374 | sessions/hc | planned |

## Discharge
| `discharge_227` | Discharge | 250 / 262 ← 227/239 | sessions/magistrate | planned |

## Family
| `maintenance_125` | Maintenance | 144 ← 125 | family | planned |
| `dv_12` | Domestic violence application | §12 PWDVA 2005 | magistrate | planned |
| `hma_9` | Restitution of conjugal rights | §9 HMA 1955 | family | planned |

## Procedural
| `production_91` | Production of documents / statement | 94 ← 91 | magistrate | built (review) |
| `reply_jawav` | Reply / जवाब | — | any | built |
| `affidavit` | Affidavit (शपथ पत्र) | — | any | planned |
| `vakalatnama` | Vakalatnama | — | any | planned |

Notes:
- BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023) replaced CrPC from 2024-07-01.
  Matters with a pre-2024 FIR still run on CrPC — hence BNSS + CrPC-in-brackets.
- BNS (Bharatiya Nyaya Sanhita) replaced IPC; BSA replaced the Evidence Act.
  Offence sections in a matter follow whichever code the FIR was registered under.
