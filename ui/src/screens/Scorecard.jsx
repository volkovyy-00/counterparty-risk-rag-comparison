import { DATA, NAMES, NM, f2, pct, short, tickers } from "../lib/data.js";
import { Strip } from "../components/Strip.jsx";

const ORDER = ["1_plain_rag", "2_graphrag", "3_taxonomy_first", "0_long_context"];
const card = () => DATA.scorecard;
const cols = () => ORDER.filter(c => card().columns.includes(c) && DATA.approaches[c]);
const err = c => DATA.approaches[c]?.error;
const usage = u => !u ? NM : !u.llm_calls ? (u.embed_calls ? "no model call" : "no model call")
  : `${u.cost_usd == null ? NM : "$" + u.cost_usd.toFixed(2)}`;
const runs = c => (card().rows.reruns || {})[c] || 1;

function Row({ label, k, fmt, val, dir, stage }) {
  const R = card().rows, three = cols().filter(c => c !== "0_long_context" && !err(c));
  const vals = three.map(c => val((R[k] || {})[c])).filter(v => v != null);
  const best = vals.length > 1 ? (dir === "max" ? Math.max(...vals) : Math.min(...vals)) : null;
  return <tr style={{ height: stage ? "5rem" : "3.6rem" }}><td class="ink2" style={{ fontSize: "var(--t-body)" }}>{label}</td>{cols().map(c => {
    if (err(c)) return <td key={c} class="ink3">{short(err(c), 30)}</td>;
    const raw = (R[k] || {})[c], v = val(raw), isBest = best != null && v === best && c !== "0_long_context";
    return <td key={c} class={isBest ? "best" : ""} style={{ fontSize: stage ? "var(--t-focal)" : "var(--t-lead)", color: c === "0_long_context" ? "var(--ink-3)" : "" }}>{fmt(raw, c)}</td>;
  })}</tr>;
}

export function View() {
  const nF = tickers().length, rebuild = DATA.meta.rebuild_usd;
  const prfSub = x => x ? <span class="meta" style={{ display: "block", fontSize: "var(--t-meta)" }}>P {f2(x.precision)} · R {f2(x.recall)}</span> : null;
  return (
    <div class="screen">
      <table class="t" style={{ tableLayout: "fixed" }}>
        <thead><tr><th style={{ width: "21rem" }} />{cols().map(c => <th key={c} style={{ fontSize: "var(--t-table)", color: c === "0_long_context" ? "var(--ink-3)" : "var(--ink)" }}>
          {NAMES[c]}{c === "0_long_context" ? " (control)" : ""}</th>)}</tr></thead>
        <tbody>
          <Row stage label="F1, leaf level" k="leaf_prf" fmt={x => x ? <>{f2(x.f1)}{prfSub(x)}</> : NM} val={x => x?.f1} dir="max" />
          <Row label="F1, category level" k="category_prf" fmt={x => x ? f2(x.f1) : NM} val={x => x?.f1} dir="max" />
          <Row label="Quote coverage" k="quote_coverage" fmt={pct} val={x => x} dir="max" />
          <Row label="Rerun agreement" k="rerun_jaccard_leaf" fmt={(x, c) => x != null ? <>{f2(x)} <span class="meta">{runs(c)} runs</span></>
            : <span class="meta">{c === "2_graphrag" && rebuild != null ? `not rerun (~$${rebuild.toFixed(2)})` : "not rerun"}</span>} val={x => x} dir="max" />
          <Row label="Companies in the answer" k="companies_covered" fmt={x => x == null ? NM : `${x}/${nF}`} val={x => x} dir="max" />
          <Row label="Cost to build" k="build" fmt={usage} val={x => x?.llm_calls ? x.cost_usd : null} dir="min" />
          <Row label="Cost per question" k="ask" fmt={usage} val={x => x?.cost_usd} dir="min" />
        </tbody>
      </table>
      <div class="meta">Same rule, same verifier, same hand-labelled key ({DATA.meta.key_status}). Best of the three approaches is shaded; the control is not compared.</div>
    </div>
  );
}

export function Detail() {
  const R = card().rows, gq = DATA.graph?.quality;
  return <>
    <section><h3>Which companies each answer reached</h3>{cols().filter(c => !err(c)).map(c => <div key={c} style={{ marginBottom: "var(--s4)" }}>
      <div class="ink2" style={{ marginBottom: "var(--s2)" }}>{NAMES[c]}</div><Strip size="sm" on={DATA.approaches[c].companies_covered || []} /></div>)}</section>
    <section><h3>Rejections</h3><dl class="ledger">{cols().map(c => <><dt>{NAMES[c]}</dt><dd>{R.quotes_rejected?.[c] ?? 0} quotes · {R.labels_rejected?.[c] ?? 0} labels</dd></>)}</dl></section>
    <section><h3>Tokens and time</h3><dl class="ledger">{cols().map(c => { const b = R.build?.[c], a = R.ask?.[c];
      const t = u => !u || !u.llm_calls ? "–" : `${((u.input_tokens + u.output_tokens) / 1000).toFixed(0)}k tok${u.latency_s != null ? ` · ${Math.round(u.latency_s)}s` : ""}`;
      return <><dt>{NAMES[c]}</dt><dd>build {t(b)} · ask {t(a)}</dd></>; })}</dl></section>
    {gq && typeof gq.quote_verification_rate === "number" && <section><h3>Graph quality (approach 2 only)</h3>
      <p class="ink2" style={{ margin: 0 }}>Quotes verified {pct(gq.quote_verification_rate)} · paragraph coverage {pct(gq.paragraph_coverage)}</p></section>}
    <section><p class="meta" style={{ margin: 0 }}>P/R/F1 over shared (company, label) pairs. Cost from pricing.yaml (checked {DATA.meta.pricing_checked}). Run {DATA.meta.created_at.slice(0, 10)}.</p></section>
  </>;
}
