import { DATA, short, tickers } from "../lib/data.js";
import { stream } from "../lib/live.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Ask } from "../components/Ask.jsx";
import { ClaimTable, Ledger } from "../components/Claims.jsx";

const recorded = () => DATA.approaches["1_plain_rag"];

export const ragReplay = (question, note) => ({
  mode: "replay", result: recorded(), asked: question || DATA.meta.question, note,
  recorded: recorded().details.answer_recorded_at || DATA.meta.created_at,
});

export async function askRag(S, set, question) {
  if (S.rag?.running) return;
  if (!S.server?.live) return set({ rag: ragReplay(question, S.server ? "live asks are off on this server" : "no server: offline copy") });
  let text = "";
  set({ rag: { mode: "live", running: true, text: "", asked: question, stage: "retrieving the top-12 chunks" } });
  const msg = await stream("/api/live_rag", { question }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 3000,
    onStage: st => set(s => ({ rag: { ...s.rag, stage: st } })),
    onToken: t => { text += t; set(s => ({ rag: { ...s.rag, text, stage: null } })); },
  });
  if (msg.type === "result") set({ rag: { mode: "live", result: msg.result, asked: question, seconds: msg.seconds } });
  else set({ rag: ragReplay(question, msg.note) });
}

export const mode = S => { const st = S.rag || ragReplay();
  return { mode: st.mode, running: st.running, seconds: st.seconds, recorded: st.mode === "replay" ? st.recorded : null, why: st.note }; };
export const onKey = (e, S, set) => { if (e.key.toUpperCase() === "R") askRag(S, set, DATA.meta.question); };

export function View() {
  const { S, set } = useApp(), st = S.rag || ragReplay(), r = st.result, N = tickers().length, mainQ = DATA.meta.question;
  const inCtx = r && !st.running ? r.details.tickers_in_retrieved_context : [];
  const inAns = r && !st.running ? r.companies_covered : [];
  const typedFallback = st.mode === "replay" && st.asked && st.asked !== mainQ;
  return (
    <div class="screen">
      <Ask chips={[{ id: "main", label: "The main question", question: mainQ }]} current={st.asked === mainQ && !st.running ? "main" : null}
        busy={st.running} inputRef={S.refs.rag} placeholder="Ask the filings, e.g. Which companies depend on a single foundry?"
        onAsk={q => askRag(S, set, q)} />
      <div>
        <div class="stripline">
          <Strip on={inAns} part={inCtx} />
          <div class="figure"><b>{st.running ? "–" : inAns.length}</b><span>of {N} in the answer<br />{st.running ? "" : `${inCtx.length} retrieved`}</span></div>
        </div>
        <div class="keyline"><span><i class="f" />cited in the answer</span><span><i />retrieved, not cited</span><span><i class="e" />never retrieved</span></div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
        {st.running && !st.text
          ? <div><div class="ink3">{st.stage || "waiting for the model"}…</div><div class="skeleton" style={{ width: "80%" }} /><div class="skeleton" style={{ width: "60%" }} /></div>
          : <div class={`answer ${st.running ? "streaming" : ""}`}>{st.running ? st.text : short(r?.summary, 380)}</div>}
        {!st.running && r && <div class="verified"><span><b>{r.verification.accepted} of {r.verification.claims}</b> claims verified against the filings</span>
          <span>{r.verification.rejected_quote + r.verification.rejected_label} rejected</span></div>}
        {typedFallback && <div class="note">The live call did not finish ({st.note}). This is the recorded answer to the main question, not to the one typed.</div>}
      </div>
      {!st.running && r && <ClaimTable claims={r.claims} approach="1_plain_rag" max={5} title="Plain RAG · verified claims" />}
    </div>
  );
}

export function Detail() {
  const { S } = useApp(), r = (S.rag || ragReplay()).result;
  if (!r) return null;
  return <>
    <section><h3>Verifier</h3><Ledger v={r.verification} /></section>
    <section><h3>Why the reach is narrow</h3><p class="ink2" style={{ margin: 0 }}>Top-k favours the closest wording, so the same few filings win. A company that was never retrieved cannot be linked to anyone.</p></section>
    <section><h3>Top-{r.details.top_k} of {r.details.chunks_indexed} chunks, cosine</h3>
      <table class="t"><tbody>{(r.details.retrieved || []).map(c => (
        <tr key={c.chunk_id}><td class="mono">{c.chunk_id}</td><td class="num">{c.score.toFixed(3)}</td></tr>))}</tbody></table></section>
  </>;
}
