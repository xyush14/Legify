"""Generate a simple, team-friendly pricing-proposal PDF for Headnote."""
from fpdf import FPDF
from fpdf.fonts import FontFace

FONT = "/Library/Fonts/Arial Unicode.ttf"  # has the ₹ glyph

INK   = (28, 28, 28)
MUTE  = (110, 110, 110)
ACCENT= (20, 70, 120)     # deep blue
GREEN = (22, 110, 70)
BAND  = (26, 33, 46)      # dark header band
LINE  = (220, 220, 220)
SOFT  = (244, 246, 249)
GOLD  = (250, 244, 230)

R = "Rs "  # the installed Arial Unicode predates the ₹ glyph; "Rs " renders everywhere


class PDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-13)
        self.set_font("AU", "", 8)
        self.set_text_color(*MUTE)
        self.cell(0, 6, "Headnote · pricing proposal for team review · May 2026   —   "
                        "numbers are planning estimates", align="C")


pdf = PDF(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=16)
pdf.add_font("AU", "", FONT)
pdf.add_font("AU", "B", FONT)   # same file; emphasis via size+color
pdf.set_margins(16, 16, 16)
pdf.add_page()
W = 210 - 32  # usable width


def h_band(title, sub):
    pdf.set_fill_color(*BAND)
    pdf.rect(16, pdf.get_y(), W, 20, "F")
    y = pdf.get_y()
    pdf.set_xy(20, y + 4)
    pdf.set_font("AU", "", 16); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 7, title)
    pdf.set_xy(20, y + 12)
    pdf.set_font("AU", "", 9); pdf.set_text_color(200, 205, 215)
    pdf.cell(0, 5, sub)
    pdf.set_y(y + 20 + 5)


def section(title, color=ACCENT):
    pdf.ln(2)
    pdf.set_font("AU", "", 12.5); pdf.set_text_color(*color)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE); pdf.set_line_width(0.3)
    pdf.line(16, pdf.get_y(), 16 + W, pdf.get_y())
    pdf.ln(2)


def body(txt, size=10, color=INK, gap=5):
    pdf.set_font("AU", "", size); pdf.set_text_color(*color)
    pdf.multi_cell(W, gap, txt)


# ---------------------------------------------------------------- PAGE 1
h_band("Headnote — Pricing Proposal", "Simpler plans, a more generous free trial, and a partner program for law houses")

body("Our AI running-cost dropped about 4-5x after we switched the engine. "
     "That lets us give a stronger free trial and keep plans simple, while still "
     "keeping very healthy margins. Proposal: drop the Weekly plan, keep Monthly "
     f"({R}499) and Annual ({R}4,999), and make the free Demo genuinely useful.", size=10.5, gap=5.5)
pdf.ln(2)

section("The 3 plans")

plans = [
    ("DEMO  (free)", "3 days · no card", [
        "10 full research queries",
        "5 document drafts",
        "ALL features unlocked",
        "(incl. Hindi + PDF export)",
        "Goal: feel the full product",
    ], SOFT, INK),
    (f"MONTHLY  {R}499/mo", "billed monthly", [
        "150 research queries / month",
        "Unlimited drafts",
        "Hindi + PDF export",
        "Full case history",
        "Email support",
    ], (235, 242, 250), ACCENT),
    (f"ANNUAL  {R}4,999/yr", f"≈ {R}417/mo · best value", [
        "Effectively unlimited research",
        "Unlimited drafts",
        "Everything in Monthly, plus:",
        "Priority + custom letterhead",
        "WhatsApp support",
    ], GOLD, GREEN),
]
col_w = W / 3
top = pdf.get_y()
card_h = 56
for i, (name, sub, feats, fill, namecol) in enumerate(plans):
    x = 16 + i * col_w
    pdf.set_fill_color(*fill)
    pdf.rect(x + 1.5, top, col_w - 3, card_h, "F")
    pdf.set_xy(x + 4, top + 3)
    pdf.set_font("AU", "", 11); pdf.set_text_color(*namecol)
    pdf.multi_cell(col_w - 8, 5, name)
    pdf.set_xy(x + 4, top + 12)
    pdf.set_font("AU", "", 8); pdf.set_text_color(*MUTE)
    pdf.cell(col_w - 8, 4, sub)
    yy = top + 18
    pdf.set_font("AU", "", 8.6); pdf.set_text_color(*INK)
    for f in feats:
        pdf.set_xy(x + 4, yy)
        pdf.multi_cell(col_w - 7, 4.4, "·  " + f)
        yy = pdf.get_y() + 0.6
pdf.set_y(top + card_h + 3)
body("The Weekly plan is removed — the generous 3-day Demo replaces it.", size=9, color=MUTE)

pdf.ln(2)
section("Law-house partner program", GREEN)
body(f"Any law house or senior chamber that sells an Annual plan earns {R}500 (10%) per "
     f"sale — one-time, paid by us. It is the simplest way to turn respected advocates "
     f"into a sales channel, and it sells exactly the plan we want most (Annual).", size=10.5, gap=5.5)


# ---------------------------------------------------------------- PAGE 2
pdf.add_page()
section("What a customer costs us", ACCENT)
body(f"About {R}2 per research query and {R}0.50 per draft. A typical active lawyer "
     f"(40 searches + 15 drafts a month) costs us roughly {R}68 / month to serve. "
     f"Search of the case-law and the Hindi engine run on our own servers, so there is "
     f"no per-use licence fee.", size=10.5, gap=5.5)
pdf.ln(1)

section("What we keep per customer (after all costs)")
HEAD = FontFace(color=(255, 255, 255), fill_color=ACCENT)
pdf.set_font("AU", "", 9.5); pdf.set_text_color(*INK)
with pdf.table(width=W, col_widths=(44, 28, 28), text_align=("LEFT","CENTER","CENTER"),
               line_height=7, first_row_as_headings=True,
               headings_style=HEAD) as t:
    row = t.row(); row.cell("Plan"); row.cell("We keep"); row.cell("Margin")
    for a, b, c in [
        (f"Monthly ({R}499/mo)", f"{R}420 / mo", "84%"),
        (f"Annual — direct ({R}4,999)", f"{R}4,071 / yr", "81%"),
        (f"Annual — via law house", f"{R}3,571 / yr", "71%"),
    ]:
        r = t.row(); r.cell(a); r.cell(b); r.cell(c)
pdf.ln(2)

section("What we earn as we grow", GREEN)
body("Steady-state (that many paying customers active all year):", size=9.5, color=MUTE, gap=5)
HEAD2 = FontFace(color=(255, 255, 255), fill_color=GREEN)
pdf.set_font("AU", "", 9.5); pdf.set_text_color(*INK)
with pdf.table(width=W, col_widths=(40, 38, 38), text_align=("LEFT","CENTER","CENTER"),
               line_height=7, first_row_as_headings=True, headings_style=HEAD2) as t:
    r = t.row(); r.cell("Paying customers"); r.cell("We earn / month"); r.cell("We earn / year")
    for a, b, c in [
        ("50",  f"~ {R}15,000",   f"~ {R}1.8 lakh"),
        ("100", f"~ {R}33,000",   f"~ {R}4.0 lakh"),
        ("200", f"~ {R}70,000",   f"~ {R}8.3 lakh"),
        ("500", f"~ {R}1.8 lakh", f"~ {R}21.5 lakh"),
    ]:
        rr = t.row(); rr.cell(a); rr.cell(b); rr.cell(c)
pdf.ln(2)
body(f"Break-even: just ~10 paying customers cover ALL our running costs. "
     f"In the first year, while we build up to 100 customers, expect about "
     f"{R}2.5-3 lakh (then ~{R}4 lakh/year once steady).", size=10, gap=5.5)

pdf.ln(2)
section("The one thing to push", ACCENT)
pdf.set_fill_color(*GOLD)
y0 = pdf.get_y()
pdf.rect(16, y0, W, 18, "F")
pdf.set_xy(20, y0 + 3.5)
body(f"Sell ANNUAL plans. Paid upfront, no month-to-month drop-off, and worth about "
     f"8 months of a monthly subscriber — and the law-house partners sell exactly these.",
     size=10.5, gap=5.5)
pdf.set_y(y0 + 18 + 3)

body("Note: figures are planning estimates. GST registration becomes required once "
     "yearly turnover crosses ~" + R + "20 lakh (roughly 300-400 customers); at that "
     "point we either absorb 18% or add it on top (" + R + "499 → " + R + "589).",
     size=8.5, color=MUTE, gap=4.5)

out = "/Users/ayushshivhare/Downloads/Headnote_Pricing_Proposal.pdf"
pdf.output(out)
print("Saved:", out)
