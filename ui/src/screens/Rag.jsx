import { DATA, industry, tickers } from "../lib/data.js";
import { stream } from "../lib/live.js";
import { closest, play, typeOut } from "../lib/asks.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ask } from "../components/Ask.jsx";
import { Steps } from "../components/Steps.jsx";
import { Findings } from "../components/Findings.jsx";
import { Output } from "../components/Output.jsx";
import { Ledger } from "../components/Claims.jsx";
import { Unanswered } from "../components/Unanswered.jsx";

// A recorded ask with its question and answer filled in (the main one's answer is the frozen approach-1 result).
const ASKS = () => (DATA.rag_asks || []).map(a => a.main
  ? { ...a, question: DATA.meta.question, result: DATA.approaches["1_plain_rag"] } : a);
const noteFor = a => (DATA.notes || {})[`rag:${a.id}`] || null;
const companiesIn = r => [...new Set((r?.claims || []).map(c => c.company))];
const citedIds = r => new Set((r?.claims || []).map(c => c.source_ref));

function stepsFor(st) {
  const a = st?.ask, r = st?.result, v = r?.verification, k = a?.top_k || 12, got = [...new Set((a?.retrieved || []).map(c => c.ticker))];
  return [
    { label: "Embed the question", detail: DATA.meta.embed_model ? `${DATA.meta.embed_model.split("/").pop()}, on this laptop` : "local model", done: "one vector" },
    { label: `Search ${a?.chunks_indexed ?? "all"} chunks`, detail: `top ${k} by cosine similarity`, done: `${k} chunks · ${got.length} ${got.length === 1 ? "company" : "companies"}` },
    { label: "Model writes the answer", detail: `from those ${k} chunks only`, done: st?.missing ? "not recorded" : `${v?.claims ?? 0} claims, each with a quote` },
    { label: "Verifier checks every quote", detail: "verbatim, in the cited chunk", done: v ? `${v.accepted} of ${v.claims} verified` : "–" },
    { label: "Analyst note", detail: "from the verified claims only", done: st?.anote ? `takeaway + ${st.anote.points.length} points` : "not recorded" },
  ];
}

let cancel = () => {};

// Replay a recorded ask at a readable pace: embed, chunks arrive one by one, the answer types out, the verifier ticks.
function replay(set, a, asked, note) {
  cancel();
  const base = { mode: "replay", ask: a, asked, note, recorded: a.recorded_at || DATA.meta.created_at, at: 0, shown: 0, text: "", running: true };
  const upd = p => set(s => ({ rag: { ...s.rag, ...p } }));
  const n = a.retrieved.length, text = a.result?.summary || "";
  const steps = [{ ms: 650, run: () => set({ rag: base }) }, { ms: 250, run: () => upd({ at: 1 }) }];
  for (let i = 1; i <= n; i++) steps.push({ ms: 110, run: () => upd({ shown: i }) });
  if (!a.result) steps.push({ ms: 0, run: () => upd({ at: 2, missing: true, running: false }) });
  else {
    const ms = Math.max(1800, Math.min(4200, text.length * 9));
    let stopType = () => {};
    const an = noteFor(a);
    // With a note, the panel waits for it: the approach's own answer is not typed out first, then replaced.
    steps.push({ ms: 400 }, an ? { ms: 1800, run: () => upd({ at: 2, text }) }
      : { ms: ms + 150, run: () => { upd({ at: 2 }); stopType = typeOut(text, ms, t => upd({ text: t })); } },
      { ms: 900, run: () => upd({ at: 3, result: a.result, text }) });
    if (an) steps.push({ ms: 400, run: () => upd({ at: 4, anote: an, noteText: "" }) },
      { ms: 1700, run: () => { stopType = typeOut(an.takeaway, 1500, t => upd({ noteText: t })); } });
    steps.push({ ms: 0, run: () => upd({ at: 5, running: false, noteText: an?.takeaway }) });
    const stopPlay = play(steps);
    cancel = () => { stopPlay(); stopType(); };
    return;
  }
  cancel = play(steps);
}

export async function askRag(S, set, question, id) {
  if (S.rag?.running && S.rag.mode === "live") return;
  const asks = ASKS(), byId = id && asks.find(a => a.id === id), m = byId ? { ask: byId, exact: true } : closest(asks, question);
  const recorded = m.exact ? m.ask : null;
  if (!S.server?.live && !S.server?.retrieval) {
    if (recorded) return replay(set, recorded, question, S.server ? "live asks are off on this server" : "offline copy, no server");
    cancel();  // never show another question's answer under this one
    return set({ rag: { mode: "none", asked: question, at: -1, unanswered: { suggest: m.ask,
      why: "Plain RAG embeds a new question with a model on the laptop, and this copy has no server behind it, so only the recorded questions can run here. Typed questions do run live on the GraphRAG screen." } } });
  }
  // The server embeds and retrieves for real (free, on this laptop); it answers only when live asks are on.
  cancel();
  let st = { mode: "live", running: true, asked: question, at: 0, shown: 0, text: "", ask: { retrieved: [], top_k: 12 } };
  const upd = p => { st = { ...st, ...p }; set({ rag: st }); };
  upd({});
  const msg = await stream("/api/live_rag", { question }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 5000,
    onEvent: e => {
      if (e.type === "stage") upd({ at: e.step });
      else if (e.type === "retrieved") {
        upd({ at: 1, ask: { ...st.ask, ...e }, shown: 0 });
        e.retrieved.forEach((_, i) => setTimeout(() => upd({ shown: i + 1 }), 90 * (i + 1)));
      }
    },
    onToken: t => upd({ at: 2, text: st.text + t }),
  });
  if (msg.type === "result") return upd({ at: 5, running: false, result: msg.result, anote: msg.result.note, noteText: msg.result.note?.takeaway, text: msg.result.summary, seconds: msg.seconds,
    ask: { ...st.ask, retrieved: msg.retrieved || st.ask.retrieved, chunks_indexed: msg.chunks_indexed || st.ask.chunks_indexed }, shown: 99 });
  if (recorded) return replay(set, recorded, question, msg.note);
  if (st.ask.retrieved.length) return upd({ at: 2, running: false, missing: true, note: msg.note, liveRetrieval: true, shown: 99 });
  set({ rag: { mode: "none", asked: question, at: -1, unanswered: { suggest: m.ask, why: `The live ask did not finish (${msg.note}).` } } });
}

export const mode = S => { const st = S.rag; if (!st || st.unanswered) return null;
  if (st.liveRetrieval) return { mode: "live", running: false, why: "retrieval live, no answer" };
  return { mode: st.mode, running: st.running && st.mode === "live", seconds: st.seconds, recorded: st.mode === "replay" ? st.recorded : null, why: st.note }; };
export const onKey = (e, S, set) => { if (e.key.toUpperCase() === "R") askRag(S, set, DATA.meta.question, "main"); };

export function View() {
  const { S, set } = useApp(), st = S.rag, N = tickers().length, asks = ASKS();
  const a = st?.ask, r = st?.at >= 3 ? st.result : null, shown = (a?.retrieved || []).slice(0, st?.shown || 0);
  const inCtx = [...new Set(shown.map(c => c.ticker))], inAns = companiesIn(r);
  const chips = asks.map(x => ({ id: x.id, label: x.label, question: x.question }));
  const wrongQ = st && st.ask?.question && st.asked && st.ask.question !== st.asked && closest([st.ask], st.asked).score < 0.6;
  return (
    <div class="screen ask-screen">
      <Ask chips={chips} asked={st?.asked} current={!st?.running && st?.ask?.id} busy={st?.running && st.mode === "live"} inputRef={S.refs.rag}
        placeholder="Ask the filings, e.g. What industry risks connect all counterparties?" onAsk={(q, id) => askRag(S, set, q, id)} />
      <Steps steps={stepsFor(st)} at={st ? st.at : -1} />
      <div class="stripline">
        <Strip on={inAns} part={inCtx} />
        <div class="figure"><b>{r ? inAns.length : st ? inCtx.length : "–"}</b><span>of {N} {r ? "in the answer" : "retrieved"}<br />{r ? `${inCtx.length} retrieved` : ""}</span></div>
      </div>
      {!st ? <Empty /> : st.unanswered ? <Unanswered st={st} onAsk={(q, id) => askRag(S, set, q, id)} /> : (
        <div class="ask-grid">
          <div class="ask-answer">
            <div class="asked">{st.asked}</div>
            {wrongQ && <div class="note">{st.note}. The answer below is to that question, not to the one typed.</div>}
            {st.missing
              ? <div class="note">{st.liveRetrieval ? "Retrieval above is live." : "Retrieval above is recorded."} The answer to this question is not recorded{st.note ? ` (${st.note})` : ""}.</div>
              : <Output source={`written from the ${a?.top_k || 12} retrieved chunks only`} text={st.at >= 2 ? st.text : null} streaming={st.at === 2}
                wait={st.at < 5 && (st.mode === "live" || noteFor(a || {})) ? ["Searching", "Searching", "Writing the answer", "Checking every quote", "Writing the analyst note"][st.at] : null}
                note={st.at >= 4 ? st.anote : null} noteText={st.noteText} done={st.at >= 5} />}
            {r && <div><div class="label">Verified findings · click one for its quotes in the filings</div>
              <Findings claims={r.claims} approach="1_plain_rag" max={5} title="Plain RAG · verified claims" /></div>}
          </div>
          <Chunks a={a} shown={shown} cited={citedIds(r)} />
        </div>)}
    </div>
  );
}

function Empty() {
  return <div class="empty-ask"><p class="serif">Plain RAG embeds the question, pulls the 12 closest chunks from the ten filings, and answers from those chunks only.</p>
    <p class="meta">Type a question, pick one above, or press R for the main question.</p></div>;
}

// The chunks the model saw, best first. Cited ones are marked; each opens in its filing.
function Chunks({ a, shown, cited }) {
  const { set } = useApp(), max = Math.max(...(a?.retrieved || []).map(c => c.score), 0.01), min = 0.5;
  const open = c => set({ drawer: { title: `${c.ticker} · chunk ${c.chunk_id}`, approach: "1_plain_rag", sub: `Retrieved chunk, cosine ${c.score.toFixed(3)}${cited.has(c.chunk_id) ? " · cited in the answer" : ""} · characters ${c.start}–${c.end} of Item 1A`,
    claims: [{ company: c.ticker, leaf: "Retrieved chunk", quote: (DATA.texts[c.ticker] || "").slice(c.start, c.end), start: c.start, end: c.end, source_ref: c.chunk_id }] } });
  return (
    <div class="chunks">
      <div class="label">Top {a?.top_k || 12} of {a?.chunks_indexed ?? "–"} chunks, by cosine</div>
      <ol>{shown.map((c, i) => (
        <li key={c.chunk_id} class={cited.has(c.chunk_id) ? "cited" : ""}>
          <button onClick={() => open(c)}>
            <span class="rank">{i + 1}</span><span class={`tk ${industry(c.ticker)}`}>{c.ticker}</span>
            <span class="bar"><i style={{ width: `${Math.max(4, 100 * (c.score - min) / (max - min))}%` }} /></span>
            <span class="mono">{c.score.toFixed(3)}</span>
            <span class="tag">{cited.has(c.chunk_id) ? "cited" : ""}</span>
          </button></li>))}</ol>
    </div>
  );
}

export function Detail() {
  const { S } = useApp(), st = S.rag, r = st?.result, a = st?.ask;
  return <>
    {r && <section><h3>Verifier</h3><Ledger v={r.verification} /></section>}
    <section><h3>Why the reach is narrow</h3><p class="ink2" style={{ margin: 0 }}>Top-k favours the closest wording, so the same few filings win. A company that was never retrieved cannot be linked to anyone.</p></section>
    {a?.retrieved?.length > 0 && <section><h3>Top-{a.top_k} of {a.chunks_indexed} chunks, cosine</h3>
      <table class="t"><tbody>{a.retrieved.map(c => (
        <tr key={c.chunk_id}><td class="mono">{c.chunk_id}</td><td class="num">{c.score.toFixed(3)}</td><td class="ink3">chars {c.start}–{c.end}</td></tr>))}</tbody></table></section>}
  </>;
}
