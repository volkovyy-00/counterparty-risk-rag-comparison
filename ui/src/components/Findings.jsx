import { industry, leafName, oneLine, short } from "../lib/data.js";
import { findings } from "../lib/asks.js";
import { useApp } from "../store.js";

// The answer's depth: each risk it found, the companies behind it and one of their own sentences.
// A row opens every quote for that risk in the drawer.
export function Findings({ claims, approach, max = 6, title = "Verified claims" }) {
  const { set } = useApp();
  const rows = findings(claims, c => leafName(c.leaf));
  const open = f => set({ drawer: { title: `${f.label} · ${f.tickers.length} ${f.tickers.length === 1 ? "company" : "companies"}`, claims: f.claims, approach } });
  if (!rows.length) return <div class="ink3">No verified claims.</div>;
  return (
    <div class="findings">
      {rows.slice(0, max).map(f => (
        <button key={f.leaf} class="finding" onClick={() => open(f)}>
          <div class="fh"><b>{f.label}</b>
            <span class="tks">{f.tickers.map(t => <span key={t} class={`tk ${industry(t)}`}>{t}</span>)}</span></div>
          <div class="fq"><span class="tk ink3">{f.claims[0].company}</span> <span class="quote">{short(oneLine(f.claims[0].quote), 150)}</span></div>
        </button>))}
      {rows.length > max && <div class="more"><button onClick={() => set({ drawer: { title, claims, approach } })}>
        + {rows.length - max} more risks · all {claims.length} quotes</button></div>}
    </div>
  );
}
