import { industry, leafName, oneLine, short } from "../lib/data.js";
import { useApp } from "../store.js";

// Verified claims as a ruled table; a row opens its quote in the drawer.
export function ClaimTable({ claims, approach, max = 8 }) {
  const { set } = useApp();
  const open = c => set({ drawer: { title: `${c.company} · ${leafName(c.leaf)}`, claims: [c], approach } });
  return (
    <table class="t">
      <thead><tr><th>Company</th><th>Risk (taxonomy leaf)</th><th>Verbatim quote</th></tr></thead>
      <tbody>
        {claims.slice(0, max).map((c, i) => (
          <tr key={i} class="click" tabIndex={0} onClick={() => open(c)} onKeyDown={e => e.key === "Enter" && open(c)}>
            <td><span class={`tk ${industry(c.company)}`}>{c.company}</span></td>
            <td>{leafName(c.leaf)}</td>
            <td><span class="quote">{short(oneLine(c.quote), 120)}</span></td>
          </tr>))}
        {claims.length > max && <tr><td colSpan={3} class="dim">+ {claims.length - max} more verified claims</td></tr>}
        {!claims.length && <tr><td colSpan={3} class="dim">No verified claims.</td></tr>}
      </tbody>
    </table>
  );
}

export function Ledger({ v, extra = [] }) {
  return (
    <dl class="ledger">
      <dt>Claims verified</dt><dd>{v.accepted} of {v.claims}</dd>
      <dt>Quotes rejected</dt><dd class={v.rejected_quote ? "bad" : ""}>{v.rejected_quote ?? 0}</dd>
      <dt>Labels rejected</dt><dd class={v.rejected_label ? "bad" : ""}>{v.rejected_label ?? 0}</dd>
      {v.not_in_cited_source != null && <><dt>Not in the cited chunk</dt><dd class={v.not_in_cited_source ? "bad" : ""}>{v.not_in_cited_source}</dd></>}
      {extra.map(([k, val]) => <><dt>{k}</dt><dd>{val}</dd></>)}
    </dl>
  );
}
