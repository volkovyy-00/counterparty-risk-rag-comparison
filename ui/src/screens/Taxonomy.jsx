import { DATA, catName, filings, heatRows, labelName, leafName, otherDrivers } from "../lib/data.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ledger } from "../components/Claims.jsx";

// Sequential ramp in the shell's own hue: few risk factors = dark navy, many = ivory. Generic rows lose their hue.
const shade = (v, max, generic) => {
  const t = Math.min(1, v / Math.max(max, 1)), L = 0.34 + 0.58 * t;
  return { background: `oklch(${L} ${generic ? 0.008 : 0.075} ${generic ? 250 : 238})`, color: L > 0.64 ? "var(--ground)" : "var(--ink)" };
};
const R = () => DATA.approaches["3_taxonomy_first"];

export const onKey = (e, S, set) => { if (e.key.toUpperCase() === "L") set({ hmLevel: S.hmLevel === "leaf" ? "category" : "leaf" }); };
export function Tools() {
  const { S, set } = useApp();
  return <button class="btn" aria-pressed={S.hmLevel === "leaf"} onClick={() => set({ hmLevel: S.hmLevel === "leaf" ? "category" : "leaf" })}>Leaf level <span class="kbd">L</span></button>;
}

export function View() {
  const { S, set } = useApp(), r = R();
  if (!r || r.error) return <div class="screen"><h1>Approach 3 did not run</h1><div>{r?.error}</div></div>;
  const level = S.hmLevel, m = r.matrix[level] || {}, val = (label, t) => (m[label] || {})[t] || 0;
  const F = filings(), A = F.filter(f => f.industry !== "semis"), Sm = F.filter(f => f.industry === "semis");
  const rows = heatRows(r, level).slice(0, level === "leaf" ? 17 : 18);
  const max = Math.max(1, ...rows.flatMap(x => F.map(f => val(x.label, f.ticker))));
  const openCell = (label, t) => {
    const lvl = label.includes(".") ? "leaf" : "category";
    set({ drawer: { title: `${t} · ${labelName(label)}`, claims: r.claims.filter(c => c.company === t && c[lvl] === label), approach: "3_taxonomy_first" } });
  };
  const cell = (x, f) => {
    const v = val(x.label, f.ticker);
    return v ? <td key={f.ticker} class="cell" style={shade(v, max, x.generic)} tabIndex={0} title={`${f.ticker} · ${v} risk factors`}
      onClick={() => openCell(x.label, f.ticker)} onKeyDown={e => e.key === "Enter" && openCell(x.label, f.ticker)}>{v}</td>
      : <td key={f.ticker} class="cell zero" />;
  };
  const firstGeneric = rows.findIndex(x => x.generic);
  const cross = heatRows(r, "leaf").filter(x => x.cross && !x.generic).slice(0, 4);
  return (
    <div class="screen">
      <div class="tax-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 24rem", gap: "var(--s7)", alignItems: "start" }}>
        <div style={{ overflowX: "auto" }}>
          <table class="hm">
            <thead><tr><th />{A.map(f => <th key={f.ticker} class="c"><span class="tk auto">{f.ticker}</span></th>)}<th class="gapc" />
              {Sm.map(f => <th key={f.ticker} class="c"><span class="tk semis">{f.ticker}</span></th>)}<th /></tr></thead>
            <tbody>{rows.map((x, i) => <>
              {i === firstGeneric && <tr class="split" key="split"><td class="lab">Generic: 80% or more of companies</td><td colSpan={F.length + 2} /></tr>}
              <tr key={x.label} class={x.generic ? "generic" : ""}>
                <td class="lab" title={level === "leaf" ? `${leafName(x.label)} · ${catName(x.label.split(".")[0])}` : catName(x.label)}>
                  {level === "category" ? catName(x.label) : leafName(x.label)}</td>
                {A.map(f => cell(x, f))}<td class="gapc" />{Sm.map(f => cell(x, f))}
                <td class="k">{x.k}/{F.length}</td>
              </tr></>)}</tbody>
          </table>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--s6)" }}>
          {level === "leaf" ? <>
            <h2 style={{ fontSize: "var(--t-lead)" }}>Where autos and chips connect</h2>
            {cross.map(x => <div key={x.label}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--s4)", marginBottom: "var(--s2)" }}>
                <b style={{ fontSize: "var(--t-body)" }}>{leafName(x.label)}</b><span class="ink3">{x.k} of {F.length}</span></div>
              <Strip size="sm" on={x.has} title={`${leafName(x.label)}: ${x.has.join(", ")}`} /></div>)}
          </> : <>
            <div class="figure" style={{ flexDirection: "column", alignItems: "flex-start" }}><b>{r.verification.accepted}</b>
              <span style={{ fontSize: "var(--t-body)" }}>of {r.verification.claims} labels verified, each with its quote</span></div>
            <div class="ink2" style={{ fontSize: "var(--t-table)" }}>{r.verification.rejected_label} labels and {r.verification.rejected_quote} quote rejected by code</div>
            <div class="ink3" style={{ fontSize: "var(--t-table)" }}>Grey rows are generic: almost every company cites them. Press L for the leaf level.</div>
          </>}
          <div class="ramp">0 {[0.1, 0.3, 0.5, 0.7, 0.9].map(t => <span key={t} style={{ background: shade(t * max, max).background }} />)} {max} risk factors per cell</div>
          <div class="meta">Click a cell for every quote</div>
        </div>
      </div>
    </div>
  );
}

export function Detail() {
  const { set } = useApp(), r = R(), drivers = otherDrivers(r);
  const openDriver = d => set({ drawer: { title: `OTHER · ${d.name}`, approach: "3_taxonomy_first",
    claims: r.claims.filter(c => c.leaf.startsWith("OTHER.") && (c.driver || "").toLowerCase().trim() === d.key) } });
  return <>
    <section><h3>Verifier</h3><Ledger v={r.verification} /></section>
    {drivers && <section><h3>OTHER drivers (not scored)</h3><table class="t"><tbody>{drivers.slice(0, 12).map(d => (
      <tr key={d.key} class="click" tabIndex={0} onClick={() => openDriver(d)}><td>{d.name}</td>
        <td class="ink3">{d.tickers.length === 1 ? d.tickers[0] : `${d.tickers.length} companies`}</td><td class="num">{d.n}</td></tr>))}</tbody></table></section>}
    <section><h3>How it works</h3><p class="ink2" style={{ margin: 0 }}>The model labels each risk factor with one id from a fixed taxonomy ({DATA.taxonomy.categories.length} categories, {DATA.taxonomy.leaves.length} leaves, v{DATA.taxonomy.version}) and copies a quote. Code checks the label and the quote, then counts.</p></section>
  </>;
}
