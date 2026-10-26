// Live calls to src/serve.py. Each streams NDJSON lines:
//   {"type": "token", "text": "..."}        answer text as the model writes it
//   {"type": "stage", "step": 1, "text"}   which pipeline step the server is on (retrieving, routing, querying)
//   {"type": "retrieved", ...}             plain RAG only: the top-k chunks, before the answer
//   {"type": "plan", ...}                  graph ask only: template, params, Cypher and the rows, before the answer
//   {"type": "result", ...}                 the verified result (same contract as results/demo_run/)
//   {"type": "replay", "note": "..."}       the server fell back (timeout, error, cap reached)
// Any client-side failure (no server, network, deadline) also ends in replay: never a blank screen.

export async function status() {
  if (!location.protocol.startsWith("http")) return { live: false };
  try { return await (await fetch("/api/status")).json(); } catch (e) { return { live: false }; }
}

export async function stream(path, body, { onToken, onStage, onPlan, onEvent, deadlineMs = 30000, signal } = {}) {
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), deadlineMs);
  signal?.addEventListener("abort", () => ctl.abort());
  try {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: ctl.signal });
    if (!res.ok || !res.body) return { type: "replay", note: `server answered ${res.status}` };
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "", final = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line) continue;
        const msg = JSON.parse(line);
        onEvent?.(msg);
        if (msg.type === "token") onToken?.(msg.text);
        else if (msg.type === "stage") onStage?.(msg.text);
        else if (msg.type === "plan") onPlan?.(msg);
        else if (msg.type === "result" || msg.type === "replay") final = msg;
      }
    }
    return final || { type: "replay", note: "the live answer ended without a result" };
  } catch (e) {
    return { type: "replay", note: e.name === "AbortError" ? `no answer within ${Math.round(deadlineMs / 1000)} s` : "live call failed" };
  } finally { clearTimeout(timer); }
}
