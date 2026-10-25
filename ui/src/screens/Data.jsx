import { DATA, short } from "../lib/data.js";

const ORDER = { ERROR: 0, WARN: 1, INFO: 2 };
const PRI = { document_identity: 0, ticker_mismatch: 1, duplicate_company: 2, file_missing: 3, mixed_years: 4, file_unreferenced: 5 };
const Issue = ({ i }) => (
  <div class="issue"><span class={`sev ${i.severity}`}>{i.severity}</span><b>{i.check}</b> · <b>{short(i.subject, 40)}</b>
    <div class="d">{short(i.detail, 170)}</div></div>);

export function Data() {
  const ed = DATA.dq.edgar, ws = DATA.dq.workshop, n = s => ed.filter(i => i.severity === s).length;
  const pick = ed.slice().sort((a, b) => ORDER[a.severity] - ORDER[b.severity]).slice(0, 7);
  const wsPick = ws.slice().sort((a, b) => (PRI[a.check] ?? 9) - (PRI[b.check] ?? 9)).slice(0, 7);
  return (
    <div class="screen">
      <div class="screen-head"><h1>Data-quality gate</h1><div class="sub">Before any answer is trusted. Findings are logged, never auto-fixed.</div></div>
      <div class="grid2">
        <div class="panel">
          <h2>SEC EDGAR set <span class="muted">{DATA.filings.length} filings</span></h2>
          <div class="figs" style={{ marginBottom: "var(--s3)" }}>
            <div class="fig"><b style={{ color: n("ERROR") ? "var(--bad)" : "" }}>{n("ERROR")}</b><span>errors</span></div>
            <div class="fig"><b>{n("WARN")}</b><span>warnings</span></div>
            <div class="fig"><b>{n("INFO")}</b><span>notes</span></div></div>
          {pick.map((i, k) => <Issue key={k} i={i} />)}
          {ed.length > pick.length && <div class="xs dim" style={{ marginTop: "var(--s2)" }}>+ {ed.length - pick.length} more · full list in results/data_quality_edgar_latest.md</div>}
        </div>
        <div class="panel">
          <h2>Same gate, the workshop sample</h2>
          <div class="small muted" style={{ marginBottom: "var(--s2)" }}>The public sample this demo started from, caught before any model saw it.</div>
          {wsPick.map((i, k) => <Issue key={k} i={i} />)}
        </div>
      </div>
    </div>
  );
}
