// Read-only helpers over the run data (results/demo_run/ -> data.json, written by src/build_demo.py --json).
// Ported from demo/template.html so both pages show the same numbers, quotes and offsets.

export let DATA = null;
export const setData = d => { DATA = d; LEAVES = DEBRIS = DEBRIS_INLINE = null; };

export const NAMES = {
  "1_plain_rag": "Plain RAG", "2_graphrag": "GraphRAG", "3_taxonomy_first": "Taxonomy-first", "0_long_context": "Long context",
};
export const NUM = { "1_plain_rag": "1", "2_graphrag": "2", "3_taxonomy_first": "3", "0_long_context": "L" };
export const NM = "not measured";

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
export const pct = x => x == null ? NM : Math.round(x * 100) + "%";
export const f2 = x => x == null ? NM : x.toFixed(2);

// Shorten at a word boundary (never mid-word); the full text is always one click away.
export const short = (s, n) => {
  s = String(s ?? ""); if (s.length <= n) return s;
  const cut = s.slice(0, n - 1), sp = cut.lastIndexOf(" ");
  return (sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:–-]+$/, "") + "…";
};

export const filings = () => DATA.filings;
export const tickers = () => DATA.filings.map(f => f.ticker);
export const filing = t => DATA.filings.find(f => f.ticker === t) || {};
export const industry = t => filing(t).industry || "other";
export const groupN = () => DATA.graph_qa?.build?.n_group || tickers().length;

let LEAVES = null;
export const leafName = id => {
  LEAVES = LEAVES || Object.fromEntries(DATA.taxonomy.leaves.map(l => [l.id, l.label]));
  return LEAVES[id] || (String(id).includes(".") ? id.split(".")[1].replace(/_/g, " ") : String(id));
};
export const catName = id => (DATA.taxonomy.categories.find(c => c.id === id) || {}).name || String(id);
export const labelName = id => String(id).includes(".") ? leafName(id) : catName(id);
export const keyVerified = () => DATA.meta.key_status === "verified";

// Page furniture dropped from DISPLAYED text only; offsets and verification use the untouched filing text.
let DEBRIS = null, DEBRIS_INLINE = null;
export function clean(s) {
  DEBRIS = DEBRIS || (DATA.debris || []).map(([p, f]) => new RegExp(p, f));
  return String(s ?? "").split("\n").map(l => DEBRIS.some(rx => rx.test(l.trim())) ? "\0" : l).join("\n")
    .replace(/(?<=[^.!?:;\s])\s*\0(?:\s*\0)*\s*(?=[a-z])/g, " ").replace(/\n*\0(?:\s*\0)*\n*/g, "\n\n").replace(/\n{3,}/g, "\n\n");
}
export const oneLine = s => {
  DEBRIS_INLINE = DEBRIS_INLINE || (DATA.debris_inline || []).map(([p, f]) => new RegExp(p, f + "g"));
  let out = clean(s).replace(/\s+/g, " ").trim(); DEBRIS_INLINE.forEach(rx => out = out.replace(rx, " "));
  return out.replace(/\s+/g, " ").trim();
};

// Times in the talk's time zone (Prague: CET on 4 Nov), with the zone named.
export function local(iso) {
  if (!iso) return "?";
  try {
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Prague", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hourCycle: "h23", timeZoneName: "short",
    }).formatToParts(new Date(iso.replace(/([+-]\d\d)(\d\d)$/, "$1:$2"))).map(x => [x.type, x.value]));
    return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute} ${p.timeZoneName}`;
  } catch (e) { return String(iso).slice(0, 16).replace("T", " ") + " UTC"; }
}

// The quote in its filing: {before, hit, after}, about `pad` characters each side.
export function context(c, pad = 420) {
  const text = DATA.texts[c.company] || "";
  if (c.start == null || !text) return { before: "", hit: c.quote, after: "", a: 0, b: 0 };
  const a = Math.max(0, c.start - pad), b = Math.min(text.length, c.end + pad);
  return {
    before: (a > 0 ? "…" : "") + clean(text.slice(a, c.start)), hit: clean(text.slice(c.start, c.end)).trim(),
    after: clean(text.slice(c.end, b)) + (b < text.length ? "…" : ""),
  };
}
export function fullText(c) {
  const text = DATA.texts[c.company] || "";
  return { before: clean(text.slice(0, c.start)), hit: clean(text.slice(c.start, c.end)).trim(), after: clean(text.slice(c.end)) };
}
export function edgarLink(c) {
  const f = filing(c.company);
  if (!f.url || !String(f.url).startsWith("http")) return "";
  const w = c.quote.replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/\s+/g, " ").trim().split(" ");
  const enc = s => encodeURIComponent(s).replace(/-/g, "%2D");
  const frag = w.length <= 10 ? enc(w.join(" ")) : enc(w.slice(0, 5).join(" ")) + "," + enc(w.slice(-5).join(" "));
  return `${f.url}#:~:text=${frag}`;
}

/* ---------------------------------------------------------------- taxonomy heatmap */
export function heatRows(r, level) {
  const m = r.matrix[level] || {}, T = tickers(), n = T.length, v = (label, t) => (m[label] || {})[t] || 0;
  const rows = Object.keys(m).map(label => {
    const has = T.filter(t => v(label, t) > 0);
    const total = T.reduce((a, t) => a + v(label, t), 0);
    const inds = new Set(has.map(industry));
    return { label, k: has.length, has, total, generic: has.length >= 0.8 * n, cross: inds.has("auto") && inds.has("semis") };
  });
  const rank = x => x.k >= 2 ? (x.generic ? 1 : 0) : 2;
  return rows.filter(x => level === "category" || x.k >= 2)
    .sort((a, b) => rank(a) - rank(b) || b.k - a.k || b.total - a.total || a.label.localeCompare(b.label));
}
export function otherDrivers(r) {
  const cs = r.claims || [];
  if (!cs.some(c => "driver" in c && c.driver)) return null;
  const g = {};
  cs.filter(c => c.leaf.startsWith("OTHER.") && c.driver).forEach(c => {
    const k = c.driver.toLowerCase().trim(), e = g[k] = g[k] || { key: k, n: 0, tickers: [], forms: {} };
    e.n++; e.forms[c.driver.trim()] = (e.forms[c.driver.trim()] || 0) + 1;
    if (!e.tickers.includes(c.company)) e.tickers.push(c.company);
  });
  Object.values(g).forEach(e => e.name = Object.entries(e.forms).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0]);
  return Object.values(g).sort((a, b) => b.tickers.length - a.tickers.length || b.n - a.n || a.key.localeCompare(b.key));
}

/* ---------------------------------------------------------------- graph */
export const isCross = n => (n.industries || []).includes("auto") && (n.industries || []).includes("semis");
// Which companies a risk or driver node links to, from the edges.
export function companiesOf(g, id) {
  return [...new Set(g.edges.concat(g.driver_edges || []).filter(e => e.target === id).map(e => e.source.slice(2)))];
}
export function qaHeadline(q) {
  const g = q.subgraph, N = groupN();
  if (q.empty) return q.template === "BRIDGE_DRIVERS" ? "No bridge found. The graph won't invent a link." : "No rows returned";
  if (q.generic_only) return "Only generic links, no specific bridge";
  const d = (g.drivers || [])[0];
  if (q.template === "BRIDGE_DRIVERS" && d) return `Most specific link: ${d.label}, ${d.n_companies ?? d.degree} of ${N}, both industries`;
  const risks = g.nodes.filter(n => n.type === "RiskFactor");
  if (q.template === "SHARED_VS_SPECIFIC") {
    const sp = risks.find(n => n.role === "most specific"), sh = risks.find(n => n.role === "most shared") || risks[0];
    if (sp) return `Most specific: ${sp.label}, ${sp.n_companies} of ${N}, both industries`;
    if (sh) return `Most shared: ${sh.label}, ${sh.n_companies} of ${N}; no specific risk spans both industries`;
  }
  const top = risks[0], cos = g.nodes.filter(n => n.type === "Company").length, tk = q.params?.ticker;
  if (top && q.template === "MOST_COMMON") return `Most common: ${top.label}, ${top.n_companies} of ${N}`;
  if (top && q.template === "WHO_FACES") return `${cos} of ${N} disclose ${risks.length === 1 ? "it" : "these risks"}`;
  if (top && q.template === "COMPANY_RISKS") return `${tk}: ${risks.length} risks shown, ${risks.filter(n => n.n_companies > 1).length} shared with peers`;
  if (top && q.template === "COMPANY_PEERS") return `${tk} is linked to ${cos - 1} companies; widest: ${top.label}, ${top.n_companies} of ${N}`;
  if (top && q.template === "UNIQUE_TO") return `${risks.length} risks only ${tk} discloses`;
  if (top && q.template === "CROSS_INDUSTRY") return `${risks.length} specific risks span both industries; widest: ${top.label}, ${top.n_companies} of ${N}`;
  if (top && q.template === "INDUSTRY_ONLY") return `${risks.length} risks only ${q.params.industry === "auto" ? "automakers and suppliers" : "chipmakers"} disclose`;
  const sp = risks.filter(n => !n.generic).sort((a, b) => a.n_companies - b.n_companies || a.label.localeCompare(b.label))[0];
  return sp ? `${risks.length} shared · most specific: ${sp.label}, ${sp.n_companies} of ${N}` : `${risks.length} shared, all generic`;
}
export const cypherCore = c => [...new Set(c.split("\n").map(l => l.trim())
  .filter(l => /^(OPTIONAL\s+)?MATCH\b|^WHERE\b/.test(l)))].join("\n");

// Claims behind a graph node: every quote on its edges.
export function riskClaims(g, id) {
  const n = g.nodes.concat(g.drivers || []).find(x => x.id === id);
  const claims = g.edges.concat(g.driver_edges || []).filter(e => e.target === id).flatMap(e => (e.quotes || []).map(q =>
    ({ company: e.source.slice(2), leaf: q.risk_name || n.label, quote: q.text, start: q.start, end: q.end, source_ref: q.chunk_id })));
  return { node: n, claims };
}
