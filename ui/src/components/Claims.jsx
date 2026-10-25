import { industry, leafName, oneLine, short } from "../lib/data.js";
import { useApp } from "../store.js";

// Verified claims as ruled rows; a row opens its quote in the drawer.
export function ClaimTable({ claims, approach, max = 5, title = "Verified claims" }) {
  const { set } = useApp();
  const open = c => set({ drawer: { title: `${c.company} · ${leafName(c.leaf)}`, claims: [c], approach } });
  return (
    <div>
      <table class="t">
        <tbody>
          {claims.slice(0, max).map((c, i) => (
            <tr key={i} class="click" tabIndex={0} onClick={() => open(c)} onKeyDown={e => e.key === "Enter" && open(c)}>
              <td style={{ width: "6rem" }}><span class={`tk ${industry(c.company)}`}>{c.company}</span></td>
              <td style={{ width: "22rem" }}>{leafName(c.leaf)}</td>
              <td><span class="quote ink2">{short(oneLine(c.quote), 110)}</span></td>
            </tr>))}
          {!claims.length && <tr><td class="ink3">No verified claims.</td></tr>}
        </tbody>
      </table>
      {claims.length > max && <div class="more"><button onClick={() => set({ drawer: { title, claims, approach } })}>+ {claims.length - max} more verified claims</button></div>}
    </div>
  );
}

export function Ledger({ v }) {
  return (
    <dl class="ledger">
      <dt>Claims verified</dt><dd>{v.accepted} of {v.claims}</dd>
      <dt>Quotes rejected</dt><dd class={v.rejected_quote ? "bad" : ""}>{v.rejected_quote ?? 0}</dd>
      <dt>Labels rejected</dt><dd class={v.rejected_label ? "bad" : ""}>{v.rejected_label ?? 0}</dd>
      {v.not_in_cited_source != null && <><dt>Not in the cited chunk</dt><dd class={v.not_in_cited_source ? "bad" : ""}>{v.not_in_cited_source}</dd></>}
    </dl>
  );
}
