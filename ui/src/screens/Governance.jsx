import { DATA, labelName, leafName, oneLine, pct, short } from "../lib/data.js";
import { useApp } from "../store.js";
import { Play } from "lucide-preact";

const KEY = { fabricated: "fabricated", offtaxonomy: "off_taxonomy", audit: "audit" };
const TABS = [
  { id: "fabricated", key: "F", label: "Fabricated quote", what: "Plants a paraphrase of a real Item 1A sentence and runs the real verifier on it." },
  { id: "offtaxonomy", key: "O", label: "Off-taxonomy label", what: "Plants a claim with a label that is not in the taxonomy and runs the code validator on it." },
  { id: "audit", key: "A", label: "Audit trail", what: "Compares the manifests of run A and run B (approach 3 after a model swap) and lists the heatmap cells that changed." },
];
const FIELD = { served_models: "served model", taxonomy_prompt_version: "taxonomy prompt", taxonomy_split: "taxonomy split",
  "prompt_sha256.3_taxonomy_first": "prompt sha256", taxonomy_version: "taxonomy version", taxonomy_sha256: "taxonomy sha256",
  corpus_manifest_sha256: "corpus sha256", "git.sha": "git commit", created_at: "recorded", cache_mode: "cache mode" };

export async function runGov(S, set, kind) {
  set(s => ({ govTab: kind, gov: { ...s.gov, [kind]: { running: true } } }));
  let res = null;
  if (S.server) {
    try { res = await (await fetch("/api/governance/" + kind, { method: "POST" })).json(); if (res.error) res = null; else res._live = true; }
    catch (e) { res = null; }
  }
  if (!res && DATA.governance) res = { ...DATA.governance[KEY[kind]], _live: false };
  set(s => ({ gov: { ...s.gov, [kind]: res || { error: "no governance data" } } }));
}
export const onKey = (e, S, set) => { const g = { F: "fabricated", O: "offtaxonomy", A: "audit" }[e.key.toUpperCase()]; if (g) runGov(S, set, g); };

const val = v => v == null ? "–" : Array.isArray(v) ? v.join(", ") : /^[0-9a-f]{40,64}$/.test(String(v)) ? String(v).slice(0, 10) + "…" : String(v).replace("T", " ").replace("Z", "");

export function View() {
  const { S, set } = useApp(), tab = TABS.find(t => t.id === S.govTab), x = S.gov[tab.id];
  return (
    <div class="screen">
      <div class="tabs" role="tablist">{TABS.map(t => <button key={t.id} role="tab" aria-selected={t.id === tab.id}
        onClick={() => set({ govTab: t.id })}>{t.label} <span class="kbd">{t.key}</span></button>)}</div>
      {!x ? <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)", alignItems: "flex-start", paddingTop: "var(--s7)" }}>
        <div style={{ fontSize: "var(--t-lead)", maxWidth: "50ch" }}>{tab.what}</div>
        <button class="btn primary" style={{ height: "2.6rem" }} onClick={() => runGov(S, set, tab.id)}><Play /> Run the check</button>
        <div class="meta">Deterministic and offline: no model call.</div></div>
        : x.running ? <div class="skeleton" style={{ width: "40%" }} /> : <Result id={tab.id} x={x} />}
    </div>
  );
}

function Result({ id, x }) {
  const how = <div class="meta">{x._live ? "ran now in Python, no model call" : "precomputed copy (no server)"}</div>;
  if (id === "audit") {
    if (!x.available) return <div>{how}<p class="ink2">{x.reason}</p></div>;
    const cells = x.changed_cells.category, flips = cells.filter(c => c.flip);
    return (
      <div class="cols" style={{ gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr)" }}>
        <div>{how}<table class="t" style={{ marginTop: "var(--s3)" }}><thead><tr><th>Field</th><th>Run A</th><th>Run B</th></tr></thead><tbody>
          {x.manifest_rows.filter(r => r.field !== "label").slice(0, 8).map(r => <tr key={r.field} style={{ color: r.changed ? "var(--ink)" : "var(--ink-3)" }}>
            <td>{r.changed ? <b>{FIELD[r.field] || r.field}</b> : FIELD[r.field] || r.field}</td><td class="mono">{short(val(r.a), 24)}</td><td class="mono">{short(val(r.b), 24)}</td></tr>)}
        </tbody></table></div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
          <div class="figure" style={{ flexDirection: "column", alignItems: "flex-start" }}><b>{cells.length}</b><span style={{ fontSize: "var(--t-body)" }}>
            category cells changed after the model swap, {flips.length} flipped between exposed and not</span></div>
          <div class="ink2" style={{ fontSize: "var(--t-table)" }}>{cells.slice(0, 5).map(c => <div key={c.ticker + c.label}>{c.ticker} · {labelName(c.label)}: {c.a} → {c.b}</div>)}</div>
        </div>
      </div>);
  }
  const left = id === "fabricated"
    ? <><span class="planted">PLANTED</span><p class="serif" style={{ fontSize: "var(--t-lead)", lineHeight: 1.45, margin: "var(--s4) 0" }}>“{short(oneLine(x.planted_quote), 260)}”</p>
        <div class="ink2"><span class="tk">{x.company}</span> · {leafName(x.leaf)}</div></>
    : <><span class="planted">PLANTED</span><p style={{ fontSize: "var(--t-lead)", margin: "var(--s4) 0" }}>Label <span class="mono" style={{ fontSize: "var(--t-body)" }}>{x.category} / {x.leaf}</span></p>
        <div class="ink2">Checked by the code validator against taxonomy v{x.taxonomy_version}: {x.categories} categories, {x.leaves} leaves</div></>;
  return (
    <div class="cols" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)", paddingTop: "var(--s5)" }}>
      <div>{how}<div style={{ marginTop: "var(--s4)" }}>{left}</div></div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
        <div class={`verdict ${x.verdict}`}>{String(x.verdict).toUpperCase()}</div>
        <div style={{ fontSize: "var(--t-body)" }}>{x.reason}</div>
        {id === "fabricated" && <div><div class="label">Closest real sentence · similarity {pct(x.similarity)}</div>
          <p class="serif ink2" style={{ margin: 0, fontSize: "var(--t-body)" }}>“{short(oneLine(x.closest_real_sentence), 260)}”</p></div>}
        {id === "offtaxonomy" && <div class="meta">{x.note}</div>}
      </div>
    </div>);
}
