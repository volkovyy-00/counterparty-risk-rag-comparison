import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { createRef } from "preact";
import { Database, Info, LayoutGrid, Menu, MessageSquareText, Network, PanelRight, Scale, Search, ShieldCheck, Table } from "lucide-preact";
import { DATA, keyVerified, local } from "./lib/data.js";
import { status } from "./lib/live.js";
import { AppCtx, SCREENS } from "./store.js";
import { Drawers } from "./components/Drawer.jsx";
import { Badge } from "./components/Badge.jsx";
import * as Q from "./screens/Question.jsx";
import * as Dq from "./screens/Data.jsx";
import * as R from "./screens/Rag.jsx";
import * as G from "./screens/Graph.jsx";
import * as T from "./screens/Taxonomy.jsx";
import * as Sc from "./screens/Scorecard.jsx";
import * as De from "./screens/Decision.jsx";
import * as Go from "./screens/Governance.jsx";

// Each screen: View (the stage), optional Tools (step-bar toggles), Detail (the D drawer), Mode (LIVE/REPLAY state).
const VIEWS = { question: Q, data: Dq, rag: R, graph: G, taxonomy: T, scorecard: Sc, decision: De, governance: Go };
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
    screen: params.get("screen") || fromHash(), drawer: null, full: null, detail: false, nav: false, info: false, focus: null, server: null, refs,
    rag: null, graph: null, gov: {}, govTab: "fabricated", hmLevel: params.get("leaf") ? "leaf" : "category", overview: !!params.get("overview"),
    hideGeneric: false, showDrivers: false, fullCypher: false, qaMore: false, timer: null,
  }));
  const sref = useRef(S); sref.current = S;
  const set = patch => setS(s => ({ ...s, ...(typeof patch === "function" ? patch(s) : patch) }));
  const go = id => { set({ screen: id, drawer: null, full: null, detail: false, focus: null, nav: false }); history.replaceState(null, "", "#/" + id); };

  useEffect(() => { status().then(server => set({ server })); }, []);
  useEffect(() => { const h = () => set({ screen: fromHash(), detail: false, drawer: null, full: null, focus: null }); addEventListener("hashchange", h); return () => removeEventListener("hashchange", h); }, []);
  useEffect(() => {
    const onKey = e => {
      const S = sref.current, k = e.key, K = k.toUpperCase();
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (k === "Escape") {
        if (S.full) set({ full: null }); else if (S.drawer) set({ drawer: null }); else if (S.detail || S.nav || S.info) set({ detail: false, nav: false, info: false });
        else document.activeElement?.blur();
        return;
      }
      if (/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) return;
      const scr = SCREENS.find(x => x.key === K);
      if (scr) return go(scr.id);
      if (K === "N") return set({ nav: !S.nav });
      if (K === "D") return VIEWS[S.screen].Detail && set({ detail: !S.detail, drawer: null });
      if (K === "I") return set({ info: !S.info });
      if (k === "/" && (S.screen === "rag" || S.screen === "graph")) { e.preventDefault(); refs[S.screen].current?.focus(); return; }
      if (K === "T") return set({ timer: e.shiftKey || !S.timer ? { start: Date.now(), open: true } : { ...S.timer, open: !S.timer.open } });
      VIEWS[S.screen].onKey?.(e, S, set);
    };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { document.body.dataset.ready = "1"; }, []);

  const V = VIEWS[S.screen] || Q, m = DATA.meta, cur = SCREENS.find(x => x.id === S.screen);
  const mode = V.mode?.(S);
  return (
    <AppCtx.Provider value={{ S, set, go }}>
      <div class="shell">
        <header class="stepbar">
          <div class="where">
            <button class="menu" onClick={() => set({ nav: !S.nav })} aria-label="Screens (N)" title="Screens (N)"><Menu size="1.1rem" /></button>
            <span class="name">{cur.n ? `${cur.n} · ` : ""}{cur.label}</span>
            <div class="dots" role="tablist" aria-label="Screens">{SCREENS.map(x => <>
              {x.id === "governance" && <span class="sep" />}
              <button key={x.id} aria-current={S.screen === x.id ? "page" : null} onClick={() => go(x.id)} title={`${x.label} (${x.key})`} aria-label={x.label} /></>)}</div>
          </div>
          <div class="q">{S.screen !== "question" ? m.question : ""}</div>
          <div class="tools">
            {V.Tools && <V.Tools />}
            {mode && <Badge {...mode} />}
            {V.Detail && <button class="btn" aria-pressed={S.detail} onClick={() => set({ detail: !S.detail, drawer: null })} title="Details (D)"><PanelRight /> <span class="kbd">D</span></button>}
            <button class="btn" aria-pressed={S.info} onClick={() => set({ info: !S.info })} title="Run info (I)" aria-label="Run info"><Info /></button>
          </div>
        </header>
        <main class="content">
          {!keyVerified() && <div class="banner">DRAFT KEY, not for slides (ground truth: {m.key_status})</div>}
          {m.fixture && <div class="banner">TEST FIXTURE: fake model output, not results</div>}
          <V.View />
        </main>
      </div>
      <nav class={`rail ${S.nav ? "open" : ""}`} aria-label="Screens" aria-hidden={!S.nav}>
        <div class="brand">Counterparty risk<span>{DATA.filings.length} 10-K filings · Item 1A</span></div>
        <ul>{SCREENS.map(x => { const Icon = ICONS[x.id];
          return <li key={x.id}><button aria-current={S.screen === x.id ? "page" : null} onClick={() => go(x.id)} tabIndex={S.nav ? 0 : -1}>
            <Icon size="1.1rem" /><span>{x.n ? `${x.n} · ` : ""}{x.label}</span><span class="kbd">{x.key}</span></button></li>; })}</ul>
        <div class="hint meta">N screens · D details · I run info · T timer · Esc close</div>
      </nav>
      {S.info && <div class="popover" role="dialog" aria-label="Run info"><dl>
        <dt>Model</dt><dd>{m.model}, effort {m.effort}</dd>
        <dt>Run</dt><dd>{local(m.created_at)}</dd>
        <dt>Key</dt><dd>{m.key_status}{m.labeller ? ` (${m.labeller})` : ""}</dd>
        <dt>Group</dt><dd>{m.group}</dd>
        <dt>Server</dt><dd>{S.server?.live ? "live asks on" : S.server ? "offline mode" : "no server: offline copy"}</dd>
      </dl></div>}
      <Drawers detail={V.Detail && <V.Detail />} />
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
