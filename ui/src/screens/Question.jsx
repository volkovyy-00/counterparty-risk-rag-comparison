import { DATA, filings, local } from "../lib/data.js";
import { Check, X } from "lucide-preact";

export function Question() {
  const r = DATA.scoring_rule, m = DATA.meta, F = filings();
  const A = F.filter(f => f.industry !== "semis"), S = F.filter(f => f.industry === "semis");
  const predates = r.committed_at && new Date(r.committed_at) < new Date(m.created_at);
  const tile = f => (
    <div class="tile" key={f.ticker} style={{ "--c": f.industry === "semis" ? "var(--semis)" : "var(--auto)" }}>
      <div class={`tk ${f.industry}`}>{f.ticker}</div>
      <div class="nm" title={f.company}>{f.short_name || f.company}</div>
      <div class="fp">FY end {f.report_date}</div>
      <div class="fp">{f.url?.startsWith("http") ? <a href={f.url} target="_blank" rel="noopener" title={`10-K ${f.accession}`}>10-K filed {f.filing_date}</a> : `10-K filed ${f.filing_date}`}</div>
    </div>);
  return (
    <div class="screen">
      <div class="screen-head"><h1>One question, ten counterparties</h1>
        <div class="sub">Latest 10-K for each company, Item 1A Risk Factors only, from SEC EDGAR. Answered three ways under one output contract, one verifier and one scoring rule.</div></div>
      <div class="panel" style={{ fontSize: "var(--t-2xl)", fontWeight: 600, lineHeight: 1.25 }}>{m.question}</div>
      <div>
        <div class="strip-legend"><span><b>{A.length} autos</b></span><span><b>{S.length} chips</b></span></div>
        <div class="tiles" style={{ "--na": A.length, "--ns": S.length }}>{A.map(tile)}<div />{S.map(tile)}</div>
      </div>
      <div class="panel">
        <h2>Scoring rule, fixed before the run</h2>
        <div class="row">{r.bullets.map(b => <span class="chip" style={{ cursor: "default" }} key={b.title}>{b.title}</span>)}</div>
        <div class="row" style={{ marginTop: "var(--s3)" }}>
          <span>SCORING_RULE.md committed <b>{r.committed_at ? local(r.committed_at) : "not committed"}</b> <span class="mono dim">{(r.sha || "").slice(0, 7)}</span></span>
          <span class="dim">·</span><span>results recorded <b>{local(m.created_at)}</b></span><span class="dim">·</span>
          {predates ? <b style={{ color: "var(--live)" }}><Check size="1em" /> rule predates results</b>
            : <b style={{ color: "var(--bad)" }}><X size="1em" /> rule does not predate results</b>}
        </div>
      </div>
    </div>
  );
}
