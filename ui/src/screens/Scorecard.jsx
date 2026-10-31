import { DATA, NAMES, NM, f2, pct, short, tickers } from "../lib/data.js";
import { Strip } from "../components/Strip.jsx";

const ORDER = ["1_plain_rag", "2_graphrag", "3_taxonomy_first", "0_long_context"];
const card = () => DATA.scorecard;
const cols = () => ORDER.filter(c => card().columns.includes(c) && DATA.approaches[c]);
const err = c => DATA.approaches[c]?.error;
const usage = u => !u ? NM : !u.llm_calls ? (u.embed_calls ? "no model call" : "no model call")
  : `${u.cost_usd == null ? NM : "$" + u.cost_usd.toFixed(2)}`;
const runs = c => (card().rows.reruns || {})[c] || 1;

// Editorial rows (the author's judgement, not measured): how hard each approach is to build, and its trade-offs.
const COMPLEXITY = { "1_plain_rag": "Low", "2_graphrag": "High", "3_taxonomy_first": "Low", "0_long_context": "Low" };
const PROS = {
  "1_plain_rag": ["Cheapest and fastest; nothing to build", "Same answer every rerun"],
  "2_graphrag": ["Links between companies are explicit", "Every query is read-only Cypher you can inspect"],
  "3_taxonomy_first": ["Names every shared theme and every company", "Answers without a model call once built"],
  "0_long_context": ["No retrieval to get wrong", "Nothing to build"],
};
const CONS = {
  "1_plain_rag": ["Sees only the 12 closest chunks", "Misses companies and links outside them"],
  "2_graphrag": ["Most to build: an extraction run and a graph database", "Answer limited by what extraction caught"],
  "3_taxonomy_first": ["Needs a taxonomy built and kept up to date", "A risk outside the taxonomy goes unseen"],
  "0_long_context": ["Pays for every filing on every question", "Stops working when filings outgrow the window"],
};
const view = c => (DATA.answer_view || {})[c];
const total = c => { const R = card().rows, b = R.build?.[c], a = R.ask?.[c];
  return b == null && a == null ? null : (b?.cost_usd || 0) + (a?.cost_usd || 0); };

// One table row. get(c) -> the raw value for column c; fmt renders it; val ranks it (dir max|min) to shade the best
// of the three approaches (the control is never compared).
function Row({ label, get, fmt, val, dir, stage, small }) {
  const three = cols().filter(c => c !== "0_long_context" && !err(c));
  const vals = val ? three.map(c => val(get(c))).filter(v => v != null) : [];
  const best = vals.length > 1 ? (dir === "max" ? Math.max(...vals) : Math.min(...vals)) : null;
  return <tr style={{ height: stage ? "4.6rem" : small ? "auto" : "3.2rem" }}><td class="ink2" style={{ fontSize: "var(--t-body)", verticalAlign: small ? "top" : "" }}>{label}</td>{cols().map(c => {
    if (err(c)) return <td key={c} class="ink3">{short(err(c), 30)}</td>;
    const raw = get(c), v = val ? val(raw) : null, isBest = best != null && v === best && c !== "0_long_context";
    return <td key={c} class={isBest ? "best" : ""} style={{ fontSize: stage ? "var(--t-focal)" : small ? "var(--t-table)" : "var(--t-lead)",
      color: c === "0_long_context" ? "var(--ink-3)" : "", verticalAlign: small ? "top" : "" }}>{fmt(raw, c)}</td>;
  })}</tr>;
}

const List = ({ items, mark }) => <ul class="pc">{(items || []).map(t => <li key={t}><span class="mk">{mark}</span>{t}</li>)}</ul>;

export function View() {
  const nF = tickers().length, R = card().rows;
  return (
    <div class="screen">
      <table class="t score" style={{ tableLayout: "fixed" }}>
        <thead><tr><th style={{ width: "17rem" }} />{cols().map(c => <th key={c} style={{ fontSize: "var(--t-table)", color: c === "0_long_context" ? "var(--ink-3)" : "var(--ink)" }}>
          {NAMES[c]}{c === "0_long_context" ? " (control)" : ""}</th>)}</tr></thead>
        <tbody>
          <Row stage label="Precision" get={c => view(c)?.precision} fmt={x => x == null ? NM : pct(x)} val={x => x} dir="max" />
          <Row stage label="Risk themes found" get={c => view(c)} fmt={x => x ? `${x.themes_found}/${x.themes_total}` : NM} val={x => x?.themes_found} dir="max" />
          <Row label="Companies in the answer" get={c => view(c)?.companies.length} fmt={x => x == null ? NM : `${x}/${nF}`} val={x => x} dir="max" />
          <Row label="Quote coverage" get={c => R.quote_coverage?.[c]} fmt={pct} val={x => x} dir="max" />
          <Row label="Build complexity" get={c => COMPLEXITY[c]} fmt={x => x} />
          <Row label="Cost for this answer" get={total} fmt={x => x == null ? NM : `$${x.toFixed(2)}`} val={x => x} dir="min" />
          <Row small label="Pros" get={c => PROS[c]} fmt={x => <List items={x} mark="+" />} />
          <Row small label="Cons" get={c => CONS[c]} fmt={x => <List items={x} mark="–" />} />
        </tbody>
      </table>
      <div class="meta">Precision: share of the answer's company-risk claims the hand-labelled key confirms. Themes: of the {view("3_taxonomy_first")?.themes_total ?? "–"} risk themes the key shares across companies, how many the answer names. Both computed after the run from the same verified claims and key ({DATA.meta.key_status}). Cost: build plus one ask. Best of the three approaches is shaded; the control is not compared.</div>
    </div>
  );
}

export function Detail() {
  const R = card().rows, gq = DATA.graph?.quality;
  return <>
    <section><h3>Which companies each answer reached</h3>{cols().filter(c => !err(c)).map(c => <div key={c} style={{ marginBottom: "var(--s4)" }}>
      <div class="ink2" style={{ marginBottom: "var(--s2)" }}>{NAMES[c]}</div><Strip size="sm" on={view(c)?.companies || []} /></div>)}</section>
    <section><h3>The committed scoring rule</h3><dl class="ledger">{cols().map(c => { const l = R.leaf_prf?.[c], k = R.category_prf?.[c], j = R.rerun_jaccard_leaf?.[c];
      return <><dt>{NAMES[c]}</dt><dd>F1 leaf {f2(l?.f1)} · category {f2(k?.f1)} · rerun agreement {j != null ? `${f2(j)} (${runs(c)} runs)` : "not rerun"}</dd></>; })}</dl>
      <p class="meta" style={{ margin: "var(--s3) 0 0" }}>F1 compares each answer with every shared exposure in the key ({R.leaf_prf?.["3_taxonomy_first"]?.true ?? "–"} at leaf level), so a short answer scores low even when every claim is right. Rerun agreement: overlap of the answers across independent reruns.</p></section>
    <section><h3>Rejections</h3><dl class="ledger">{cols().map(c => <><dt>{NAMES[c]}</dt><dd>{R.quotes_rejected?.[c] ?? 0} quotes · {R.labels_rejected?.[c] ?? 0} labels</dd></>)}</dl></section>
    <section><h3>Tokens and time</h3><dl class="ledger">{cols().map(c => { const b = R.build?.[c], a = R.ask?.[c];
      const t = u => !u || !u.llm_calls ? "–" : `${((u.input_tokens + u.output_tokens) / 1000).toFixed(0)}k tok${u.latency_s != null ? ` · ${Math.round(u.latency_s)}s` : ""}`;
      return <><dt>{NAMES[c]}</dt><dd>build {t(b)} · ask {t(a)}</dd></>; })}</dl></section>
    {gq && typeof gq.quote_verification_rate === "number" && <section><h3>Graph quality (approach 2 only)</h3>
      <p class="ink2" style={{ margin: 0 }}>Quotes verified {pct(gq.quote_verification_rate)} · paragraph coverage {pct(gq.paragraph_coverage)}</p></section>}
    <section><p class="meta" style={{ margin: 0 }}>P/R/F1 over shared (company, label) pairs. Cost from pricing.yaml (checked {DATA.meta.pricing_checked}). Run {DATA.meta.created_at.slice(0, 10)}.</p></section>
  </>;
}
