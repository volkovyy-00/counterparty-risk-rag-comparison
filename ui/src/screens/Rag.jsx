import { DATA, short, tickers } from "../lib/data.js";
import { stream } from "../lib/live.js";
import { useApp } from "../store.js";
import { Strip } from "../components/Strip.jsx";
import { Badge } from "../components/Badge.jsx";
import { Ask } from "../components/Ask.jsx";
import { ClaimTable, Ledger } from "../components/Claims.jsx";

const recorded = () => DATA.approaches["1_plain_rag"];
const MAIN = { id: "main", label: "The main question" };

export const ragReplay = (question, note) => ({
  mode: "replay", result: recorded(), question: DATA.meta.question, asked: question || DATA.meta.question, note,
  recorded: recorded().details.answer_recorded_at || DATA.meta.created_at,
});

export async function askRag(S, set, question) {
  if (S.rag?.running) return;
  if (!S.server?.live) return set({ rag: ragReplay(question, S.server ? "live asks are off on this server (start it with --live)" : "no server: offline copy") });
  let text = "";
  set({ rag: { mode: "live", running: true, text: "", asked: question, question, stage: "retrieving top-12 chunks" } });
  const msg = await stream("/api/live_rag", { question }, {
    deadlineMs: (S.server.timeout_s || 20) * 1000 + 3000,
    onStage: st => set(s => ({ rag: { ...s.rag, stage: st } })),
    onToken: t => { text += t; set(s => ({ rag: { ...s.rag, text, stage: null } })); },
  });
  if (msg.type === "result") set({ rag: { mode: "live", result: msg.result, question, asked: question, seconds: msg.seconds, text: msg.result.summary } });
  else set({ rag: ragReplay(question, msg.note) });
}

export function Rag() {
  const { S, set } = useApp(), st = S.rag || ragReplay();
  const r = st.result, N = tickers().length;
  const mainQ = DATA.meta.question;
  const chips = [{ ...MAIN, question: mainQ }];
  const inCtx = r ? r.details.tickers_in_retrieved_context : [];
  const inAns = r ? r.companies_covered : [];
  const typedFallback = st.mode === "replay" && st.asked && st.asked !== mainQ;
  return (
    <div class="screen">
      <div class="screen-head">
        <h1>Approach 1 · Plain RAG</h1>
        <div class="right"><Badge mode={st.mode} running={st.running} seconds={st.seconds} recorded={st.mode === "replay" ? st.recorded : null} why={st.note} /></div>
        <div class="sub">Embed the question, take the top {recorded().details.top_k} chunks out of {recorded().details.chunks_indexed}, one model call. Same claim contract and verifier as the other approaches.</div>
      </div>
      <Ask chips={chips} current={st.asked === mainQ ? "main" : null} busy={st.running} inputRef={S.refs.rag}
        placeholder="Ask the filings a question, e.g. Which companies depend on a single foundry?" onAsk={q => askRag(S, set, q)} />
      <div class="grid2">
        <div class="stripline">
          <div><div class="strip-legend"><span>Retrieved into the model's context</span></div>
            <Strip size="lg" on={st.running ? [] : inCtx} /></div>
          <div class="count">{st.running ? "–" : inCtx.length}<small>of {N}</small></div>
        </div>
        <div class="stripline">
          <div><div class="strip-legend"><span>Cited in the verified answer</span><span>outlined: retrieved, not cited</span></div>
            <Strip size="lg" on={st.running ? [] : inAns} part={st.running ? [] : inCtx} /></div>
          <div class="count">{st.running ? "–" : inAns.length}<small>of {N}</small></div>
        </div>
      </div>
      <div class="split">
        <div class="stack">
          <div class="panel stack">
            <div class="small dim">{st.asked || mainQ}</div>
            {st.running && !st.text
              ? <div><div class="small muted">{st.stage || "waiting for the model"}…</div><div class="skeleton" style={{ width: "92%" }} /><div class="skeleton" style={{ width: "74%" }} /></div>
              : <div class={`answer ${st.running ? "streaming" : ""}`}>{st.running ? st.text : short(r?.summary, 600)}</div>}
            {typedFallback && <div class="note">The live call did not finish ({st.note}). This is the recorded answer to the main question, not to the question typed.</div>}
          </div>
          {!st.running && r && <ClaimTable claims={r.claims} approach="1_plain_rag" max={5} />}
        </div>
        <div class="stack">
          <div class="panel"><h3>Verifier</h3>{r && !st.running ? <Ledger v={r.verification} /> : <div class="skeleton" />}</div>
          <div class="panel"><h3>Why the reach is narrow</h3>
            <div class="small muted">A company that was never retrieved cannot be linked to anyone. Top-k favours the closest wording, so the same few filings win.</div></div>
          {r && !st.running && <div class="panel"><h3>Top-{r.details.top_k} chunks <span class="muted">cosine</span></h3>
            <table class="t"><tbody>{(r.details.retrieved || []).map(c => (
              <tr key={c.chunk_id}><td class="mono xs">{c.chunk_id}</td><td class="num">{c.score.toFixed(3)}</td></tr>))}</tbody></table></div>}
        </div>
      </div>
    </div>
  );
}
