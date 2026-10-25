import { DATA, catName, filings, heatRows, labelName, leafName, otherDrivers, plural } from "../lib/data.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ledger } from "../components/Claims.jsx";

// Sequential ramp in the shell's own hue: few risk factors = dark navy, many = ivory. Generic rows lose their hue.
const shade = (v, max, generic) => {
  const t = Math.min(1, v / Math.max(max, 1)), L = 0.38 + 0.54 * t;
  return { background: `oklch(${L} ${generic ? 0.005 : 0.07} ${generic ? 250 : 238})`, color: L > 0.66 ? "var(--ground)" : "var(--ink)" };
};

export function Taxonomy() {
  const { S, set } = useApp(), r = DATA.approaches["3_taxonomy_first"];
  if (!r || r.error) return <div class="screen"><h1>Approach 3 did not run</h1><div>{r?.error}</div></div>;
  const level = S.hmLevel, m = r.matrix[level] || {}, val = (label, t) => (m[label] || {})[t] || 0;
  const F = filings(), A = F.filter(f => f.industry !== "semis"), Sm = F.filter(f => f.industry === "semis");
  const all = heatRows(r, level), MAX = level === "leaf" ? 16 : 19, rows = all.slice(0, MAX);
  const max = Math.max(1, ...rows.flatMap(x => F.map(f => val(x.label, f.ticker))));
  const openCell = (label, t) => {
    const lvl = label.includes(".") ? "leaf" : "category";
    const cs = r.claims.filter(c => c.company === t && c[lvl] === label);
    set({ drawer: { title: `${t} · ${labelName(label)}`, claims: cs, approach: "3_taxonomy_first" } });
  };
  const cell = (x, f) => {
    const v = val(x.label, f.ticker);
    return v ? <td key={f.ticker} class="cell" style={shade(v, max, x.generic)} tabIndex={0} title={`${f.ticker} · ${v} risk factors`}
      onClick={() => openCell(x.label, f.ticker)} onKeyDown={e => e.key === "Enter" && openCell(x.label, f.ticker)}>{v}</td>
      : <td key={f.ticker} class="cell zero" />;
  };
  const drivers = otherDrivers(r);
  const cross = heatRows(r, "leaf").filter(x => x.cross && !x.generic).slice(0, drivers ? 4 : 6);
  const openDriver = d => set({ drawer: { title: `OTHER · ${d.name}`, approach: "3_taxonomy_first",
    claims: r.claims.filter(c => c.leaf.startsWith("OTHER.") && (c.driver || "").toLowerCase().trim() === d.key) } });
  return (
    <div class="screen">
      <div class="screen-head"><h1>Approach 3 · Taxonomy-first</h1>
        <div class="right">
          <div class="row" role="group" aria-label="Level">
            <button class="btn" aria-pressed={level === "category"} onClick={() => set({ hmLevel: "category" })}>Category</button>
            <button class="btn" aria-pressed={level === "leaf"} onClick={() => set({ hmLevel: "leaf" })}>Leaf <span class="kbd">L</span></button>
          </div></div>
        <div class="sub">The model does one narrow job: label each risk factor with a fixed taxonomy id and copy a quote. Counting is code. Company × {level}, risk factors per cell.</div></div>
      <div class="split" style={{ gridTemplateColumns: "minmax(0, 1fr) 26rem" }}>
        <div class="panel" style={{ overflow: "auto" }}>
          <table class="hm">
            <thead><tr><th />{A.map(f => <th key={f.ticker} class="c"><span class="tk auto">{f.ticker}</span></th>)}<th class="gapc" />
              {Sm.map(f => <th key={f.ticker} class="c"><span class="tk semis">{f.ticker}</span></th>)}<th /></tr></thead>
            <tbody>{rows.map(x => (
              <tr key={x.label} class={x.generic ? "generic" : ""}>
                <td class="lab">{level === "category" ? catName(x.label) : leafName(x.label)}
                  {(level === "leaf" || x.generic || x.cross) && <span class="cap">{x.cross && !x.generic && <span class="x">AUTOS + CHIPS </span>}{level === "leaf" ? catName(x.label.split(".")[0]) : x.generic ? "generic: 80% or more of companies" : ""}</span>}</td>
                {A.map(f => cell(x, f))}<td class="gapc" />{Sm.map(f => cell(x, f))}
                <td class="k">{x.k}/{F.length}</td>
              </tr>))}</tbody>
          </table>
          {all.length > MAX && <div class="xs dim" style={{ marginTop: "var(--s2)" }}>+ {all.length - MAX} more {level === "leaf" ? "shared leaves" : "rows"}, ranked lower</div>}
        </div>
        <div class="stack">
          <div class="ramp">0 {[0.1, 0.3, 0.5, 0.7, 0.9].map(t => <span key={t} style={{ background: shade(t * max, max).background }} />)} {max} <span style={{ marginLeft: "var(--s2)" }}>risk factors per cell</span></div>
          <div class="panel stack"><h3>Where autos and chips connect <span class="muted">specific leaves</span></h3>
            {cross.map(x => <div key={x.label}>
              <div class="row" style={{ justifyContent: "space-between", marginBottom: 3 }}><b class="small">{leafName(x.label)}</b><span class="xs muted">{x.k} of {F.length}</span></div>
              <Strip size="sm" on={x.has} title={`${leafName(x.label)}: ${x.has.join(", ")}`} /></div>)}
            {!cross.length && <span class="dim">none</span>}</div>
          {drivers && <div class="panel"><h3>OTHER drivers <span class="muted">not scored</span></h3>
            <table class="t"><tbody>{drivers.slice(0, 4).map(d => (
              <tr key={d.key} class="click" tabIndex={0} onClick={() => openDriver(d)} onKeyDown={e => e.key === "Enter" && openDriver(d)}>
                <td>{d.name}</td><td class="muted">{d.tickers.length === 1 ? d.tickers[0] : `${d.tickers.length} companies`}</td><td class="num">{d.n}</td></tr>))}</tbody></table>
            {drivers.length > 4 && <div class="xs dim">+ {drivers.length - 4} more</div>}</div>}
          <div class="panel"><h3>Verifier</h3><Ledger v={r.verification} /><div class="xs dim" style={{ marginTop: "var(--s2)" }}>Click a cell for every quote. {plural(r.verification.rejected_label, "label")} rejected by the code validator.</div></div>
        </div>
      </div>
    </div>
  );
}
