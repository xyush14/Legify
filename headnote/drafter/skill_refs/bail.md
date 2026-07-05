# Bail family — drafting knowledge

Covers regular bail (Sessions §483 / Magistrate §480), High-Court successive
bail (§483), and anticipatory bail (§482). Grounds are genericised court Hindi;
case-specifics are ` ____ ` placeholders. Every citation is a CANDIDATE to verify
on Indian Kanoon / SCC and confirm with Vishnu ji before any use.

---

## A. Regular bail — Sessions (`regular_bail_439`) and Magistrate (`bail_437`)

**Section:** §483 BNSS (← 439 CrPC) at Sessions/HC; §480 BNSS (← 437 CrPC) at
Magistrate. Magistrate cannot grant in offences punishable with death/life;
Sessions & HC are unfettered.

**Structure:** cause title → parties (applicant full descriptor / State) → title
line (`प्रथम/द्वितीय जमानत आवेदन पत्र अन्तर्गत धारा 483 …`) → salutation → intro →
grounds → prayer → date+signature → advocate block → affidavit + verification.

**OCR source:** FIR (all pages) → fills `name, father, crime_no, police_station,
district, sections`. Facts narrative seeds ground 1.

### Legal test the court applies (drives the grounds)
- **Bail is the rule, jail the exception** (Article 21).
- **Triple test:** (a) flight risk, (b) tampering with evidence, (c) influencing
  witnesses — the grounds must rebut all three.
- Plus: nature & gravity, severity of punishment, prima-facie case, antecedents,
  **parity** with co-accused, **delay in trial / prolonged custody**.

### Grounds library
`always` = include in order; `conditional` = include only if the matter carries
the tag. Source `vishnu_filed` = from his real 439; `research` = added from court
principles (mark `reviewed: false` until Vishnu ji approves).

1. **[case line — always, case-specific]** `यह कि प्रार्थी के विरुद्ध पुलिस थाना ____ जिला ____ द्वारा अपराध क्रमांक ____ अंतर्गत धारा ____ के अंतर्गत प्रकरण पंजीबद्ध किया गया है।`  *(source: vishnu_filed)*
2. **[innocence / false implication — always]** `यह कि प्रार्थी के द्वारा कोई अपराध कारित नहीं किया गया है। प्रार्थी का किसी अपराध अथवा अपराधी से प्रत्यक्ष अथवा अप्रत्यक्ष कोई संबंध नहीं है तथा प्रार्थी को उक्त प्रकरण में झूठा फँसाया गया है।`  *(vishnu_filed)*
3. **[respected resident — always]** `यह कि प्रार्थी समाज का प्रतिष्ठित एवं सम्मानीय व्यक्ति है तथा उपर्युक्त वर्णित पते का स्थायी निवासी है।`  *(vishnu_filed)*
4. **[offence triable, not capital — always]** `यह कि अधिरोपित अपराध आजीवन कारावास अथवा मृत्यु दण्ड से दण्डनीय नहीं है तथा माननीय न्यायालय के समक्ष विचारणीय है।`  *(vishnu_filed)*
5. **[nature & circumstance — always]** `यह कि प्रकरण की परिस्थिति, तथ्यों एवं अपराध के स्वरूप को दृष्टिगत रखते हुए प्रार्थी को जमानत का लाभ दिया जाना न्यायोचित है।`  *(vishnu_filed)*
6. **[no flight / tampering — always; rebuts triple test]** `यह कि प्रार्थी के स्थायी निवासी होने के कारण जमानत का लाभ दिए जाने पर उसके फरार होने अथवा अभियोजन साक्ष्य अथवा साक्षियों को प्रभावित किए जाने की कोई संभावना नहीं है।`  *(vishnu_filed)*
7. **[will abide conditions — always]** `यह कि प्रार्थी जमानत पर रिहा किए जाने पर माननीय न्यायालय द्वारा अधिरोपित समस्त शर्तों का पालन करेगा एवं प्रत्येक नियत तिथि पर उपस्थित रहेगा।`  *(vishnu_filed)*
8. **[investigation complete — conditional: investigation_complete]** `यह कि विवेचना/अनुसंधान पूर्ण हो चुका है, अतः अब प्रार्थी को न्यायिक अभिरक्षा में रखे जाने की कोई आवश्यकता नहीं है।`  *(research)*
9. **[prolonged custody / trial delay — conditional: delay_in_trial]** `यह कि प्रार्थी दिनांक ____ से न्यायिक अभिरक्षा में निरुद्ध है तथा विचारण में समय लगना संभावित है; दीर्घ निरोध अनुच्छेद 21 के विरुद्ध है।`  *(research — anchor: Satender Kumar Antil)*
10. **[parity — conditional: co_accused_bailed]** `यह कि सह-अभियुक्त ____ को समान आधार पर माननीय न्यायालय द्वारा जमानत का लाभ प्रदान किया जा चुका है, अतः समानता (parity) के सिद्धांत पर प्रार्थी भी जमानत का पात्र है।`  *(research)*
11. **[statutory leniency — conditional: applicant_is_woman | is_sick | is_minor]** `यह कि प्रार्थिनी महिला है / प्रार्थी अस्वस्थ/वृद्ध है / प्रार्थी किशोर है, अतः धारा 480 बी.एन.एस.एस. के परंतुक के अंतर्गत विशेष रियायत का पात्र है।`  *(research)*
12. **[closer — always, last]** `यह कि शेष तर्क बहस के समय मौखिक रूप से निवेदित किए जाएँगे।`  *(vishnu_filed)*

### Candidate judgments (cite-at-hearing list — VERIFY before use)
- *P. Chidambaram v. Directorate of Enforcement* — triple test. `verified: false`
- *Sanjay Chandra v. CBI* (2012) — economic offence, bail not punitive. `verified: false`
- *Satender Kumar Antil v. CBI* (2022) — bail categories & guidelines; delay. `verified: false`
- *Ram Govind Upadhyay v. Sudarshan Singh* — factors for bail. `verified: false`

---

## B. Anticipatory bail (`anticipatory_bail_438`)

**Section:** §482 BNSS (← 438 CrPC). Pre-arrest; Sessions/HC only.

**Structure:** as above, but title `अग्रिम जमानत आवेदन अन्तर्गत धारा 482 …` and the
grounds pivot on *apprehension of arrest* + *false implication* rather than custody.

### Legal test
- Liberal protection of liberty; concrete apprehension of arrest required.
- Factors: nature & gravity, antecedents, flight risk, whether implication is to
  injure/humiliate, need for custodial interrogation.
- Arnesh Kumar guidelines apply for offences ≤ 7 years (§35 BNSS / 41 CrPC).

### Grounds library (anticipatory)
1. **[apprehension — always, case-specific]** `यह कि प्रार्थी को उपर्युक्त अपराध क्रमांक ____ में गिरफ्तारी की प्रबल आशंका है।`
2. **[false / malicious implication — always]** `यह कि प्रार्थी को रंजिशवश/द्वेषवश झूठा फँसाया गया है तथा उसका अपराध से कोई संबंध नहीं है।`
3. **[no custodial interrogation needed — always]** `यह कि प्रकरण में प्रार्थी से अभिरक्षात्मक पूछताछ की कोई आवश्यकता नहीं है; प्रार्थी अनुसंधान में सहयोग करने को तत्पर है।`
4. **[respected resident, no flight — always]** `यह कि प्रार्थी स्थायी निवासी एवं प्रतिष्ठित व्यक्ति है, फरार होने की कोई संभावना नहीं है।`
5. **[no antecedents — conditional: no_antecedents]** `यह कि प्रार्थी का कोई आपराधिक पूर्ववृत्त नहीं है।`
6. **[Arnesh Kumar — conditional: offence_upto_7yr]** `यह कि अधिरोपित अपराध सात वर्ष तक दण्डनीय है तथा अर्णेश कुमार के निर्देशानुसार स्वतः गिरफ्तारी अपेक्षित नहीं है।`  *(research — verify)*
7. **[will abide conditions — always]**
8. **[closer — always]** `यह कि शेष तर्क बहस के समय मौखिक रूप से निवेदित किए जाएँगे।`

### Candidate judgments (VERIFY)
- *Gurbaksh Singh Sibbia v. State of Punjab* (1980) — liberal interpretation. `verified: false`
- *Sushila Aggarwal v. State (NCT of Delhi)* (2020) — no automatic time-limit. `verified: false`
- *Arnesh Kumar v. State of Bihar* (2014) — arrest guidelines. `verified: false`

---

## Conditional tags (set from the matter / OCR / form)
`applicant_is_woman` · `is_sick` · `is_minor` · `successive_bail` ·
`co_accused_bailed` · `delay_in_trial` · `long_custody` · `investigation_complete`
· `economic_offence` · `no_antecedents` · `offence_upto_7yr`

These drive which `conditional` grounds appear, so one template adapts to the
matter without the lawyer hunting. The UI surfaces them as toggles.
