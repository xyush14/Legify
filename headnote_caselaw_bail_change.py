"""Generate a branded Headnote case-law research PDF — Bail / Change of Circumstances.

Query: successive bail application on change of circumstances; filing of charge sheet
after an earlier rejection (court inclined but blocked on the investigation-stage /
technical footing) as a substantial change requiring fresh consideration on merits.
Jurisdiction asked: Bombay High Court / Supreme Court.

Every citation below was verified on Indian Kanoon before inclusion. No fabrication.
"""
from fpdf import FPDF
import os, datetime

FONT     = "/Library/Fonts/Arial Unicode.ttf"
LOGO_SVG = os.path.join(os.path.dirname(__file__), "static", "headnote-logo.svg")
OUT      = os.path.expanduser("~/Downloads/Headnote_CaseLaw_Bail_Change_of_Circumstances.pdf")

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
BRICK     = (158, 64, 46)        # contra / caution accent
BRICK_BG  = (252, 243, 240)
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
            "All citations verified on Indian Kanoon. Not legal advice.",
            align="C")


pdf = HN(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_font("AU", "",  FONT)
pdf.add_font("AU", "B", FONT)
try:
    pdf.set_text_shaping(True)   # correct Devanagari shaping (needs uharfbuzz)
except Exception:
    pass
pdf.set_margins(18, 18, 18)
pdf.add_page()
W = 210 - 36   # usable width
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
    """Add a page if less than `space` mm remain — keeps a card off a page seam."""
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
pdf.cell(W, 5, "Case Law Research   ·   Bail — Change of Circumstances", align="R")

pdf.set_y(BAND_H + 5)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. QUERY BOX
# ═══════════════════════════════════════════════════════════════════════════════

vgap(1)
label("Original Query")
vgap(1)

qbox_y = pdf.get_y()
QUERY_TEXT = (
    "Whether a fresh / successive bail application is maintainable on the ground of "
    "\"change of circumstances\" — specifically, where an earlier bail application was "
    "rejected before the charge sheet (the Court otherwise inclined to grant bail but "
    "held back on the investigation-stage / technical footing), can the filing of the "
    "charge sheet after such rejection be urged as a substantial change of circumstance "
    "requiring the Court to consider bail afresh on merits? Authorities sought from the "
    "Bombay High Court or the Supreme Court."
)

pdf.set_fill_color(*GOLD_SOFT)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
pdf.set_font("AU", "", 9.5)
lines_needed = pdf.get_string_width(QUERY_TEXT) / (W - 12) + 1
box_h = max(28, lines_needed * 5.2 + 8)
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
pdf.cell(W // 2, 5, "Jurisdiction: Bombay High Court / Supreme Court", align="R",
         new_x="LMARGIN", new_y="NEXT")
vgap(5)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SECTION HEADING
# ═══════════════════════════════════════════════════════════════════════════════

pdf.set_font("AU", "", 11)
pdf.set_text_color(*INK)
pdf.cell(0, 7, "न्याय दृष्टांत  (Verified Case Law — supporting)", new_x="LMARGIN", new_y="NEXT")
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
    """blocks: list of (LABEL, text, label_color, text_color)."""
    ensure(70)
    start_page = pdf.page
    start_y = pdf.get_y()

    # Number badge
    pdf.set_xy(22, start_y)
    pdf.set_font("AU", "", 9)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.cell(6, 6, f"{num}.")

    # Citation
    pdf.set_xy(28, start_y)
    pdf.set_font("AU", "B", 10.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(W - 10, 6, citation)
    vgap(1)

    # Court / date meta
    pdf.set_x(28)
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*INK3)
    pdf.multi_cell(W - 10, 4.5, court_date)
    vgap(2)

    # Tags row
    tx, ty = 28, pdf.get_y()
    for t, bg, fg in tags:
        tx = tag(t, bg, fg, tx, ty)
    pdf.set_y(ty + 7)
    vgap(1.5)

    # Content blocks
    for lab, text, lcol, tcol in blocks:
        label(lab, color=lcol, x=28)
        vgap(0.5)
        body(text, size=9, color=tcol, gap=4.8, w=W - 10, x=28)
        vgap(2)

    # Source link
    pdf.set_x(28)
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.cell(0, 5, f"Source (verified): {link}", new_x="LMARGIN", new_y="NEXT")
    end_y = pdf.get_y()

    # Left accent rule — only if the card stayed on one page
    if pdf.page == start_page:
        pdf.set_draw_color(*accent)
        pdf.set_line_width(1.4)
        pdf.line(19.5, start_y, 19.5, end_y)

    vgap(6)
    if pdf.page == start_page:
        rule(LINE, 0.2)
        vgap(6)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 1 — Laxman Irappa Hatti (Bombay HC — squarely on point)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="1",
    citation="Laxman Irappa Hatti & Anr. v. State of Maharashtra",
    court_date="2004 (4) Mh.L.J. 415  ·  Bombay High Court  ·  Justice D. B. Bhosale  ·  "
               "Crl. Appln. No. 38 of 2003  ·  15 July 2004",
    tags=[("ON POINT", GOOD, WHITE),
          ("BOMBAY HC", (50, 50, 45), WHITE),
          ("Charge-sheet = substantial change", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Accused arrested 14.04.2004 in a dowry-death / murder matter. First bail "
         "application was rejected by the Sessions Court on 13.05.2004 while the "
         "investigation was still pending. Charge sheet was filed on 04.06.2004. The "
         "accused then moved a fresh, post-charge-sheet bail application on 16.06.2004, "
         "which the Sessions Court again rejected on 22.06.2004 — holding that filing of "
         "the charge sheet was not a change of circumstance and declining to go into the "
         "merits.", GOLD_INK, INK2),
        ("Held",
         "Para 9: \"Until filing of the chargesheet one of the important facts that weigh "
         "on the mind of a Judge is the continuity of investigation and whether the "
         "investigation will be hampered if the accused is set at large. However, after "
         "filing of the chargesheet, this approach changes... This change, in the "
         "approach of the Court after filing of the chargesheet towards evaluating the "
         "need of keeping the accused in custody, should be termed as substantial "
         "change.\" The Court added it is \"not open for the Court to hold that filing of "
         "the chargesheet is not a substantive change of circumstance and refuse to enter "
         "into merits,\" and that the Court is \"obliged to consider merits of the case "
         "afresh\" on the documents supplied with the charge sheet (S. 207 CrPC).",
         GOOD, (30, 80, 30)),
        ("Why it fits",
         "The Bombay High Court authority directly on the proposition. It holds that the "
         "filing of the charge sheet after an earlier rejection IS a substantial change of "
         "circumstance and that the Court may not refuse to hear the merits. Its reasoning "
         "— that the pre-charge-sheet worry of \"investigation being hampered\" disappears "
         "once investigation is complete — maps exactly onto a case where the Court was "
         "earlier inclined to grant bail but held back on that investigation-stage / "
         "technical footing.", GOLD_INK, INK2),
    ],
    link="https://indiankanoon.org/doc/1507643/",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 2 — Kalyan Chandra Sarkar (SC — the governing test)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="2",
    citation="Kalyan Chandra Sarkar v. Rajesh Ranjan @ Pappu Yadav & Anr.",
    court_date="(2005) 2 SCC 42 ; AIR 2005 SC 921  ·  Supreme Court of India  ·  "
               "Santosh Hegde, S. B. Sinha & Balasubramanyan, JJ.  ·  18 January 2005",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE),
          ("THE TEST", GOOD, WHITE),
          ("Successive bail", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Bail / cancellation matter in which the Supreme Court restated the settled "
         "parameters governing when a second or subsequent bail application may be "
         "entertained after an earlier rejection.", GOLD_INK, INK2),
        ("Held",
         "\"Even though there is room for filing a subsequent bail application in cases "
         "where earlier applications have been rejected, the same can be done if there is "
         "a change in the fact situation or in law which requires the earlier view being "
         "interfered with or where the earlier finding has become obsolete.\" The Court "
         "must give due weight to the grounds on which the earlier / higher court refused "
         "bail, and the same grounds cannot be re-agitated.", GOOD, (30, 80, 30)),
        ("Why it fits",
         "The leading Supreme Court statement of the rule the application must satisfy: a "
         "successive bail plea is maintainable only on a \"change in the fact situation or "
         "in law.\" Pair it with Case 1 — the filing of the charge sheet is precisely such "
         "a change in the fact situation. It also dictates the drafting: expressly show "
         "why the earlier rejection no longer holds (the constraint is gone), instead of "
         "repeating the earlier grounds.", GOLD_INK, INK2),
    ],
    link="https://indiankanoon.org/doc/1521407/",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 3 — Babu Singh (SC — refusal is not res judicata)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="3",
    citation="Babu Singh & Ors. v. State of U.P.",
    court_date="(1978) 1 SCC 579 ; AIR 1978 SC 527  ·  Supreme Court of India  ·  "
               "V. R. Krishna Iyer & D. A. Desai, JJ.  ·  31 January 1978",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE),
          ("REFUSAL ≠ RES JUDICATA", GOOD, WHITE),
          ("Foundational", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "Bail sought afresh after an earlier refusal. The Court considered whether an "
         "earlier order refusing bail bars a later application.", GOLD_INK, INK2),
        ("Held",
         "Para 8: \"An order refusing an application for bail does not necessarily preclude "
         "another, on a later occasion, giving more materials, further developments and "
         "different considerations... An interim direction is not a conclusive "
         "adjudication, and updated reconsideration is not over-turning an earlier "
         "negation.\"", GOOD, (30, 80, 30)),
        ("Why it fits",
         "Foundational Supreme Court authority that an earlier refusal of bail does NOT "
         "operate as res judicata and does not bar a fresh application on \"further "
         "developments and different considerations.\" Directly supports moving afresh "
         "after rejection — especially where the Court was earlier inclined but "
         "constrained, and that constraint (the technical point) has since changed. This "
         "is also the very passage relied on in Laxman Irappa Hatti (Case 1).",
         GOLD_INK, INK2),
    ],
    link="https://indiankanoon.org/doc/1515744/",
    accent=GOLD,
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRA SECTION — must distinguish
# ═══════════════════════════════════════════════════════════════════════════════

ensure(80)
pdf.set_font("AU", "", 11)
pdf.set_text_color(*BRICK)
pdf.cell(0, 7, "सावधान  (Contra authority — be ready to distinguish)",
         new_x="LMARGIN", new_y="NEXT")
rule((230, 200, 190), 0.5)
vgap(4)

case_card(
    num="!",
    citation="Virupakshappa Gouda & Anr. v. State of Karnataka & Anr.",
    court_date="(2017) 5 SCC 406 ; AIR 2017 SC 1685  ·  Supreme Court of India  ·  "
               "Dipak Misra & A. M. Khanwilkar, JJ.  ·  28 March 2017",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE),
          ("CONTRA", BRICK, WHITE),
          ("Distinguish — don't ignore", (90, 70, 60), WHITE)],
    blocks=[
        ("Held (against)",
         "\"Filing of the charge-sheet does not in any manner lessen the allegations made "
         "by the prosecution. On the contrary, filing of the charge-sheet establishes that "
         "after due investigation the investigating agency, having found materials, has "
         "placed the charge-sheet for trial.\" Bail granted on a third application — the "
         "trial court being \"swayed by the factum that when a charge-sheet is filed it "
         "amounts to change of circumstance\" — was set aside and the High Court's "
         "cancellation affirmed. (Grave offence: murder.)", BRICK, (110, 50, 38)),
        ("How to distinguish",
         "This does NOT overrule Laxman Irappa Hatti — the two answer different questions. "
         "The charge sheet does not reduce the GRAVITY / strength of the allegations "
         "(Virupakshappa); but it does remove the NEED for investigation-stage custody "
         "(Laxman Irappa Hatti). So never argue \"charge sheet filed, therefore bail.\" "
         "Argue that the earlier refusal rested on the investigation-stage / custodial "
         "footing — the technical point on which the Court was otherwise inclined to grant "
         "bail — which the charge sheet has now extinguished, coupled with the merits "
         "favourable to the accused. Framed that way you stay within Laxman Irappa Hatti "
         "and clear of Virupakshappa.", GOLD_INK, INK2),
    ],
    link="https://indiankanoon.org/doc/146045597/",
    accent=BRICK,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ADVISORY / STRATEGY BOX
# ═══════════════════════════════════════════════════════════════════════════════

ensure(96)
vgap(1)
adv_y = pdf.get_y()
ADVISORY = (
    "1.  THE TEST  (Kalyan Chandra Sarkar):  a successive bail application is maintainable "
    "only on a \"change in the fact situation or in law.\" So (a) state the date and the "
    "ground of the earlier rejection, then (b) show precisely what has changed.\n\n"
    "2.  THE CHANGE TO PLEAD  (Laxman Irappa Hatti):  before the charge sheet the dominant "
    "concern is that releasing the accused may hamper the ongoing investigation. Once the "
    "charge sheet is filed the investigation is over, that concern disappears, and the "
    "Court is obliged to reconsider custody on the merits afresh — it cannot refuse to "
    "enter the merits.\n\n"
    "3.  FIT TO YOUR FACTS:  where the Court was earlier inclined to grant bail but was "
    "held back on the investigation-stage / \"technical\" footing, the filing of the "
    "charge sheet removes that very footing. That is the substantial (not cosmetic) change.\n\n"
    "4.  AVOID THE TRAP  (Virupakshappa Gouda):  never argue that the charge sheet has "
    "weakened the prosecution case — the Supreme Court has rejected that. Anchor the "
    "change to the end of investigation-stage custody, not to the strength of the "
    "allegations.\n\n"
    "5.  ALSO CITE  (Babu Singh):  an earlier refusal is not res judicata; reconsideration "
    "on \"further developments and different considerations\" is not overturning the "
    "earlier order."
)
HINDI_LINE = (
    "संक्षेप:  आरोप-पत्र दाखिल होने पर अनुसंधान समाप्त हो जाता है — इसलिए हिरासत की "
    "आवश्यकता का आधार समाप्त; यही \"सारभूत परिवर्तन\" है। यह तर्क न दें कि आरोप-पत्र से "
    "अभियोजन के आरोप कमज़ोर हुए।"
)

pdf.set_font("AU", "", 8.8)
# rough height estimate, box auto-extends visually via content
approx_h = 104
pdf.set_fill_color(*WARN_BG)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
pdf.rect(18, adv_y, W, approx_h, "FD")
pdf.set_fill_color(*GOLD)
pdf.rect(18, adv_y, 3, approx_h, "F")

pdf.set_xy(24, adv_y + 4)
pdf.set_font("AU", "", 8)
pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4.5, "ADVISORY  —  HOW TO SATISFY THE COURT", new_x="LMARGIN", new_y="NEXT")
vgap(1.5)
body(ADVISORY, size=8.8, color=INK, gap=4.6, w=W - 8, x=24)
vgap(1)
body(HINDI_LINE, size=8.8, color=GOLD_INK, gap=4.8, w=W - 8, x=24)

pdf.output(OUT)
print("Saved:", OUT)
