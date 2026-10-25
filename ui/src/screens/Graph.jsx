import { DATA, cypherCore, groupN, qaHeadline, riskClaims, short } from "../lib/data.js";
import { overviewItems } from "../lib/layout.js";
import { stream } from "../lib/live.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Badge } from "../components/Badge.jsx";
import { Ask } from "../components/Ask.jsx";
import { GraphView } from "../components/GraphView.jsx";

const QS = () => DATA.graph_qa?.questions || [];
const recordedQ = id => QS().find(q => q.id === id);
const recordedAt = () => DATA.graph_qa?.build?.created_at;

export const graphReplay = (id, asked, note) => {
  const q = recordedQ(id) || QS().find(x => x.stage) || QS()[0];
  return { mode: "replay", q, qid: q?.id, asked: asked || q?.question, note, recorded: recordedAt() };
};

export async function askGraph(S, set, question, qid) {
  if (S.graph?.running) return;
  if (!S.server?.live) return set({ graph: graphReplay(qid || "shared_vs_specific", question, S.server ? "live asks are off on this server (start it with --live)" : "no server: offline copy"), focus: null });
  let text = "";
  set({ graph: { mode: "live", running: true, asked: question, qid, text: "", stage: "choosing a fixed template" }, focus: null });
  const msg = await stream("/api/graph_ask", { question, qid }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 3000,
    onStage: st => set(s => ({ graph: { ...s.graph, stage: st } })),
    onPlan: p => set(s => ({ graph: { ...s.graph, plan: p, stage: p.rows ? "writing the answer from the rows" : null } })),
    onToken: t => { text += t; set(s => ({ graph: { ...s.graph, text, stage: null } })); },
  });
  if (msg.type === "result") set({ graph: { mode: "live", q: msg.result, qid: msg.result.id, asked: question, seconds: msg.seconds, routed: msg.routed } });
  // typed question, no recording of its own: the closest fixed question's recorded answer, labelled as such
  else set({ graph: graphReplay(msg.closest || qid || "shared_vs_specific", question, msg.note) });
}

const KW = /\b(MATCH|OPTIONAL|WHERE|WITH|RETURN|ORDER BY|LIMIT|CALL|UNION|AS|AND|IN|NOT|DESC|collect|count|size|all|coalesce|DISTINCT)\b/g;
function Cypher({ text }) {
  const parts = String(text).split(/(\$\w+)/g);
  return <pre class="cypher">{parts.map((p, i) => p.startsWith("$") ? <span key={i} class="pr">{p}</span>
    : p.split(KW).map((x, j) => j % 2 ? <span key={j} class="kw">{x}</span> : x))}</pre>;
}

export function Graph() {
  const { S, set } = useApp();
  if (!DATA.graph_qa) return <div class="screen"><h1>No graph questions recorded</h1></div>;
  const st = S.graph || graphReplay("shared_vs_specific");
  const chips = QS().filter(q => q.stage || S.qaMore);
  if (S.overview) return <Overview />;
  const plan = st.running ? st.plan : null, q = st.running ? null : st.q;
  const g = q ? q.subgraph : plan?.subgraph || { nodes: [], edges: [] };
  const comps = g.nodes.filter(n => n.type === "Company").map(n => n.label);
  const focusCos = S.focus ? [...new Set(g.edges.concat(g.driver_edges || []).filter(e => e.target === S.focus).map(e => e.source.slice(2)))] : null;
  const template = q?.template || plan?.template, params = q?.params || plan?.params, cypher = q?.cypher || plan?.cypher;
  const typedFallback = st.mode === "replay" && st.asked && q && st.asked !== q.question;
  const open = id => { const { node, claims } = riskClaims(g, id); if (claims.length)
    set({ drawer: { title: `${node.label} · ${node.degree} companies`, claims, approach: "2_graphrag" } }); };
  const v = q?.verification;
  const empty = q?.empty ? [q.template === "BRIDGE_DRIVERS" ? "No bridge found" : "No rows returned", "The graph won't invent a link."]
    : st.running && !plan ? ["Routing the question…", "to one of three fixed, read-only templates"] : null;
  return (
    <div class="screen">
      <div class="screen-head">
        <h1>Approach 2 · Ask the graph</h1>
        <div class="right">
          <Badge mode={st.mode} running={st.running} seconds={st.seconds} recorded={st.mode === "replay" ? st.recorded : null} why={st.note} />
          <button class="btn ghost" onClick={() => set({ overview: true, drawer: null })}>Whole graph <span class="kbd">O</span></button>
        </div>
        <div class="sub">Every question runs a fixed, parameterised, read-only Cypher template on the exported graph. The model only picks the template and its parameters, then writes the answer from the rows. It never writes Cypher.</div>
      </div>
      <Ask chips={chips.concat(QS().some(x => !x.stage) ? [] : [])} current={!st.running && st.qid} busy={st.running} inputRef={S.refs.graph}
        placeholder="Ask the graph, e.g. Which risks do Tesla and Microchip share?" onAsk={(text, id) => askGraph(S, set, text, id)} />
      <div class="split">
        <div class="stack">
          <div class="stripline">
            <div><div class="strip-legend"><span>{focusCos ? "Companies linked to the highlighted node" : "Companies in the returned rows"}</span></div>
              <Strip size="lg" on={focusCos || comps} part={focusCos ? comps : []} /></div>
            <div class="count">{(focusCos || comps).length}<small>of {groupN()}</small></div>
          </div>
          <GraphView g={g} focus={S.focus} onFocus={id => set({ focus: id })} onOpen={open} empty={empty} />
          <div class="legend"><span><i /> risk, size = companies</span><span><i class="g" /> generic</span><span><i class="x" /> links autos and chips</span><span><i class="d" /> named driver</span><span>click a node for its quotes</span></div>
        </div>
        <div class="stack">
          <div class="panel stack">
            <div class="small dim">{st.asked}</div>
            {q && <h3 style={{ fontSize: "var(--t-lg)" }}>{qaHeadline(q)}</h3>}
            {st.running
              ? (st.text ? <div class="answer streaming" style={{ fontSize: "var(--t-md)" }}>{st.text}</div>
                : <div><div class="small muted">{st.stage}…</div><div class="skeleton" /><div class="skeleton" style={{ width: "70%" }} /></div>)
              : <div style={{ fontSize: "var(--t-md)" }}>{q?.generic_only ? (g.drivers || []).map(d => `${d.label}: ${d.why_generic || "generic"}`).join(" · ") : short(q?.summary, 420)}</div>}
            {v && <div class="row small"><span>{v.accepted} of {v.claims} claims verified{v.rejected ? ` · ${v.rejected} rejected` : ""}</span>
              <a href="#" onClick={e => { e.preventDefault(); set({ drawer: { title: q.question, claims: q.claims, approach: "2_graphrag" } }); }}>open quotes</a></div>}
            {typedFallback && <div class="note">The live call did not finish ({st.note}). Showing the recorded answer to the closest fixed question: “{q.question}”</div>}
            {st.routed && <div class="note">Routed to <span class="mono">{st.routed.template}</span>{st.routed.reason ? `: ${st.routed.reason}` : ""}</div>}
          </div>
          {template && <div class="panel stack">
            <h3>Read-only Cypher <span class="muted mono">{template}</span></h3>
            <Cypher text={S.fullCypher ? cypher : cypherCore(cypher)} />
            <div class="mono xs muted">{Object.entries(params || {}).map(([k, x]) => `$${k} = ${JSON.stringify(x)}`).join("\n")}</div>
            <div class="row xs dim"><span>{q ? `${q.rows} row${q.rows === 1 ? "" : "s"} → the graph on the left` : ""}</span>
              <button class="btn ghost" onClick={() => set({ fullCypher: !S.fullCypher })}>{S.fullCypher ? "Core lines" : "Full query"} <span class="kbd">C</span></button></div>
          </div>}
        </div>
      </div>
    </div>
  );
}

function Overview() {
  const { S, set } = useApp(), g = DATA.graph, r = DATA.approaches["2_graphrag"];
  const sub = overviewItems(g, S), res = g.resolution || {}, mg = g.most_generic || {};
  const comps = sub.nodes.filter(n => n.type === "Company").map(n => n.label);
  const focusCos = S.focus ? [...new Set(sub.edges.concat(sub.driver_edges).filter(e => e.target === S.focus).map(e => e.source.slice(2)))] : null;
  const open = id => { const { node, claims } = riskClaims(g, id); if (claims.length)
    set({ drawer: { title: `${node.label} · ${node.degree} companies`, claims, approach: "2_graphrag" } }); };
  const specificCross = g.nodes.filter(n => n.type === "RiskFactor" && n.degree >= 2 && !n.generic && n.industries.includes("auto") && n.industries.includes("semis")).length;
  return (
    <div class="screen">
      <div class="screen-head"><h1>Approach 2 · The whole graph</h1>
        <div class="right">
          <button class="btn" aria-pressed={S.hideGeneric} onClick={() => set({ hideGeneric: !S.hideGeneric })}>Hide generic <span class="kbd">H</span></button>
          <button class="btn" aria-pressed={S.showDrivers} onClick={() => set({ showDrivers: !S.showDrivers })}>Named drivers <span class="kbd">X</span></button>
          <button class="btn primary" onClick={() => set({ overview: false })}>Back to questions <span class="kbd">O</span></button>
        </div>
        <div class="sub">Top-ranked shared risks only. {sub.hiddenSingles} single-company risks hidden{sub.notDrawn > 0 ? `, ${sub.notDrawn} lower-ranked shared risks not drawn` : ""}.</div></div>
      <div class="split">
        <div class="stack">
          <Strip size="lg" on={focusCos || comps} part={focusCos ? comps : []} legend />
          <GraphView g={sub} focus={S.focus} onFocus={id => set({ focus: id })} onOpen={open} />
        </div>
        <div class="stack">
          <div class="panel"><div class="fig"><b>{specificCross}</b><span>specific risks shared across autos and chips</span></div></div>
          <div class="panel"><h3>Entity resolution</h3>
            {res.mentions != null ? <div class="small"><b>{res.mentions}</b> verified mentions → <b>{res.risk_factors}</b> risk factors<br />
              {res.merges_approved} merges approved · {res.merges_rejected} rejected ({res.merges_rejected_by_rule || 0} by rule)</div> : null}
            <div class="small" style={{ marginTop: "var(--s2)" }}>Most generic: “{mg.label}” links {mg.companies} of {groupN()} companies</div></div>
          {r && !r.error && <div class="panel small">Answer claims: {r.verification.accepted} of {r.verification.claims} verified ·{" "}
            <a href="#" onClick={e => { e.preventDefault(); set({ drawer: { title: "Approach 2 · verified claims", claims: r.claims, approach: "2_graphrag" } }); }}>open quotes</a></div>}
        </div>
      </div>
    </div>
  );
}
