import { DATA, NAMES } from "../lib/data.js";

export function View() {
  const d = DATA.decision;
  const strip = t => String(t).replace(/^.{2,30}?\s[-–:]\s/, "");
  return (
    <div class="screen" style={{ gap: "var(--s8)" }}>
      <div class="cols" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
        {["1_plain_rag", "2_graphrag", "3_taxonomy_first"].map(k => <div key={k} class="rule-top">
          <div class="wide" style={{ fontWeight: 650, marginBottom: "var(--s2)" }}>{NAMES[k]}</div>
          <div class="ink2" style={{ fontSize: "var(--t-body)" }}>{strip(d.when_to_use[k])}</div></div>)}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: "var(--s5)" }}>
        <div class="label">What I would take to a risk committee</div>
        <p class="serif" style={{ fontSize: "var(--t-focal)", lineHeight: 1.3, maxWidth: "42ch", margin: 0 }}>{d.recommendation}</p>
      </div>
      <div class="serif ink2" style={{ fontSize: "var(--t-body)", fontStyle: "italic", maxWidth: "70ch" }}>{d.caveat}</div>
    </div>
  );
}
