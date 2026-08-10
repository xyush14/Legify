#!/usr/bin/env python3
"""
Headnote — Authorized Regional Distributor pack.

A formal appointment + programme-terms PDF to onboard law houses / senior
chambers as exclusive regional distributors. Same house style (Montserrat +
warm orange) as make_partnership_brochure.py.

Usage:
    python3 make_distributor_pack.py \
        --partner "Sharma & Associates" \
        --territory "Bhopal District, Madhya Pradesh" \
        --recipient "Adv. R. K. Sharma" \
        --ref "HN/ARD/2026/014"

All flags are optional; clean fill-in placeholders are used when omitted, so
the file doubles as a reusable template.
"""

import argparse
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak,
    Frame, PageTemplate, BaseDocTemplate, NextPageTemplate, Flowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg

# ── Fonts: Montserrat if present, else Helvetica fallback ───────────────
FONT, FONT_B, FONT_SB, FONT_MD, FONT_LT = (
    "Mont", "Mont-Bold", "Mont-Semi", "Mont-Med", "Mont-Light")
try:
    pdfmetrics.registerFont(TTFont("Mont",      "/tmp/fonts/Montserrat-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Mont-Bold", "/tmp/fonts/Montserrat-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("Mont-Semi", "/tmp/fonts/Montserrat-SemiBold.ttf"))
    pdfmetrics.registerFont(TTFont("Mont-Med",  "/tmp/fonts/Montserrat-Medium.ttf"))
    pdfmetrics.registerFont(TTFont("Mont-Light","/tmp/fonts/Montserrat-Light.ttf"))
except Exception:
    FONT = FONT_MD = FONT_LT = "Helvetica"
    FONT_B = FONT_SB = "Helvetica-Bold"

# ── Palette ─────────────────────────────────────────────────────────────
OR    = HexColor("#e67e22")
OR_D  = HexColor("#c0651a")
OR_L  = HexColor("#fdf2e6")
INK   = HexColor("#1a1a1a")
TXT   = HexColor("#2d2d2d")
TXT2  = HexColor("#555555")
GRAY  = HexColor("#999999")
LGRAY = HexColor("#e5e5e5")
BG    = HexColor("#fafafa")
W     = white

PW, PH = A4
M = 30 * mm
CW = PW - 2 * M

SVG_LOGO_PATH = "static/headnote-logo.svg"
TODAY = datetime.date.today().strftime("%d %B %Y")
R = "Rs."  # Montserrat / Helvetica lack a reliable rupee glyph


def S(name, font=FONT, size=10, leading=None, color=TXT, align=TA_LEFT,
      after=0, before=0, indent=0):
    return ParagraphStyle(name, fontName=font, fontSize=size,
        leading=leading or size * 1.55, textColor=color, alignment=align,
        spaceAfter=after, spaceBefore=before, leftIndent=indent)

s_mega    = S("Mega",  FONT_B, 34, 41, INK)
s_h1      = S("H1",    FONT_SB, 20, 28, INK, after=4)
s_h2      = S("H2",    FONT_SB, 13, 19, INK, after=2, before=10)
s_body    = S("Body",  FONT, 10, 16.5, TXT, after=5, align=TA_JUSTIFY)
s_body_l  = S("BodyL", FONT, 10, 16.5, TXT, after=5)
s_body_c  = S("BodyC", FONT, 10, 16.5, TXT, align=TA_CENTER, after=5)
s_light   = S("Light", FONT_LT, 10, 16, TXT2, after=4)
s_cap     = S("Cap",   FONT_SB, 8, 14, GRAY, after=4)
s_sm      = S("Sm",    FONT, 8, 12, GRAY)
s_sm_c    = S("SmC",   FONT, 8, 12, GRAY, align=TA_CENTER)
s_th      = S("TH",    FONT_SB, 8.5, 13, W, align=TA_CENTER)
s_td      = S("TD",    FONT, 9, 14, TXT, align=TA_CENTER)
s_td_b    = S("TDB",   FONT_SB, 9, 14, INK, align=TA_CENTER)
s_bullet  = S("Bul",   FONT, 9.5, 15.5, TXT, indent=12, after=3)
s_cl_body = S("ClB",   FONT, 9, 14.5, TXT, after=2, align=TA_JUSTIFY)
s_field_l = S("FL",    FONT_SB, 9, 13, TXT2)
s_field_v = S("FV",    FONT, 9.5, 13, INK)


# ── Flowables ───────────────────────────────────────────────────────────
class HRule(Flowable):
    def __init__(self, color=LGRAY, w=None, thick=0.5):
        Flowable.__init__(self)
        self.width = w or CW; self.height = 6; self.color = color; self.thick = thick
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(self.thick)
        self.canv.line(0, 3, self.width, 3)


class OrangeMark(Flowable):
    def __init__(self, w=40):
        Flowable.__init__(self)
        self.width = w; self.height = 6
    def draw(self):
        self.canv.setStrokeColor(OR); self.canv.setLineWidth(2.5)
        self.canv.line(0, 3, self.width, 3)


class CalloutBox(Flowable):
    def __init__(self, text, style=None):
        Flowable.__init__(self)
        st = style or s_body
        self.para = Paragraph(text, st)
        self.para.wrap(CW - 32, 1000)
        self.width = CW; self.height = self.para.height + 24
    def draw(self):
        c = self.canv
        c.setFillColor(OR_L); c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setFillColor(OR);   c.rect(0, 0, 3.5, self.height, fill=1, stroke=0)
        self.para.drawOn(c, 20, 12)


def svg_logo(path, target_w):
    d = svg2rlg(path)
    scale = target_w / d.width
    d.width = target_w; d.height = d.height * scale
    d.scale(scale, scale)
    return d


# ── Page templates ──────────────────────────────────────────────────────
def page_cover(c, doc):
    c.saveState()
    c.setFillColor(W); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    c.setFillColor(OR); c.rect(0, PH - 3, PW, 3, fill=1, stroke=0)
    c.setFont(FONT, 7.5); c.setFillColor(GRAY)
    c.drawCentredString(PW / 2, 22, "headnote.in  |  +91 88156 21916  |  hello@headnote.in")
    c.restoreState()


def page_white(c, doc):
    c.saveState()
    c.setFillColor(W); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    c.setFillColor(OR); c.rect(0, PH - 2.5, PW, 2.5, fill=1, stroke=0)
    c.setFont(FONT, 7); c.setFillColor(GRAY)
    c.drawString(M, 18, "headnote.in  ·  hello@headnote.in")
    c.drawCentredString(PW / 2, 18, "Headnote — Authorized Regional Distributor")
    c.drawRightString(PW - M, 18, f"Page {doc.page}")
    c.restoreState()


# ── Builders ────────────────────────────────────────────────────────────
def make_table(headers, rows, widths=None, highlight_col=None):
    data = [[Paragraph(h, s_th) for h in headers]]
    for r in rows:
        cells = []
        for j, cell in enumerate(r):
            st = s_td_b if (highlight_col is not None and j == highlight_col) else s_td
            cells.append(Paragraph(str(cell), st))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1)
    cmds = [
        ("BACKGROUND",     (0, 0), (-1, 0), INK),
        ("TEXTCOLOR",      (0, 0), (-1, 0), W),
        ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [W, BG]),
        ("GRID",           (0, 0), (-1, -1), 0.4, LGRAY),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
    ]
    if highlight_col is not None:
        cmds.append(("BACKGROUND", (highlight_col, 1), (highlight_col, -1), OR_L))
    t.setStyle(TableStyle(cmds))
    return t


def bullets(items, style=s_bullet):
    return [Paragraph(f"<bullet>&bull;</bullet> {i}", style) for i in items]


def section(title):
    return [Spacer(1, 6), Paragraph(title, s_h1), OrangeMark(), Spacer(1, 12)]


def clause(n, title, body):
    head = Paragraph(f'<font color="#1a1a1a"><b>{n}.&nbsp;&nbsp;{title}</b></font>',
                     S("clh", FONT_SB, 10, 15, INK, after=2, before=6))
    paras = body if isinstance(body, list) else [body]
    return KeepTogether([head] + [Paragraph(p, s_cl_body) for p in paras])


def field_block(fields, total_w):
    """Stack of label + write-on line rows."""
    data, cmds = [], [
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i, (label, val) in enumerate(fields):
        data.append([Paragraph(label, s_field_l), Paragraph(val or "", s_field_v)])
        cmds.append(("LINEBELOW", (1, i), (1, i), 0.6, GRAY if not val else LGRAY))
    t = Table(data, colWidths=[30 * mm, total_w - 30 * mm])
    t.setStyle(TableStyle(cmds))
    return t


# ════════════════════════════════════════════════════════════════════════
def build(partner, territory, recipient, ref, out):
    doc = BaseDocTemplate(out, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M + 10, bottomMargin=M,
        title="Headnote — Authorized Regional Distributor Appointment", author="Headnote")
    doc.addPageTemplates([
        PageTemplate("Cover", frames=Frame(M, M, CW, PH - 2 * M, id="c"), onPage=page_cover),
        PageTemplate("Inner", frames=Frame(M, M + 6, CW, PH - M - 44, id="i"), onPage=page_white),
    ])
    F = []

    # ── PAGE 1 — COVER ────────────────────────────────────────────────
    F.append(Spacer(1, 26))
    F.append(svg_logo(SVG_LOGO_PATH, 170))
    F.append(Spacer(1, 78))
    F.append(Paragraph("Authorized", s_mega))
    F.append(Paragraph("Regional Distributor", s_mega))
    F.append(Spacer(1, 10))
    F.append(OrangeMark(50))
    F.append(Spacer(1, 16))
    F.append(Paragraph("Letter of Appointment &amp; Programme Terms",
                       S("tag", FONT_LT, 14, 21, TXT2)))
    F.append(Paragraph("Verified AI legal research for Indian criminal advocates.",
                       S("tag2", FONT_LT, 11, 18, GRAY)))
    F.append(Spacer(1, 54))
    F.append(Paragraph("PREPARED FOR", s_cap))
    F.append(Spacer(1, 2))
    F.append(Paragraph(f"<b>{partner}</b>", S("pn", FONT_SB, 16, 22, INK)))
    F.append(Paragraph(territory, S("pc", FONT, 11, 16, TXT2)))
    F.append(Spacer(1, 10))
    ref_tbl = Table([
        [Paragraph(f"<b>Reference</b>&nbsp;&nbsp;{ref}", S("rf", FONT, 9, 13, TXT2)),
         Paragraph(f"<b>Date</b>&nbsp;&nbsp;{TODAY}", S("dt", FONT, 9, 13, TXT2, align=TA_LEFT))]],
        colWidths=[CW / 2, CW / 2])
    ref_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    F.append(ref_tbl)
    F.append(NextPageTemplate("Inner")); F.append(PageBreak())

    # ── PAGE 2 — LETTER OF APPOINTMENT ────────────────────────────────
    F += section("Letter of Appointment")
    F.append(Paragraph(f"<b>To,</b>  {partner} &mdash; {territory}", s_body_l))
    F.append(Paragraph(f"<b>Subject:</b>  Appointment as Headnote Authorized "
                       f"Regional Distributor for {territory}.", s_body_l))
    F.append(Spacer(1, 8))
    sal = f"Dear {recipient}," if recipient else "Dear Partner,"
    F.append(Paragraph(sal, s_body_l))
    F.append(Spacer(1, 4))
    F.append(Paragraph(
        "It is our pleasure to invite your firm to represent Headnote — India's "
        "<b>verified</b> AI legal-research and drafting platform, purpose-built for "
        "criminal-law practice. We are appointing a select group of established law "
        "houses and senior chambers as authorized distributors in their regions, and "
        f"we would be privileged to have {partner} represent us in {territory}.", s_body))
    F.append(Paragraph(
        f"On your acceptance of the terms in this document, {partner} is appointed as "
        f"Headnote's <b>Authorized Regional Distributor for {territory}</b>, on an "
        "<b>exclusive</b> basis, with effect from the date of acceptance. This entitles "
        "you to market Headnote and enrol advocates onto Headnote subscriptions within "
        "your territory, and to earn a <b>recurring margin</b> on every subscription you "
        "bring — full commercials are in Schedule 1.", s_body))
    F.append(Paragraph(
        "This pack contains everything from our side, with nothing left to negotiate "
        "before you begin: the commercial terms (Schedule 1), the responsibilities of "
        "each party (Schedule 2), the standard terms &amp; conditions (Schedule 3), and "
        "an acceptance form (Schedule 4). Sign the acceptance form — or simply confirm "
        "on a short kickoff call — and we will activate your distributor account, your "
        "unique referral code, and your live earnings dashboard the same week.", s_body))
    F.append(Paragraph(
        "We are confident this association will bring real value to the advocates in "
        "your region and a meaningful new revenue line to your practice.", s_body))
    F.append(Spacer(1, 14))
    F.append(Paragraph("With warm regards,", s_body_l))
    F.append(Spacer(1, 10))
    F.append(Paragraph("<b>Ayush Shivhare</b>", S("sg", FONT_SB, 12, 16, INK)))
    F.append(Paragraph("Founder, Headnote", S("sg2", FONT, 10, 14, TXT2)))
    F.append(Paragraph("hello@headnote.in  ·  +91 88156 21916  ·  headnote.in",
                       S("sg3", FONT, 9, 14, OR_D)))
    F.append(PageBreak())

    # ── PAGE 3 — WHAT YOU'LL BE REPRESENTING ──────────────────────────
    F += section("What You'll Be Representing")
    F.append(Paragraph(
        "Headnote is India's first <b>verified</b> AI research and drafting platform "
        "built for criminal law. It does three things no general AI tool does safely: "
        "finds the right precedents, checks every citation against its source before "
        "showing it, and drafts court-ready documents — in English and Hindi.", s_body))
    F.append(Spacer(1, 8))
    stats = [("27L+", "Judgments"), ("3-Check", "Verification"),
             ("35+", "Draft templates"), ("Bilingual", "Hindi + English")]
    srow = [[Paragraph(f"<b>{v}</b>", S("sv", FONT_B, 18, 22, OR, TA_CENTER)) for v, _ in stats],
            [Paragraph(l, S("sl", FONT, 8, 12, GRAY, TA_CENTER)) for _, l in stats]]
    st = Table(srow, colWidths=[CW / 4] * 4)
    st.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    F.append(st)
    F.append(Spacer(1, 12))
    F.append(CalloutBox(
        "<b>Why advocates need this now.</b> In February 2026 the Supreme Court "
        "observed that relying on AI-fabricated citations in court could amount to "
        "professional misconduct. General tools like ChatGPT and Gemini still invent "
        "judgments. Headnote was built for exactly this moment — every citation is "
        "verified to its source paragraph before it reaches the advocate."))
    F.append(Spacer(1, 12))
    F.append(Paragraph("WHY LAW HOUSES PARTNER WITH US", s_cap))
    F.extend(bullets([
        "A genuinely useful product your advocates will thank you for — not a gimmick.",
        "Priced at <b>" + R + "5,999/year</b>, roughly <b>8&ndash;12x cheaper</b> than "
        "SCC Online or Manupatra — easy to sell.",
        "Recurring margin to you on every subscription, for as long as it renews.",
        "Exclusive territory, so your effort builds your own book — not a competitor's.",
    ]))
    F.append(PageBreak())

    # ── PAGE 4 — SCHEDULE 1: COMMERCIAL TERMS ─────────────────────────
    F += section("Schedule 1 — Commercial Terms")
    F.append(Paragraph(
        "<b>Product &amp; price.</b>  You distribute the <b>Headnote Annual plan</b> at "
        "the listed price of <b>" + R + "5,999 per advocate, per year</b> (inclusive of "
        "all features — research, drafting, section-mapper, and Hindi). The list price is "
        "set by Headnote; subscriptions are sold at list price unless we agree a "
        "promotion in writing.", s_body))
    F.append(Spacer(1, 4))
    F.append(Paragraph("YOUR MARGIN — STARTS AT 10%, GROWS TO 20%, RECURRING", s_cap))
    F.append(Paragraph(
        "Your margin begins at <b>10%</b> and rises <b>2% for every 50 active "
        "subscribers</b> in your territory, up to a maximum of <b>20%</b>. It is "
        "<b>recurring</b> — you earn it again each year your subscribers renew. At 10% "
        "every Annual subscription pays you <b>" + R + "600</b>; at 20%, <b>" + R +
        "1,200</b> — every year.", s_body))
    F.append(Spacer(1, 4))
    F.append(make_table(
        ["Active subscribers", "Your margin", "Illustrative recurring earning / year"],
        [["50", "10%", R + "29,995 / year"],
         ["100", "12%", R + "71,988 / year"],
         ["150", "14%", R + "1,25,979 / year"],
         ["200", "16%", R + "1,91,968 / year"],
         ["250", "18%", R + "2,69,955 / year"],
         ["300+", "20%", R + "3,59,940+ / year"]],
        widths=[CW * 0.30, CW * 0.22, CW * 0.48], highlight_col=2))
    F.append(Spacer(1, 9))
    F.append(Paragraph("HOW IT'S TRACKED &amp; PAID", s_cap))
    F.extend(bullets([
        "Every subscription is attributed to you through your <b>unique referral code "
        "and link</b>, visible on your live dashboard in real time.",
        "Payouts are made <b>monthly</b>, by bank transfer or UPI, within <b>7 working "
        "days</b> of month-end, on payments actually <b>realised</b> (cleared) that month.",
        "Margin recurs on every renewal for as long as you remain an active distributor "
        "and the subscriber renews.",
        "Payouts are subject to applicable <b>TDS/GST</b>; you are responsible for your "
        "own tax compliance on amounts received.",
    ]))
    F.append(Spacer(1, 6))
    F.append(CalloutBox(
        "<b>Exclusivity condition.</b> Your territory is exclusive. To retain it, enrol "
        "at least <b>25 active subscriptions in the first 12 months</b>. If not met, "
        "Headnote may convert the territory to non-exclusive on 30 days' notice — your "
        "appointment and earnings otherwise continue unchanged.", s_body))
    F.append(PageBreak())

    # ── PAGE 5 — SCHEDULE 2: RESPONSIBILITIES ─────────────────────────
    F += section("Schedule 2 — What Each Side Does")
    F.append(Paragraph("HEADNOTE PROVIDES", s_cap))
    F.extend(bullets([
        "A <b>free, unlimited Headnote account</b> for you and your team.",
        "<b>Onboarding &amp; training</b> for your staff, plus demo support for prospects.",
        "<b>Co-branded marketing material</b> — brochures, decks, and social assets.",
        "A <b>live dashboard</b> tracking every referral, subscription, and payout.",
        "<b>Monthly payouts</b> and a <b>priority support line</b> for you and your clients.",
        "Ongoing product updates and early input into the roadmap.",
    ]))
    F.append(Spacer(1, 8))
    F.append(Paragraph("THE DISTRIBUTOR AGREES TO", s_cap))
    F.extend(bullets([
        "Promote Headnote <b>honestly and accurately</b> — no false, exaggerated, or "
        "guaranteed-outcome claims, and no misrepresentation of the product or the law.",
        "Make clear that Headnote is a <b>research and drafting aid</b>: AI output must "
        "always be verified by the advocate before it is relied on or filed.",
        "Sell at the <b>list price</b>; not offer unauthorised discounts or bundles.",
        "Not appoint <b>sub-distributors or resellers</b> without Headnote's written consent.",
        "Protect login credentials and any <b>customer data</b>, and use it only to serve "
        "those customers.",
        "Use the Headnote name and logo only per our brand guidelines, and stop on request.",
        "Comply with all <b>applicable law and Bar Council of India norms</b> on advertising "
        "and solicitation by / through advocates.",
        "Route product issues and customer escalations to Headnote support.",
    ]))
    F.append(PageBreak())

    # ── PAGE 6 — SCHEDULE 3: STANDARD TERMS & CONDITIONS ──────────────
    F += section("Schedule 3 — Standard Terms & Conditions")
    F.append(clause(1, "Relationship of the parties",
        "The distributor is an independent contractor. Nothing in this appointment "
        "creates employment, partnership, agency, or joint venture, and the distributor "
        "has no authority to bind Headnote, make representations on its behalf, or incur "
        "any obligation in its name beyond what is expressly permitted here."))
    F.append(clause(2, "Term &amp; renewal",
        "This appointment takes effect on the date of acceptance and continues for "
        "<b>12 months</b>, renewing automatically for further 12-month periods unless "
        "either party gives <b>30 days'</b> written notice of non-renewal."))
    F.append(clause(3, "Territory &amp; exclusivity",
        "The territory and its exclusivity, and the minimum-performance condition for "
        "retaining exclusivity, are as set out in Schedule 1. Headnote will not appoint "
        "another distributor in an exclusive territory while the condition is met."))
    F.append(clause(4, "Pricing, attribution &amp; payment",
        "Headnote sets the list price. Margins, attribution, and payout timing are as "
        "set out in Schedule 1 and are payable on <b>realised</b> revenue only. Amounts "
        "relating to refunds, chargebacks, or reversed payments may be adjusted against "
        "future payouts."))
    F.append(clause(5, "Intellectual property &amp; brand",
        "All intellectual property in Headnote, including the software, content, name, "
        "and logo, remains with Headnote. The distributor receives a limited, "
        "non-transferable, revocable licence to use the marks solely to promote Headnote "
        "under this appointment, and must not register or attempt to register any "
        "confusingly similar mark, domain, or handle."))
    F.append(clause(6, "Confidentiality",
        "Each party will keep the other's non-public information (including commercial "
        "terms, customer lists, and product information) confidential and use it only for "
        "this appointment. This obligation survives termination."))
    F.append(clause(7, "Data protection",
        "Each party will comply with applicable data-protection law, including the "
        "Digital Personal Data Protection Act, 2023, and will protect personal data of "
        "customers and prospects and not use it for any unrelated purpose."))
    F.append(clause(8, "Conduct &amp; compliance",
        "The distributor will act lawfully and ethically, comply with all applicable law "
        "and Bar Council of India norms on advertising and solicitation, and represent "
        "Headnote's capabilities and limitations truthfully — including that AI output is "
        "an aid that the advocate must independently verify."))
    F.append(clause(9, "No guarantee &amp; limitation of liability",
        "Headnote is provided on an “as is” basis as a research and drafting aid. "
        "Headnote does not warrant any particular result and is not liable for how output "
        "is used in practice. To the extent permitted by law, Headnote's aggregate "
        "liability under this appointment is limited to the total margin paid to the "
        "distributor in the preceding three months."))
    F.append(clause(10, "Termination",
        "Either party may terminate on <b>30 days'</b> written notice, and immediately on "
        "material breach (uncured for 15 days), insolvency, or conduct that damages the "
        "Headnote brand. On termination the distributor stops using the marks and "
        "accounts; accrued margin on realised payments up to the termination date remains "
        "payable in the ordinary payout cycle."))
    F.append(clause(11, "Governing law &amp; dispute resolution",
        "This appointment is governed by the laws of India. The parties will first "
        "attempt to resolve any dispute in good faith; failing which, the dispute will be "
        "referred to arbitration by a sole arbitrator under the Arbitration and "
        "Conciliation Act, 1996, seated at <b>Bhopal, Madhya Pradesh</b>, whose courts "
        "have jurisdiction."))
    F.append(clause(12, "General",
        "This document and its Schedules are the entire understanding between the parties "
        "on this subject and supersede prior discussions. Any change must be in writing. "
        "Notices may be given by email to the addresses on the acceptance form. If any "
        "term is held unenforceable, the rest remains in force."))
    F.append(PageBreak())

    # ── PAGE 7 — SCHEDULE 4: ACCEPTANCE ───────────────────────────────
    F += section("Schedule 4 — Acceptance")
    F.append(Paragraph(
        "By signing below, the distributor accepts appointment as Headnote's Authorized "
        "Regional Distributor for the territory named above, on the terms set out in this "
        "document and its Schedules.", s_body))
    F.append(Spacer(1, 6))
    left = field_block([
        ("Law house", partner if partner != "[LAW HOUSE NAME]" else ""),
        ("Territory", territory if territory != "[CITY / DISTRICT]" else ""),
        ("Signatory", recipient or ""),
        ("Designation", ""),
        ("Phone / Email", ""),
        ("PAN / GSTIN", ""),
        ("Signature", ""),
        ("Date &amp; place", ""),
    ], CW / 2 - 6)
    right = field_block([
        ("Name", "Ayush Shivhare"),
        ("Designation", "Founder"),
        ("For", "Headnote"),
        ("Entity / GSTIN", ""),
        ("Email", "hello@headnote.in"),
        ("Phone", "+91 88156 21916"),
        ("Signature", ""),
        ("Date &amp; place", ""),
    ], CW / 2 - 6)
    head = Table([[Paragraph("FOR THE DISTRIBUTOR", s_cap),
                   Paragraph("FOR HEADNOTE", s_cap)]], colWidths=[CW / 2, CW / 2])
    head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    F.append(head)
    sigtbl = Table([[left, right]], colWidths=[CW / 2, CW / 2])
    sigtbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (1, 0), 12),
        ("RIGHTPADDING", (0, 0), (0, 0), 12), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    F.append(sigtbl)
    F.append(Spacer(1, 18))
    F.append(HRule(color=OR, thick=1.5))
    F.append(Spacer(1, 10))
    F.append(Paragraph("TO ACCEPT", s_cap))
    F.extend(bullets([
        "Sign this page, scan it, and email it to <b>hello@headnote.in</b>; or",
        "Reply to our email confirming acceptance and we'll schedule a 20-minute "
        "kickoff call to activate your account.",
    ]))
    F.append(Spacer(1, 8))
    F.append(Paragraph(
        "This pack sets out the proposed terms of appointment; it becomes binding on "
        "acceptance by both parties.", s_sm))

    doc.build(F)
    print(f"Done: {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--partner", default="[LAW HOUSE NAME]")
    ap.add_argument("--territory", default="[CITY / DISTRICT]")
    ap.add_argument("--recipient", default="")
    ap.add_argument("--ref", default="HN/ARD/2026/____")
    ap.add_argument("--out", default="Headnote_Distributor_Appointment.pdf")
    a = ap.parse_args()
    build(a.partner, a.territory, a.recipient, a.ref, a.out)
