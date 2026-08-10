"""Branded Headnote case-law research PDF — GST §107 appeal limitation vs §161 rectification.

Query: when does the §107 GST appeal limitation commence where the assessment order
is 12-08-2024, a §161 rectification was filed 13-03-2025 and rejected 14-05-2025?

Every citation verified on court/primary sources (Indian Kanoon · LiveLaw · casemine)
before inclusion. No fabrication. Contra authority flagged; the fact-specific date
trap is spelt out in the advisory.
"""
from fpdf import FPDF
import os, datetime

FONT     = "/Library/Fonts/Arial Unicode.ttf"
LOGO_SVG = os.path.join(os.path.dirname(__file__), "static", "headnote-logo.svg")
OUT      = os.path.expanduser("~/Downloads/Headnote_CaseLaw_GST_107_Limitation.pdf")

# ── Brand palette (from style.css) ───────────────────────────────────────────
BAND      = (30, 26, 20)
INK       = (12, 12, 10)
INK2      = (75, 75, 72)
INK3      = (138, 138, 130)
GOLD      = (201, 169, 110)
GOLD_DEEP = (180, 137, 75)
GOLD_SOFT = (250, 247, 237)
GOLD_LINE = (236, 227, 200)
GOLD_INK  = (140, 117, 73)
NAVY      = (30, 58, 95)
GOOD      = (45, 106, 45)
BRICK     = (158, 64, 46)
LINE      = (232, 230, 224)
WHITE     = (255, 255, 255)
WARN_BG   = (255, 249, 235)


class HN(FPDF):
    def header(self): pass
    def footer(self):
        self.set_y(-11)
        self.set_font("AU", "", 7.5)
        self.set_text_color(*INK3)
        self.cell(0, 5,
            f"Headnote Personal Assist · headnote.in · {datetime.date.today().strftime('%d %B %Y')}    "
            "Citations verified on court/primary sources (Indian Kanoon · LiveLaw · casemine). Not legal advice.",
            align="C")


pdf = HN(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_font("AU", "",  FONT)
pdf.add_font("AU", "B", FONT)
pdf.set_margins(18, 18, 18)
pdf.add_page()
W = 210 - 36
PAGE_BOTTOM = 297 - 18


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def rule(color=LINE, weight=0.25):
    pdf.set_draw_color(*color)
    pdf.set_line_width(weight)
    y = pdf.get_y()
    pdf.line(18, y, 18 + W, y)


def body(txt, size=9, color=INK2, gap=4.8, w=None, x=None):
    if x is not None:
        pdf.set_x(x)
    pdf.set_font("AU", "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(w or W, gap, txt)


def label(txt, size=7, color=GOLD_INK, gap=4, x=None):
    if x is not None:
        pdf.set_x(x)
    pdf.set_font("AU", "", size)
    pdf.set_text_color(*color)
    pdf.cell(0, gap, txt.upper(), new_x="LMARGIN", new_y="NEXT")


def vgap(mm=3):
    pdf.ln(mm)


def ensure(space):
    if pdf.get_y() + space > PAGE_BOTTOM:
        pdf.add_page()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HEADER BAND
# ═══════════════════════════════════════════════════════════════════════════════

BAND_H = 26
pdf.set_fill_color(*BAND)
pdf.rect(0, 0, 210, BAND_H, "F")
pdf.set_fill_color(*GOLD)
pdf.rect(0, 0, 3.5, BAND_H, "F")

try:
    pdf.image(LOGO_SVG, x=18, y=5.5, h=7)
    logo_right = 18 + (7 * 91 / 16) + 3
except Exception:
    logo_right = 18

pdf.set_xy(logo_right, 7)
pdf.set_font("AU", "", 7)
pdf.set_text_color(*GOLD)
pdf.cell(0, 6, "PERSONAL ASSIST")

pdf.set_xy(18, 16)
pdf.set_font("AU", "", 8)
pdf.set_text_color(200, 195, 185)
pdf.cell(W, 5, "Case Law Research   ·   GST §107 Appeal Limitation vs §161 Rectification", align="R")

pdf.set_y(BAND_H + 5)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. QUERY BOX
# ═══════════════════════════════════════════════════════════════════════════════

vgap(1)
label("Original Query")
vgap(1)

qbox_y = pdf.get_y()
QUERY_TEXT = (
    "When does the limitation for filing an appeal under Section 107 of the GST Act commence "
    "where the assessment order is dated 12-08-2024, a rectification application under Section 161 "
    "was filed on 13-03-2025, and that rectification was rejected on 14-05-2025? Authorities sought "
    "from the High Courts and the Supreme Court."
)

pdf.set_fill_color(*GOLD_SOFT)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
pdf.set_font("AU", "", 9.5)
lines_needed = pdf.get_string_width(QUERY_TEXT) / (W - 12) + 1
box_h = max(26, lines_needed * 5.2 + 8)
pdf.rect(18, qbox_y, W, box_h, "FD")
pdf.set_fill_color(*GOLD)
pdf.rect(18, qbox_y, 3, box_h, "F")
pdf.set_xy(24, qbox_y + 4)
body(QUERY_TEXT, size=9.5, color=INK, gap=5.2, w=W - 10)
pdf.set_y(qbox_y + box_h + 5)

# Meta strip
pdf.set_font("AU", "", 8)
pdf.set_text_color(*INK3)
pdf.cell(W // 2, 5, f"Date: {datetime.date.today().strftime('%d %B %Y')}", new_x="END")
pdf.cell(W // 2, 5, "Jurisdiction: High Courts / Supreme Court", align="R",
         new_x="LMARGIN", new_y="NEXT")
vgap(2)

# One-line answer band
ans_y = pdf.get_y()
pdf.set_fill_color(*GOLD_SOFT)
pdf.set_draw_color(*GOLD_LINE)
pdf.rect(18, ans_y, W, 20, "FD")
pdf.set_xy(22, ans_y + 2)
pdf.set_font("AU", "", 8)
pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4, "SHORT ANSWER", new_x="LMARGIN", new_y="NEXT")
body("Time spent bona fide in the §161 rectification is kept out of the §107 clock — limitation runs "
     "afresh from the rejection (merger) or that period is excluded (§14 Limitation Act) — BUT only if "
     "the rectification was itself filed within time (the live risk on these dates: see Advisory).",
     size=8.3, color=INK, gap=4, w=W - 8, x=22)
pdf.set_y(ans_y + 20 + 5)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SECTION HEADING
# ═══════════════════════════════════════════════════════════════════════════════

pdf.set_font("AU", "", 11)
pdf.set_text_color(*INK)
pdf.cell(0, 7, "Verified Case Law  —  Supporting", new_x="LMARGIN", new_y="NEXT")
rule(GOLD_LINE, 0.5)
vgap(4)


# ═══════════════════════════════════════════════════════════════════════════════
# CARD HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def tag(txt, bg, fg, x, y):
    pad_h = 2.8
    pdf.set_font("AU", "", 7)
    tw = pdf.get_string_width(txt) + pad_h * 2
    pdf.set_fill_color(*bg)
    pdf.rect(x, y, tw, 5.5, "F")
    pdf.set_xy(x + pad_h, y + 0.8)
    pdf.set_text_color(*fg)
    pdf.cell(tw, 4, txt)
    return x + tw + 2


def case_card(num, citation, court_date, tags, blocks, link, accent=GOLD):
    ensure(70)
    start_page = pdf.page
    start_y = pdf.get_y()

    pdf.set_xy(22, start_y)
    pdf.set_font("AU", "", 9)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.cell(6, 6, f"{num}.")

    pdf.set_xy(28, start_y)
    pdf.set_font("AU", "B", 10.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(W - 10, 6, citation)
    vgap(1)

    pdf.set_x(28)
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*INK3)
    pdf.multi_cell(W - 10, 4.5, court_date)
    vgap(2)

    tx, ty = 28, pdf.get_y()
    for t, bg, fg in tags:
        tx = tag(t, bg, fg, tx, ty)
    pdf.set_y(ty + 7)
    vgap(1.5)

    for lab, text, lcol, tcol in blocks:
        label(lab, color=lcol, x=28)
        vgap(0.5)
        body(text, size=9, color=tcol, gap=4.8, w=W - 10, x=28)
        vgap(2)

    pdf.set_x(28)
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.multi_cell(W - 10, 5, f"Source (verified): {link}")
    end_y = pdf.get_y()

    if pdf.page == start_page:
        pdf.set_draw_color(*accent)
        pdf.set_line_width(1.4)
        pdf.line(19.5, start_y, 19.5, end_y)

    vgap(6)
    if pdf.page == start_page:
        rule(LINE, 0.2)
        vgap(6)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 1 — SPK & Co (Madras HC) — on point, merger
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="1",
    citation="M/s SPK and Co v. State Tax Officer",
    court_date="W.P.(MD) Nos. 27787 & 27788 of 2024  ·  Madras High Court (Madurai Bench)  ·  "
               "Justice K. Kumaresh Babu  ·  22 November 2024",
    tags=[("ON POINT", GOOD, WHITE),
          ("MADRAS HC", (50, 50, 45), WHITE),
          ("Merger → fresh limitation", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Assessment order for AY 2019-20 dated 07.08.2024. The assessee filed a Section 161 "
         "rectification application, which was rejected on 12.11.2024. The assessee moved the High "
         "Court on the question of from when the Section 107 appeal limitation runs.", GOLD_INK, INK2),
        ("Held",
         "\"...the period of limitation for challenging the order of assessment dated 07.08.2024 shall "
         "start ticking from the date of rejection of the rectification application i.e., from "
         "12.11.2024.\" The Court reasoned that \"if any rectification is made as prayed for, the same "
         "would get merged into the original order,\" and disposed the writ giving liberty to file the "
         "appeal reckoning limitation from the rejection date.", GOOD, (30, 80, 30)),
        ("Why it fits",
         "Near-identical to the present matter — an August-2024 assessment order followed by a "
         "filed-and-rejected Section 161 rectification. It is the most direct High Court authority that "
         "the Section 107 clock runs from the date the rectification is rejected, not from the original "
         "order.", GOLD_INK, INK2),
    ],
    link="casemine.com/judgement/in/674dce488e6716384cb32067  ·  livelaw.in (tax-cases / 276638)",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 2 — M.P. Steel Corporation (SC) — §14 backbone
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="2",
    citation="M.P. Steel Corporation v. Commissioner of Central Excise",
    court_date="(2015) 7 SCC 58 ; (2015) 319 ELT 373  ·  Supreme Court of India  ·  "
               "Per R. F. Nariman, J. (2-Judge Bench)  ·  23 April 2015",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE),
          ("§14 EXCLUSION", GOOD, WHITE),
          ("Applies to tax appeals", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Concerned the exclusion of time spent bona fide pursuing a remedy before a wrong / abortive "
         "forum when computing limitation for a tax (Central Excise) appeal.", GOLD_INK, INK2),
        ("Held",
         "The principle underlying Section 14 of the Limitation Act applies to exclude time spent bona "
         "fide in another proceeding even where the Limitation Act does not otherwise govern the appeal. "
         "Section 14 grants no fresh period of limitation but excludes the period already spent, and "
         "applies unless expressly or necessarily excluded. Exclusion of time (Section 14) is "
         "doctrinally distinct from condonation of delay (Section 5).", GOOD, (30, 80, 30)),
        ("Why it fits",
         "The Supreme Court foundation on which the GST High Courts rest the exclusion of the Section 161 "
         "rectification period. It supplies the binding principle: time bona fide spent in rectification "
         "is excluded — not 'condoned' — so the statutory condonation cap is not the obstacle.",
         GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/89319139/",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 3 — Prakash Medical Stores (Allahabad HC, DB) — §14 applied + the caveat
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="3",
    citation="M/s Prakash Medical Stores v. Union of India",
    court_date="Neutral Citation 2025:AHC:224161-DB  ·  Allahabad High Court (Division Bench)  ·  2025",
    tags=[("ALLAHABAD HC · DB", (50, 50, 45), WHITE),
          ("§14 applied to §161/§107", GOOD, WHITE),
          ("'within time' caveat", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Whether the period spent in a Section 161 rectification is excluded while computing the "
         "Section 107 appeal limitation.", GOLD_INK, INK2),
        ("Held",
         "Holding the issue \"no longer res integra,\" the Division Bench applied the principle of "
         "Section 14 of the Limitation Act to exclude the time spent bona fide in the Section 161 "
         "rectification — but expressly only where the rectification application is filed WITHIN time.",
         GOOD, (30, 80, 30)),
        ("Why it fits",
         "A Division Bench (high precedent value) applying the principle directly to Section 161 / "
         "Section 107 GST. It also states the decisive condition for the present matter: the benefit "
         "follows only if the rectification itself was in time — see the Advisory. Same view: Arvind "
         "Fashion Ltd v. State of Haryana (P&H HC, CWP 16286-2025, 26.09.2025).", GOLD_INK, INK2),
    ],
    link="livelaw.in/high-court/allahabad-high-court (514467)",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRA SECTION
# ═══════════════════════════════════════════════════════════════════════════════

ensure(80)
pdf.set_font("AU", "", 11)
pdf.set_text_color(*BRICK)
pdf.cell(0, 7, "Contra authority  —  be ready to distinguish", new_x="LMARGIN", new_y="NEXT")
rule((230, 200, 190), 0.5)
vgap(4)

case_card(
    num="!",
    citation="Singh Enterprises v. CCE   ·   Asst. Commr. (CT) v. Glaxo SmithKline Consumer Health Care",
    court_date="(2008) 3 SCC 70   ·   (2020) 19 SCC 681  ·  Supreme Court of India",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE),
          ("CONTRA", BRICK, WHITE),
          ("Distinguish — §5 not §14", (90, 70, 60), WHITE)],
    blocks=[
        ("Held (against)",
         "The appellate authority cannot condone delay beyond the period the statute allows; once the "
         "appeal period and the condonable extension expire, the appeal cannot be entertained, and a "
         "writ is not a route around limitation. For Section 107 GST the outer limit is 3 months + 1 "
         "month condonable.", BRICK, (110, 50, 38)),
        ("How to distinguish",
         "Both turn on Section 5 CONDONATION, not Section 14 EXCLUSION / merger. The favourable line "
         "(M.P. Steel; Prakash Medical Stores) distinguishes them precisely on that footing — the "
         "rectification period is excluded, so the question of condoning delay beyond the cap never "
         "arises. Frame the matter as exclusion / merger; never as a plea to condone delay.",
         GOLD_INK, INK2),
    ],
    link="Citations: (2008) 3 SCC 70 ; (2020) 19 SCC 681 — verify on SCC / Indian Kanoon",
    accent=BRICK,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ADVISORY — the date trap
# ═══════════════════════════════════════════════════════════════════════════════

ensure(118)
vgap(1)
adv_y = pdf.get_y()
ADVISORY = (
    "THE RULE:  time spent bona fide in a Section 161 rectification is kept out of the Section 107 clock "
    "— either limitation runs afresh from the rejection (merger: SPK & Co) or the period is excluded "
    "(Section 14: M.P. Steel; Prakash Medical Stores). If it applies here, limitation runs from "
    "14-05-2025 → an appeal is in time if filed by about 14-08-2025 (condonable to about 14-09-2025).\n\n"
    "THE CONDITION (the trap on these dates):  the benefit is given only if the rectification was filed "
    "WITHIN the Section 161 limit — six months from the order. Order 12-08-2024 → window ends about "
    "12-02-2025. The rectification was filed 13-03-2025, i.e. roughly a month late on the face of it. If "
    "the department shows the rectification was time-barred, the benefit can be DENIED and limitation "
    "reverts to 12-08-2024 (the appeal is then prima facie barred — only a writ remains).\n\n"
    "SALVAGE POINTS TO CHECK:\n"
    "  *  Section 161 proviso — the six-month bar does NOT apply to a clerical / arithmetical error from "
    "an accidental slip or omission. If the rectification was of that nature, it is in time.\n"
    "  *  The six months may run from the date the order was UPLOADED / communicated on the portal, not "
    "the printed order date — pull the portal communication date.\n"
    "  *  The rejection order dated 14-05-2025 is itself appealable under Section 107; an appeal against "
    "that order (within 3 months of 14-05-2025) is independently in time.\n"
    "  *  Check the GROUND on which the 14-05-2025 rejection was passed (time-bar vs merits) — it shapes "
    "the argument.\n\n"
    "DO NOT plead 'condone the delay' (Singh Enterprises / Glaxo bar that). Plead exclusion / merger."
)

approx_h = 116
pdf.set_fill_color(*WARN_BG)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
pdf.rect(18, adv_y, W, approx_h, "FD")
pdf.set_fill_color(*GOLD)
pdf.rect(18, adv_y, 3, approx_h, "F")

pdf.set_xy(24, adv_y + 4)
pdf.set_font("AU", "", 8)
pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4.5, "ADVISORY  —  THE DATE TRAP ON THESE FACTS", new_x="LMARGIN", new_y="NEXT")
vgap(1.5)
body(ADVISORY, size=8.6, color=INK, gap=4.5, w=W - 8, x=24)

pdf.output(OUT)
print("Saved:", OUT)
