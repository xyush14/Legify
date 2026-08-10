"""Branded Headnote case-law research PDF — §201 IPC (dependent) + §420 IPC:
compounding vs quashing-on-settlement.

Query (adv. Jeetisha Rattan, 15-min assist): §201 IPC has no independent identity;
if the main offence §420 is compoundable/settled, is §201 also compoundable so the
case can be compounded/quashed together? SC authority sought (she cited Gian Singh, 2012).

Every citation verified on Indian Kanoon / SCC OnLine / LiveLaw before inclusion.
The premise is corrected: §201 is NOT compoundable (§320) — the route is §482 quashing
on settlement. Contra/caveat (V.L. Tresa: §201 is an independent offence) is flagged.
"""
from fpdf import FPDF
import os, datetime

FONT     = "/Library/Fonts/Arial Unicode.ttf"
LOGO_SVG = os.path.join(os.path.dirname(__file__), "static", "headnote-logo.svg")
OUT      = os.path.expanduser("~/Downloads/Headnote_CaseLaw_201_420_Compounding.pdf")

BAND, INK, INK2, INK3 = (30, 26, 20), (12, 12, 10), (75, 75, 72), (138, 138, 130)
GOLD, GOLD_DEEP, GOLD_SOFT, GOLD_LINE, GOLD_INK = (201,169,110), (180,137,75), (250,247,237), (236,227,200), (140,117,73)
NAVY, GOOD, BRICK, LINE, WHITE, WARN_BG = (30,58,95), (45,106,45), (158,64,46), (232,230,224), (255,255,255), (255,249,235)


class HN(FPDF):
    def header(self): pass
    def footer(self):
        self.set_y(-11)
        self.set_font("AU", "", 7.5)
        self.set_text_color(*INK3)
        self.cell(0, 5,
            f"Headnote Personal Assist · headnote.in · {datetime.date.today().strftime('%d %B %Y')}    "
            "Citations verified on Indian Kanoon · SCC · LiveLaw. Not legal advice.",
            align="C")


pdf = HN(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_font("AU", "", FONT); pdf.add_font("AU", "B", FONT)
pdf.set_margins(18, 18, 18); pdf.add_page()
W = 210 - 36
PAGE_BOTTOM = 297 - 18


def rule(color=LINE, weight=0.25):
    pdf.set_draw_color(*color); pdf.set_line_width(weight); y = pdf.get_y(); pdf.line(18, y, 18 + W, y)

def body(txt, size=9, color=INK2, gap=4.8, w=None, x=None):
    if x is not None: pdf.set_x(x)
    pdf.set_font("AU", "", size); pdf.set_text_color(*color); pdf.multi_cell(w or W, gap, txt)

def label(txt, size=7, color=GOLD_INK, gap=4, x=None):
    if x is not None: pdf.set_x(x)
    pdf.set_font("AU", "", size); pdf.set_text_color(*color); pdf.cell(0, gap, txt.upper(), new_x="LMARGIN", new_y="NEXT")

def vgap(mm=3): pdf.ln(mm)

def ensure(space):
    if pdf.get_y() + space > PAGE_BOTTOM: pdf.add_page()


# ── HEADER BAND ──────────────────────────────────────────────────────────────
BAND_H = 26
pdf.set_fill_color(*BAND); pdf.rect(0, 0, 210, BAND_H, "F")
pdf.set_fill_color(*GOLD); pdf.rect(0, 0, 3.5, BAND_H, "F")
try:
    pdf.image(LOGO_SVG, x=18, y=5.5, h=7); logo_right = 18 + (7 * 91 / 16) + 3
except Exception:
    logo_right = 18
pdf.set_xy(logo_right, 7); pdf.set_font("AU", "", 7); pdf.set_text_color(*GOLD); pdf.cell(0, 6, "PERSONAL ASSIST")
pdf.set_xy(18, 16); pdf.set_font("AU", "", 8); pdf.set_text_color(200, 195, 185)
pdf.cell(W, 5, "Case Law Research   ·   §201 IPC + §420 — Compounding vs Quashing on Settlement", align="R")
pdf.set_y(BAND_H + 5)


# ── QUERY BOX ────────────────────────────────────────────────────────────────
vgap(1); label("Original Query"); vgap(1)
qbox_y = pdf.get_y()
QUERY_TEXT = (
    "Section 201 IPC has no independent identity; so if the main offence — here §420 IPC — is "
    "compoundable, is §201 also compoundable, so that the case can be compounded / quashed together? "
    "Supreme Court authority sought in favour of such an application. (Gian Singh v. State of Punjab, "
    "2012, was cited.)"
)
pdf.set_fill_color(*GOLD_SOFT); pdf.set_draw_color(*GOLD_LINE); pdf.set_line_width(0.4)
pdf.set_font("AU", "", 9.5)
lines_needed = pdf.get_string_width(QUERY_TEXT) / (W - 12) + 1
box_h = max(24, lines_needed * 5.2 + 8)
pdf.rect(18, qbox_y, W, box_h, "FD"); pdf.set_fill_color(*GOLD); pdf.rect(18, qbox_y, 3, box_h, "F")
pdf.set_xy(24, qbox_y + 4); body(QUERY_TEXT, size=9.5, color=INK, gap=5.2, w=W - 10)
pdf.set_y(qbox_y + box_h + 5)

pdf.set_font("AU", "", 8); pdf.set_text_color(*INK3)
pdf.cell(W // 2, 5, f"Date: {datetime.date.today().strftime('%d %B %Y')}", new_x="END")
pdf.cell(W // 2, 5, "For: Adv. Jeetisha Rattan  ·  Supreme Court", align="R", new_x="LMARGIN", new_y="NEXT")
vgap(2)

# Short answer band
ans_y = pdf.get_y()
pdf.set_fill_color(*GOLD_SOFT); pdf.set_draw_color(*GOLD_LINE); pdf.rect(18, ans_y, W, 26, "FD")
pdf.set_xy(22, ans_y + 2); pdf.set_font("AU", "", 8); pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4, "SHORT ANSWER", new_x="LMARGIN", new_y="NEXT")
body("§201 is NOT compoundable under §320 CrPC (it is not in the table) — so it cannot be \"compounded\" "
     "along with §420. BUT the correct route succeeds: on a genuine settlement, the WHOLE §420+§201 FIR can "
     "be QUASHED under §482 CrPC (Gian Singh) — §420 is a civil/commercial-flavour offence and §201 is "
     "ancillary. Caveat: §201 is an independent offence (V.L. Tresa) — plead quashing-on-settlement, not "
     "auto-compounding.",
     size=8.3, color=INK, gap=4, w=W - 8, x=22)
pdf.set_y(ans_y + 26 + 5)


# ── SECTION HEADING ──────────────────────────────────────────────────────────
pdf.set_font("AU", "", 11); pdf.set_text_color(*INK)
pdf.cell(0, 7, "Verified Case Law  —  Supreme Court", new_x="LMARGIN", new_y="NEXT")
rule(GOLD_LINE, 0.5); vgap(4)


# ── CARD HELPERS ─────────────────────────────────────────────────────────────
def tag(txt, bg, fg, x, y):
    pad_h = 2.8; pdf.set_font("AU", "", 7); tw = pdf.get_string_width(txt) + pad_h * 2
    pdf.set_fill_color(*bg); pdf.rect(x, y, tw, 5.5, "F")
    pdf.set_xy(x + pad_h, y + 0.8); pdf.set_text_color(*fg); pdf.cell(tw, 4, txt)
    return x + tw + 2

def case_card(num, citation, court_date, tags, blocks, link, accent=GOLD):
    ensure(70); start_page = pdf.page; start_y = pdf.get_y()
    pdf.set_xy(22, start_y); pdf.set_font("AU", "", 9); pdf.set_text_color(*GOLD_DEEP); pdf.cell(6, 6, f"{num}.")
    pdf.set_xy(28, start_y); pdf.set_font("AU", "B", 10.5); pdf.set_text_color(*INK); pdf.multi_cell(W - 10, 6, citation)
    vgap(1); pdf.set_x(28); pdf.set_font("AU", "", 8); pdf.set_text_color(*INK3); pdf.multi_cell(W - 10, 4.5, court_date)
    vgap(2); tx, ty = 28, pdf.get_y()
    for t, bg, fg in tags: tx = tag(t, bg, fg, tx, ty)
    pdf.set_y(ty + 7); vgap(1.5)
    for lab, text, lcol, tcol in blocks:
        label(lab, color=lcol, x=28); vgap(0.5); body(text, size=9, color=tcol, gap=4.8, w=W - 10, x=28); vgap(2)
    pdf.set_x(28); pdf.set_font("AU", "", 8); pdf.set_text_color(*GOLD_DEEP)
    pdf.multi_cell(W - 10, 5, f"Source (verified): {link}")
    end_y = pdf.get_y()
    if pdf.page == start_page:
        pdf.set_draw_color(*accent); pdf.set_line_width(1.4); pdf.line(19.5, start_y, 19.5, end_y)
    vgap(6)
    if pdf.page == start_page:
        rule(LINE, 0.2); vgap(6)


# ── CASE 1 — Gian Singh ──────────────────────────────────────────────────────
case_card(
    num="1",
    citation="Gian Singh v. State of Punjab",
    court_date="(2012) 10 SCC 303  ·  Supreme Court of India (3-Judge Bench)  ·  "
               "R. M. Lodha, Anil R. Dave & S. J. Mukhopadhaya, JJ.  ·  24 September 2012",
    tags=[("ON POINT — YOU CITED THIS", GOOD, WHITE), ("§482 QUASHING", (50, 50, 45), WHITE), ("420 + 120B facts", NAVY, WHITE)],
    blocks=[
        ("Facts",
         "The accused had been convicted under §§420 & 120B IPC and sought quashing on the basis of a "
         "compromise. The 3-Judge Bench settled the scope of the High Court's inherent power under §482 to "
         "quash proceedings on a settlement, and its distinction from compounding under §320.", GOLD_INK, INK2),
        ("Held — para 57",
         "The §482 power to QUASH is distinct from §320 compounding and is not limited by it. \"Heinous and "
         "serious offences… like murder, rape, dacoity\" cannot be quashed on settlement. But \"criminal "
         "cases having overwhelmingly and pre-dominantly civil flavour… offences arising from commercial, "
         "financial, mercantile, civil, partnership or such like transactions\" MAY be quashed where the "
         "possibility of conviction is remote and continuation would cause oppression/injustice. Approved "
         "B.S. Joshi, Nikhil Merchant and Manoj Sharma.", GOOD, (30, 80, 30)),
        ("Why it fits",
         "This is the authority you cited — and it is the correct vehicle. §420 cheating is precisely a "
         "'civil/commercial-flavour' offence; on a genuine settlement the High Court can quash the entire "
         "FIR, and the ancillary §201 goes with it. Note it is QUASHING under §482, not 'compounding' §201.",
         GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/69949024/",
)

# ── CASE 2 — Narinder Singh ──────────────────────────────────────────────────
case_card(
    num="2",
    citation="Narinder Singh v. State of Punjab",
    court_date="(2014) 6 SCC 466  ·  Supreme Court of India  ·  27 March 2014",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE), ("THE GUIDELINES", GOOD, WHITE), ("§320 vs §482", NAVY, WHITE)],
    blocks=[
        ("Held — para 29 (29.1–29.7)",
         "Laid down the guidelines for quashing on compromise. It draws the exact distinction you need: §320 "
         "compounding is confined to listed offences and is guided only by the compromise; §482 quashing is "
         "wider, guided by whether the ends of justice justify it. Offences with a civil/commercial character "
         "and private disputes are fit for quashing on settlement; offences against society / heinous ones are "
         "not. Timing: exercise it after the charge-sheet/at trial, and refrain once evidence is nearly complete.",
         GOOD, (30, 80, 30)),
        ("Why it fits",
         "Supplies the framework and the §320-vs-§482 distinction that answers the 'is §201 compoundable?' "
         "confusion directly: don't compound §201 — seek quashing of the whole §420/§201 case on the "
         "settlement, and satisfy the para-29 factors (civil flavour, voluntary compromise, stage).", GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/160278245/",
)

# ── CASE 3 — Ramgopal ────────────────────────────────────────────────────────
case_card(
    num="3",
    citation="Ramgopal v. State of Madhya Pradesh",
    court_date="(2022) 14 SCC 531 ; 2021 SCC OnLine SC 834  ·  Supreme Court of India  ·  29 September 2021",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE), ("RECENT — REAFFIRMS", GOOD, WHITE), ("non-compoundable", NAVY, WHITE)],
    blocks=[
        ("Held",
         "Reaffirmed that a High Court under §482 (and the Supreme Court under Article 142) can quash even "
         "NON-COMPOUNDABLE offences on a compromise — \"beyond the metes and bounds of §320\". Unlike §320, "
         "where the court is squarely guided by the compromise for listed offences, §482 is the extraordinary "
         "power. Factors: nature/effect of the offence on society, seriousness of injury, the voluntary nature "
         "of the compromise, and the accused's conduct.", GOOD, (30, 80, 30)),
        ("Why it fits",
         "The most recent, cleanest statement that 'not compoundable under §320' is NOT the end of the road — "
         "§482 quashing on settlement is available. Directly meets the 'compoundable' framing: §201 need not "
         "be compoundable for the case to end on a genuine compromise.", GOLD_INK, INK2),
    ],
    link="livelaw.in — Ramgopal v. State of M.P. (LL 2021 SC 516)",
)


# ── CONTRA / CAUTION ─────────────────────────────────────────────────────────
ensure(80)
pdf.set_font("AU", "", 11); pdf.set_text_color(*BRICK)
pdf.cell(0, 7, "Caveat  —  the premise needs correcting", new_x="LMARGIN", new_y="NEXT")
rule((230, 200, 190), 0.5); vgap(4)

case_card(
    num="!",
    citation="V.L. Tresa v. State of Kerala   ·   Palvinder Kaur v. State of Punjab",
    court_date="(2001) 3 SCC 549   ·   AIR 1952 SC 354  ·  Supreme Court of India  ·  + §320(9) CrPC",
    tags=[("SUPREME COURT", (50, 50, 45), WHITE), ("CAVEAT", BRICK, WHITE), ("§201 is independent", (90, 70, 60), WHITE)],
    blocks=[
        ("Held (against the premise)",
         "§201 IPC is an INDEPENDENT offence: in V.L. Tresa the Court UPHELD a §201 conviction even though the "
         "accused was acquitted of the main offence (§302). Palvinder Kaur requires proof the main offence was "
         "actually committed (not mere suspicion). Separately, §320(9) CrPC bars compounding any offence not "
         "listed — and §201 is not listed. So the premise \"§201 has no independent identity, hence "
         "auto-compoundable with §420\" is legally imprecise.", BRICK, (110, 50, 38)),
        ("How to use it",
         "Do NOT argue that §201 is 'compoundable' or 'automatically dies' with §420 — the State will cite "
         "V.L. Tresa. Instead argue: the §420 dispute is essentially civil/commercial and is genuinely "
         "settled; continuing the ancillary §201 alone (screening an offender for a cheating that is now "
         "resolved) is futile and oppressive; therefore quash the ENTIRE FIR under §482 (Gian Singh / "
         "Ramgopal). Frame it as quashing-on-settlement, not compounding.", GOLD_INK, INK2),
    ],
    link="Citations: (2001) 3 SCC 549 ; AIR 1952 SC 354 — verify on SCC / Indian Kanoon",
    accent=BRICK,
)


# ── ADVISORY ─────────────────────────────────────────────────────────────────
ensure(96); vgap(1); adv_y = pdf.get_y()
ADVISORY = (
    "THE VEHICLE:  file a §482 CrPC quashing petition in the High Court on the strength of the compromise — "
    "not a §320 compounding application (§201 cannot be compounded; §320(9)).\n\n"
    "WHAT TO PLEAD (from the three judgments):\n"
    "  *  §420 is an offence of overwhelmingly civil / commercial / financial flavour, and the dispute is "
    "genuinely and voluntarily settled (Gian Singh, para 57).\n"
    "  *  §201 is merely ancillary to that §420 transaction; with the underlying cheating settled, the "
    "possibility of conviction is remote and continuation would be oppression (Gian Singh).\n"
    "  *  Satisfy the Narinder Singh para-29 factors — civil character, voluntariness, and the stage of the "
    "case (move after charge-sheet; don't wait till evidence is complete).\n"
    "  *  A non-compoundable tag is no bar to quashing on compromise (Ramgopal).\n\n"
    "AVOID:  arguing that §201 is 'compoundable' or that it 'has no independent existence' for conviction — "
    "V.L. Tresa says a §201 conviction can stand even without the main-offence conviction. Keep the argument "
    "on the settlement + civil flavour, and seek to quash the whole FIR (§420 + §201) together."
)
approx_h = 95
pdf.set_fill_color(*WARN_BG); pdf.set_draw_color(*GOLD_LINE); pdf.set_line_width(0.4); pdf.rect(18, adv_y, W, approx_h, "FD")
pdf.set_fill_color(*GOLD); pdf.rect(18, adv_y, 3, approx_h, "F")
pdf.set_xy(24, adv_y + 4); pdf.set_font("AU", "", 8); pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4.5, "ADVISORY  —  HOW TO RUN THE APPLICATION", new_x="LMARGIN", new_y="NEXT")
vgap(1.5)
body(ADVISORY, size=8.6, color=INK, gap=4.5, w=W - 8, x=24)

pdf.output(OUT)
print("Saved:", OUT)
