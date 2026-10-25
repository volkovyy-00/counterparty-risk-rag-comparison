import { DATA, NAMES, NM, f2, pct, short, tickers } from "../lib/data.js";
import { Strip } from "../components/Strip.jsx";

const ORDER = ["1_plain_rag", "2_graphrag", "3_taxonomy_first", "0_long_context"];

export function Scorecard() {
  const card = DATA.scorecard, R = card.rows, nF = tickers().length;
  const cols = ORDER.filter(c => card.columns.includes(c) && DATA.approaches[c]);
  const err = c => DATA.approaches[c]?.error;
  const usage = u => !u ? NM : !u.llm_calls ? (u.embed_calls ? "local embeddings, no model call" : "no model call")
    : `${((u.input_tokens + u.output_tokens) / 1000).toFixed(0)}k tok · ${u.cost_usd == null ? "cost " + NM : "$" + u.cost_usd.toFixed(2)}${u.latency_s == null ? "" : ` · ${Math.round(u.latency_s)}s`}`;
  const prf = x => x ? <>{f2(x.precision)} / {f2(x.recall)} / <b>{f2(x.f1)}</b></> : `${NM} (no key)`;
  const runs = c => (R.reruns || {})[c] || 1, rebuild = DATA.meta.rebuild_usd;
  const jac = (x, c) => x != null ? `${f2(x)} (${runs(c)} runs)` : c === "2_graphrag"
    ? `1 run · a rebuild costs ~${rebuild != null ? "$" + rebuild.toFixed(2) : "(not estimated)"}` : "1 run, not rerun";
  const defs = [
    ["P / R / F1, category", "category_prf", prf, x => x?.f1, "max"],
    ["P / R / F1, leaf", "leaf_prf", prf, x => x?.f1, "max"],
    ["Quote coverage", "quote_coverage", pct, x => x, "max"],
    ["Quotes rejected", "quotes_rejected", x => x ?? NM, x => x, "min"],
    ["Rerun consistency (Jaccard)", "rerun_jaccard_leaf", jac, x => x, "max"],
    ["Companies in the answer", "companies_covered", x => x == null ? NM : `${x}/${nF}`, x => x, "max"],
    ["Build: tokens · cost · time", "build", usage, x => x?.llm_calls ? x.cost_usd : null, "min"],
    ["Ask: tokens · cost · time", "ask", usage, x => x?.cost_usd, "min"],
  ];
  const three = cols.filter(c => c !== "0_long_context" && !err(c));
  const gq = DATA.graph?.quality;
  return (
    <div class="screen">
      <div class="screen-head"><h1>Scorecard</h1><div class="sub">Same rule, same verifier, same hand-labelled key ({DATA.meta.key_status}{DATA.meta.labeller ? `, ${DATA.meta.labeller}` : ""}). Best value per row is underlined; the long-context control is not compared.</div></div>
      <div class="panel" style={{ overflow: "auto" }}>
        <table class="t" style={{ fontSize: "var(--t-md)" }}>
          <thead><tr><th>Metric</th>{cols.map(c => <th key={c}>{NAMES[c]}{c === "0_long_context" ? " (control)" : ""}</th>)}</tr></thead>
          <tbody>
            {defs.map(([label, key, fmt, val, dir]) => {
              const vals = three.map(c => val((R[key] || {})[c])).filter(v => v != null);
              const best = vals.length > 1 ? (dir === "max" ? Math.max(...vals) : Math.min(...vals)) : null;
              return <tr key={key}><td class="muted">{label}</td>{cols.map(c => {
                if (err(c)) return <td key={c} class="dim">{short(err(c), 40)}</td>;
                const raw = (R[key] || {})[c], v = val(raw), isBest = best != null && v === best && c !== "0_long_context";
                return <td key={c} class={isBest ? "best" : ""}>{fmt(raw, c)}</td>;
              })}</tr>;
            })}
            <tr><td class="muted">Which companies the answer reached</td>{cols.map(c => <td key={c}>{err(c) ? "" :
              <Strip size="sm" on={DATA.approaches[c].companies_covered || []} />}</td>)}</tr>
            {gq && typeof gq.quote_verification_rate === "number" && <tr><td class="muted">Graph: quotes verified · paragraph coverage</td>
              {cols.map(c => <td key={c} class={c === "2_graphrag" ? "" : "dim"}>{c === "2_graphrag" ? `${pct(gq.quote_verification_rate)} · ${pct(gq.paragraph_coverage)}` : "–"}</td>)}</tr>}
          </tbody>
        </table>
      </div>
      <div class="xs dim">P/R/F1 over shared (company, label) pairs against the key. Cost from pricing.yaml (checked {DATA.meta.pricing_checked}). Latency is live wall clock only. Run {DATA.meta.created_at.slice(0, 10)}, effort {DATA.meta.effort || "-"}.</div>
    </div>
  );
}
