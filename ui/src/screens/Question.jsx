import { DATA, filings, local } from "../lib/data.js";
import { Check, X } from "lucide-preact";

export function View() {
  const r = DATA.scoring_rule, m = DATA.meta, F = filings();
  const A = F.filter(f => f.industry !== "semis"), S = F.filter(f => f.industry === "semis");
  const predates = r.committed_at && new Date(r.committed_at) < new Date(m.created_at);
  const tile = f => (
    <div class="tile" key={f.ticker} style={{ "--c": f.industry === "semis" ? "var(--semis)" : "var(--auto)" }} title={`10-K ${f.accession}`}>
      <span class={`tk ${f.industry}`}>{f.ticker}</span>
      <div class="nm">{f.short_name || f.company}</div>
      <div class="fp">filed {f.filing_date}</div>
    </div>);
  return (
    <div class="screen" style={{ justifyContent: "center", gap: "var(--s8)" }}>
      <h1 class="serif" style={{ fontSize: "var(--t-display)", fontWeight: 450, maxWidth: "30ch", lineHeight: 1.15 }}>{m.question}</h1>
      <div>
        <div class="row-between meta" style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--s3)" }}>
          <span>{A.length} automakers and suppliers</span><span>{S.length} chipmakers</span></div>
        <div class="tiles" style={{ "--na": A.length, "--ns": S.length }}>{A.map(tile)}<div />{S.map(tile)}</div>
        <div class="meta" style={{ marginTop: "var(--s4)" }}>Latest 10-K each, Item 1A Risk Factors only, from SEC EDGAR</div>
      </div>
      <div class="rule-top" style={{ fontSize: "var(--t-lead)", display: "flex", gap: "var(--s5)", alignItems: "baseline", flexWrap: "wrap" }}>
        <span>Scoring rule committed <b>{r.committed_at ? local(r.committed_at) : "never"}</b> <span class="mono ink3">{(r.sha || "").slice(0, 7)}</span></span>
        <span class="ink3">→</span><span>results recorded <b>{local(m.created_at)}</b></span>
        {predates ? <b style={{ color: "var(--live)" }}><Check size="1em" style={{ verticalAlign: "-0.12em" }} /> rule predates results</b>
          : <b style={{ color: "var(--bad)" }}><X size="1em" /> rule does not predate results</b>}
      </div>
    </div>
  );
}

export function Detail() {
  const r = DATA.scoring_rule;
  return <>
    <section><h3>Scoring rule, as committed</h3>
      {r.bullets.map(b => <p key={b.title} style={{ margin: "0 0 var(--s3)" }}><b>{b.title}.</b> <span class="ink2">{b.text}</span></p>)}</section>
    <section><h3>Filings</h3><table class="t"><tbody>{filings().map(f => (
      <tr key={f.ticker}><td><span class={`tk ${f.industry}`}>{f.ticker}</span></td><td class="ink2">FY end {f.report_date}</td>
        <td>{f.url?.startsWith("http") ? <a href={f.url} target="_blank" rel="noopener" class="mono">{f.accession}</a> : f.accession}</td></tr>))}</tbody></table></section>
  </>;
}
