#!/usr/bin/env python3
"""
Headnote Partnership Deck — clean, modern, Montserrat typography.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak,
    Frame, PageTemplate, BaseDocTemplate, NextPageTemplate, Flowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
import datetime, copy

# ── Register Montserrat ────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont("Mont",      "/tmp/fonts/Montserrat-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Mont-Bold", "/tmp/fonts/Montserrat-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mont-Semi", "/tmp/fonts/Montserrat-SemiBold.ttf"))
pdfmetrics.registerFont(TTFont("Mont-Med",  "/tmp/fonts/Montserrat-Medium.ttf"))
pdfmetrics.registerFont(TTFont("Mont-Light","/tmp/fonts/Montserrat-Light.ttf"))

# ── Palette ────────────────────────────────────────────────────────────
OR      = HexColor("#e67e22")   # warm orange
OR_D    = HexColor("#c0651a")   # darker orange
OR_L    = HexColor("#fdf2e6")   # very light warm
INK     = HexColor("#1a1a1a")
TXT     = HexColor("#2d2d2d")
TXT2    = HexColor("#555555")
GRAY    = HexColor("#999999")
LGRAY   = HexColor("#e5e5e5")
BG      = HexColor("#fafafa")
W       = white

PW, PH = A4
M = 30 * mm
CW = PW - 2*M

PARTNER = "{{PARTNER_NAME}}"
CITY    = "{{PARTNER_CITY}}"
TODAY   = datetime.date.today().strftime("%B %Y")

SVG_LOGO_PATH = "static/headnote-logo.svg"

# ── Styles ─────────────────────────────────────────────────────────────

def S(name, font="Mont", size=10, leading=None, color=TXT, align=TA_LEFT,
      after=0, before=0, indent=0):
    return ParagraphStyle(name, fontName=font, fontSize=size,
        leading=leading or size*1.55, textColor=color, alignment=align,
        spaceAfter=after, spaceBefore=before, leftIndent=indent)

s_mega    = S("Mega",   "Mont-Bold", 42, 50, INK)
s_big     = S("Big",    "Mont-Bold", 28, 36, INK)
s_big_w   = S("BigW",   "Mont-Bold", 28, 36, W)
s_h1      = S("H1",     "Mont-Semi", 20, 28, INK, after=4)
s_h1_w    = S("H1W",    "Mont-Semi", 20, 28, W, after=4)
s_h2      = S("H2",     "Mont-Semi", 13, 19, INK, after=2, before=10)
s_h2_or   = S("H2or",   "Mont-Semi", 13, 19, OR, after=2, before=10)
s_body    = S("Body",   "Mont",      10, 16.5, TXT, after=5, align=TA_JUSTIFY)
s_body_w  = S("BodyW",  "Mont",      10, 16.5, HexColor("#cccccc"), after=5, align=TA_JUSTIFY)
s_body_c  = S("BodyC",  "Mont",      10, 16.5, TXT, align=TA_CENTER, after=5)
s_light   = S("Light",  "Mont-Light",10, 16, TXT2, after=4)
s_light_c = S("LightC", "Mont-Light",10, 16, TXT2, align=TA_CENTER, after=4)
s_cap     = S("Cap",    "Mont-Semi", 8,  14, GRAY, after=4)   # uppercase caption
s_cap_w   = S("CapW",   "Mont-Semi", 8,  14, HexColor("#888888"), after=4)
s_cap_c   = S("CapC",   "Mont-Semi", 8,  14, GRAY, align=TA_CENTER, after=4)
s_num     = S("Num",    "Mont-Bold", 36, 40, OR, align=TA_CENTER)
s_num_w   = S("NumW",   "Mont-Bold", 36, 40, OR, align=TA_CENTER)
s_numsub  = S("NumSub", "Mont-Med",  9,  14, TXT2, align=TA_CENTER)
s_numsub_w= S("NumSubW","Mont-Med",  9,  14, HexColor("#aaaaaa"), align=TA_CENTER)
s_sm      = S("Sm",     "Mont",      8,  12, GRAY)
s_sm_c    = S("SmC",    "Mont",      8,  12, GRAY, align=TA_CENTER)
s_th      = S("TH",     "Mont-Semi", 8.5,13, W, align=TA_CENTER)
s_td      = S("TD",     "Mont",      9,  14, TXT, align=TA_CENTER)
s_td_l    = S("TDL",    "Mont",      9,  14, TXT, align=TA_LEFT)
s_td_b    = S("TDB",    "Mont-Semi", 9,  14, INK, align=TA_CENTER)
s_bullet  = S("Bul",    "Mont",      9.5,16, TXT, indent=14, after=2)


# ── Flowables ──────────────────────────────────────────────────────────

class HRule(Flowable):
    def __init__(self, color=LGRAY, w=None, thick=0.5):
        Flowable.__init__(self)
        self.width = w or CW; self.height = 6; self.color = color; self.thick = thick
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(self.thick)
        self.canv.line(0, 3, self.width, 3)

class OrangeMark(Flowable):
    """Short orange accent line."""
    def __init__(self, w=40):
        Flowable.__init__(self)
        self.width = w; self.height = 6
    def draw(self):
        self.canv.setStrokeColor(OR); self.canv.setLineWidth(2.5)
        self.canv.line(0, 3, self.width, 3)

class CalloutBox(Flowable):
    """Light orange box with left orange border."""
    def __init__(self, text, style=None):
        Flowable.__init__(self)
        st = style or s_body
        bw = CW
        self.para = Paragraph(text, st)
        self.para.wrap(bw - 32, 1000)
        self.width = bw; self.height = self.para.height + 24
    def draw(self):
        c = self.canv
        c.setFillColor(OR_L)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setFillColor(OR)
        c.rect(0, 0, 3.5, self.height, fill=1, stroke=0)
        self.para.drawOn(c, 20, 12)

class DarkBlock(Flowable):
    """Full-width dark background block with content."""
    def __init__(self, elements, pad_top=30, pad_bot=30):
        Flowable.__init__(self)
        self.elements = elements
        self.pad_top = pad_top
        self.pad_bot = pad_bot
        # pre-wrap elements
        self.total_h = pad_top + pad_bot
        for el in self.elements:
            if hasattr(el, 'wrap'):
                _, h = el.wrap(CW, 1000)
                self.total_h += h
        self.width = CW
        self.height = self.total_h

    def draw(self):
        c = self.canv
        # dark background extends to page edges
        c.setFillColor(INK)
        x_off = -M  # extend left to page edge
        c.rect(x_off, 0, PW, self.height, fill=1, stroke=0)
        # draw elements from top
        y = self.height - self.pad_top
        for el in self.elements:
            if hasattr(el, 'wrap'):
                _, h = el.wrap(CW, 1000)
                y -= h
                el.drawOn(c, 0, y)


def svg_logo(path, target_w):
    """Load SVG logo scaled to target width."""
    d = svg2rlg(path)
    scale = target_w / d.width
    d.width = target_w
    d.height = d.height * scale
    d.scale(scale, scale)
    return d

def logo_flowable(target_w=160):
    """Return the headnote. SVG logo as a Flowable."""
    return svg_logo(SVG_LOGO_PATH, target_w)


# ── Page templates ─────────────────────────────────────────────────────

def page_white(c, doc):
    c.saveState()
    c.setFillColor(W); c.rect(0,0,PW,PH,fill=1,stroke=0)
    # thin top orange strip
    c.setFillColor(OR); c.rect(0, PH-2.5, PW, 2.5, fill=1, stroke=0)
    # footer
    c.setFont("Mont", 7); c.setFillColor(GRAY)
    c.drawString(M, 18, "headnote.in")
    c.drawRightString(PW-M, 18, "+91 88156 21916")
    c.drawCentredString(PW/2, 18, f"Confidential  |  {TODAY}")
    c.restoreState()

def page_cover(c, doc):
    c.saveState()
    c.setFillColor(W); c.rect(0,0,PW,PH,fill=1,stroke=0)
    c.setFillColor(OR); c.rect(0, PH-3, PW, 3, fill=1, stroke=0)
    # footer
    c.setFont("Mont", 7.5); c.setFillColor(GRAY)
    c.drawCentredString(PW/2, 22, "headnote.in  |  +91 88156 21916  |  hello@headnote.in")
    c.restoreState()


# ── Clean table builder ────────────────────────────────────────────────

def make_table(headers, rows, widths=None, highlight_col=None):
    data = [[Paragraph(h, s_th) for h in headers]]
    for r in rows:
        cells = []
        for j, cell in enumerate(r):
            st = s_td_b if (highlight_col is not None and j == highlight_col) else s_td
            cells.append(Paragraph(str(cell), st))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0,0),(-1,0), INK),
        ("TEXTCOLOR",     (0,0),(-1,0), W),
        ("ALIGN",         (0,0),(-1,-1),"CENTER"),
        ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
        ("BACKGROUND",    (0,1),(-1,-1), W),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[W, BG]),
        ("GRID",          (0,0),(-1,-1), 0.4, LGRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
    ]
    if highlight_col is not None:
        style_cmds.append(("BACKGROUND", (highlight_col,1),(highlight_col,-1), OR_L))
    t.setStyle(TableStyle(style_cmds))
    return t

def bullets(items):
    return [Paragraph(f"<bullet>&bull;</bullet> {i}", s_bullet) for i in items]


# ══════════════════════════════════════════════════════════════════════
# CONTENT
# ══════════════════════════════════════════════════════════════════════

def build(path="Headnote_Partnership_Proposal.pdf"):
    doc = BaseDocTemplate(path, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M+10, bottomMargin=M,
        title="Headnote Partnership Proposal", author="Headnote")

    doc.addPageTemplates([
        PageTemplate("Cover", frames=Frame(M,M,CW,PH-2*M,id="c"), onPage=page_cover),
        PageTemplate("Inner", frames=Frame(M,M+6,CW,PH-M-44,id="i"), onPage=page_white),
    ])

    F = []  # story

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 1 — COVER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 30))
    F.append(logo_flowable(180))
    F.append(Spacer(1, 80))
    F.append(Paragraph("Partnership", s_mega))
    F.append(Paragraph("Proposal", s_mega))
    F.append(Spacer(1, 10))
    F.append(OrangeMark(50))
    F.append(Spacer(1, 16))
    F.append(Paragraph(
        "Verified AI legal research for Indian criminal advocates.",
        S("tag", "Mont-Light", 13, 20, TXT2)))
    F.append(Spacer(1, 60))

    # Prepared for block
    F.append(Paragraph("PREPARED FOR", s_cap))
    F.append(Spacer(1, 2))
    F.append(Paragraph(f"<b>{PARTNER}</b>", S("pn","Mont-Semi",16,22,INK)))
    F.append(Paragraph(CITY, S("pc","Mont",11,16,TXT2)))
    F.append(Spacer(1, 6))
    F.append(Paragraph(TODAY, s_sm))

    F.append(NextPageTemplate("Inner"))
    F.append(PageBreak())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 2 — WHY THIS MATTERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 6))
    F.append(Paragraph("Why This Matters", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 12))

    F.append(CalloutBox(
        '<b>Supreme Court, February 2026:</b> Filing AI-generated fake citations '
        'is professional misconduct — punishable by suspension or disbarment.'))
    F.append(Spacer(1, 12))

    F.append(Paragraph(
        "Every AI tool your team uses for research today carries this risk. ChatGPT, "
        "Gemini, and even legal-branded AI tools fabricate citations. The consequences "
        "are no longer theoretical — they're regulatory.", s_body))
    F.append(Spacer(1, 4))
    F.append(Paragraph(
        "Meanwhile, quality legal databases cost Rs.3,000–9,000/month. Most junior "
        "advocates can't afford them. They rely on memory or unverified searches.", s_body))

    F.append(Spacer(1, 22))
    F.append(Paragraph("What is Headnote", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 12))

    F.append(Paragraph(
        "Headnote is India's first <b>verified AI research platform</b> purpose-built "
        "for criminal law. Every citation passes three independent checks before "
        "reaching the advocate. No hallucinated judgments. Ever.", s_body))
    F.append(Spacer(1, 14))

    # 4 stats in a row
    stats = [("27L+","Judgments"), ("3-Check","Verification"), ("35+","Templates"), ("Hindi + En","Bilingual")]
    stat_row = [[Paragraph(f'<b>{v}</b>', S("sv","Mont-Bold",22,26,OR,TA_CENTER)) for v,_ in stats],
                [Paragraph(lbl, S("sl","Mont",8,12,GRAY,TA_CENTER)) for _,lbl in stats]]
    st = Table(stat_row, colWidths=[CW/4]*4)
    st.setStyle(TableStyle([
        ("ALIGN",(0,0),(-1,-1),"CENTER"), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    F.append(st)

    F.append(PageBreak())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 3 — PLATFORM
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 6))
    F.append(Paragraph("The Platform", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 14))

    feats = [
        ("Case Research",
         "Describe a situation in plain English. Get 3–5 verified precedents with "
         "Cri.L.J. headnotes and practitioner notes. Our <b>Hidden Authorities</b> "
         "mode surfaces non-obvious cases that opposing counsel won't find."),
        ("Smart Drafting",
         "35+ court-ready templates — bail applications, writ petitions, legal notices, "
         "vakalatnama, and more. Conversational flow in English or Hindi. Not forms — "
         "a conversation."),
        ("Section Mapper",
         "Bidirectional IPC/BNS, CrPC/BNSS, Evidence/BSA lookup. Handles messy input, "
         "Devanagari, shows full classification. Hand-verified against official "
         "concordances."),
        ("Judgment Browser",
         "Full Indian Kanoon search with court, year, judge, and statute filters. "
         "One-click Hindi translation on every output."),
    ]
    for title, desc in feats:
        F.append(Paragraph(f'<font color="#e67e22">{title}</font>', s_h2))
        F.append(Paragraph(desc, s_body))

    F.append(Spacer(1, 14))
    F.append(HRule(color=LGRAY))
    F.append(Spacer(1, 8))
    F.append(Paragraph("THE VERIFICATION MOAT", s_cap))
    F.append(Spacer(1, 4))

    checks = Table([
        [Paragraph("<b>1. Existence</b><br/>Is this a real case from the evidence set?", s_light_c),
         Paragraph("<b>2. Anchor</b><br/>Do the cited paragraph numbers actually exist?", s_light_c),
         Paragraph("<b>3. Verbatim</b><br/>Does the quoted text match the source?", s_light_c)],
    ], colWidths=[CW/3]*3)
    checks.setStyle(TableStyle([
        ("ALIGN",(0,0),(-1,-1),"CENTER"), ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LINEBEFORE",(1,0),(1,0),0.4,LGRAY), ("LINEBEFORE",(2,0),(2,0),0.4,LGRAY),
    ]))
    F.append(checks)
    F.append(Spacer(1, 4))
    F.append(Paragraph(
        "All three checks pass before any citation reaches the advocate. "
        "Failures trigger automatic retry. Nothing unverified gets through.",
        s_sm_c))

    F.append(PageBreak())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 4 — THE YEARLY VALUE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 6))
    F.append(Paragraph("The Annual Plan", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 16))

    # Hero price
    price_block = Table([
        [Paragraph('<font color="#e67e22"><b>Rs.5,999</b></font>',
                   S("price","Mont-Bold",48,52,OR,TA_CENTER)),
         Paragraph("per advocate<br/>per year",
                   S("pricetag","Mont-Light",14,20,TXT2,TA_LEFT))],
    ], colWidths=[240, CW-250])
    price_block.setStyle(TableStyle([
        ("ALIGN",(0,0),(0,0),"RIGHT"), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),10),
    ]))
    F.append(price_block)
    F.append(Spacer(1, 8))
    F.append(HRule(color=LGRAY))
    F.append(Spacer(1, 12))

    # Value math
    F.append(Paragraph("WHAT Rs.5,999/YEAR GETS YOU", s_cap))
    F.append(Spacer(1, 6))

    val_items = [
        ("2,000", "verified research queries — enough for 5+ cases per day, every working day"),
        ("Unlimited", "document drafts across 35+ court-ready templates"),
        ("Full", "IPC/BNS section mapper, judgment browser, and Hindi translation"),
        ("Rs.500/mo", "effective cost — less than a single consultation fee"),
    ]
    for val, desc in val_items:
        row = Table([[
            Paragraph(f'<b>{val}</b>', S("v","Mont-Bold",12,16,OR)),
            Paragraph(desc, S("d","Mont",9.5,15,TXT)),
        ]], colWidths=[90, CW-100])
        row.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LINEBELOW",(0,0),(-1,-1),0.3,LGRAY),
        ]))
        F.append(row)

    F.append(Spacer(1, 16))
    F.append(Paragraph("THE COMPARISON", s_cap))
    F.append(Spacer(1, 6))

    comp = make_table(
        ["", "SCC Online", "Manupatra", "Headnote"],
        [
            ["Annual cost",         "Rs.36,000–72,000", "Rs.24,000–48,000", "Rs.5,999"],
            ["Criminal-law focus",  "No",                "No",                "Purpose-built"],
            ["Verified citations",  "Manual only",       "Manual only",       "Three-check AI"],
            ["BNS / BNSS mapping",  "Partial",           "Partial",           "Native"],
            ["Hindi output",        "No",                "No",                "One-click"],
            ["Document drafting",   "No",                "No",                "35+ templates"],
        ],
        widths=[105, (CW-115)/3, (CW-115)/3, (CW-115)/3],
        highlight_col=3,
    )
    F.append(comp)

    F.append(Spacer(1, 10))
    F.append(Paragraph(
        "Your advocates get better research at <b>8–12x lower cost</b> "
        "than traditional databases — with AI verification no one else offers.",
        s_body_c))

    F.append(PageBreak())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 5 — PARTNERSHIP & COMMISSION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 6))
    F.append(Paragraph("Partner With Us", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 12))

    F.append(Paragraph(
        "Refer advocates to Headnote. Earn recurring commission on every "
        "subscription — and your rate grows as your network does.", s_body))
    F.append(Spacer(1, 10))

    # Commission hero
    comm_hero = Table([
        [Paragraph('<b>10%</b>', S("ch","Mont-Bold",44,48,OR,TA_CENTER)),
         Paragraph("starting commission<br/>on every plan",
                   S("cht","Mont-Light",13,19,TXT2,TA_LEFT))],
    ], colWidths=[140, CW-150])
    comm_hero.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8),
    ]))
    F.append(comm_hero)
    F.append(Spacer(1, 4))

    F.append(Paragraph(
        "For every <b>50 subscribers</b> you bring, your commission rate increases "
        "by <b>2%</b> — permanently. Capped at 20%.", s_body))
    F.append(Spacer(1, 8))

    F.append(Paragraph("EARNING POTENTIAL (ANNUAL PLAN — Rs.5,999/sub)", s_cap))
    F.append(Spacer(1, 4))

    earn = make_table(
        ["Subscribers", "Rate", "Your Annual Earning"],
        [
            ["50",  "10%", "Rs.29,995 / year"],
            ["100", "12%", "Rs.71,988 / year"],
            ["150", "14%", "Rs.1,25,979 / year"],
            ["200", "16%", "Rs.1,91,968 / year"],
            ["250", "18%", "Rs.2,69,955 / year"],
            ["300+","20%", "Rs.3,59,940+ / year"],
        ],
        widths=[CW/3]*3,
    )
    F.append(earn)

    F.append(Spacer(1, 12))
    F.append(Paragraph("WHAT YOU RECEIVE", s_cap))
    F.append(Spacer(1, 4))

    F.extend(bullets([
        "<b>Free premium account</b> — unlimited, for you personally",
        "<b>Recurring payouts</b> — monthly, via bank transfer or UPI",
        "<b>Live dashboard</b> — track every referral and earning in real time",
        "<b>Co-branded materials</b> — shareable assets for your network",
        "<b>Priority feature input</b> — shape the product your network uses",
    ]))

    F.append(PageBreak())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PAGE 6 — LET'S TALK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    F.append(Spacer(1, 6))
    F.append(Paragraph("Let's Talk", s_h1))
    F.append(OrangeMark())
    F.append(Spacer(1, 20))

    steps = [
        ("01", "Quick Call",
         "20 minutes. We understand your network and structure the "
         "partnership around what works for you."),
        ("02", "Pilot Access",
         "You and a few colleagues get full Headnote access for 14 days. "
         "Use it on real cases. No obligation."),
        ("03", "Go Live",
         "Referral link, dashboard, co-branded materials. "
         "Start earning from day one."),
    ]
    for num, title, desc in steps:
        row = Table([[
            Paragraph(f'<b>{num}</b>', S("sn","Mont-Bold",24,28,OR,TA_CENTER)),
            Paragraph(f"<b>{title}</b><br/><font color='#555555'>{desc}</font>",
                      S("sd","Mont",10,16,INK)),
        ]], colWidths=[50, CW-60])
        row.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),10),
            ("LINEBELOW",(0,0),(-1,-1),0.3,LGRAY),
        ]))
        F.append(row)

    F.append(Spacer(1, 40))
    F.append(HRule(color=OR, thick=1.5))
    F.append(Spacer(1, 18))

    # Contact — two columns, clean
    contact = Table([
        [Paragraph("<b>Ayush Shivhare</b>", S("cn","Mont-Semi",12,16,INK)),
         Paragraph("", s_body)],
        [Paragraph("Co-Founder, Headnote", S("ct","Mont",10,14,TXT2)),
         Paragraph("", s_body)],
        [Paragraph("", s_body), Paragraph("", s_body)],
        [Paragraph('<font color="#e67e22"><b>Phone / WhatsApp</b></font>'
                   '&nbsp;&nbsp;&nbsp;+91 88156 21916',
                   S("cp","Mont",10,14,TXT)),
         Paragraph('<font color="#e67e22"><b>Email</b></font>'
                   '&nbsp;&nbsp;&nbsp;hello@headnote.in',
                   S("ce","Mont",10,14,TXT))],
        [Paragraph('<font color="#e67e22"><b>Web</b></font>'
                   '&nbsp;&nbsp;&nbsp;headnote.in',
                   S("cw","Mont",10,14,TXT)),
         Paragraph("", s_body)],
    ], colWidths=[CW/2, CW/2])
    contact.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("TOPPADDING",(0,0),(-1,-1),2), ("BOTTOMPADDING",(0,0),(-1,-1),2),
        ("LEFTPADDING",(0,0),(-1,-1),0),
    ]))
    F.append(contact)

    F.append(Spacer(1, 30))
    F.append(Paragraph(
        "We'd love to explore this with you.",
        S("end","Mont-Light",11,16,GRAY,TA_LEFT)))

    # ── Build ──────────────────────────────────────────────────────
    doc.build(F)
    print(f"Done: {path}  ({6} pages)")
    return path

if __name__ == "__main__":
    build()
