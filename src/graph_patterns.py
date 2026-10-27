"""Console only: the read-only Cypher patterns a typed GraphRAG question is routed to.

A small model picks ONE pattern and fills its parameters (tickers, an industry, risk names from a shortlist); it
never writes Cypher. Code checks the parameters, then the pattern runs over the exported graph in Python
(src/graph_local.py), which returns the same rows Neo4j returns for the Cypher shown on screen.
src/graph_parity.py runs every pattern in a real Neo4j and compares; tests/test_console_api.py runs it when one is up.

The two screen-4 templates (SHARED_AMONG, SHARED_VS_SPECIFIC) stay in graph_qa.TEMPLATES, untouched, so the scored
run's prompt hash does not move. Every row has the same shape as theirs, so graph_qa.prompt / to_subgraph / answer
work unchanged.
"""
import graph_qa
from graph_qa import _EVIDENCE

_RETURN = """RETURN r.id AS id, r.name AS risk, r.definition AS definition, coalesce(r.generic, false) AS generic,
       r.n_companies AS n_companies, {role} AS role, evidence"""

CYPHER = {
    "SHARED_AMONG": graph_qa.TEMPLATES["SHARED_AMONG"],
    "SHARED_VS_SPECIFIC": graph_qa.TEMPLATES["SHARED_VS_SPECIFIC"],
    "MOST_COMMON": f"""
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WHERE $industry IS NULL OR c.industry = $industry
WITH r, collect({_EVIDENCE}) AS evidence
WHERE NOT ($specific_only AND coalesce(r.generic, false))
{_RETURN.format(role="'most common'")}
ORDER BY size(evidence) DESC, coalesce(r.boilerplate_share, 0) DESC, risk
LIMIT $limit""",
    "WHO_FACES": f"""
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WHERE r.name IN $risks
WITH r, collect({_EVIDENCE}) AS evidence
{_RETURN.format(role="'asked about'")}
ORDER BY size(evidence) DESC, risk""",
    "COMPANY_RISKS": f"""
MATCH (:Company {{ticker: $ticker}})-[:FACES_RISK]->(r:RiskFactor)
MATCH (c:Company)-[f:FACES_RISK]->(r)
WITH r, collect({_EVIDENCE}) AS evidence
{_RETURN.format(role="'company profile'")}
ORDER BY generic, size(evidence) DESC, coalesce(r.boilerplate_share, 0), risk
LIMIT $limit""",
    "COMPANY_PEERS": f"""
MATCH (:Company {{ticker: $ticker}})-[:FACES_RISK]->(r:RiskFactor)
WHERE NOT coalesce(r.generic, false)
MATCH (c:Company)-[f:FACES_RISK]->(r)
WITH r, collect({_EVIDENCE}) AS evidence
WHERE size(evidence) >= 2
{_RETURN.format(role="'shared with peers'")}
ORDER BY size(evidence) DESC, coalesce(r.boilerplate_share, 0), risk
LIMIT $limit""",
    "UNIQUE_TO": f"""
MATCH (c:Company {{ticker: $ticker}})-[f:FACES_RISK]->(r:RiskFactor)
WHERE COUNT {{ (:Company)-[:FACES_RISK]->(r) }} = 1
WITH r, collect({_EVIDENCE}) AS evidence
{_RETURN.format(role="'only this company'")}
ORDER BY coalesce(r.boilerplate_share, 0), risk
LIMIT $limit""",
    "CROSS_INDUSTRY": f"""
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WHERE NOT coalesce(r.generic, false)
WITH r, collect({_EVIDENCE}) AS evidence, collect(DISTINCT c.industry) AS inds
WHERE all(i IN $industries WHERE i IN inds)
{_RETURN.format(role="'both industries'")}
ORDER BY size(evidence) DESC, coalesce(r.boilerplate_share, 0), risk
LIMIT $limit""",
    "INDUSTRY_ONLY": f"""
MATCH (c:Company)-[f:FACES_RISK]->(r:RiskFactor)
WITH r, collect({_EVIDENCE}) AS evidence, collect(DISTINCT c.industry) AS inds
WHERE inds = [$industry] AND size(evidence) >= 2
{_RETURN.format(role="'one industry only'")}
ORDER BY size(evidence) DESC, coalesce(r.boilerplate_share, 0), risk
LIMIT $limit""",
}

# What the router reads: one line per pattern, the parameters it must fill, and an example question.
ROUTES = {
    "MOST_COMMON": "the most common / most widely disclosed risks across the pool, optionally within one industry "
                   "(industry) and optionally ignoring boilerplate (specific_only). E.g. 'what is the most common risk?'",
    "SHARED_AMONG": "which risks two or more named companies share (tickers, at least two). E.g. 'what do GM and "
                    "NXP have in common?'",
    "WHO_FACES": "which companies disclose a given risk or topic (risks: pick 1-3 names from the shortlist). E.g. "
                 "'who is exposed to rare earths?'",
    "COMPANY_RISKS": "one company's main risks, its risk profile (tickers: exactly one). E.g. 'what are Tesla's "
                     "main risks?'",
    "COMPANY_PEERS": "one company's specific risks that other companies also disclose, i.e. who it is linked to "
                     "(tickers: exactly one). E.g. 'who shares Tesla's risks?'",
    "UNIQUE_TO": "risks only one company discloses (tickers: exactly one). E.g. 'what is unique to Ford?'",
    "CROSS_INDUSTRY": "specific risks that autos and chipmakers both disclose. E.g. 'what links autos to semis?'",
    "INDUSTRY_ONLY": "risks disclosed only within one industry (industry). E.g. 'which risks only chipmakers have?'",
    "SHARED_VS_SPECIFIC": "the single most shared risk and the single most shared specific auto-chip risk, side by side.",
    "BRIDGE_DRIVERS": "which named place, input or policy (not risk category) links automakers to chipmakers.",
    "SHARED_RISKS": "the overall question: what risks connect all the companies and who shares each.",
    "NONE": "anything else (not about these companies' disclosed risks, or needs numbers, dates or prices).",
}
LIMITS = {"MOST_COMMON": 5, "COMPANY_RISKS": 8, "COMPANY_PEERS": 6, "UNIQUE_TO": 6, "CROSS_INDUSTRY": 6, "INDUSTRY_ONLY": 6}
LOCAL = tuple(CYPHER)


def params_for(pattern, tickers, industry, risks, specific_only):
    """Parameters from the router's reply, checked in code. (params, None) or (None, why it cannot run)."""
    ind = industry if industry in graph_qa.INDUSTRIES else None
    lim = LIMITS.get(pattern)
    if pattern == "SHARED_AMONG":
        if len(tickers) < 2:
            return None, "it names fewer than two companies"
        return {"tickers": tickers, "min_shared": 2 if len(tickers) <= 3 else 3, "limit": 8}, None
    if pattern == "SHARED_VS_SPECIFIC":
        return {"min_shared": 2, "industries": graph_qa.INDUSTRIES}, None
    if pattern == "MOST_COMMON":
        return {"industry": ind, "specific_only": bool(specific_only), "limit": lim}, None
    if pattern == "WHO_FACES":
        return ({"risks": risks[:3]}, None) if risks else (None, "no risk in the graph matches it")
    if pattern in ("COMPANY_RISKS", "COMPANY_PEERS", "UNIQUE_TO"):
        return ({"ticker": tickers[0], "limit": lim}, None) if len(tickers) == 1 else (None, "it needs one company")
    if pattern == "CROSS_INDUSTRY":
        return {"industries": graph_qa.INDUSTRIES, "limit": lim}, None
    if pattern == "INDUSTRY_ONLY":
        return ({"industry": ind, "limit": lim}, None) if ind else (None, "it names no industry")
    return None, "no pattern answers it"
