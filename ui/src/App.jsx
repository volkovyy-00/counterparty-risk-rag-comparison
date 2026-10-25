import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { createRef } from "preact";
import { Database, LayoutGrid, MessageSquareText, Network, Scale, Search, ShieldCheck, Table } from "lucide-preact";
import { DATA, keyVerified, local } from "./lib/data.js";
import { status } from "./lib/live.js";
import { AppCtx, SCREENS } from "./store.js";
import { Drawer } from "./components/Drawer.jsx";
import { Question } from "./screens/Question.jsx";
import { Data } from "./screens/Data.jsx";
import { Rag, askRag } from "./screens/Rag.jsx";
import { Graph, askGraph } from "./screens/Graph.jsx";
import { Taxonomy } from "./screens/Taxonomy.jsx";
import { Scorecard } from "./screens/Scorecard.jsx";
import { Decision } from "./screens/Decision.jsx";
import { Governance, runGov } from "./screens/Governance.jsx";

const VIEWS = { question: Question, data: Data, rag: Rag, graph: Graph, taxonomy: Taxonomy, scorecard: Scorecard, decision: Decision, governance: Governance };
const ICONS = { question: MessageSquareText, data: Database, rag: Search, graph: Network, taxonomy: LayoutGrid, scorecard: Table, decision: Scale, governance: ShieldCheck };
const BEATS = [
  { id: "question", title: "Question and scoring rule", start: 0, end: 45 }, { id: "data", title: "Data-quality gate", start: 45, end: 90 },
  { id: "rag", title: "Plain RAG", start: 90, end: 180 }, { id: "graph", title: "GraphRAG", start: 180, end: 270 },
  { id: "taxonomy", title: "Taxonomy-first", start: 270, end: 390 }, { id: "scorecard", title: "Scorecard", start: 390, end: 495 },
  { id: "decision", title: "Decision", start: 495, end: 540 },
];
const fromHash = () => { const id = location.hash.replace(/^#\/?/, "").split("?")[0]; return VIEWS[id] ? id : "question"; };

export function App() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const refs = useMemo(() => ({ rag: createRef(), graph: createRef() }), []);
  const [S, setS] = useState(() => ({
    screen: params.get("screen") || fromHash(), drawer: null, full: null, focus: null, server: null, refs,
    rag: null, graph: null, gov: {}, hmLevel: params.get("leaf") ? "leaf" : "category", overview: !!params.get("overview"),
    hideGeneric: false, showDrivers: false, fullCypher: false, qaMore: false, timer: null,
  }));
  const sref = useRef(S); sref.current = S;
  const set = patch => setS(s => ({ ...s, ...(typeof patch === "function" ? patch(s) : patch) }));
  const go = id => { set({ screen: id, drawer: null, full: null, focus: null }); history.replaceState(null, "", "#/" + id); };

  useEffect(() => { status().then(server => set({ server })); }, []);
  useEffect(() => { const h = () => set({ screen: fromHash() }); addEventListener("hashchange", h); return () => removeEventListener("hashchange", h); }, []);
  useEffect(() => {
    const onKey = e => {
      const S = sref.current, k = e.key, K = k.toUpperCase();
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (k === "Escape") { if (S.full) set({ full: null }); else if (S.drawer) set({ drawer: null }); else document.activeElement?.blur(); return; }
      if (/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) return;
      const scr = SCREENS.find(x => x.key === K);
      if (scr) return go(scr.id);
      if (k === "/" && (S.screen === "rag" || S.screen === "graph")) { e.preventDefault(); refs[S.screen].current?.focus(); return; }
      if (K === "T") { set({ timer: e.shiftKey || !S.timer ? { start: Date.now(), open: true } : { ...S.timer, open: !S.timer.open } }); return; }
      if (S.screen === "rag" && K === "R") askRag(S, set, DATA.meta.question);
      if (S.screen === "graph") {
        if (K === "O") set({ overview: !S.overview, drawer: null });
        else if (K === "H") set({ hideGeneric: !S.hideGeneric });
        else if (K === "X") set({ showDrivers: !S.showDrivers });
        else if (K === "C") set({ fullCypher: !S.fullCypher });
        else if (K === "M") set({ qaMore: !S.qaMore });
        else if (k === "ArrowRight" || k === "ArrowLeft") {
          const L = DATA.graph_qa.questions.filter(q => q.stage || S.qaMore), cur = S.graph?.qid || "shared_vs_specific";
          const i = L.findIndex(q => q.id === cur), n = L[(i + (k === "ArrowRight" ? 1 : -1) + L.length) % L.length];
          askGraph(S, set, n.question, n.id);
        }
      }
      if (S.screen === "taxonomy" && K === "L") set({ hmLevel: S.hmLevel === "leaf" ? "category" : "leaf" });
      if (S.screen === "governance") { const g = { F: "fabricated", O: "offtaxonomy", A: "audit" }[K]; if (g) runGov(S, set, g); }
    };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { document.body.dataset.ready = "1"; }, []);

  const View = VIEWS[S.screen] || Question, m = DATA.meta;
  let group = null;
  return (
    <AppCtx.Provider value={{ S, set, go }}>
      <div class="shell">
        <nav class="rail" aria-label="Screens">
          <div class="brand"><b>Counterparty risk</b><span>{DATA.filings.length} 10-K filings · Item 1A</span></div>
          <ul class="nav">{SCREENS.map(x => {
            const Icon = ICONS[x.id], head = x.group !== group ? (group = x.group) : null;
            return <li key={x.id}>{head && <div class="grp">{head}</div>}
              <button aria-current={S.screen === x.id ? "page" : null} onClick={() => go(x.id)}>
                <Icon size="1.05rem" /><span class="label">{x.n ? `${x.n} · ` : ""}{x.label}</span><span class="kbd">{x.key}</span></button></li>;
          })}</ul>
          <div class="foot">
            <div>Model {m.model} · effort {m.effort}</div>
            <div>Run {local(m.created_at)}</div>
            <div>Key {m.key_status}{m.labeller ? ` (${m.labeller})` : ""}</div>
            <div>{S.server?.live ? <span style={{ color: "var(--live)" }}>Live asks on</span> : S.server ? "Server: offline mode" : "No server: offline copy"}</div>
          </div>
        </nav>
        <header class="top">
          <div class="q">{S.screen !== "question" && <><small>The question</small>{m.question}</>}</div>
          <div class="meta"><b>{DATA.filings.filter(f => f.industry !== "semis").length} autos · {DATA.filings.filter(f => f.industry === "semis").length} chips</b><br />group {m.group}</div>
        </header>
        <main class="main">
          {!keyVerified() && <div class="banner">DRAFT KEY, not for slides (ground truth: {m.key_status})</div>}
          {m.fixture && <div class="banner">TEST FIXTURE: fake model output, not results</div>}
          <View />
        </main>
      </div>
      <Drawer />
      {S.timer?.open && <TimerBox start={S.timer.start} screen={S.screen} />}
    </AppCtx.Provider>
  );
}

function TimerBox({ start, screen }) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick(x => x + 1), 500); return () => clearInterval(t); }, []);
  const s = Math.floor((Date.now() - start) / 1000), beat = BEATS.find(b => s < b.end) || BEATS[BEATS.length - 1];
  const mm = x => `${Math.floor(x / 60)}:${String(x % 60).padStart(2, "0")}`;
  const idx = id => BEATS.findIndex(b => b.id === id), d = idx(screen) - idx(beat.id);
  return <div class="timer" role="status"><div class="t">{mm(s)} / 9:00</div>{beat.title} · {mm(beat.start)}–{mm(beat.end)} · <b>{d === 0 ? "on plan" : d < 0 ? "behind" : "ahead"}</b></div>;
}
