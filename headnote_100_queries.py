"""Generate a .docx file with 100 Indian criminal law test queries for Headnote."""

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

queries = [
    # --- BAIL (1-15) ---
    "My client is a first-time offender charged under Section 420 IPC for cheating. No recovery has been made. He has been in judicial custody for 45 days. What are the strongest precedents for regular bail?",
    "Accused is a 22-year-old college student charged under NDPS Act Section 20 for possession of 15 grams of cannabis. No prior record, cooperated with investigation. What bail precedents apply?",
    "A woman has been arrested under Section 498A IPC based on her in-laws' complaint. She is 7 months pregnant and the only caretaker of a 3-year-old child. What are the bail precedents considering her condition?",
    "Client charged under Section 307 IPC for attempt to murder after a road rage incident. Single blow with a blunt object, victim has recovered fully. Investigation complete, chargesheet filed. Bail grounds?",
    "Accused is charged under PMLA along with predicate offence under IPC 420. He is a salaried employee, not the main accused. Twin conditions under Section 45 PMLA — what precedents allow bail?",
    "My client has been denied bail twice by the Sessions Court under Section 376 IPC. The complainant's statement has major contradictions with the medical report. Grounds for High Court bail?",
    "Juvenile (17 years 8 months) charged under Section 302 IPC. The Juvenile Justice Board treated him as an adult. What precedents challenge this transfer and support bail?",
    "Client arrested under SC/ST Prevention of Atrocities Act. The FIR was filed 6 months after the alleged incident with no corroboration. What anticipatory bail precedents apply?",
    "Accused in a cheque bounce case under Section 138 NI Act has been summoned. He wants anticipatory bail fearing arrest. Is anticipatory bail even maintainable in NI Act cases?",
    "My client is charged under Section 304B IPC (dowry death). The death occurred 8 years after marriage. What is the legal position on the 7-year presumption period and bail prospects?",
    "Accused charged under UAPA Section 18 (conspiracy). He is a student who attended a protest. No direct evidence of violence. What are the bail precedents under UAPA's strict bail provisions?",
    "Client granted bail by Sessions Court but the State has challenged it in High Court. What are the principles governing cancellation of bail and how to resist it?",
    "Undertrial has been in custody for 3 years for an offence carrying maximum 7 years. Section 436A CrPC default bail — what are the precedents when the prosecution opposes?",
    "Co-accused in a murder case. My client was not present at the scene — only allegation is prior conspiracy based on phone records. All other co-accused are on bail. Bail parity argument?",
    "Accused is an 80-year-old with multiple comorbidities charged under Section 302 IPC. Medical reports confirm he cannot survive prolonged incarceration. Humanitarian bail precedents?",

    # --- FIR QUASHING (16-25) ---
    "FIR registered under Section 420/406/506 IPC arising from a civil property dispute between siblings. The entire dispute is over partition of ancestral property. Quashing under Section 482 CrPC?",
    "Complainant filed FIR under 498A/406 IPC after divorce petition was filed by husband. All allegations are vague without specific dates or instances. What are the quashing precedents for vague FIRs?",
    "FIR under Section 376 IPC filed by a woman after the accused refused to marry her. They had a consensual relationship for 3 years with WhatsApp evidence. Quashing on grounds of consent?",
    "Criminal complaint under Section 138 NI Act filed despite the cheque amount already being paid through a civil decree. Can the criminal proceedings be quashed as an abuse of process?",
    "FIR registered under Section 420 IPC for a genuine commercial dispute where goods were delivered but payment is delayed. No mens rea for cheating. What precedents support quashing?",
    "Police filed closure report but the Magistrate rejected it and directed further investigation. Can the accused challenge this order and seek quashing of the FIR?",
    "FIR under Section 354/509 IPC filed by a colleague at workplace. CCTV footage contradicts the allegations completely. What are the precedents for quashing when evidence disproves the FIR?",
    "Two FIRs filed for the same incident — one by the complainant and a counter-FIR by the accused. Can the second FIR be quashed on grounds of double jeopardy or abuse of process?",
    "FIR under IT Act Section 66A which has been struck down by the Supreme Court. The FIR was registered before the judgment but chargesheet filed after. Can it be quashed?",
    "Matrimonial FIR under 498A naming 15 family members including minor children and elderly parents living in a different city. What are the precedents for quashing against distant relatives?",

    # --- EVIDENCE & TRIAL (26-40) ---
    "Prosecution's sole eyewitness is an interested witness (brother of the deceased). No independent corroboration. What are the precedents on conviction based solely on interested witness testimony?",
    "Electronic evidence — WhatsApp messages and call records — produced without Section 65B certificate. Defence objected at trial. What are the latest precedents on admissibility?",
    "Confession made to police officer recorded on video. Defence argues it violates Section 25 of the Evidence Act. Prosecution says it was a voluntary statement. What precedents apply?",
    "Post-mortem report contradicts the eyewitness version about the nature of injuries and weapon used. How do courts treat such medical-ocular discrepancy?",
    "Dying declaration recorded by a Magistrate but the doctor's fitness certificate was obtained 2 hours after the declaration was recorded. Can the dying declaration be relied upon?",
    "Prosecution examined only 3 out of 15 listed witnesses and closed evidence. Defence argues this creates adverse inference. What are the precedents on non-examination of material witnesses?",
    "DNA evidence presented in a rape case but the chain of custody has gaps — sample collected by constable, not forensic expert. Defence challenges admissibility. Precedents?",
    "Identification parade conducted 6 months after the incident. Only 3 suspects in the parade alongside the accused. Defence challenges the TIP procedure. What precedents apply?",
    "FIR registered 72 hours after the incident with no explanation for the delay. Defence argues this makes the FIR an afterthought. What are the precedents on delayed FIR?",
    "Recovery of weapon shown as made on the disclosure statement of the accused under Section 27 Evidence Act. But the independent witnesses turned hostile. What are the evidentiary consequences?",
    "Child witness aged 8 years is the sole eyewitness to a murder. No corroboration from any other source. Can conviction rest on uncorroborated child witness testimony?",
    "The investigating officer has been found to have fabricated evidence in a prior case. Defence seeks to impeach the entire investigation. What precedents address tainted investigation?",
    "Circumstantial evidence case — prosecution relies on last-seen theory. Gap between last-seen and discovery of body is 5 days. Is the chain of circumstances complete?",
    "Expert witness (handwriting expert) gives opinion that signature is forged. Defence produces its own expert who says signature is genuine. How do courts resolve conflicting expert opinions?",
    "Confession to Magistrate under Section 164 CrPC retracted at trial by the accused. What evidentiary value does a retracted confession have and what precedents govern this?",

    # --- SENTENCING (41-50) ---
    "Client convicted under Section 302 IPC. He was 19 at the time of offence, first offender, from a disadvantaged background. Arguments for commuting death sentence to life imprisonment?",
    "Accused convicted for dowry death under 304B. He has already served 10 years. What are the precedents on premature release and remission for 304B convicts?",
    "Conviction under Section 376 IPC. Mandatory minimum sentence is 10 years. The relationship was initially consensual but the promise to marry was broken. Can court go below the mandatory minimum?",
    "Client convicted under NDPS Act Section 21 for commercial quantity. Mandatory minimum 10 years. He is a first-time offender and an addict himself. Precedents for sentence reduction?",
    "Two accused convicted for the same offence. One got 7 years, the other got 3 years despite identical roles. Can the disparity in sentencing be challenged?",
    "Accused convicted under Section 304 Part II (culpable homicide not amounting to murder) instead of 302. Prosecution appeals seeking enhancement to Section 302. What are the precedents?",
    "Client convicted for attempt to murder (307 IPC). Victim has fully recovered and has filed an affidavit supporting lenient sentence. How do courts consider victim's forgiveness in sentencing?",
    "Accused has been on bail throughout trial and convicted. He has a family to support, no prior record. Arguments against immediate incarceration pending appeal?",
    "Juvenile convicted by JJB sent to special home. He is now 21. Can he be released or does he continue to serve? What happens when a juvenile becomes an adult during sentence?",
    "Multiple FIRs for the same transaction — client convicted in one case, acquitted in another. Can the conviction be challenged on grounds of inconsistency?",

    # --- APPEAL & REVISION (51-60) ---
    "Client acquitted by Sessions Court. State appeals in High Court after 2 years. What are the precedents on interference with acquittal and the standard for reversing acquittal?",
    "High Court convicted the accused while reversing the trial court's acquittal, without re-appreciating the entire evidence. Grounds for appeal to Supreme Court?",
    "Trial court dismissed the discharge application. Can this order be challenged in revision? What are the precedents on revisability of discharge rejection orders?",
    "Magistrate took cognizance without applying mind — issued process mechanically on the chargesheet. What are the precedents for challenging such orders in revision?",
    "Victim's right to appeal against acquittal under Section 372 CrPC. The State decided not to appeal. Can the victim independently challenge the acquittal?",
    "Appeal against conviction filed one day late due to advocate's illness. What are the precedents on condonation of delay in criminal appeals?",
    "Client convicted ex parte after the trial court refused adjournment when he was hospitalized. The medical certificate was produced. Grounds for setting aside ex parte conviction?",
    "Two judges in a division bench gave conflicting opinions on the appeal — one for acquittal, one for conviction. What is the procedure when there is a split verdict?",
    "Accused wants to file a review petition against Supreme Court judgment dismissing SLP. What are the very limited grounds on which criminal review is entertained?",
    "Trial court convicted under Section 302, High Court reduced it to 304 Part I on appeal. Prosecution files appeal to Supreme Court for restoration. What are the precedents?",

    # --- CRPC PROCEDURES (61-75) ---
    "Magistrate issued non-bailable warrant without first issuing summons or bailable warrant. The accused was never given an opportunity to appear. Can this be challenged?",
    "Private complaint under Section 200 CrPC. The Magistrate dismissed it without examining the complainant on oath. Is this a reversible error?",
    "Charge was framed under Section 302 IPC but evidence during trial disclosed Section 304 Part II at best. Can the charge be altered mid-trial under Section 216 CrPC?",
    "Investigation has been pending for 3 years with no chargesheet filed. Accused is on bail with conditions restricting travel. Can the FIR be quashed for unexplained delay in investigation?",
    "Section 164 statement of a witness recorded by a Magistrate. Witness deviates from it during trial. What is the evidentiary value and how can the 164 statement be used?",
    "Complainant wants to withdraw the criminal case filed under 498A after reconciliation. What is the procedure for compounding and what precedents permit it?",
    "Accused was not served with copy of FIR or chargesheet before the trial began. Trial completed and conviction entered. Is non-supply of documents a ground to set aside conviction?",
    "Police registered FIR under cognizable offence but the Magistrate directed investigation under Section 156(3) for additional offences. Can the police challenge this direction?",
    "Anticipatory bail granted with condition to join investigation. Accused joined investigation once but police want him again for custodial interrogation. Can the condition be modified?",
    "Complainant filed protest petition after the Magistrate accepted the closure report. What are the precedents on the Magistrate's powers after accepting a final report?",
    "Defence filed application under Section 311 CrPC to recall a prosecution witness for further cross-examination based on newly discovered documents. When must this be allowed?",
    "Case has been transferred from one court to another three times in 5 years. Accused argues this violates right to speedy trial. What are the precedents on transfer and speedy trial?",
    "Police refused to register FIR despite a cognizable offence being disclosed. Complainant approached Magistrate under Section 156(3). What are the Magistrate's powers and precedents?",
    "Accused wants to produce a witness who was not listed in the defence witness list. Trial court refused. Can additional defence witnesses be allowed at a late stage?",
    "Session court denied bail. Accused filed fresh application before High Court without mentioning the earlier rejection. Is non-disclosure of prior applications fatal to the bail plea?",

    # --- BNS / BNSS TRANSITION (76-85) ---
    "Offence committed before July 2024 but chargesheet filed after BNS came into force. Should the accused be charged under IPC or BNS? What are the transitional provisions?",
    "Client convicted under Section 420 IPC (old law). The corresponding BNS Section 318 has different punishment. Which law applies for sentencing when the appeal is heard post-BNS?",
    "Anticipatory bail application filed under Section 438 CrPC. After BNSS came into force, should the application be treated under Section 482 BNSS? Do the conditions differ?",
    "FIR registered under BNSS for an offence that was non-cognizable under CrPC but is now cognizable under BNSS. Can the accused argue that the old law should apply since the act was committed before BNSS?",
    "Zero FIR concept under BNSS Section 173(1). FIR registered at a police station with no jurisdiction over the offence. What are the precedents on the validity of zero FIR and subsequent transfer?",
    "Bail conditions under BNSS Section 480(2) — mandatory conditions not present in old CrPC. What are these new conditions and how have courts interpreted them in the first year?",
    "Section 528 BNSS (inherent powers, formerly Section 482 CrPC). Has the scope of inherent powers changed under the new code? Any early precedents interpreting the transition?",
    "Plea bargaining expanded under BNSS. Client charged under BNS Section 115 (voluntarily causing hurt). Can he apply for plea bargaining and what sentence reduction can he expect?",
    "Victim's right to be heard under BNSS Section 360 at every stage including bail. How have courts implemented this and does it change the bail hearing dynamics?",
    "Community service as punishment introduced under BNS. Client convicted for a minor offence — can community service be sought as an alternative to imprisonment?",

    # --- SPECIFIC OFFENCES (86-100) ---
    "Client is a doctor accused of medical negligence resulting in patient death. Charged under Section 304A IPC. The medical board opinion says it was an error of judgment, not negligence. Precedents?",
    "Husband charged under Section 306 IPC (abetment of suicide) after wife's suicide. Only evidence is a suicide note naming him. No evidence of instigation or provocation. What are the precedents?",
    "Accused charged with criminal defamation under Section 499/500 IPC for a social media post criticizing a public official's policy decisions. Freedom of speech defence and precedents?",
    "Client is a company director charged under Section 138 NI Act for a cheque signed by another director. He had resigned before the cheque was issued. Vicarious liability precedents?",
    "Accused charged under Section 354A IPC (sexual harassment at workplace). The only evidence is the complainant's statement with no corroboration. Internal committee found no misconduct. Precedents?",
    "False rape case — DNA evidence excludes the accused completely. The complainant has a history of filing false cases. What are the precedents for quashing and action against false complainant?",
    "Client charged under Section 379/411 IPC for possessing a second-hand phone that turned out to be stolen. He purchased it from a shop with a receipt. How to establish bona fide purchase defence?",
    "Accused charged under Section 304B and 498A. The marriage lasted only 3 months. Deceased's family alleges dowry demand but the only evidence is their own testimony. Sufficiency of evidence?",
    "Client accused of forgery under Section 465/468 IPC of educational certificates for government job. He claims he obtained them from an authorized institution. What defences apply?",
    "My client ran over a pedestrian while driving. Charged under Section 304A IPC. The deceased was jaywalking on a highway at night wearing dark clothes. Contributory negligence as a defence?",
    "Accused charged under Prevention of Corruption Act for demanding bribe. The trap was laid but no marked currency was recovered from his person. Only video evidence of conversation. Precedents?",
    "Client is a journalist charged under Official Secrets Act for publishing classified defence information. He claims protection under freedom of press. What precedents balance national security and press freedom?",
    "Accused charged under Section 506 IPC (criminal intimidation) for sending a legal notice threatening to file a case. Can a legal notice constitute criminal intimidation?",
    "Wife filed FIR under Section 377 IPC (unnatural offences) against husband during matrimonial dispute. Post-2018 SC judgment decriminalizing homosexuality, does Section 377 still apply to non-consensual acts?",
    "Client charged under Wildlife Protection Act for possessing a shahtoosh shawl. She claims she inherited it from her grandmother and didn't know it was illegal. What defences and precedents apply?",
]

doc = Document()

# Title
title = doc.add_heading("Headnote — 100 Test Queries", level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

# Subtitle
sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run("Indian Criminal Law Research Queries for Testing")
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(100, 100, 100)

doc.add_paragraph()  # spacer

# Category headers and query ranges
categories = [
    ("Bail & Anticipatory Bail", 0, 15),
    ("FIR Quashing (Section 482 CrPC / 528 BNSS)", 15, 25),
    ("Evidence & Trial", 25, 40),
    ("Sentencing", 40, 50),
    ("Appeal & Revision", 50, 60),
    ("CrPC / BNSS Procedures", 60, 75),
    ("BNS / BNSS Transition Issues", 75, 85),
    ("Specific Offences & Defences", 85, 100),
]

for cat_name, start, end in categories:
    doc.add_heading(cat_name, level=1)
    for i in range(start, end):
        para = doc.add_paragraph()
        # Query number in bold
        run_num = para.add_run(f"{i+1}. ")
        run_num.bold = True
        run_num.font.size = Pt(10)
        # Query text
        run_text = para.add_run(queries[i])
        run_text.font.size = Pt(10)
        # Add spacing after each query
        para.paragraph_format.space_after = Pt(8)
    doc.add_paragraph()  # spacer between categories

# Footer note
footer = doc.add_paragraph()
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run(
    "Generated for Headnote (headnote.in) — "
    "No location/jurisdiction specified in any query. "
    "All queries are original and cover the full spectrum of Indian criminal law practice."
)
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(130, 130, 130)
run.italic = True

out_path = "/Users/ayushshivhare/Downloads/Headnote_100_Test_Queries.docx"
doc.save(out_path)
print(f"Saved to {out_path}")
