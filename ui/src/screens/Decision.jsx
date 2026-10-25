import { DATA, NAMES } from "../lib/data.js";

export function Decision() {
  const d = DATA.decision;
  return (
    <div class="screen">
      <div class="screen-head"><h1>Decision</h1></div>
      <div class="grid2" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
        {["1_plain_rag", "2_graphrag", "3_taxonomy_first"].map(k => <div class="panel" key={k}><h3>{NAMES[k]}</h3><div>{d.when_to_use[k]}</div></div>)}
      </div>
      <div class="panel" style={{ borderColor: "var(--ink-2)" }}>
        <h2 style={{ fontSize: "var(--t-lg)" }}>What I would take to a risk committee</h2>
        <div class="reco">{d.recommendation}</div>
      </div>
      <div class="muted" style={{ maxWidth: "75ch" }}>{d.caveat}</div>
    </div>
  );
}
