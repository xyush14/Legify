"""Bundle the canonical engine (all 10 types) into one JSON the Drafting Studio
loads client-side: per type → label, field schema, sample data, rendered HI + EN
document HTML. Lets the studio run fully on the static node preview (no backend),
while prod uses the same field_spec/render via the API.

Run:  venv/bin/python scripts/build_studio_data.py
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# id → (module, label_hi, label_en, sample_attr, field_spec_args)
TYPES = [
    ("bail",        "जमानत",        "Bail",               "SAMPLE_SESSIONS", ("sessions", "regular")),
    ("cheque_138",  "चेक §138",     "Cheque §138",        "SAMPLE",          ()),
    ("discharge",   "उन्मोचन",      "Discharge",          "SAMPLE",          ("sessions",)),
    ("maintenance", "भरण-पोषण §144","Maintenance §144",   "SAMPLE",          ()),
    ("revision",    "पुनरीक्षण",     "Revision",           "SAMPLE",          ("hc",)),
    ("appeal",      "अपील §415",    "Appeal §415",        "SAMPLE",          ("sessions",)),
    ("dv",          "घरेलू हिंसा §12","Domestic Violence", "SAMPLE",          ()),
    ("quashing",    "अभिखण्डन §528","Quashing §528",      "SAMPLE",          ()),
    ("parivad",     "परिवाद §223",  "Complaint §223",     "SAMPLE",          ()),
    ("vakalatnama", "वकालतनामा",    "Vakalatnama",        "SAMPLE",          ()),
]

out = {"types": []}
for tid, lhi, len_, samp_attr, args in TYPES:
    m = importlib.import_module(f"headnote.drafter.templates.{tid}")
    spec = m.field_spec(*args)
    sample = getattr(m, samp_attr)
    # BLANK draft = the variant selectors (court/bail_type) + toggle defaults, NO dummy values.
    # This is what the studio opens with: empty fields + placeholder chips, no fake client data.
    blank = {k: sample[k] for k in ("court", "bail_type") if k in sample}
    blank["grounds"] = {t["key"]: bool(t.get("default", False)) for t in spec.get("toggles", [])}
    out["types"].append({
        "id": tid, "label_hi": lhi, "label_en": len_,
        "fields": spec.get("fields", []), "toggles": spec.get("toggles", []),
        "variants": spec.get("variants", {}), "companions": spec.get("companions", []),
        "blank": blank, "blank_hi": m.render_hi(blank), "blank_en": m.render_en(blank),
        "data": sample,   # example fill (available if we add a "load example" later)
        "hi": m.render_hi(sample), "en": m.render_en(sample),
    })

dest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    ".preview_tmp", "reviews", "studio-data.json")
with open(dest, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
print(f"wrote {dest} — {len(out['types'])} types, {os.path.getsize(dest)//1024} KB")
