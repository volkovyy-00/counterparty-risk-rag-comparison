"""Console only: an analyst note written from an answer's VERIFIED claims, the same way for every approach.

    python src/analyst_note.py                         # builds every prompt, prints the estimate, STOPS
    python src/analyst_note.py --only rag:main --confirm-usd 0.05   # one note (an example)
    python src/analyst_note.py --confirm-usd 0.5       # every recorded console ask -> results/console/notes.json

The approaches' own answers and the scored run are untouched: this is a reading aid on top of them. The model sees
the question and the claims the verifier accepted (company, risk, quote), nothing else, so it can only talk about
companies and risks that are already backed by a quote. Code then drops any ticker it names that no accepted claim
supports, and lists the companies the answer never reached (the model is not asked to).
"""
import argparse
import datetime
import json

import config
import llm
import taxonomy

OUT = config.RESULTS_DIR / "console" / "notes.json"
ASSUME_OUT = 700  # output tokens per note, assumed (stated, not measured)
NOTE_MODEL = config.env("CONSOLE_NOTE_MODEL", config.LLM_MODEL)

SYSTEM = (
    "You are a senior credit analyst writing a note a risk committee reads in thirty seconds. You get a question "
    "about a group of counterparties and the claims an automatic verifier accepted. Each claim is a company "
    "ticker, a risk and a sentence quoted verbatim from that company's latest 10-K, Item 1A Risk Factors. Use ONLY "
    "these claims: no outside knowledge, no numbers, dates or names that are not in a quote.\n\n"
    "Write:\n"
    "- takeaway: one sentence (at most 30 words) that answers the question and says what it means for "
    "counterparty credit risk: a concentration, a shock several counterparties would feel at once, or that the "
    "evidence shows nothing specific.\n"
    "- points: 3 to 5 risks, most decision-relevant first. Prefer risks that several companies share, and that "
    "link the two industries, over risks every filer states. For each give a short risk name (2-5 words), the "
    "tickers whose claims support it, and why it matters for credit in at most 25 words (the transmission: a "
    "common supplier, a shared policy or trade shock, funding and refinancing, demand from the same end market). "
    "Call boilerplate boilerplate.\n"
    "- caveat: one short sentence on what this evidence cannot tell (for example, only two companies were "
    "reached, or quotes describe exposure, not size). Do not repeat the takeaway."
)


def schema():
    return {"type": "object", "additionalProperties": False, "required": ["takeaway", "points", "caveat"],
            "properties": {
                "takeaway": {"type": "string"},
                "points": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["risk", "tickers", "why"],
                    "properties": {"risk": {"type": "string"},
                                   "tickers": {"type": "array", "items": {"type": "string", "enum": config.TICKERS}},
                                   "why": {"type": "string"}}}},
                "caveat": {"type": "string"}}}


def user_prompt(question, claims):
    names = ", ".join(f"{t} ({config.INDUSTRY.get(t, 'other')})" for t in config.TICKERS)
    lines = [f"[{i + 1}] {c['company']} | {taxonomy.leaf_name(c['leaf'])} | \"{' '.join(c['quote'].split())}\""
             for i, c in enumerate(claims)]
    return f"Question: {question}\n\nCounterparties: {names}\n\nAccepted claims:\n" + "\n".join(lines)


def check(note, claims):
    """Keep only tickers an accepted claim supports; add, in code, who the answer never reached."""
    have = {c["company"] for c in claims}
    points = []
    for p in note.get("points") or []:
        tks = [t for t in dict.fromkeys(p.get("tickers") or []) if t in have]
        if tks:
            points.append(dict(p, tickers=tks))
    return {"takeaway": note.get("takeaway", "").strip(), "points": points[:5], "caveat": note.get("caveat", "").strip(),
            "covered": sorted(have), "not_reached": [t for t in config.TICKERS if t not in have],
            "claims": len(claims)}


def write(question, claims, cache=None, timeout=None):
    """(note, record). No claims -> no call."""
    if not claims:
        return None, None
    reply, record = llm.chat(SYSTEM, user_prompt(question, claims), schema=schema(), schema_name="analyst_note",
                             model=NOTE_MODEL, effort="low", cache=cache, timeout=timeout, return_record=True)
    return check(reply, claims), record


def recorded_asks():
    """(key, question, claims) for every answer the console replays."""
    run = config.RESULTS_DIR / "demo_run"
    a1 = json.loads((run / "approach_1_plain_rag.json").read_text())
    a2 = json.loads((run / "approach_2_graphrag.json").read_text())
    out = [("rag:main", config.QUESTION, a1["claims"])]
    path = config.RESULTS_DIR / "console" / "rag_asks.json"
    if path.exists():
        out += [(f"rag:{a['id']}", a["question"], a["result"]["claims"])
                for a in json.loads(path.read_text())["asks"] if a.get("result")]
    out.append(("graph:main", config.QUESTION, a2["claims"]))
    qa = run / "graph_qa.json"
    if qa.exists():
        out += [(f"graph:{q['id']}", q["question"], q.get("claims") or []) for q in json.loads(qa.read_text())["questions"]]
    return [x for x in out if x[2]]


def main():
    from estimate_cost import _row, _tokens

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm-usd", type=float, default=0.0)
    parser.add_argument("--only", help="comma-separated keys, e.g. rag:main")
    args = parser.parse_args()
    notes = json.loads(OUT.read_text())["notes"] if OUT.exists() else {}
    want = set(args.only.split(",")) if args.only else None
    todo = [x for x in recorded_asks() if (want is None or x[0] in want) and x[0] not in notes]
    measure = bool(config.env("ANTHROPIC_API_KEY")) and config.LLM_PROVIDER == "anthropic"
    tok, measured = 0, True
    for _, q, claims in todo:
        n, m = _tokens(SYSTEM, user_prompt(q, claims), measure, NOTE_MODEL)
        tok, measured = tok + n, measured and m
    est = _row("analyst notes", len(todo), tok, len(todo) * ASSUME_OUT, model=NOTE_MODEL)
    how = "measured" if measured else "estimated as characters / 4"
    print(f"Analyst notes ({NOTE_MODEL}): {est['calls']} calls, {est['input_tokens']:,} input tokens ({how}), "
          f"{est['output_tokens']:,} output tokens (assumed) = ${est['cost_usd'] or 0:.2f}")
    if not todo or (est["cost_usd"] or 0) > args.confirm_usd:
        raise SystemExit("Nothing was spent." + (f" Re-run with --confirm-usd N (N >= {est['cost_usd'] or 0:.2f})."
                                                 if todo else " Every note is already recorded."))
    for key, q, claims in todo:
        note, record = write(q, claims)
        notes[key] = dict(note, recorded_at=record.get("recorded_at"))
        print(f"  {key}: {note['takeaway']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"notes": notes, "prompt": SYSTEM,
                               "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                               "usage": llm.METER.summary(*llm.METER.stages)}, indent=1))
    print(f"{len(notes)} notes -> {config.rel(OUT)}")


if __name__ == "__main__":
    main()
