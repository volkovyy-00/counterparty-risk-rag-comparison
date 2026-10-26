import { DATA, cypherCore, groupN, industry, isCross, oneLine, qaHeadline, riskClaims, short } from "../lib/data.js";
import { overviewItems } from "../lib/layout.js";
import { stream } from "../lib/live.js";
import { closest, play, typeOut } from "../lib/asks.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ask } from "../components/Ask.jsx";
import { Steps } from "../components/Steps.jsx";
import { Findings } from "../components/Findings.jsx";
import { ForceGraph } from "../components/ForceGraph.jsx";

// Every recorded graph ask: the main question (approach 2's global query + its frozen answer), then the fixed questions.
const QS = () => DATA.graph_qa?.questions || [];
function ASKS() {
  const m = DATA.graph_main, r = DATA.approaches["2_graphrag"];
  const main = m && r && !r.error ? [{ ...m, question: DATA.meta.question, stage: true, summary: r.summary, claims: r.claims,
    verification: r.verification, main: true, recorded_at: DATA.meta.created_at }] : [];
  return main.concat(QS().map(q => ({ ...q, recorded_at: DATA.graph_qa.build?.created_at })));
}
const linked = (g, id) => [...new Set(g.edges.concat(g.driver_edges || []).filter(e => e.target === id || e.source === id)
  .map(e => (e.source === id ? e.target : e.source)).filter(x => x.startsWith("c:")).map(x => x.slice(2)))];
const companiesOf = g => g.nodes.filter(n => n.type === "Company").map(n => n.label);

function headline(q) {
  if (!q.main) return qaHeadline(q);
  const risks = q.subgraph.nodes.filter(n => n.type === "RiskFactor"), cross = risks.filter(n => !n.generic && isCross(n));
  return `${risks.length} shared risks; ${cross.length} specific ones link autos and chips`;
}

function stepsFor(st) {
  const q = st?.ask, g = q?.subgraph, v = st?.result?.verification;
  const tks = q?.params?.tickers;
  return [
    { label: "Route to a fixed query", detail: "picks a template, never writes Cypher", done: q ? `${q.template}${tks ? ` · ${tks.join(", ")}` : ""}` : "" },
    { label: "Run read-only Cypher", detail: "on the exported graph", done: q ? `${q.rows} rows` : "" },
    { label: "Draw what came back", detail: "only the rows, nothing added", done: g ? `${g.nodes.length + (g.drivers || []).length} nodes · ${g.edges.length + (g.driver_edges || []).length} links` : "" },
    { label: "Model answers from the rows", detail: "quotes each company", done: q?.empty || q?.generic_only ? "no model call" : `${q?.verification?.claims ?? 0} claims` },
    { label: "Verifier checks every quote", detail: "verbatim, in the filing", done: v ? `${v.accepted} of ${v.claims} verified` : "nothing to check" },
  ];
}

let cancel = () => {};

function replay(set, q, asked, note) {
  cancel();
  const base = { mode: "replay", ask: q, asked, note, recorded: q.recorded_at, at: 0, reveal: 0, text: "", running: true };
  const upd = p => set(s => ({ graph: { ...s.graph, ...p } }));
  const text = q.summary || "", ms = Math.max(1800, Math.min(4200, text.length * 8));
  let stopType = () => {};
  const steps = [{ ms: 700, run: () => set({ graph: base, focus: null }) }, { ms: 700, run: () => upd({ at: 1 }) }, { ms: 50, run: () => upd({ at: 2 }) }];
  for (let i = 1; i <= 12; i++) steps.push({ ms: 110, run: () => upd({ reveal: i / 12 }) });
  if (q.empty || q.generic_only) steps.push({ ms: 0, run: () => upd({ at: 5, text, result: q, running: false }) });
  else steps.push({ ms: 300, run: () => upd({ at: 3 }) }, { ms: ms + 150, run: () => { stopType = typeOut(text, ms, t => upd({ text: t })); } },
    { ms: 900, run: () => upd({ at: 4, text, result: q }) }, { ms: 0, run: () => upd({ at: 5, running: false }) });
  const stopPlay = play(steps);
  cancel = () => { stopPlay(); stopType(); };
}

export async function askGraph(S, set, question, id) {
  if (S.graph?.running && S.graph.mode === "live") return;
  const asks = ASKS(), byId = id && asks.find(a => a.id === id), m = byId ? { ask: byId, exact: true } : closest(asks, question);
  const recorded = m.exact ? m.ask : null;
  if (!S.server?.live) {
    if (recorded) return replay(set, recorded, question, S.server ? "live asks are off on this server" : "offline copy, no server");
    return replay(set, m.ask, question, `no recording of this question; closest recorded one: “${m.ask.question}”`);
  }
  cancel();
  let st = { mode: "live", running: true, asked: question, at: 0, reveal: 0, text: "" };
  const upd = p => { st = { ...st, ...p }; set({ graph: st }); };
  upd({}); set({ focus: null });
  const msg = await stream("/api/graph_ask", { question, qid: id }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 8000,
    onEvent: e => { if (e.type === "stage") upd({ at: e.step }); },
    onPlan: p => { upd({ at: 2, ask: { ...p, question }, reveal: 0 });
      for (let i = 1; i <= 12; i++) setTimeout(() => upd({ reveal: i / 12 }), 100 * i);
      setTimeout(() => st.at < 3 && upd({ at: 3 }), 1300); },
    onToken: t => upd({ text: st.text + t }),
  });
  if (msg.type === "result") return upd({ at: 5, running: false, reveal: 1, ask: { ...st.ask, ...msg.result }, result: msg.result,
    text: msg.result.summary, seconds: msg.seconds, routed: msg.routed });
  const back = asks.find(a => a.id === msg.closest) || recorded || m.ask;
  replay(set, back, question, back === recorded ? msg.note : `${msg.note}; closest recorded question: “${back.question}”`);
}

export const mode = S => { if (S.overview) return null; const st = S.graph; if (!st) return null;
  return { mode: st.mode, running: st.running && st.mode === "live", seconds: st.seconds, recorded: st.mode === "replay" ? st.recorded : null, why: st.note }; };

export function onKey(e, S, set) {
  const k = e.key, K = k.toUpperCase();
  if (K === "O") set({ overview: !S.overview, drawer: null, focus: null });
  else if (K === "R") askGraph(S, set, DATA.meta.question, "main");
  else if (K === "H") set({ hideGeneric: !S.hideGeneric });
  else if (K === "X") set({ showDrivers: !S.showDrivers });
  else if (K === "C") set({ detail: !S.detail });
  else if (K === "M") set({ qaMore: !S.qaMore });
  else if ((k === "ArrowRight" || k === "ArrowLeft") && !S.overview) {
    const L = ASKS().filter(q => q.stage || S.qaMore), cur = S.graph?.ask?.id;
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

export function View() {
  const { S, set } = useApp();
  if (!DATA.graph_qa && !DATA.graph_main) return <div class="screen"><h1>No graph questions recorded</h1></div>;
  if (S.overview) return <Overview />;
  const st = S.graph, q = st?.ask, g = st && st.at >= 2 && q?.subgraph ? q.subgraph : { nodes: [], edges: [] };
  const asks = ASKS(), chips = asks.filter(x => x.stage || S.qaMore).map(x => ({ id: x.id, label: x.label, question: x.question }));
  const comps = companiesOf(g), focusCos = S.focus ? linked(g, S.focus) : null;
  const wrongQ = st && q?.question && st.asked && q.question !== st.asked && closest([q], st.asked).score < 0.6;
  const hasMore = asks.some(x => !x.stage);
  return (
    <div class="screen ask-screen">
      <Ask chips={chips} current={!st?.running && q?.id} busy={st?.running && st.mode === "live"} inputRef={S.refs.graph}
        placeholder="Ask the graph, e.g. Which risks do GM and NXP both disclose?" onAsk={(text, id) => askGraph(S, set, text, id)}
        extra={hasMore && <button class="chip" style={{ borderStyle: "dashed" }} onClick={() => set({ qaMore: !S.qaMore })}>{S.qaMore ? "Fewer" : "More questions"}</button>} />
      <Steps steps={stepsFor(st)} at={st ? st.at : -1} />
      <div class="stripline">
        <Strip on={focusCos || comps} part={focusCos ? comps : []} />
        <div class="figure"><b>{st && st.at >= 2 ? (focusCos || comps).length : "–"}</b><span>of {groupN()}<br />{focusCos ? "on this node" : "in the rows"}</span></div>
      </div>
      {!st ? <div class="empty-ask"><p class="serif">GraphRAG answers from a knowledge graph of the ten filings. The question is routed to one of a few fixed, read-only queries; the model only sees the rows that come back.</p>
        <p class="meta">Type a question, pick one above, or press R for the main question.</p></div> : (
        <div class="graph-ask">
          <div class="graph-pane">
            {st.at >= 2 && q?.subgraph ? <ForceGraph g={g} selected={S.focus} onSelect={id => set({ focus: id })} reveal={st.reveal ?? 1} />
              : <div class="fgraph placeholder"><span class="ink3">{st.at === 0 ? "Routing the question…" : "Running the query…"}</span></div>}
            {S.focus && <Inspector g={g} id={S.focus} />}
            {q?.empty && st.at >= 2 && <div class="graph-empty"><b>{q.template === "BRIDGE_DRIVERS" ? "No bridge found" : "No rows returned"}</b><span class="ink2">The graph won't invent a link.</span></div>}
          </div>
          <div class="ask-answer">
            <div class="asked">{st.asked}</div>
            {wrongQ && <div class="note">{st.note}. The answer below is to that question, not to the one typed.</div>}
            {st.at >= 3 && q && <h2 class="headline">{headline(q)}</h2>}
            {st.at >= 3 ? <div class={`answer ${st.at === 3 ? "streaming" : ""}`}>{q?.generic_only ? (g.drivers || []).map(d => `${d.label}: ${d.why_generic || "generic"}`).join(" · ") : st.text}</div>
              : <div><div class="skeleton" style={{ width: "80%" }} /><div class="skeleton" style={{ width: "55%" }} /></div>}
            {st.at >= 4 && st.result?.claims?.length > 0 && <Findings claims={st.result.claims} approach="2_graphrag" max={5} title="GraphRAG · verified claims" />}
            {q?.cypher && st.at >= 1 && <div class="rule-top cy">
              <div class="label">Read-only Cypher · {q.template} <span class="kbd">C</span></div>
              <Cypher text={cypherCore(q.cypher).split("\n").slice(0, 3).join("\n")} /></div>}
          </div>
        </div>)}
    </div>
  );
}

// Neo4j-browser style node panel: what the node is, and every link it has in these rows.
function Inspector({ g, id }) {
  const { set } = useApp();
  const all = g.nodes.concat(g.drivers || []), n = all.find(x => x.id === id);
  if (!n) return null;
  const edges = g.edges.concat(g.driver_edges || []);
  const company = n.type === "Company";
  const open = rid => { const { node, claims } = riskClaims(g, rid); if (claims.length)
    set({ drawer: { title: `${node.label} · ${node.degree} companies`, claims, approach: "2_graphrag" } }); };
  const rels = company ? edges.filter(e => e.source === id).map(e => ({ e, other: all.find(x => x.id === e.target) })).filter(x => x.other)
    : edges.filter(e => e.target === id).map(e => ({ e, other: all.find(x => x.id === e.source) })).filter(x => x.other);
  return (
    <div class="inspector" role="dialog" aria-label={`${n.label} links`}>
      <div class="ih"><span class={`pill ${company ? industry(n.label) : n.generic ? "generic" : "risk"}`}>{company ? "Company" : n.type === "ExposureDriver" ? "Driver" : "RiskFactor"}</span>
        <b>{company ? `${n.label} · ${n.name || ""}` : n.label}</b>
        <button class="btn icon" onClick={() => set({ focus: null })} aria-label="Close">×</button></div>
      {!company && <div class="props">{n.n_companies ?? n.degree} of {groupN()} companies{n.generic ? " · generic" : ""}{isCross(n) ? " · links autos and chips" : ""}
        {n.definition && <div class="ink3">{short(n.definition, 150)}</div>}</div>}
      <div class="label">{rels.length} {company ? "FACES_RISK links in these rows" : "companies disclose it"}</div>
      <ul>{rels.map(({ e, other }) => (
        <li key={other.id}>
          {company
            ? <button onClick={() => set({ focus: other.id })}><span>{other.label}</span><span class="ink3">{other.degree}</span></button>
            : <button onClick={() => open(id)}><span class={`tk ${industry(other.label)}`}>{other.label}</span>
                <span class="quote ink2">{short(oneLine(e.quotes?.[0]?.text || ""), 90)}</span></button>}
        </li>))}</ul>
    </div>
  );
}

function Overview() {
  const { S, set } = useApp(), g = DATA.graph;
  const sub = overviewItems(g, S);
  const comps = companiesOf(sub), focusCos = S.focus ? linked(sub, S.focus) : null;
  const specificCross = g.nodes.filter(n => n.type === "RiskFactor" && n.degree >= 2 && !n.generic && isCross(n)).length;
  const res = g.resolution || {};
  return (
    <div class="screen ask-screen">
      <div class="stripline">
        <Strip on={focusCos || comps} part={focusCos ? comps : []} />
        <div class="figure"><b>{(focusCos || comps).length}</b><span>of {groupN()}<br />{focusCos ? "on this node" : "companies"}</span></div>
      </div>
      <div class="graph-ask">
        <div class="graph-pane"><ForceGraph g={sub} selected={S.focus} onSelect={id => set({ focus: id })} />
          {S.focus && <Inspector g={sub} id={S.focus} />}</div>
        <div class="ask-answer">
          <div class="figure" style={{ flexDirection: "column", alignItems: "flex-start", whiteSpace: "normal" }}><b>{specificCross}</b>
            <span style={{ fontSize: "var(--t-body)" }}>specific risks shared across autos and chips</span></div>
          {res.mentions != null && <div class="ink2" style={{ fontSize: "var(--t-table)" }}>{res.mentions} verified mentions resolved into {res.risk_factors} risk factors</div>}
          <div class="meta">Top-ranked shared risks only. {sub.hiddenSingles} single-company risks hidden{sub.notDrawn > 0 ? `, ${sub.notDrawn} more not drawn` : ""}. Drag nodes, scroll to zoom, click a node for its links.</div>
        </div>
      </div>
    </div>
  );
}

export function Detail() {
  const { S, set } = useApp(), g = DATA.graph, res = g.resolution || {}, mg = g.most_generic || {}, r = DATA.approaches["2_graphrag"];
  const st = S.graph, q = st?.ask;
  return <>
    {q?.cypher && !S.overview && <section><h3>Full query · {q.template} · {q.rows} rows</h3><Cypher text={q.cypher} />
      <div class="mono ink3" style={{ marginTop: "var(--s3)", whiteSpace: "pre-wrap" }}>{Object.entries(q.params || {}).map(([k, x]) => `$${k} = ${JSON.stringify(x)}`).join("\n")}</div>
      {st.routed && <p class="ink2">Routed to {st.routed.template}{st.routed.reason ? `: ${st.routed.reason}` : ""}</p>}
      {q.ranked && <p class="ink2">{q.ranked}.</p>}
      {q.ranked_by && <p class="ink2">Bridge ranked in code: no home country or ≥80% driver, fewest companies first, top 3.</p>}</section>}
    <section><h3>Entity resolution</h3><dl class="ledger">
      <dt>Verified mentions</dt><dd>{res.mentions ?? "–"}</dd><dt>Risk factors</dt><dd>{res.risk_factors ?? "–"}</dd>
      <dt>Merges approved</dt><dd>{res.merges_approved ?? "–"}</dd><dt>Merges rejected</dt><dd>{res.merges_rejected ?? "–"} ({res.merges_rejected_by_rule || 0} by rule)</dd>
    </dl><p class="ink2">Most generic: “{mg.label}” links {mg.companies} of {groupN()} companies.</p></section>
    {r && !r.error && <section><h3>Approach 2 answer to the main question</h3>
      <p class="ink2" style={{ margin: 0 }}>{r.verification.accepted} of {r.verification.claims} claims verified · <a href="#" onClick={e => { e.preventDefault();
        set({ drawer: { title: "GraphRAG · verified claims", claims: r.claims, approach: "2_graphrag" } }); }}>open quotes</a></p></section>}
  </>;
}
