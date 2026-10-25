import { DATA, cypherCore, groupN, qaHeadline, riskClaims, short } from "../lib/data.js";
import { overviewItems } from "../lib/layout.js";
import { stream } from "../lib/live.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ask } from "../components/Ask.jsx";
import { GraphView } from "../components/GraphView.jsx";

const QS = () => DATA.graph_qa?.questions || [];
const recordedAt = () => DATA.graph_qa?.build?.created_at;
const DEFAULT = "shared_vs_specific";

export const graphReplay = (id, asked, note) => {
  const q = QS().find(x => x.id === id) || QS().find(x => x.id === DEFAULT) || QS()[0];
  return { mode: "replay", q, qid: q?.id, asked: asked || q?.question, note, recorded: recordedAt() };
};

export async function askGraph(S, set, question, qid) {
  if (S.graph?.running) return;
  if (!S.server?.live) return set({ graph: graphReplay(qid || DEFAULT, question, S.server ? "live asks are off on this server" : "no server: offline copy"), focus: null });
  let text = "";
  set({ graph: { mode: "live", running: true, asked: question, qid, text: "", stage: "choosing a fixed template" }, focus: null });
  const msg = await stream("/api/graph_ask", { question, qid }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 3000,
    onStage: st => set(s => ({ graph: { ...s.graph, stage: st } })),
    onPlan: p => set(s => ({ graph: { ...s.graph, plan: p, stage: p.rows ? "writing the answer from the rows" : null } })),
    onToken: t => { text += t; set(s => ({ graph: { ...s.graph, text, stage: null } })); },
  });
  if (msg.type === "result") set({ graph: { mode: "live", q: msg.result, qid: msg.result.id, asked: question, seconds: msg.seconds, routed: msg.routed } });
  // a typed question with no recording of its own: the closest fixed question's recorded answer, labelled as such
  else set({ graph: graphReplay(msg.closest || qid || DEFAULT, question, msg.note) });
}

export const mode = S => { if (S.overview) return null; const st = S.graph || graphReplay(DEFAULT);
  return { mode: st.mode, running: st.running, seconds: st.seconds, recorded: st.mode === "replay" ? st.recorded : null, why: st.note }; };

export function onKey(e, S, set) {
  const k = e.key, K = k.toUpperCase();
  if (K === "O") set({ overview: !S.overview, drawer: null, focus: null });
  else if (K === "H") set({ hideGeneric: !S.hideGeneric });
  else if (K === "X") set({ showDrivers: !S.showDrivers });
  else if (K === "C") set({ detail: !S.detail });
  else if (K === "M") set({ qaMore: !S.qaMore });
  else if ((k === "ArrowRight" || k === "ArrowLeft") && !S.overview) {
    const L = QS().filter(q => q.stage || S.qaMore), cur = S.graph?.qid || DEFAULT;
    const i = L.findIndex(q => q.id === cur), n = L[(i + (k === "ArrowRight" ? 1 : -1) + L.length) % L.length];
    askGraph(S, set, n.question, n.id);
  }
}

export function Tools() {
  const { S, set } = useApp();
  return <>
    {S.overview && <>
      <button class="btn" aria-pressed={S.hideGeneric} onClick={() => set({ hideGeneric: !S.hideGeneric })}>Hide generic <span class="kbd">H</span></button>
      <button class="btn" aria-pressed={S.showDrivers} onClick={() => set({ showDrivers: !S.showDrivers })}>Named drivers <span class="kbd">X</span></button></>}
    <button class="btn" aria-pressed={S.overview} onClick={() => set({ overview: !S.overview, drawer: null, focus: null })}>Whole graph <span class="kbd">O</span></button>
  </>;
}

const KW = /\b(MATCH|OPTIONAL|WHERE|WITH|RETURN|ORDER BY|LIMIT|CALL|UNION|AS|AND|IN|NOT|DESC|collect|count|size|all|coalesce|DISTINCT)\b/g;
export function Cypher({ text }) {
  const parts = String(text).split(/(\$\w+)/g);
  return <pre class="cypher">{parts.map((p, i) => p.startsWith("$") ? <span key={i} class="pr">{p}</span>
    : p.split(KW).map((x, j) => j % 2 ? <span key={j} class="kw">{x}</span> : x))}</pre>;
}

const linked = (g, id) => [...new Set(g.edges.concat(g.driver_edges || []).filter(e => e.target === id).map(e => e.source.slice(2)))];

function current(S) {
  const st = S.graph || graphReplay(DEFAULT), plan = st.running ? st.plan : null, q = st.running ? null : st.q;
  return { st, plan, q, g: q ? q.subgraph : plan?.subgraph || { nodes: [], edges: [] } };
}

export function View() {
  const { S, set } = useApp();
  if (!DATA.graph_qa) return <div class="screen"><h1>No graph questions recorded</h1></div>;
  if (S.overview) return <Overview />;
  const { st, plan, q, g } = current(S);
  const chips = QS().filter(x => x.stage || S.qaMore);
  const comps = g.nodes.filter(n => n.type === "Company").map(n => n.label);
  const focusCos = S.focus ? linked(g, S.focus) : null;
  const cypher = q?.cypher || plan?.cypher;
  const typedFallback = st.mode === "replay" && st.asked && q && st.asked !== q.question;
  const open = id => { const { node, claims } = riskClaims(g, id); if (claims.length)
    set({ drawer: { title: `${node.label} · ${node.degree} companies`, claims, approach: "2_graphrag" } }); };
  const v = q?.verification;
  const empty = q?.empty ? [q.template === "BRIDGE_DRIVERS" ? "No bridge found" : "No rows returned", "The graph won't invent a link."]
    : st.running && !plan ? ["Choosing a template…", "one of three fixed, read-only queries"] : null;
  const hasMore = QS().some(x => !x.stage);
  return (
    <div class="screen">
      <Ask chips={chips} current={!st.running && st.qid} busy={st.running} inputRef={S.refs.graph}
        placeholder="Ask the graph, e.g. Which risks do Tesla and Microchip share?" onAsk={(text, id) => askGraph(S, set, text, id)}
        extra={hasMore && <button class="chip" style={{ borderStyle: "dashed" }} onClick={() => set({ qaMore: !S.qaMore })}>{S.qaMore ? "Fewer" : "More questions"}</button>} />
      <div class="stripline">
        <Strip on={focusCos || comps} part={focusCos ? comps : []} />
        <div class="figure"><b>{(focusCos || comps).length}</b><span>of {groupN()}<br />{focusCos ? "on this node" : "in the rows"}</span></div>
      </div>
      <div class="graph-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 26rem", gap: "var(--s7)", alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--s3)" }}>
          <GraphView g={g} focus={S.focus} onFocus={id => set({ focus: id })} onOpen={open} empty={empty} />
          <div class="legend"><span><i /> risk</span><span><i class="g" /> generic</span><span><i class="x" /> links autos and chips</span>
            {(g.drivers || []).length > 0 && <span><i class="d" /> named driver</span>}<span>hover a node, click for its quotes</span></div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
          <div class="ink3" style={{ fontSize: "var(--t-table)" }}>{st.asked}</div>
          {q && <h2 style={{ fontSize: "var(--t-head)" }}>{qaHeadline(q)}</h2>}
          {st.running
            ? (st.text ? <div class="answer streaming" style={{ fontSize: "var(--t-table)" }}>{st.text}</div>
              : <div><div class="ink3">{st.stage}…</div><div class="skeleton" /><div class="skeleton" style={{ width: "70%" }} /></div>)
            : <div class="ink2" style={{ fontSize: "var(--t-table)" }}>{q?.generic_only ? (g.drivers || []).map(d => `${d.label}: ${d.why_generic || "generic"}`).join(" · ") : short(q?.summary, 260)}</div>}
          {v && <div class="verified"><span><b>{v.accepted} of {v.claims}</b> verified</span>
            <a href="#" onClick={e => { e.preventDefault(); set({ drawer: { title: q.question, claims: q.claims, approach: "2_graphrag" } }); }}>open quotes</a></div>}
          {typedFallback && <div class="note">The live call did not finish ({st.note}). Showing the recorded answer to the closest fixed question.</div>}
          {cypher && <div class="rule-top">
            <div class="label">Read-only Cypher · {q?.template || plan?.template} <span class="kbd">C</span></div>
            <Cypher text={cypherCore(cypher).split("\n").slice(0, 3).join("\n")} /></div>}
        </div>
      </div>
    </div>
  );
}

function Overview() {
  const { S, set } = useApp(), g = DATA.graph;
  const sub = overviewItems(g, S);
  const comps = sub.nodes.filter(n => n.type === "Company").map(n => n.label);
  const focusCos = S.focus ? linked(sub, S.focus) : null;
  const open = id => { const { node, claims } = riskClaims(g, id); if (claims.length)
    set({ drawer: { title: `${node.label} · ${node.degree} companies`, claims, approach: "2_graphrag" } }); };
  const specificCross = g.nodes.filter(n => n.type === "RiskFactor" && n.degree >= 2 && !n.generic && n.industries.includes("auto") && n.industries.includes("semis")).length;
  const res = g.resolution || {};
  return (
    <div class="screen">
      <div class="stripline">
        <Strip on={focusCos || comps} part={focusCos ? comps : []} />
        <div class="figure"><b>{(focusCos || comps).length}</b><span>of {groupN()}<br />{focusCos ? "on this node" : "companies"}</span></div>
      </div>
      <div class="graph-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 22rem", gap: "var(--s7)", alignItems: "start" }}>
        <GraphView g={sub} focus={S.focus} onFocus={id => set({ focus: id })} onOpen={open} />
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
          <div class="figure" style={{ flexDirection: "column", alignItems: "flex-start", whiteSpace: "normal" }}><b>{specificCross}</b>
            <span style={{ fontSize: "var(--t-body)" }}>specific risks shared across autos and chips</span></div>
          {res.mentions != null && <div class="ink2" style={{ fontSize: "var(--t-table)" }}>{res.mentions} verified mentions resolved into {res.risk_factors} risk factors</div>}
          <div class="meta">Top-ranked shared risks only. {sub.hiddenSingles} single-company risks hidden{sub.notDrawn > 0 ? `, ${sub.notDrawn} more not drawn` : ""}.</div>
        </div>
      </div>
    </div>
  );
}

export function Detail() {
  const { S, set } = useApp(), g = DATA.graph, res = g.resolution || {}, mg = g.most_generic || {}, r = DATA.approaches["2_graphrag"];
  const { st, plan, q } = current(S), cypher = q?.cypher || plan?.cypher, params = q?.params || plan?.params;
  return <>
    {cypher && !S.overview && <section><h3>Full query · {q?.template || plan?.template}{q ? ` · ${q.rows} rows` : ""}</h3><Cypher text={cypher} />
      <div class="mono ink3" style={{ marginTop: "var(--s3)", whiteSpace: "pre-wrap" }}>{Object.entries(params || {}).map(([k, x]) => `$${k} = ${JSON.stringify(x)}`).join("\n")}</div>
      {st.routed && <p class="ink2">Routed to {st.routed.template}{st.routed.reason ? `: ${st.routed.reason}` : ""}</p>}
      {q?.ranked_by && <p class="ink2">Bridge ranked in code: no home country or ≥80% driver, fewest companies first, top 3.</p>}</section>}
    <section><h3>Entity resolution</h3><dl class="ledger">
      <dt>Verified mentions</dt><dd>{res.mentions ?? "–"}</dd><dt>Risk factors</dt><dd>{res.risk_factors ?? "–"}</dd>
      <dt>Merges approved</dt><dd>{res.merges_approved ?? "–"}</dd><dt>Merges rejected</dt><dd>{res.merges_rejected ?? "–"} ({res.merges_rejected_by_rule || 0} by rule)</dd>
    </dl><p class="ink2">Most generic: “{mg.label}” links {mg.companies} of {groupN()} companies.</p></section>
    {r && !r.error && <section><h3>Approach 2 answer to the main question</h3>
      <p class="ink2" style={{ margin: 0 }}>{r.verification.accepted} of {r.verification.claims} claims verified · <a href="#" onClick={e => { e.preventDefault();
        set({ drawer: { title: "GraphRAG · verified claims", claims: r.claims, approach: "2_graphrag" } }); }}>open quotes</a></p></section>}
  </>;
}
