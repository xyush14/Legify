"""Run the 100-query benchmark against the LIVE prompt-drafter classifier.

Each query gets an ACCEPTABLE-SET of doc_types (many research-style queries have
more than one defensible route). Score = classified type in the acceptable set.
Also reports the heuristic fallback's score on the same set.
"""
import sys, time, json, importlib.util
sys.path.insert(0, '/Users/ayushshivhare/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d')

spec = importlib.util.spec_from_file_location(
    "q", "/Users/ayushshivhare/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d/headnote_100_queries.py")
# import only the list without executing docx generation: read the file and eval the list
import re
src = open("/Users/ayushshivhare/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d/headnote_100_queries.py", encoding="utf-8").read()
m = re.search(r"queries = (\[.*?\n\])\n", src, re.S)
queries = eval(m.group(1))
assert len(queries) == 100, len(queries)

from headnote.drafter import from_prompt as FP

# acceptable doc_types per query (1-indexed → set)
A = {}
def acc(rng, *types):
    for i in (rng if isinstance(rng, (list, range)) else [rng]):
        A[i] = set(types)

# --- bail 1-15
acc(range(1, 8), "bail")
A[7] |= {"other_criminal", "revision"}          # juvenile transfer challenge
acc(8, "anticipatory_bail"); acc(9, "anticipatory_bail")
acc(range(10, 12), "bail")
acc(12, "reply", "other_criminal", "bail")       # resist bail-cancellation
acc(13, "default_bail", "bail")                  # 436A undertrial (query says "default bail")
acc(14, "bail"); acc(15, "bail")
# --- quashing 16-25
acc(range(16, 26), "quashing")
A[21] |= {"revision", "other_criminal"}          # challenge further-investigation order
# --- evidence & trial 26-40 (research → generic criminal or appeal)
acc(range(26, 41), "other_criminal", "appeal")
# --- sentencing 41-50
acc(range(41, 51), "appeal", "other_criminal")
A[47] |= {"compounding"}
A[48] |= {"suspension_389", "bail"}              # against incarceration pending appeal
A[49] |= {"bail"}
# --- appeal & revision 51-60
acc(51, "appeal", "other_criminal"); acc(52, "appeal")
acc(53, "revision"); acc(54, "revision", "quashing")
acc(55, "appeal"); acc(56, "appeal", "other_criminal")
acc(57, "appeal", "revision", "other_criminal")
acc(58, "appeal", "other_criminal"); acc(59, "appeal", "other_criminal"); acc(60, "appeal")
# --- procedures 61-75
acc(61, "revision", "quashing", "other_criminal")
acc(62, "revision", "parivad", "other_criminal")
acc(63, "other_criminal", "revision")
acc(64, "quashing")
acc(65, "other_criminal")
acc(66, "compounding", "quashing")
acc(67, "appeal", "other_criminal")
acc(68, "revision", "quashing", "other_criminal")
acc(69, "anticipatory_bail", "other_criminal")
acc(70, "other_criminal", "revision", "parivad")
acc(71, "recall_311", "other_criminal")
acc(72, "transfer_petition", "quashing", "other_criminal")
acc(73, "complaint_156")
acc(74, "other_criminal", "recall_311")
acc(75, "bail")
# --- BNSS transition 76-85 (research)
acc(76, "other_criminal", "discharge")
acc(77, "appeal", "other_criminal")
acc(78, "anticipatory_bail")
acc(79, "other_criminal", "quashing", "revision")
acc(80, "other_criminal", "quashing")
acc(81, "bail", "other_criminal")
acc(82, "quashing", "other_criminal")
acc(83, "other_criminal")
acc(84, "bail", "other_criminal")
acc(85, "other_criminal")
# --- specific offences 86-100 (defence research)
acc(86, "other_criminal", "quashing", "discharge", "bail")
acc(87, "quashing", "discharge", "bail", "other_criminal")
acc(88, "quashing", "other_criminal", "discharge")
acc(89, "quashing", "discharge", "ni_138_dismiss", "other_criminal")
acc(90, "discharge", "quashing", "other_criminal")
acc(91, "quashing", "other_criminal", "discharge")
acc(92, "other_criminal", "discharge", "bail")
acc(93, "discharge", "other_criminal", "quashing", "bail")
acc(94, "other_criminal", "discharge", "quashing")
acc(95, "other_criminal", "bail", "discharge")
acc(96, "other_criminal", "discharge", "bail")
acc(97, "other_criminal", "quashing", "bail")
acc(98, "quashing", "discharge", "other_criminal")
acc(99, "quashing", "other_criminal", "discharge")
acc(100, "other_criminal", "bail", "discharge")

assert set(A) == set(range(1, 101))

results = []
llm_hit = heur_hit = 0
for i, q in enumerate(queries, 1):
    heur = FP._heuristic_type(q)
    for attempt in range(3):
        try:
            cls = FP.classify(q)
            break
        except Exception as e:
            time.sleep(4 * (attempt + 1))
    dt = cls["doc_type"]
    ok = dt in A[i]
    hok = heur in A[i]
    llm_hit += ok; heur_hit += hok
    results.append({"i": i, "llm": dt, "conf": cls.get("confidence"), "heur": heur,
                    "ok": ok, "heur_ok": hok, "acc": sorted(A[i]), "q": q[:90]})
    print(f"{i:3d} {'✓' if ok else '✗'} llm={dt:<18} heur={'✓' if hok else '✗'}{heur:<18} | {q[:70]}")
    time.sleep(0.4)   # stay under Groq rate limits

print(f"\nLLM classifier: {llm_hit}/100   heuristic fallback: {heur_hit}/100")
misses = [r for r in results if not r["ok"]]
print(f"\n--- LLM misses ({len(misses)}) ---")
for r in misses:
    print(f"{r['i']:3d} got={r['llm']:<18} want∈{r['acc']}  | {r['q']}")
json.dump(results, open("/private/tmp/claude-501/-Users-ayushshivhare-Downloads-Legify-0bb187ba264e218517be944dbf64c433be6ae19d/c37a198d-6df0-4bfa-9afa-90fbbbf3402f/scratchpad/eval_results.json", "w"), ensure_ascii=False, indent=1)
