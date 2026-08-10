"""Branded Headnote case-law research PDF — §201 + §420: the CONTRA (opposite) set.
When the §420 / §201 case will NOT be quashed on a compromise — the limits on Gian Singh.

Follow-up for adv. Jeetisha Rattan (she asked for the opposite of the quashing set).
Cross-references the 'for-quashing' authorities so she has both sides in one report.
Every citation verified on Indian Kanoon / SCC before inclusion. No fabrication.
"""
from fpdf import FPDF
import os, datetime

FONT     = "/Library/Fonts/Arial Unicode.ttf"
LOGO_SVG = os.path.join(os.path.dirname(__file__), "static", "headnote-logo.svg")
OUT      = os.path.expanduser("~/Downloads/Headnote_CaseLaw_201_420_Contra.pdf")

BAND, INK, INK2, INK3 = (30, 26, 20), (12, 12, 10), (75, 75, 72), (138, 138, 130)
GOLD, GOLD_DEEP, GOLD_SOFT, GOLD_LINE, GOLD_INK = (201,169,110), (180,137,75), (250,247,237), (236,227,200), (140,117,73)
NAVY, GOOD, BRICK, LINE, WHITE, WARN_BG = (30,58,95), (45,106,45), (158,64,46), (232,230,224), (255,255,255), (255,249,235)


class HN(FPDF):
    def header(self): pass
    def footer(self):
        self.set_y(-11); self.set_font("AU", "", 7.5); self.set_text_color(*INK3)
        self.cell(0, 5,
            f"Headnote Personal Assist · headnote.in · {datetime.date.today().strftime('%d %B %Y')}    "
            "Citations verified on Indian Kanoon · SCC. Not legal advice.", align="C")


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


# ── HEADER BAND ──
BAND_H = 26
pdf.set_fill_color(*BAND); pdf.rect(0, 0, 210, BAND_H, "F")
pdf.set_fill_color(*GOLD); pdf.rect(0, 0, 3.5, BAND_H, "F")
try:
    pdf.image(LOGO_SVG, x=18, y=5.5, h=7); logo_right = 18 + (7 * 91 / 16) + 3
except Exception:
    logo_right = 18
pdf.set_xy(logo_right, 7); pdf.set_font("AU", "", 7); pdf.set_text_color(*GOLD); pdf.cell(0, 6, "PERSONAL ASSIST")
pdf.set_xy(18, 16); pdf.set_font("AU", "", 8); pdf.set_text_color(200, 195, 185)
pdf.cell(W, 5, "Case Law Research   ·   §201 + §420 — CONTRA: no quashing on settlement", align="R")
pdf.set_y(BAND_H + 5)


# ── QUERY BOX ──
vgap(1); label("The Question (contra)"); vgap(1)
qbox_y = pdf.get_y()
QUERY_TEXT = (
    "Opposite case law — Supreme Court authority where a §420 / §201 case is NOT quashed on a "
    "compromise, and the limits on Gian Singh: for when the matter is an economic / public fraud rather "
    "than a purely private civil dispute."
)
pdf.set_fill_color(*GOLD_SOFT); pdf.set_draw_color(*GOLD_LINE); pdf.set_line_width(0.4)
pdf.set_font("AU", "", 9.5)
lines_needed = pdf.get_string_width(QUERY_TEXT) / (W - 12) + 1
box_h = max(22, lines_needed * 5.2 + 8)
pdf.rect(18, qbox_y, W, box_h, "FD"); pdf.set_fill_color(*GOLD); pdf.rect(18, qbox_y, 3, box_h, "F")
pdf.set_xy(24, qbox_y + 4); body(QUERY_TEXT, size=9.5, color=INK, gap=5.2, w=W - 10)
pdf.set_y(qbox_y + box_h + 5)

pdf.set_font("AU", "", 8); pdf.set_text_color(*INK3)
pdf.cell(W // 2, 5, f"Date: {datetime.date.today().strftime('%d %B %Y')}", new_x="END")
pdf.cell(W // 2, 5, "For: Adv. Jeetisha Rattan  ·  Supreme Court", align="R", new_x="LMARGIN", new_y="NEXT")
vgap(2)

# THE PIVOT band
ans_y = pdf.get_y()
pdf.set_fill_color(*GOLD_SOFT); pdf.set_draw_color(*GOLD_LINE); pdf.rect(18, ans_y, W, 26, "FD")
pdf.set_xy(22, ans_y + 2); pdf.set_font("AU", "", 8); pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4, "THE PIVOT", new_x="LMARGIN", new_y="NEXT")
body("Gian Singh helps ONLY if the §420 is a purely private, civil/commercial dispute. The moment it "
     "carries an economic-fraud / forgery / public dimension (fabricated documents, bogus entities, a "
     "planned fraud, bank or public money), it is an offence against society and settlement is NO ground "
     "to quash (Parbatbhai Aahir; Vikram Doshi). §201 is itself an offence against PUBLIC JUSTICE and is "
     "independent (V.L. Tresa) — so it can survive a private §420 settlement.",
     size=8.3, color=INK, gap=4, w=W - 8, x=22)
pdf.set_y(ans_y + 26 + 5)


# ── SECTION HEADING ──
pdf.set_font("AU", "", 11); pdf.set_text_color(*INK)
pdf.cell(0, 7, "Contra Authority  —  quashing REFUSED (Supreme Court)", new_x="LMARGIN", new_y="NEXT")
rule(GOLD_LINE, 0.5); vgap(4)


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


# ── CASE 1 — Parbatbhai Aahir ──
case_card(
    num="1",
    citation="Parbatbhai Aahir v. State of Gujarat",
    court_date="(2017) 9 SCC 641  ·  Supreme Court of India  ·  Dr. D. Y. Chandrachud, J.  ·  04 October 2017",
    tags=[("THE LIMITS ON GIAN SINGH", GOOD, WHITE), ("SUPREME COURT", (50, 50, 45), WHITE), ("para 16", NAVY, WHITE)],
    blocks=[
        ("Held — para 16",
         "The controlling re-statement of §482 quashing principles. Para 16 carves out the exceptions to "
         "Gian Singh: heinous / serious offences, and ECONOMIC offences \"involving the financial and "
         "economic well-being of the State\", have implications beyond a private dispute; forgery of public "
         "documents and offences with a serious impact on society are NOT to be quashed merely because the "
         "parties have settled — to do so would be \"misplaced sympathy\".", GOOD, (30, 80, 30)),
        ("Why it cuts against quashing",
         "This is the definitive limit on Gian Singh. If the §420 reads as an economic / forgery fraud "
         "rather than a two-party civil dispute, the High Court is justified in DECLINING to quash even on "
         "a genuine compromise — and the ancillary §201 goes on with it.", GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/7293093/",
)

# ── CASE 2 — Vikram Anantrai Doshi ──
case_card(
    num="2",
    citation="State of Maharashtra (CBI) v. Vikram Anantrai Doshi",
    court_date="(2014) 15 SCC 29  ·  Supreme Court of India  ·  19 September 2014",
    tags=[("ECONOMIC OFFENCE — NOT QUASHED", GOOD, WHITE), ("SUPREME COURT", (50, 50, 45), WHITE), ("420 / 467 / 468 / 471", NAVY, WHITE)],
    blocks=[
        ("Facts + Held",
         "Bank fraud through fictitious companies and forged / bogus bills discounted against letters of "
         "credit (§§420/467/468/471/120B). Held: economic offences are PUBLIC wrongs with societal impact; "
         "a civil settlement / repayment does NOT wipe out criminal liability — this is not a simple "
         "borrow-and-repay case. Quashing on the settlement was refused.", GOOD, (30, 80, 30)),
        ("Why it cuts against quashing",
         "A §420-with-forgery economic offence kept alive DESPITE settlement — the direct counter to \"420 "
         "is civil-flavour, so quash on compromise\". Where forgery / fabricated documents / public money "
         "feature, settlement is no exit.", GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/192124141/",
)

# ── CASE 3 — Laxmi Narayan ──
case_card(
    num="3",
    citation="State of M.P. v. Laxmi Narayan",
    court_date="(2019) 5 SCC 688  ·  Supreme Court of India  ·  05 March 2019",
    tags=[("GUIDELINES + LIMITS", GOOD, WHITE), ("SUPREME COURT", (50, 50, 45), WHITE), ("para 15", NAVY, WHITE)],
    blocks=[
        ("Held — para 15",
         "Summarised the law: §482 quashing on settlement is for offences of overwhelmingly civil character "
         "(commercial / matrimonial), but NOT for heinous or serious offences; the SERIOUSNESS of the crime "
         "and its SOCIAL IMPACT are decisive; a court cannot mechanically quash on the sole ground of a "
         "compromise (non-application of mind is unwarranted); §482 is distinct from §320 compounding.",
         GOOD, (30, 80, 30)),
        ("Why it cuts against quashing",
         "Requires the court to weigh seriousness and societal impact — not rubber-stamp a settlement. Lets "
         "the State resist quashing where the §420/§201 conduct is grave or has public consequences.",
         GOLD_INK, INK2),
    ],
    link="indiankanoon.org/doc/149247382/",
)


# ── THE §201 COUNTER + THE OTHER SIDE ──
ensure(80)
pdf.set_font("AU", "", 11); pdf.set_text_color(*NAVY)
pdf.cell(0, 7, "The §201 counter  ·  and the other side (for balance)", new_x="LMARGIN", new_y="NEXT")
rule((200, 210, 225), 0.5); vgap(4)

case_card(
    num="§",
    citation="§201 IPC — an offence against public justice, and independent",
    court_date="V.L. Tresa v. State of Kerala, (2001) 3 SCC 549  ·  Palvinder Kaur, AIR 1952 SC 354  ·  Supreme Court",
    tags=[("§201 SURVIVES", NAVY, WHITE), ("independent offence", (60, 80, 110), WHITE)],
    blocks=[
        ("The counter",
         "§201 (causing disappearance of evidence / screening an offender) is a wrong against the "
         "administration of justice, and is an INDEPENDENT offence — in V.L. Tresa a §201 conviction was "
         "upheld even though the accused was acquitted of the main offence. So the State can argue that "
         "§201 survives a private §420 settlement and should not be quashed with it.", NAVY, (40, 55, 80)),
    ],
    link="Citations: (2001) 3 SCC 549 ; AIR 1952 SC 354",
    accent=NAVY,
)

case_card(
    num="↔",
    citation="The FOR-quashing side (so you have both in one place)",
    court_date="Gian Singh, (2012) 10 SCC 303, para 57  ·  Narinder Singh, (2014) 6 SCC 466, para 29  ·  Ramgopal, (2022) 14 SCC 531",
    tags=[("PRIVATE CIVIL DISPUTE → QUASHABLE", (60, 80, 110), WHITE)],
    blocks=[
        ("If the §420 is purely private / civil",
         "Where the §420 is genuinely a two-party commercial dispute, fully and voluntarily settled, with "
         "no forgery / public element and a remote chance of conviction, the High Court MAY quash the whole "
         "§420 + §201 FIR under §482 (Gian Singh; Ramgopal), applying the Narinder Singh para-29 factors. "
         "The two lines are reconciled by characterisation — see the Advisory.", NAVY, (40, 55, 80)),
    ],
    link="See the companion note: 'Headnote_CaseLaw_201_420_Compounding.pdf'",
    accent=NAVY,
)


# ── ADVISORY ──
ensure(92); vgap(1); adv_y = pdf.get_y()
ADVISORY = (
    "IT ALL TURNS ON CHARACTERISATION of the §420:\n\n"
    "TO RESIST quashing (the contra):  plead the §420 as an ECONOMIC / PUBLIC fraud — a planned scheme, "
    "forged or fabricated documents, bogus entities, loss to a bank / the public, wide impact. Then "
    "Parbatbhai Aahir (para 16) and Vikram Doshi bar quashing on mere settlement. Add that §201 is an "
    "offence against public justice and independent (V.L. Tresa), so it does not fall away with the "
    "private §420 settlement.\n\n"
    "TO OBTAIN quashing (the other side):  keep it strictly a two-party private commercial dispute, fully "
    "and voluntarily settled, no forgery / no public money, conviction remote — Gian Singh (para 57) and "
    "Ramgopal apply, and move at the right stage (Narinder Singh, para 29).\n\n"
    "So the same facts can go either way depending on how the §420 is framed. Match the frame to the side "
    "you are on — and remember §201 cannot be 'compounded' (§320(9)); the only routes are quash (§482) or trial."
)
approx_h = 90
pdf.set_fill_color(*WARN_BG); pdf.set_draw_color(*GOLD_LINE); pdf.set_line_width(0.4); pdf.rect(18, adv_y, W, approx_h, "FD")
pdf.set_fill_color(*GOLD); pdf.rect(18, adv_y, 3, approx_h, "F")
pdf.set_xy(24, adv_y + 4); pdf.set_font("AU", "", 8); pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4.5, "ADVISORY  —  IT TURNS ON CHARACTERISATION", new_x="LMARGIN", new_y="NEXT")
vgap(1.5)
body(ADVISORY, size=8.6, color=INK, gap=4.5, w=W - 8, x=24)

pdf.output(OUT)
print("Saved:", OUT)
