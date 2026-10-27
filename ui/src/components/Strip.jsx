import { filings } from "../lib/data.js";

// The counterparty strip: 6 autos | 4 chips, one notch per company. `on` = companies filled, `part` = outlined only.
export function Strip({ on = [], part = [], size = "", legend = false, title }) {
  const F = filings(), A = F.filter(f => f.industry !== "semis"), S = F.filter(f => f.industry === "semis");
  const onS = new Set(on), partS = new Set(part);
  const cell = f => {
    const cls = onS.has(f.ticker) ? "on" : partS.has(f.ticker) ? "part" : "";
    return <div key={f.ticker} class={`n ${cls} ${f.industry === "semis" ? "semis" : "auto"}`}
      title={`${f.short_name || f.company}${cls ? "" : " – not reached"}`}>{f.ticker}</div>;
  };
  return (
    <div>
      {legend && <div class="strip-legend"><span><b>{A.length} autos</b></span><span><b>{S.length} chips</b></span></div>}
      <div class={`strip ${size}`} style={{ "--na": A.length, "--ns": S.length }} role="img"
        aria-label={title || `${onS.size} of ${F.length} companies: ${[...onS].join(", ") || "none"}`}>
        {A.map(cell)}<div class="gap" />{S.map(cell)}
      </div>
    </div>
  );
}
