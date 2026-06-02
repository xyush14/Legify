"""Official open-data judgment corpus (Supreme Court e-SCR / AWS Open Data).

This package is the court-accepted-source layer that supplements Indian Kanoon
(a discovery aggregator). It serves the ACTUAL official judgment PDF — the copy
a judge accepts — fetched on demand from the public AWS Open Data buckets
(CC-BY-4.0), with the neutral citation + SCR citation as the court-accepted
anchor.

Read-side (`opendata.py`) is stdlib + requests only, so it ships in production
without pyarrow. The write-side (scripts/ingest_opendata_sc.py) builds the
tables and is harvest-only.
"""
