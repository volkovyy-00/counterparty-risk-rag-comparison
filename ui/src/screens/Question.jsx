import { DATA, filings } from "../lib/data.js";
import { ArrowUpRight } from "lucide-preact";

// "2026-01-27" -> "27 Jan 2026": fits a tile on one line.
const fmtDate = d => { const [y, m, day] = String(d || "").split("-");
  return y && m ? `${+day} ${"Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")[+m - 1]} ${y}` : d; };

export function View() {
  const m = DATA.meta, F = filings();
  const A = F.filter(f => f.industry !== "semis"), S = F.filter(f => f.industry === "semis");
  // Each tile opens that company's 10-K on SEC EDGAR, in a new tab.
  const tile = f => {
    const link = f.url?.startsWith("http");
    const Tag = link ? "a" : "div";
    return (
      <Tag class="tile" key={f.ticker} style={{ "--c": f.industry === "semis" ? "var(--semis)" : "var(--auto)" }}
        {...(link ? { href: f.url, target: "_blank", rel: "noopener" } : {})} title={`10-K ${f.accession}, filed ${f.filing_date}`}>
        <span class={`tk ${f.industry}`}>{f.ticker}{link && <ArrowUpRight class="go" />}</span>
        <div class="nm">{f.short_name || f.company}</div>
        <div class="fp">10-K · {fmtDate(f.filing_date)}</div>
      </Tag>);
  };
  return (
    <div class="screen" style={{ justifyContent: "center", gap: "var(--s8)" }}>
      <h1 class="serif" style={{ fontSize: "var(--t-display)", fontWeight: 450, maxWidth: "30ch", lineHeight: 1.15 }}>{m.question}</h1>
      <div>
        <div class="row-between meta" style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--s3)" }}>
          <span>{A.length} automakers and suppliers</span><span>{S.length} chipmakers</span></div>
        <div class="tiles" style={{ "--na": A.length, "--ns": S.length }}>{A.map(tile)}<div />{S.map(tile)}</div>
        <div class="meta" style={{ marginTop: "var(--s4)" }}>Latest 10-K each, Item 1A Risk Factors only, from SEC EDGAR. Click a company to open its filing.</div>
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
