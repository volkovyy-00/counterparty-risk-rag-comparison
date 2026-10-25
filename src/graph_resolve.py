"""Entity resolution for GraphRAG v2: extract first, then resolve.

1. Normalise risk names (case, "risks related to ...", plural head noun) and merge exact matches.
2. Merge candidates: embedding neighbours (cosine >= GRAPH_SIM_MIN, top GRAPH_SIM_TOPK) united with
   RapidFuzz token_set_ratio >= GRAPH_LEX_MIN. Connected components larger than GRAPH_COMPONENT_MAX are split
   by raising the cosine threshold locally (chains otherwise make one mega-cluster).
3. GRAPH_RESOLVER=llm: one call per multi-member component decides which members are the same driver AND the
   same mechanism of harm. A code rule then refuses known opposite pairs (supplier vs customer concentration...).
   exact: step 1 only. fuzzy: WRatio >= 0.8 on names (the library resolver's rule), for comparison.
4. ExposureDrivers: alias table (config/graph_aliases.yaml), then exact match per type; the LLM only sees
   leftover near-duplicates.
5. Generic score per RiskFactor; everything is written to results/graph_resolution_<corpus>.json.
"""
import json
import math
import re
from collections import Counter

import numpy as np
import yaml

import config
import llm

RESOLVE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["groups"],
    "properties": {"groups": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["member_ids", "canonical_name", "definition"],
        "properties": {"member_ids": {"type": "array", "items": {"type": "string"}},
                       "canonical_name": {"type": "string"}, "definition": {"type": "string"}}}}},
}

RESOLVE_SYSTEM = """You decide which risk names extracted from different 10-K Risk Factors sections describe the \
same risk. You get a list of candidates, each as: id | risk name | what is specific to the company | ticker.

Merge members into one group when a credit analyst comparing companies would count them as the same risk: the \
same driver AND the same way it harms the business. Differences in wording, company-specific detail, product or \
severity are not a reason to keep members apart (e.g. "cyclical semiconductor demand volatility" and \
"semiconductor overcapacity downturns"; "emissions regulation costs" and "emissions non-compliance penalties"). \
Keep apart adjacent or opposite concepts, even when the words overlap:
- supplier concentration vs customer concentration
- shortage of an input vs price inflation of the same input
- physical climate risk (weather, natural disasters) vs climate regulation (emission standards, carbon rules)
- export controls vs import tariffs
- product recalls vs product liability claims
- disruption at the company's own plants vs disruption at its suppliers
For each group give canonical_name: the most specific name (3-7 words, sentence case) that is still true for every \
member, and definition: one sentence saying what the risk is. A member that matches no other member is returned as \
a group of one. Use every id exactly once and never invent an id."""

DRIVER_SYSTEM = """You decide which named exposure drivers from different 10-K Risk Factors sections are the same \
real-world thing (the same place, company, input, law or policy, or end market). You get candidates as: \
id | name | type. Merge only names that refer to exactly the same thing (e.g. "PRC" and "China"); keep apart \
related but different things (e.g. "China" and "Taiwan", "Section 232 tariffs" and "Section 301 tariffs"). For each \
group give canonical_name (the clearest common name) and definition (one short sentence). Use every id exactly once \
and never invent an id."""

# Opposite or adjacent concepts that must never end up in one RiskFactor (checked in code, after the LLM).
KEEP_APART = [
    ("supplier vs customer", r"\b(supplier|vendor|sourc)", r"\bcustomer"),
    ("shortage vs price", r"\b(shortage|availability|scarcit)", r"\b(price|cost|inflation)"),
    ("physical climate vs climate regulation", r"\b(physical|weather|natural disaster|flood|storm|hurricane)",
     r"\b(regulat|emission|greenhouse|carbon|standard)"),
    ("export controls vs import tariffs", r"\bexport", r"\b(import|tariff)"),
    ("recalls vs product liability", r"\brecall", r"\bliabilit"),
    ("own plants vs suppliers", r"\b(own plant|our plant|manufacturing facilit|plant|factor(y|ies))", r"\bsupplier"),
]

_PREFIX = re.compile(r"^(the\s+)?(risks?|exposure)\s+(of|from|to|in|related to|relating to|associated with|regarding)\s+")


def normalise_name(name):
    s = re.sub(r"\s+", " ", name.lower().strip().strip("."))
    s = _PREFIX.sub("", s)
    s = re.sub(r"\s+risks?$", "", s).strip()
    words = s.split(" ")
    last = words[-1]
    if len(last) > 3 and last.endswith("ies"):
        words[-1] = last[:-3] + "y"
    elif len(last) > 3 and last.endswith("s") and not last.endswith(("ss", "us", "is")):
        words[-1] = last[:-1]
    return " ".join(words)


def display_name(name):
    """A name as shown on screen: without "Risks related to ..." and with a capital first letter."""
    s = re.sub(r"^(the\s+)?(risks?|exposure)\s+(of|from|to|in|related to|relating to|associated with|regarding)\s+",
               "", name.strip(), flags=re.I)
    return s[:1].upper() + s[1:] if s else name


# --------------------------------------------------------------------------- candidates
class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _components(n, pairs):
    uf = _UF(n)
    for a, b in pairs:
        uf.union(a, b)
    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), g))


def candidate_pairs(texts, names, sim_min=None, top_k=None, lex_min=None):
    """{(i, j): {"cos": float, "lex": float}} for i < j: embedding neighbours united with lexical matches."""
    from rapidfuzz import fuzz, process

    sim_min = config.GRAPH_SIM_MIN if sim_min is None else sim_min
    top_k = top_k or config.GRAPH_SIM_TOPK
    lex_min = config.GRAPH_LEX_MIN if lex_min is None else lex_min
    n = len(texts)
    if n < 2:
        return {}, np.zeros((n, n))
    v = np.asarray(llm.embed(texts), dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True).clip(1e-9)
    cos = v @ v.T
    lex = process.cdist(names, names, scorer=fuzz.token_set_ratio, processor=str.lower)
    pairs = {}
    for i in range(n):
        order = [j for j in np.argsort(-cos[i]) if j != i][:top_k]
        for j in order:
            if cos[i, j] >= sim_min:
                pairs[(min(i, j), max(i, j))] = None
        for j in np.nonzero(lex[i] >= lex_min)[0]:
            if j != i:
                pairs[(min(i, j), max(i, j))] = None
    return {p: {"cos": round(float(cos[p]), 4), "lex": float(lex[p])} for p in pairs}, cos


def split_large(members, pairs, cos, start):
    """Split a component above GRAPH_COMPONENT_MAX by raising the cosine threshold inside it."""
    limit = config.GRAPH_COMPONENT_MAX
    if len(members) <= limit:
        return [members]
    thr = start + 0.02
    while thr <= 0.99:
        local = {m: k for k, m in enumerate(members)}
        keep = [(local[a], local[b]) for a, b in pairs if a in local and b in local and cos[a, b] >= thr]
        parts = [[members[k] for k in comp] for comp in _components(len(members), keep)]
        if all(len(p) <= limit for p in parts):
            return parts
        out = []
        for p in parts:
            out += split_large(p, pairs, cos, thr) if len(p) > limit else [p]
        return out
    return [members[i:i + limit] for i in range(0, len(members), limit)]


# --------------------------------------------------------------------------- adjudication
def _adjudicate(system, schema_name, lines, ids):
    """LLM groups for one component. Unknown ids are dropped, duplicates ignored, missing ids become singletons."""
    with llm.METER.as_stage("graph.resolve"):
        reply = llm.chat(system, "Candidates:\n" + "\n".join(lines), schema=RESOLVE_SCHEMA, schema_name=schema_name)
    seen, groups = set(), []
    for g in reply.get("groups", []):
        members = [m for m in g.get("member_ids", []) if m in ids and m not in seen]
        seen.update(members)
        if members:
            groups.append({"members": members, "canonical_name": (g.get("canonical_name") or "").strip(),
                           "definition": (g.get("definition") or "").strip()})
    groups += [{"members": [m], "canonical_name": "", "definition": ""} for m in ids if m not in seen]
    return groups


def keep_apart_violation(names):
    """The KEEP_APART rule that `names` (one proposed group) breaks, or None."""
    for label, a, b in KEEP_APART:
        side_a = [n for n in names if re.search(a, n, re.I) and not re.search(b, n, re.I)]
        side_b = [n for n in names if re.search(b, n, re.I) and not re.search(a, n, re.I)]
        if side_a and side_b:
            return label
    return None


# --------------------------------------------------------------------------- risk factors
def resolve_risks(mentions, filings, resolver=None):
    resolver = resolver or config.GRAPH_RESOLVER
    keys = {}
    for m in mentions:
        keys.setdefault(normalise_name(m["risk_name"]), []).append(m)
    norm = sorted(keys)
    display = [Counter(m["risk_name"] for m in keys[k]).most_common(1)[0][0] for k in norm]
    nid = [f"n{i}" for i in range(len(norm))]
    audit = {"resolver": resolver, "mentions": len(mentions), "names_exact": len(norm), "components": [],
             "candidate_pairs": [], "merges_approved": [], "merges_rejected": []}

    if resolver == "exact" or len(norm) < 2:
        groups = [{"members": [i], "canonical_name": "", "definition": ""} for i in range(len(norm))]
    elif resolver == "fuzzy":
        from rapidfuzz import fuzz

        pairs = [(i, j) for i in range(len(norm)) for j in range(i + 1, len(norm))
                 if fuzz.WRatio(display[i], display[j], processor=str.lower) / 100 >= 0.8]
        groups = [{"members": comp, "canonical_name": "", "definition": ""}
                  for comp in _components(len(norm), pairs)]
    else:
        first = {k: sorted(keys[k], key=lambda m: m["id"])[0] for k in norm}
        texts = [f"{display[i]} — {first[k].get('detail', '')}" for i, k in enumerate(norm)]
        pairs, cos = candidate_pairs(texts, display)
        comps = []
        for comp in _components(len(norm), list(pairs)):
            comps += split_large(comp, pairs, cos, config.GRAPH_SIM_MIN) if len(comp) > 1 else [comp]
        groups = []
        for c_idx, comp in enumerate(comps):
            if len(comp) == 1:
                groups.append({"members": comp, "canonical_name": "", "definition": ""})
                continue
            ids = [nid[i] for i in comp]
            tickers = lambda i: ",".join(sorted({m["ticker"] for m in keys[norm[i]]}))  # noqa: E731
            lines = [f"{nid[i]} | {display[i]} | {first[norm[i]].get('detail', '')} | {tickers(i)}" for i in comp]
            decided = _adjudicate(RESOLVE_SYSTEM, "risk_groups", lines, set(ids))
            audit["components"].append({"component": c_idx, "members": [display[i] for i in comp],
                                        "groups": [[display[nid.index(x)] for x in g["members"]] for g in decided]})
            for g in decided:
                idx = [nid.index(x) for x in g["members"]]
                rule = keep_apart_violation([display[i] for i in idx]) if len(idx) > 1 else None
                if rule:
                    audit["merges_rejected"].append({"members": [display[i] for i in idx], "reason": f"rule: {rule}",
                                                     "proposed_name": g["canonical_name"]})
                    groups += [{"members": [i], "canonical_name": "", "definition": ""} for i in idx]
                    continue
                if len(idx) > 1:
                    audit["merges_approved"].append({"members": [display[i] for i in idx],
                                                     "canonical_name": g["canonical_name"],
                                                     "definition": g["definition"]})
                groups.append({"members": idx, "canonical_name": g["canonical_name"], "definition": g["definition"]})
        group_of = {i: k for k, g in enumerate(groups) for i in g["members"]}
        for (a, b), s in sorted(pairs.items()):
            same = group_of[a] == group_of[b]
            audit["candidate_pairs"].append({"a": display[a], "b": display[b], **s,
                                             "decision": "merged" if same else "kept apart"})
            if not same and not any(r.get("members") == [display[a], display[b]] for r in audit["merges_rejected"]):
                audit["merges_rejected"].append({"members": [display[a], display[b]], "reason": "llm", **s})

    n_total = max(len({f["ticker"] for f in filings}), 1)
    generic_min = math.ceil(config.GENERIC_SHARE * n_total)
    risk_factors, rf_of = [], {}
    for k, g in enumerate(sorted(groups, key=lambda g: min(g["members"]))):
        members = [m for i in g["members"] for m in keys[norm[i]]]
        names = Counter(m["risk_name"] for m in members)
        tickers = sorted({m["ticker"] for m in members})
        n = len(tickers)
        boiler = sum(m.get("specificity") == "boilerplate" for m in members) / len(members)
        rf = {"id": f"rf{k}", "name": g["canonical_name"] or display_name(names.most_common(1)[0][0]),
              "definition": g["definition"], "aliases": sorted(names), "mention_ids": sorted(m["id"] for m in members),
              "tickers": tickers, "n_companies": n,
              "industries": sorted({config.INDUSTRY.get(t, "other") for t in tickers}),
              "idf": round(math.log(n_total / n), 4), "boilerplate_share": round(boiler, 3),
              "generic": n >= generic_min or (boiler >= 0.75 and n >= 3)}
        risk_factors.append(rf)
        for m in members:
            rf_of[m["id"]] = rf["id"]
    audit["risk_factors"] = len(risk_factors)
    audit["generic_rule"] = {"generic_share": config.GENERIC_SHARE, "companies": n_total, "min_companies": generic_min,
                             "or": "boilerplate_share >= 0.75 and n_companies >= 3"}
    return risk_factors, rf_of, audit


# --------------------------------------------------------------------------- drivers
def _aliases():
    path = config.CONFIG_DIR / "graph_aliases.yaml"
    table = yaml.safe_load(path.read_text()) if path.exists() else {}
    return {_driver_key(a): canon for canon, names in (table or {}).items() for a in [canon, *(names or [])]}


def _driver_key(name):
    s = re.sub(r"\s+", " ", name.strip().strip(".").lower())
    return re.sub(r"^the ", "", s)


def resolve_drivers(mentions, resolver=None):
    from rapidfuzz import fuzz

    resolver = resolver or config.GRAPH_RESOLVER
    alias = _aliases()
    keyed = {}
    for m in mentions:
        for d in m.get("drivers", []):
            canon = alias.get(_driver_key(d["name"]), d["name"].strip())
            keyed.setdefault((d["type"], _driver_key(canon)), {"names": Counter(), "mentions": set(), "canon": canon})
            entry = keyed[(d["type"], _driver_key(canon))]
            entry["names"][d["name"].strip()] += 1
            entry["mentions"].add(m["id"])
    keys = sorted(keyed)
    audit = {"drivers_exact": len(keys), "merges_approved": [], "merges_rejected": []}
    groups = [[i] for i in range(len(keys))]
    if resolver == "llm" and len(keys) > 1:
        pairs = [(i, j) for i in range(len(keys)) for j in range(i + 1, len(keys))
                 if keys[i][0] == keys[j][0] and fuzz.token_set_ratio(keys[i][1], keys[j][1]) >= config.GRAPH_LEX_MIN]
        groups = []
        for comp in _components(len(keys), pairs):
            if len(comp) == 1:
                groups.append(comp)
                continue
            ids = {f"d{i}": i for i in comp}
            lines = [f"d{i} | {keyed[keys[i]]['canon']} | {keys[i][0]}" for i in comp]
            for g in _adjudicate(DRIVER_SYSTEM, "driver_groups", lines, set(ids)):
                idx = [ids[x] for x in g["members"]]
                groups.append(idx)
                if len(idx) > 1:
                    audit["merges_approved"].append([keyed[keys[i]]["canon"] for i in idx])
            for a, b in pairs:
                if a in comp and b in comp and not any(a in g and b in g for g in groups):
                    audit["merges_rejected"].append([keyed[keys[a]]["canon"], keyed[keys[b]]["canon"]])
    drivers, drv_of = [], {}
    for k, g in enumerate(sorted(groups, key=min)):
        entries = [keyed[keys[i]] for i in g]
        names = sum((e["names"] for e in entries), Counter())
        mids = sorted(set().union(*(e["mentions"] for e in entries)))
        d = {"id": f"d{k}", "name": entries[0]["canon"], "type": keys[g[0]][0], "aliases": sorted(names),
             "mention_ids": mids}
        drivers.append(d)
        for mid in mids:
            drv_of.setdefault(mid, []).append(d["id"])
    audit["drivers"] = len(drivers)
    return drivers, drv_of, audit


def resolve(mentions, filings, resolver=None):
    """Resolve risks and drivers; write the audit file. Returns the snapshot dict (also used by the loader)."""
    risk_factors, rf_of, audit = resolve_risks(mentions, filings, resolver)
    drivers, drv_of, d_audit = resolve_drivers(mentions, resolver)
    tickers_of = {m["id"]: m["ticker"] for m in mentions}
    for d in drivers:
        d["tickers"] = sorted({tickers_of[i] for i in d["mention_ids"]})
    out = [dict(m, rf_id=rf_of[m["id"]], driver_ids=drv_of.get(m["id"], [])) for m in mentions]
    audit["drivers"] = d_audit
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RESULTS_DIR / f"graph_resolution_{config.CORPUS}.json").write_text(json.dumps(audit, indent=1))
    return {"mentions": out, "risk_factors": risk_factors, "drivers": drivers, "audit": audit}
