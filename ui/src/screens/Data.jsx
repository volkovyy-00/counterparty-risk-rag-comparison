import { DATA, short } from "../lib/data.js";

const ORDER = { ERROR: 0, WARN: 1, INFO: 2 };
const PRI = { document_identity: 0, ticker_mismatch: 1, duplicate_company: 2, file_missing: 3, mixed_years: 4, file_unreferenced: 5 };
const edgar = () => DATA.dq.edgar.slice().sort((a, b) => ORDER[a.severity] - ORDER[b.severity]);
const workshop = () => DATA.dq.workshop.slice().sort((a, b) => (PRI[a.check] ?? 9) - (PRI[b.check] ?? 9));
const Finding = ({ i }) => (
  <div class="finding"><span><span class={`sev ${i.severity}`}>{i.severity}</span></span>
    <div style={{ minWidth: 0 }}><div class="what"><b>{i.check.replace(/_/g, " ")}</b> · {short(i.subject, 40)}</div><div class="d">{i.detail}</div></div></div>);

export function View() {
  const ed = DATA.dq.edgar, ws = DATA.dq.workshop, n = (L, s) => L.filter(i => i.severity === s).length;
  return (
    <div class="screen">
      <div class="cols" style={{ gridTemplateColumns: "1fr 1fr", flex: 1 }}>
        <div>
          <div class="label">SEC EDGAR set, {DATA.filings.length} filings</div>
          <div style={{ display: "flex", gap: "var(--s7)", marginBottom: "var(--s5)" }}>
            {[["ERROR", "errors"], ["WARN", "warnings"], ["INFO", "notes"]].map(([s, l]) =>
              <div class="figure" key={s}><b style={{ color: s === "ERROR" && n(ed, s) ? "var(--bad)" : "" }}>{n(ed, s)}</b><span>{l}</span></div>)}
          </div>
          <div class="ink2" style={{ fontSize: "var(--t-body)", marginBottom: "var(--s4)" }}>Logged, never auto-fixed</div>
          {edgar().slice(0, 4).map((i, k) => <Finding key={k} i={i} />)}
        </div>
        <div>
          <div class="label">The public workshop sample this demo started from</div>
          <div class="figure" style={{ marginBottom: "var(--s5)" }}><b style={{ color: "var(--bad)" }}>{n(ws, "ERROR")}</b><span>errors</span></div>
          <div class="ink2" style={{ fontSize: "var(--t-body)", marginBottom: "var(--s4)" }}>Caught before any model saw it</div>
          {workshop().slice(0, 4).map((i, k) => <Finding key={k} i={i} />)}
        </div>
      </div>
    </div>
  );
}

export function Detail() {
  return <>
    <section><h3>Every EDGAR finding</h3>{edgar().map((i, k) => <Finding key={k} i={i} />)}</section>
    <section><h3>Every workshop finding</h3>{workshop().map((i, k) => <Finding key={k} i={i} />)}</section>
  </>;
}
