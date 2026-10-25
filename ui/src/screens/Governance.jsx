import { DATA, labelName, leafName, oneLine, pct, short } from "../lib/data.js";
import { useApp } from "../store.js";
import { Play } from "lucide-preact";

const KEY = { fabricated: "fabricated", offtaxonomy: "off_taxonomy", audit: "audit" };
const FIELD = { served_models: "served model", taxonomy_prompt_version: "taxonomy prompt", taxonomy_split: "taxonomy split",
  "prompt_sha256.3_taxonomy_first": "prompt sha256 (appr. 3)", taxonomy_version: "taxonomy version", taxonomy_sha256: "taxonomy sha256",
  corpus_manifest_sha256: "corpus sha256", "git.sha": "git commit", created_at: "recorded", cache_mode: "cache mode" };

export async function runGov(S, set, kind) {
  set(s => ({ gov: { ...s.gov, [kind]: { running: true } } }));
  let res = null;
  if (S.server) {
    try { res = await (await fetch("/api/governance/" + kind, { method: "POST" })).json(); if (res.error) res = null; else res._live = true; }
    catch (e) { res = null; }
  }
  if (!res && DATA.governance) res = { ...DATA.governance[KEY[kind]], _live: false };
  set(s => ({ gov: { ...s.gov, [kind]: res || { error: "no governance data" } } }));
}

const How = ({ x }) => <div class="xs dim">{x._live ? "ran now in Python, no model call" : "precomputed copy (no server)"}</div>;

export function Governance() {
  const { S, set } = useApp(), { fabricated: a, offtaxonomy: b, audit: c } = S.gov;
  const run = (k, key, text) => (
    <div class="stack"><div class="small muted">{text}</div>
      <div><button class="btn primary" onClick={() => runGov(S, set, k)}><Play /> Run <span class="kbd">{key}</span></button></div></div>);
  const val = v => v == null ? "–" : Array.isArray(v) ? v.join(", ") : /^[0-9a-f]{40,64}$/.test(String(v)) ? String(v).slice(0, 10) + "…" : String(v).replace("T", " ").replace("Z", "");
  return (
    <div class="screen">
      <div class="screen-head"><h1>Governance checks</h1><div class="sub">Deterministic and offline. Each check runs the real code path on a planted input.</div></div>
      <div class="grid2" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr)" }}>
        <div class="panel"><h3>Fabricated quote</h3>
          {!a ? run("fabricated", "F", "Plants a paraphrase of a real Item 1A sentence and runs the real verifier on it.") : a.running ? <div class="skeleton" /> : <>
            <How x={a} /><span class="planted">{a.label}</span>
            <div><b>{a.company}</b> · {leafName(a.leaf)}</div>
            <div class="small" style={{ marginTop: "var(--s2)" }}>Planted paraphrase: <span class="quote">{short(oneLine(a.planted_quote), 240)}</span></div>
            <div class={`verdict ${a.verdict}`}>{String(a.verdict).toUpperCase()}</div><div class="small">{a.reason}</div>
            <div class="small" style={{ marginTop: "var(--s3)" }}><b>Closest real sentence</b> <span class="muted">similarity {pct(a.similarity)}</span><br />
              <span class="quote">{short(oneLine(a.closest_real_sentence), 260)}</span></div></>}
        </div>
        <div class="panel"><h3>Off-taxonomy label</h3>
          {!b ? run("offtaxonomy", "O", "Plants a claim with a label that is not in the taxonomy and runs the code validator on it.") : b.running ? <div class="skeleton" /> : <>
            <How x={b} /><span class="planted">{b.label}</span>
            <div class="small">Label: <span class="mono">{b.category}</span> / <span class="mono">{b.leaf}</span></div>
            <div class={`verdict ${b.verdict}`}>{String(b.verdict).toUpperCase()}</div><div class="small">{b.reason}</div>
            <div class="small" style={{ marginTop: "var(--s3)" }}>Checked by the code validator (“{b.check}”) against taxonomy v{b.taxonomy_version}: {b.categories} categories, {b.leaves} leaves, independent of the provider's JSON-schema enum.</div>
            <div class="xs dim" style={{ marginTop: "var(--s2)" }}>{b.note}</div></>}
        </div>
        <div class="panel"><h3>Audit trail <span class="muted">run A vs run B</span></h3>
          {!c ? run("audit", "A", "Compares the manifests of run A and run B (approach 3 after a model swap) and lists the heatmap cells that changed.")
            : c.running ? <div class="skeleton" /> : !c.available ? <><How x={c} /><div class="muted">{c.reason}</div></> : <>
              <How x={c} /><div class="small">Run A: {c.a.label} · Run B: {c.b.label}</div>
              <table class="t"><thead><tr><th>Field</th><th>Run A</th><th>Run B</th><th /></tr></thead><tbody>
                {c.manifest_rows.filter(r => r.field !== "label").map(r => <tr key={r.field} style={{ fontWeight: r.changed ? 700 : 400 }}>
                  <td>{FIELD[r.field] || r.field}</td><td class="mono xs">{short(val(r.a), 22)}</td><td class="mono xs">{short(val(r.b), 22)}</td><td>{r.changed ? "≠" : "="}</td></tr>)}
              </tbody></table>
              <div class="small" style={{ marginTop: "var(--s3)" }}><b>{c.changed_cells.category.length}</b> category cells changed ({c.changed_cells.category.filter(x => x.flip).length} flipped exposed ↔ not) · <b>{c.changed_cells.leaf.length}</b> leaf cells changed</div>
              <div class="xs muted">{c.changed_cells.category.slice(0, 6).map(x => `${x.ticker} · ${labelName(x.label)}: ${x.a} → ${x.b}${x.flip ? " (flip)" : ""}`).join(" · ")}</div></>}
        </div>
      </div>
    </div>
  );
}
