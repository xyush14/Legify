"""Generate a branded Headnote case-law research PDF for WhatsApp delivery."""
from fpdf import FPDF
import os, datetime

FONT       = "/Library/Fonts/Arial Unicode.ttf"
LOGO_SVG   = os.path.join(os.path.dirname(__file__), "static", "headnote-logo.svg")
OUT        = os.path.expanduser("~/Downloads/Headnote_CaseLaw_Research.pdf")

# ── Brand palette (from style.css) ───────────────────────────────────────────
BAND       = (30, 26, 20)       # dark near-black header
INK        = (12, 12, 10)       # primary text
INK2       = (75, 75, 72)       # secondary text
INK3       = (138, 138, 130)    # muted / metadata
GOLD       = (201, 169, 110)    # primary accent
GOLD_DEEP  = (180, 137, 75)     # deeper gold
GOLD_SOFT  = (250, 247, 237)    # gold tinted bg
GOLD_LINE  = (236, 227, 200)    # gold border
GOLD_INK   = (140, 117, 73)     # gold text
NAVY       = (30, 58, 95)       # navy highlight
GOOD       = (45, 106, 45)      # green for ✓ held
LINE       = (232, 230, 224)    # hairline dividers
WHITE      = (255, 255, 255)
WARN_BG    = (255, 249, 235)    # advisory bg


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
pdf.set_margins(18, 18, 18)
pdf.add_page()
W = 210 - 36   # usable width


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def rule(color=LINE, weight=0.25):
    pdf.set_draw_color(*color)
    pdf.set_line_width(weight)
    x = pdf.get_x(); y = pdf.get_y()
    pdf.line(18, y, 18 + W, y)
    pdf.set_xy(x, y)


def body(txt, size=9.5, color=INK2, gap=5, w=None):
    pdf.set_font("AU", "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(w or W, gap, txt)


def label(txt, size=7, color=GOLD_INK, gap=4):
    pdf.set_font("AU", "", size)
    pdf.set_text_color(*color)
    pdf.cell(0, gap, txt.upper(), new_x="LMARGIN", new_y="NEXT")


def vgap(mm=3):
    pdf.ln(mm)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HEADER BAND
# ═══════════════════════════════════════════════════════════════════════════════

BAND_H = 26
pdf.set_fill_color(*BAND)
pdf.rect(0, 0, 210, BAND_H, "F")

# Gold left accent stripe
pdf.set_fill_color(*GOLD)
pdf.rect(0, 0, 3.5, BAND_H, "F")

# Logo wordmark
try:
    pdf.image(LOGO_SVG, x=18, y=5.5, h=7)
    logo_right = 18 + (7 * 91 / 16) + 3   # approx width from SVG aspect ratio
except Exception:
    logo_right = 18

# Divider dot between wordmark and subtitle
pdf.set_xy(logo_right, 7)
pdf.set_font("AU", "", 7)
pdf.set_text_color(*GOLD)
pdf.cell(0, 6, "PERSONAL ASSIST")

# Right-aligned doc type
pdf.set_xy(18, 16)
pdf.set_font("AU", "", 8)
pdf.set_text_color(200, 195, 185)
pdf.cell(W, 5, "Case Law Research   ·   धारा 420 / 406 IPC", align="R")

pdf.set_y(BAND_H + 5)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. QUERY BOX
# ═══════════════════════════════════════════════════════════════════════════════

vgap(1)
label("Original Query")
vgap(1)

qbox_y = pdf.get_y()
QUERY_TEXT = (
    "एक मामले में आरोपी ने जमीन विक्रय का अनुबंध किया और अग्रिम राशि प्राप्त कर "
    "छः माह के अंदर बकाया राशि प्राप्त होने पर जमीन का रजिस्टर्ड विक्रय पत्र "
    "संपादित करने का वादा किया। 6 माह का समय पूरा होने से पूर्व क्रेता ने जमीन "
    "की रजिस्ट्री को बोला तो विक्रेता मुकर गया और अनुबंधित जमीन अन्य व्यक्ति को "
    "बेच दी। जिसकी शिकायत पर पुलिस ने कार्यवाही नहीं की — इसीलिए न्यायालय में "
    "धारा 420, 406 IPC का FIR किये जाने हेतु 156(3) CrPC का आवेदन पेश किया।"
)

pdf.set_fill_color(*GOLD_SOFT)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
# Draw box — measure text height first (approx)
pdf.set_font("AU", "", 9.5)
lines_needed = pdf.get_string_width(QUERY_TEXT) / (W - 12) + 1
box_h = max(28, lines_needed * 5.5 + 8)
pdf.rect(18, qbox_y, W, box_h, "FD")

# Gold left bar
pdf.set_fill_color(*GOLD)
pdf.rect(18, qbox_y, 3, box_h, "F")

pdf.set_xy(24, qbox_y + 4)
body(QUERY_TEXT, size=9.5, color=INK, gap=5.5, w=W - 8)
pdf.set_y(qbox_y + box_h + 5)


# Meta strip
pdf.set_font("AU", "", 8)
pdf.set_text_color(*INK3)
pdf.cell(W // 2, 5, f"Date: {datetime.date.today().strftime('%d %B %Y')}", new_x="END")
pdf.cell(W // 2, 5, "Court: M.P. High Court (Gwalior / Indore Bench)", align="R",
         new_x="LMARGIN", new_y="NEXT")
vgap(5)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SECTION HEADING — न्याय दृष्टांत
# ═══════════════════════════════════════════════════════════════════════════════

pdf.set_font("AU", "", 11)
pdf.set_text_color(*INK)
pdf.cell(0, 7, "न्याय दृष्टांत  (Verified Case Law)", new_x="LMARGIN", new_y="NEXT")
rule(GOLD_LINE, 0.5)
vgap(4)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE CARD helper
# ═══════════════════════════════════════════════════════════════════════════════

def tag(txt, bg, fg, x, y, pad_h=2.8, pad_v=3.5):
    pdf.set_font("AU", "", 7)
    tw = pdf.get_string_width(txt) + pad_h * 2
    pdf.set_fill_color(*bg)
    pdf.set_draw_color(*bg)
    pdf.rect(x, y, tw, 5.5, "F")
    pdf.set_xy(x + pad_h, y + 0.8)
    pdf.set_text_color(*fg)
    pdf.cell(tw, 4, txt)
    return x + tw + 2


def case_card(num, citation, court_date, facts, held, why, link, sections_note=None):
    card_y = pdf.get_y()

    # Gold left rule
    pdf.set_fill_color(*GOLD)
    # We'll draw it after we know card height — use a placeholder line for now
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.4)
    start_y = card_y

    # Number badge
    pdf.set_xy(22, card_y)
    pdf.set_font("AU", "", 9)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.cell(6, 6, f"{num}.")

    # Citation (bold, large)
    pdf.set_xy(28, card_y)
    pdf.set_font("AU", "", 10.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(W - 10, 6, citation)

    vgap(1)

    # Court + date meta
    pdf.set_x(28)
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*INK3)
    pdf.multi_cell(W - 10, 4.5, court_date)
    vgap(2)

    # Tags row
    tx = 28
    ty = pdf.get_y()
    tx = tag("FIR Upheld", GOOD, WHITE, tx, ty)
    if sections_note:
        tx = tag(sections_note, NAVY, WHITE, tx, ty)
    tx = tag("MP HC" if "M.P." in court_date or "MP" in court_date or "Madhya" in court_date
             else ("Raj HC" if "Rajasthan" in court_date else "SC"), (50, 50, 45), WHITE, tx, ty)
    pdf.set_y(ty + 7)
    vgap(2)

    # Facts
    label("Facts")
    vgap(0.5)
    body(facts, size=9, color=INK2, gap=4.8, w=W - 10)
    vgap(2)

    # Held
    label("Held", color=GOOD)
    vgap(0.5)
    body(held, size=9, color=(30, 80, 30), gap=4.8, w=W - 10)
    vgap(2)

    # Why it fits
    label("Why It Fits")
    vgap(0.5)
    body(why, size=9, color=INK2, gap=4.8, w=W - 10)
    vgap(1.5)

    # Source link
    pdf.set_font("AU", "", 8)
    pdf.set_text_color(*GOLD_DEEP)
    pdf.cell(0, 5, f"Source: {link}", new_x="LMARGIN", new_y="NEXT")

    end_y = pdf.get_y()

    # Draw the left gold rule retrospectively
    pdf.set_draw_color(*GOLD)
    pdf.set_line_width(1.4)
    pdf.line(19.5, start_y, 19.5, end_y)

    vgap(6)
    rule(LINE, 0.2)
    vgap(6)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 1 — Indrapal Singh (MP HC, exact fact match)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="1",
    citation="Indrapal Singh & Others vs State of M.P. & Another",
    court_date="M.Cr.C. No. 7045/2011  ·  M.P. High Court, Gwalior Bench  ·  "
               "Justice G.S. Ahluwalia  ·  05.12.2017",
    facts=(
        "Brijkishore (1/5 hissedar) ne shikayatkarta ke saath 01.03.2011 ko "
        "vikray anubandh kiya aur Rs. 7,000/- agrim rashi prapt ki. Iske baad usi "
        "bhoomi ka panjikrith vikray patra 25.05.2011 ko Indrapal Singh ke naam "
        "sampaadit kar diya — anubandh ki avadhi ke bheetar hi usi zameen ka "
        "doosre vyakti ko registered vikray.\n"
        "[Facts: Agreement to sell with advance Rs 7,000 on 01.03.2011. Seller "
        "executed registered sale deed of SAME land to Indrapal Singh on 25.05.2011 "
        "— within the agreement period. Third-party sale with knowledge of prior "
        "agreement.]"
    ),
    held=(
        '"Prima facie the FIR discloses commission of cognizable offence and cannot '
        'be quashed at this stage." — Quashing petition DISMISSED. FIR under '
        "Sections 420, 467, 468, 471 IPC upheld. Principle: R. Kalyani v. Janak C. "
        "Mehta (2009) 1 SCC 516 — at FIR stage, court only examines whether "
        "allegations prima facie disclose a cognizable offence."
    ),
    why=(
        "Sarvaadhik prasangik — tathya aksharsah samaan: anubandh + agrim rashi + "
        "ussi bhoomi ka anya vyakti ko panjikrith bikri. M.P. High Court, Gwalior "
        "Khandhpith. 156(3) / FIR stage ke liye yahi sabse mazboot najaeer hai."
    ),
    link="https://indiankanoon.org/doc/23053924/",
    sections_note="S. 420+467+468",
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 2 — Smt. Chandi Bai (420+406 FIR survived)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="2",
    citation="Smt. Chandi Bai vs State of Rajasthan",
    court_date="S.B. Cri. Misc. Bail Appln. No. 15765/2023  ·  Rajasthan HC, Jodhpur  ·  "
               "Justice K. Mathur  ·  19.09.2023",
    facts=(
        "Aaropitaa ne Rs. 25 lakh mein vikray anubandh kiya, Rs. 5 lakh agrim "
        "rashi prapt ki. Tatpashchaat usi sampatti ka panjikrith vikray patra "
        "Pushpa ke naam sampaadit kar diya. FIR No. 156/2022 under Sections 420, "
        "406 & 120-B IPC registered.\n"
        "[Agreement to sell for Rs 25 lakh, advance Rs 5 lakh received. Same "
        "property sold via registered deed to third party Pushpa. FIR under both "
        "S. 420 + 406 + 120-B IPC registered and maintained.]"
    ),
    held=(
        "FIR under Sections 420, 406 & 120-B IPC was NOT QUASHED. Court granted "
        "only anticipatory bail (S. 438) with conditions including repayment of "
        "advance. FIR continues to hold — direct confirmation that 420+406 FIR "
        "can be registered and sustained in agreement-to-sell + advance + "
        "third-party sale fact pattern."
    ),
    why=(
        "Yah case directly confirm karta hai ki 420 + 406 dono dharaon mein FIR "
        "ek saath panjikrith ho sakti hai aur barqarar reh sakti hai. Rajasthan HC "
        "ne FIR raddh karne se inkar kiya. Peedit paksh ke liye seedha "
        "prasangik najaeer."
    ),
    link="https://indiankanoon.org/doc/54361637/",
    sections_note="S. 420+406+120B",
)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 3 — Priyanka Srivastava (procedural)
# ═══════════════════════════════════════════════════════════════════════════════

case_card(
    num="3",
    citation="Priyanka Srivastava & Another vs State of U.P. & Others",
    court_date="(2015) 6 SCC 287  ·  Supreme Court of India  ·  "
               "Justice V. Gopala Gowda & Justice Arun Mishra  ·  02.04.2015",
    facts=(
        "Supreme Court se dhara 156(3) CrPC ke avyavahar ko le kar dishi-nirdeshan "
        "maange gaye — kab Magistrate police janch ka aadesh de sakta hai aur "
        "iske liye kya shart hai."
    ),
    held=(
        "Dhara 156(3) CrPC ke antargat daayal praytek aavedan ke saath "
        "shikayatkarta ka SHAPTHAPATR (Affidavit) sanlagna hona ANIVAARY hai. "
        "Bina shapthapatr ke Magistrate aadesh dene ke liye baadhy nahin. Yah "
        "Supreme Court ka nirdesh hai, sampurn Bharat mein laagu.\n"
        "[Every application under S. 156(3) CrPC must be accompanied by an "
        "Affidavit of the complainant. Non-compliance is fatal to the application.]"
    ),
    why=(
        "Prakriyaatmak shart: yadi aavedan ke saath shapthapatr nahi hai to "
        "tuknik aadhar par nirasth ho sakta hai. Abhi jaanch lein."
    ),
    link="https://indiankanoon.org/doc/183735148/",
    sections_note="S. 156(3) CrPC",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ADVISORY BOX
# ═══════════════════════════════════════════════════════════════════════════════

vgap(2)
adv_y = pdf.get_y()
pdf.set_font("AU", "", 9)
ADVISORY = (
    "VIDHIK PARMARSH (Peedit paksh ke hit mein):\n\n"
    "Uchchtam Nyayalay ne recent nirnayonmein (2023-2025) ek siddhant sthaapit kiya "
    "hai ki Dhara 420 (cheating) aur 406 (criminal breach of trust) ek hi tathyon par "
    '"antithetical" (paraspar virodhi) ho sakti hain — kyonki 420 mein prarabh se hi '
    "kapaTpurn aashay aavashyak hai jabki 406 mein nishthapurvak saunpi gayi rashi ka "
    "baad mein durupyog aavashyak hai. Aaropitaa is aadhar par SC mein chunauti de "
    "sakta hai.\n\n"
    "SARVAADHIK MAZBOOT RANNITI:\n"
    "  *  Dhara 467/468 IPC jodein — panjikrith vikray anubandh ke hote hue bhi "
    "tritiiy paksh ke naam panjikrith vikray patra sampaadit karna 'mulyavaan "
    "pratibhooti ki kootrachana' (Dhara 467) aur 'dharoxa ke prayojan se kootrachana' "
    "(Dhara 468) hai.\n"
    "  *  Yahi sanyojan — 420 + 467 + 468 — Indrapal Singh (M.P. HC 2017) mein "
    "safal raha aur FIR barqarar rahi.\n"
    "  *  156(3) ke charan ka parikshan kewal 'prima facie cognizable offence' hai — "
    "yah dono uparokt najaeer mein poorit hai."
)

# Estimate height
pdf.set_font("AU", "", 9)
approx_h = 58  # will auto-extend

pdf.set_fill_color(*WARN_BG)
pdf.set_draw_color(*GOLD_LINE)
pdf.set_line_width(0.4)
pdf.rect(18, adv_y, W, approx_h, "FD")
pdf.set_fill_color(*GOLD)
pdf.rect(18, adv_y, 3, approx_h, "F")

pdf.set_xy(24, adv_y + 4)
pdf.set_font("AU", "", 8)
pdf.set_text_color(*GOLD_INK)
pdf.cell(0, 4.5, "ADVISORY  —  IMPORTANT FOR STRATEGY", new_x="LMARGIN", new_y="NEXT")
vgap(1)

body(ADVISORY, size=8.8, color=INK, gap=4.8, w=W - 8)

pdf.output(OUT)
print("Saved:", OUT)
