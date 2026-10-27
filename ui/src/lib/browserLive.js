// A typed graph question answered in the browser, for the published preview (no server behind it): the same
// pipeline as src/serve.py graph_stream, step for step, on the viewer's own Claude account (the page's `sample`
// capability, which asks the viewer's consent once).
//   route   : the model picks one pattern and fills its parameters (src/graph_patterns.py ROUTES); code checks them
//   rows    : the pattern runs over the exported graph here (a port of src/graph_local.py; same rows as Neo4j)
//   answer  : the model answers from the rows only, with the same prompt as graph_qa.answer
//   verify  : every quote must occur verbatim in that company's Item 1A (a port of src/verify.py)
//   note    : the analyst note from the verified claims (src/analyst_note.py)
// Events and the final message have the shapes of the server's NDJSON stream (see live.js).
import { DATA } from "./data.js";

let samplePromise = null;
export function sampler() {
  if (!samplePromise) samplePromise = (window.claude?.use ? window.claude.use("sample") : Promise.resolve(null)).catch(() => null);
  return samplePromise;
}

const B = () => DATA.browser_live;
const IND = t => (DATA.filings.find(f => f.ticker === t) || {}).industry || "other";

// ---------------------------------------------------------------- the patterns (src/graph_local.py)
function faces(g) {
  const out = {};
  for (const e of g.edges) (out[e.target] ||= {})[e.source.slice(2)] = e;
  return out;
}
const cmp = (a, b) => { for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return -1; if (a[i] > b[i]) return 1; } return 0; };
const bp = n => n.boilerplate_share || 0;

function row(node, edges, role, only) {
  const evidence = Object.keys(edges).sort().filter(t => !only || only.has(t)).map(t => {
    const qs = edges[t].quotes.slice(0, 2);
    return { ticker: t, quotes: qs.map(q => q.text), spans: qs.map(q => `${q.start}:${q.end}`), chunk_ids: qs.map(q => q.chunk_id) };
  });
  return { id: node.id.slice(2), risk: node.label, definition: node.definition || "", generic: !!node.generic,
    n_companies: node.degree, role, evidence };
}

function ranked(g, keep, key, role, limit) {
  const nodes = Object.fromEntries(g.nodes.map(n => [n.id, n])), f = faces(g);
  const got = Object.entries(f).map(([id, es]) => [nodes[id], es]).filter(([n, es]) => keep(n, es))
    .sort((a, b) => cmp(key(...a), key(...b)));
  return got.slice(0, limit ?? got.length).map(([n, es]) => row(n, es, role));
}

const n = es => Object.keys(es).length;
const inds = es => new Set(Object.keys(es).map(IND));

export function rowsFor(g, t, p) {
  if (t === "SHARED_AMONG") {
    const want = new Set(p.tickers);
    return ranked(g, (x, es) => Object.keys(es).filter(k => want.has(k)).length >= p.min_shared,
      (x, es) => [-Object.keys(es).filter(k => want.has(k)).length, x.generic ? 1 : 0, x.degree, x.label], "shared", p.limit)
      .map(r => ({ ...r, evidence: r.evidence.filter(e => want.has(e.ticker)) }));
  }
  if (t === "MOST_COMMON") {
    const nodes = Object.fromEntries(g.nodes.map(x => [x.id, x])), got = [];
    for (const [id, all] of Object.entries(faces(g))) {
      const es = Object.fromEntries(Object.entries(all).filter(([k]) => !p.industry || IND(k) === p.industry));
      if (n(es) && !(p.specific_only && nodes[id].generic)) got.push([nodes[id], es]);
    }
    got.sort((a, b) => cmp([-n(a[1]), -bp(a[0]), a[0].label], [-n(b[1]), -bp(b[0]), b[0].label]));
    return got.slice(0, p.limit).map(([x, es]) => row(x, es, "most common"));
  }
  if (t === "WHO_FACES") { const want = new Set(p.risks); return ranked(g, x => want.has(x.label), (x, es) => [-n(es), x.label], "asked about"); }
  if (t === "COMPANY_RISKS") return ranked(g, (x, es) => p.ticker in es, (x, es) => [x.generic ? 1 : 0, -n(es), bp(x), x.label], "company profile", p.limit);
  if (t === "COMPANY_PEERS") return ranked(g, (x, es) => p.ticker in es && !x.generic && n(es) >= 2, (x, es) => [-n(es), bp(x), x.label], "shared with peers", p.limit);
  if (t === "UNIQUE_TO") return ranked(g, (x, es) => n(es) === 1 && p.ticker in es, x => [bp(x), x.label], "only this company", p.limit);
  if (t === "CROSS_INDUSTRY") return ranked(g, (x, es) => !x.generic && p.industries.every(i => inds(es).has(i)), (x, es) => [-n(es), bp(x), x.label], "both industries", p.limit);
  if (t === "INDUSTRY_ONLY") return ranked(g, (x, es) => n(es) >= 2 && inds(es).size === 1 && inds(es).has(p.industry), (x, es) => [-n(es), bp(x), x.label], "one industry only", p.limit);
  if (t === "SHARED_VS_SPECIFIC") {
    const shared = ranked(g, () => true, (x, es) => [-n(es), -bp(x), x.label], "most shared", 1);
    const specific = ranked(g, (x, es) => !x.generic && n(es) >= p.min_shared && p.industries.every(i => inds(es).has(i)),
      (x, es) => [-n(es), bp(x), x.label], "most specific", 1);
    const seen = new Set();
    return [...shared, ...specific].sort((a, b) => (a.role < b.role ? -1 : 1)).filter(r => !seen.has(r.id) && seen.add(r.id));
  }
  throw new Error(`${t} is not a pattern`);
}

// The router's reply, checked in code (graph_patterns.params_for).
function paramsFor(t, tickers, industry, risks, specificOnly) {
  const ind = B().industries.includes(industry) ? industry : null, lim = B().limits[t];
  if (t === "SHARED_AMONG") return tickers.length < 2 ? [null, "it names fewer than two companies"]
    : [{ tickers, min_shared: tickers.length <= 3 ? 2 : 3, limit: 8 }, null];
  if (t === "SHARED_VS_SPECIFIC") return [{ min_shared: 2, industries: B().industries }, null];
  if (t === "MOST_COMMON") return [{ industry: ind, specific_only: !!specificOnly, limit: lim }, null];
  if (t === "WHO_FACES") return risks.length ? [{ risks: risks.slice(0, 3) }, null] : [null, "no risk in the graph matches it"];
  if (["COMPANY_RISKS", "COMPANY_PEERS", "UNIQUE_TO"].includes(t)) return tickers.length === 1 ? [{ ticker: tickers[0], limit: lim }, null] : [null, "it needs one company"];
  if (t === "CROSS_INDUSTRY") return [{ industries: B().industries, limit: lim }, null];
  if (t === "INDUSTRY_ONLY") return ind ? [{ industry: ind, limit: lim }, null] : [null, "it names no industry"];
  return [null, "no pattern answers it"];
}

// ---------------------------------------------------------------- rows -> prompt and subgraph (src/graph_qa.py)
function evidenceOf(r) {
  const ev = r.evidence.flatMap(e => e.quotes.map((q, i) => ({ ticker: e.ticker, risk: r.risk, quote: q, span: e.spans[i], chunk_id: e.chunk_ids[i] })));
  return ev.sort((a, b) => cmp(["ticker", "chunk_id", "span", "risk", "quote"].map(k => String(a[k] ?? "")),
    ["ticker", "chunk_id", "span", "risk", "quote"].map(k => String(b[k] ?? ""))));
}

export function toSubgraph(rows) {
  const nodes = [], edges = [], seen = new Set();
  for (const r of rows) {
    const byT = {};
    for (const e of evidenceOf(r)) {
      const [s, t] = e.span.split(":").map(Number);
      (byT[e.ticker] ||= []).push({ text: e.quote, start: s, end: t, chunk_id: e.chunk_id, risk_name: e.risk });
    }
    const id = "r:" + r.id;
    nodes.push({ id, label: r.risk, degree: Object.keys(byT).length, industries: [...new Set(Object.keys(byT).map(IND))].sort(),
      type: "RiskFactor", generic: r.generic, definition: r.definition, n_companies: r.n_companies, role: r.role });
    for (const t of Object.keys(byT).sort()) { edges.push({ source: `c:${t}`, target: id, quotes: byT[t].sort((a, b) => a.start - b.start).slice(0, 3) }); seen.add(t); }
  }
  const companies = [...seen].sort().map(t => ({ id: `c:${t}`, type: "Company", label: t, name: (DATA.filings.find(f => f.ticker === t) || {}).company || t, industry: IND(t) }));
  return { nodes: companies.concat(nodes), edges, drivers: [], driver_edges: [] };
}

function paragraph(t, start) {
  const text = DATA.texts[t] || "";
  for (const [s, e] of B().paragraphs[t] || []) if (s <= start && start < e) return text.slice(s, e).trim();
  return text.slice(Math.max(0, start - 400), start + 400).trim();
}

export function _prompt(question, rows) { return prompt(question, rows); }
function prompt(question, rows) {
  const sources = {}, blocks = [], seenBlocks = new Set(), lines = [];
  const cite = (e, whole) => {
    const body = whole ? paragraph(e.ticker, Number(e.span.split(":")[0])) : e.quote, cited = sources[e.chunk_id] || "";
    if (!whole && cited && locate(body, cited)) return e.chunk_id;
    const key = e.chunk_id + "\u0000" + body;
    if (!seenBlocks.has(key)) { seenBlocks.add(key); sources[e.chunk_id] = cited ? cited + "\n\n" + body : body; blocks.push(`[${e.chunk_id}] ${e.ticker}\n${body}\n`); }
    return e.chunk_id;
  };
  for (const r of rows) {
    const ev = evidenceOf(r), first = {};
    for (const e of ev) first[e.ticker] ||= e;
    const ids = [...new Set(ev.map(e => cite(e, first[e.ticker] === e)))];
    const tks = [...new Set(ev.map(e => e.ticker))].sort();
    lines.push(`RISK '${r.risk}'${r.role !== "shared" ? ` [${r.role}]` : ""}${r.generic ? " (generic)" : ""} disclosed by ${tks.join(", ")} (${r.n_companies} companies in the group); evidence ${ids.join(", ")}`);
  }
  return [`Question: ${question}\n\nQuery rows:\n${blocks.join("\n")}\n${lines.join("\n")}`, sources];
}

// ---------------------------------------------------------------- the verifier (src/verify.py)
const TYPO = { "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " ", "•": " ", "­": "" };
function normMap(text) {
  const out = [], index = [];
  for (let i = 0; i < text.length; i++) {
    for (let ch of text[i].normalize("NFKC")) {
      ch = ch in TYPO ? TYPO[ch] : ch;
      for (let c of ch) {
        if (/\s/.test(c)) { if (!out.length || out[out.length - 1] === " ") continue; c = " "; }
        out.push(c); index.push(i);
      }
    }
  }
  while (out.length && out[out.length - 1] === " ") { out.pop(); index.pop(); }
  return [out.join(""), index];
}
const normalise = t => normMap(t)[0].trim();
export function _locate(q, t) { return locate(q, t); }
function locate(quote, text) {
  const q = normalise(quote); if (q.length < 20) return null;
  const [norm, index] = normMap(text), i = norm.indexOf(q);
  return i < 0 ? null : [index[i], index[i + q.length - 1] + 1];
}

function verifyClaims(claims, sources) {
  const leaves = Object.fromEntries(DATA.taxonomy.leaves.map(l => [l.id, l.category])), cats = new Set(DATA.taxonomy.categories.map(c => c.id));
  const tickers = new Set(DATA.filings.map(f => f.ticker)), accepted = [], rejected = [];
  for (const raw of claims || []) {
    const c = Object.fromEntries(["company", "category", "leaf", "quote", "source_ref", "risk", "driver"].map(k => [k, String(raw?.[k] ?? "")]));
    c.secondary = false; c.fallback = false;
    const label = !tickers.has(c.company) ? `company '${c.company}' is not in the group` : !cats.has(c.category) ? `category '${c.category}' is not in the taxonomy`
      : !(c.leaf in leaves) ? `leaf '${c.leaf}' is not in the taxonomy` : leaves[c.leaf] !== c.category ? `leaf '${c.leaf}' does not belong to category '${c.category}'` : null;
    if (label) { rejected.push({ ...c, reason: label, check: "label" }); continue; }
    const span = locate(c.quote, DATA.texts[c.company] || "");
    if (!span) { rejected.push({ ...c, reason: normalise(c.quote).length < 20 ? "quote shorter than 20 characters" : "quote not found verbatim in the company's Item 1A", check: "quote" }); continue; }
    const src = sources[c.source_ref];
    accepted.push({ ...c, start: span[0], end: span[1], in_cited_source: !!(src && locate(c.quote, src)) });
  }
  const total = accepted.length + rejected.length;
  return [accepted, rejected, { claims: total, accepted: accepted.length, rejected: rejected.length,
    rejected_label: rejected.filter(r => r.check === "label").length, rejected_quote: rejected.filter(r => r.check === "quote").length,
    keyword_fallback: 0, quote_coverage: total ? Math.round(1000 * accepted.length / total) / 1000 : null,
    not_in_cited_source: accepted.filter(c => c.in_cited_source === false).length }];
}

// ---------------------------------------------------------------- the model calls
const CLAIMS_FORMAT = 'Reply with only one JSON object: {"summary": "two or three sentences answering the question", "claims": [{"risk": "2-6 word label", "company": "TICKER", "category": "category id", "leaf": "leaf id", "quote": "15-50 words copied exactly", "source_ref": "excerpt id"}]}.';
const NOTE_FORMAT = 'Reply with only one JSON object: {"takeaway": "...", "points": [{"risk": "...", "tickers": ["TICKER"], "why": "..."}], "caveat": "..."}.';

async function route(sample, question, signal) {
  const g = DATA.graph, risks = g.nodes.filter(x => x.type === "RiskFactor").map(x => x.label);
  const companies = DATA.filings.map(f => `${f.ticker}: ${f.company}, ${f.industry}`).join(", ");
  const patterns = Object.entries(B().routes).map(([k, v]) => `${k}: ${v}`).join("\n");
  const ask = `You route a question about the 10-K risk factors of a fixed group of companies to ONE read-only graph query pattern and fill its parameters. You never write a query. Patterns:\n${patterns}\n`
    + `Companies (ticker: name, industry): ${companies}.\nRisk names in the graph (use only these, exactly as written, for risks): ${risks.join("; ")}.\n\n`
    + `Question: ${question}\n\nReply with only one JSON object: {"template": "PATTERN", "tickers": ["TICKER"], "industry": "auto|semis|none", "risks": ["exact risk name"], "specific_only": false, "reason": "one line"}. tickers empty if none; risks empty unless WHO_FACES.`;
  const r = await sample.json(ask, { modelTier: "quick", signal });
  const t = String(r?.template || "NONE");
  if (["NONE", "SHARED_RISKS", "BRIDGE_DRIVERS"].includes(t) || !(t in B().routes)) return [t in B().routes ? t : "NONE", {}, String(r?.reason || "")];
  const known = new Set(DATA.filings.map(f => f.ticker)), names = new Set(risks);
  const tickers = [...new Set((r.tickers || []).map(String))].filter(x => known.has(x));
  const rs = [...new Set((r.risks || []).map(String))].filter(x => names.has(x));
  const [params, why] = paramsFor(t, tickers, r.industry, rs, r.specific_only);
  return params ? [t, params, String(r.reason || "")] : ["NONE", {}, `${t} cannot run: ${why}`];
}

function noteCheck(note, claims) {
  const have = new Set(claims.map(c => c.company));
  const points = (note?.points || []).map(p => ({ ...p, tickers: [...new Set((p.tickers || []).map(String))].filter(t => have.has(t)) })).filter(p => p.tickers.length);
  return { takeaway: String(note?.takeaway || "").trim(), points: points.slice(0, 5), caveat: String(note?.caveat || "").trim(),
    covered: [...have].sort(), not_reached: DATA.filings.map(f => f.ticker).filter(t => !have.has(t)), claims: claims.length };
}

async function writeNote(sample, question, claims, signal) {
  if (!claims.length) return null;
  const lines = claims.map((c, i) => `[${i + 1}] ${c.company} | ${c.leaf.split(".")[1].replaceAll("_", " ")} | "${c.quote.split(/\s+/).join(" ")}"`);
  const names = DATA.filings.map(f => `${f.ticker} (${f.industry})`).join(", ");
  try {
    const r = await sample.json(`${B().note_system}\n\nQuestion: ${question}\n\nCounterparties: ${names}\n\nAccepted claims:\n${lines.join("\n")}\n\n${NOTE_FORMAT}`, { signal });
    return noteCheck(r, claims);
  } catch (e) { return null; }  // the verified answer stands without a note
}

const why = e => ({ not_granted: "Claude access for this page was not allowed", sampling_disabled: "Claude is not available for this account",
  rate_limited: "too many asks just now; try again in a minute", invalid_json: "the model's reply could not be read", cancelled: "stopped" })[e?.code] || `the live call failed (${e?.code || "error"})`;

// The same events as /api/graph_ask: stage{step}, plan, then result | unanswered | replay.
export async function graphAsk(question, qid, { onEvent, onPlan, signal } = {}) {
  const sample = await sampler();
  if (!sample) return { type: "unanswered", note: "this view cannot reach Claude", offline: true };
  const t0 = performance.now(), fixed = Object.fromEntries((DATA.graph_qa?.questions || []).map(q => [q.id, q]));
  onEvent?.({ type: "stage", step: 0, text: "choosing a query pattern" });
  let template, params, reason;
  try {
    if (qid === "main") [template, params, reason] = ["SHARED_RISKS", {}, "the main question"];
    else if (fixed[qid]) [template, params, reason] = [fixed[qid].template, fixed[qid].params, "fixed question"];
    else [template, params, reason] = await route(sample, question, signal);
  } catch (e) { return { type: "unanswered", note: why(e) }; }
  if (template === "SHARED_RISKS") return { type: "replay", note: "the main question replays approach 2's frozen answer", closest: "main" };
  if (template === "BRIDGE_DRIVERS") return { type: "replay", note: "the bridge query needs every mention's quote; showing its recording", closest: "bridge" };
  if (template === "NONE") return { type: "unanswered", note: reason };
  onEvent?.({ type: "stage", step: 1, text: "running the read-only query" });
  const rows = rowsFor(DATA.graph, template, params), sub = toSubgraph(rows), cypher = B().cypher[template];
  const q = { id: qid || "typed", question, template, params };
  const plan = { type: "plan", ...q, cypher, rows: rows.length, subgraph: sub };
  onEvent?.(plan); onPlan?.(plan);
  if (!rows.length) return { type: "result", result: { ...q, rows: 0, cypher, subgraph: sub, empty: true, summary: "No link found: the query returned no rows, and the graph does not invent one.", claims: [], rejected: [], verification: null }, routed: { template, reason }, seconds: Math.round((performance.now() - t0) / 100) / 10 };
  const [user, sources] = prompt(question, rows);
  let reply;
  try { reply = await sample.json(`${B().graph_system}\n\n${user}\n\n${CLAIMS_FORMAT}`, { signal }); }
  catch (e) { return { type: "replay", note: why(e) }; }
  onEvent?.({ type: "stage", step: 4, text: "checking every quote" });
  const [claims, rejected, verification] = verifyClaims(reply?.claims, sources);
  onEvent?.({ type: "stage", step: 5, text: "writing the analyst note" });
  const note = await writeNote(sample, question, claims, signal);
  return { type: "result", routed: { template, reason }, seconds: Math.round((performance.now() - t0) / 100) / 10, browser: true,
    result: { ...q, rows: rows.length, cypher, subgraph: sub, empty: false, summary: String(reply?.summary || ""), claims, rejected, verification, note } };
}
