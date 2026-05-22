# Reference templates

Real court-filed examples used to tune the per-template `format_spec` in
[`headnote/drafter/compose_templates.py`](../headnote/drafter/compose_templates.py).

> ⚠️ **Everything in this folder except this README is gitignored.**
> Client names, FIR numbers, addresses, and any identifying details must
> never reach version control. Scrub before sharing if needed.

---

## Naming convention

```
{doc_type}__{court}__{notes}.{ext}
```

`doc_type` must match the id in `compose_templates.py`. Use lowercase + underscores.

Examples:
```
anticipatory_bail__mp_hc_gwalior__420_ipc.pdf
vakalatnama__sessions_court_bhopal__standard.pdf
mention_memo__mp_hc_gwalior__stay_extension.docx
quashing_petition__mp_hc_gwalior__civil_dispute.pdf
writ_petition__mp_hc_gwalior__habeas_corpus.pdf
default_bail__sessions_court__sample_clean.pdf
discharge_application__sessions_court__302_ipc.docx
maintenance__family_court__125_crpc.pdf
revision_petition__sessions_court__jm_order.pdf
reply_to_bail__mp_hc_gwalior__counter_to_anticipatory.docx
appeal_conviction__mp_hc_gwalior__302_acquittal_attempt.pdf
```

---

## All 11 supported `doc_type` ids

| id                     | en label                            | hi label                       |
| ---------------------- | ----------------------------------- | ------------------------------ |
| `vakalatnama`          | Vakalatnama                         | वकालतनामा                       |
| `mention_memo`         | Mention Memo                        | मेंशन मेमो                       |
| `anticipatory_bail`    | Anticipatory Bail (S.482 BNSS)      | अग्रिम जमानत                     |
| `quashing_petition`    | Quashing Petition (S.528 BNSS)      | निरस्तीकरण याचिका                |
| `writ_petition`        | Writ Petition (Art. 226)            | रिट याचिका                       |
| `default_bail`         | Default Bail (S.187(3) BNSS)        | स्थिर जमानत                       |
| `discharge_application`| Discharge Application               | उन्मोचन आवेदन                    |
| `maintenance`          | Maintenance (S.144 BNSS / 125 CrPC) | भरण-पोषण याचिका                  |
| `revision_petition`    | Criminal Revision                   | आपराधिक पुनरीक्षण                  |
| `reply_to_bail`        | Reply to Bail (Counter)             | प्रत्युत्तर                        |
| `appeal_conviction`    | Appeal against Conviction           | दोषसिद्धि अपील                    |

---

## Workflow per template

1. **You drop the file here** with the naming convention above.
2. **You tell Claude** in chat: "polish `anticipatory_bail` — see reference in `templates_reference/`"
3. Claude reads the file → extracts structure → rewrites `format_spec` and
   refines the `fields` list in `compose_templates.py`.
4. Deploy. You open `/draft/template/{doc_type}` → fill the form → watch the
   live preview match your reference.
5. Iterate via chat ("the prayer needs to be numbered like X", "missing
   verification clause", etc.).

---

## Priority order (suggested)

1. `anticipatory_bail` — reuses bail patterns, most volume
2. `vakalatnama` — fast win, simple structure
3. `mention_memo` — short, validates workflow
4. `quashing_petition` — long-form, tests format_spec under load
5. `writ_petition` — similar to quashing, builds on its patterns
6. The remaining 6 in any order — patterns will have stabilized

---

## Tip — what to scrub before adding

- Client name → "ABC" / "XYZ"
- Father's name → "[Father's name]"
- FIR number + year → keep year format, change the number ("FIR 12345/2025" → "FIR XXX/2025")
- Address → keep the city/PS name (helps the model match real geography), redact street + number
- DOB → "[DOB]"
- Phone / Aadhaar / PAN → fully redact

Court name, bench, section numbers, dates of orders, and procedural details
should stay — those carry the structural signal we need.
