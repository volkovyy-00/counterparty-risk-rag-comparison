import { local } from "../lib/data.js";

// LIVE or REPLAY, nothing else. REPLAY says when the answer was recorded and, if a live call fell back, why.
export function Badge({ mode, running, seconds, recorded, why }) {
  if (mode === "live")
    return <span class={`badge live ${running ? "running" : ""}`}>LIVE{running ? "" : seconds != null ? <span class="why">{seconds}s</span> : null}</span>;
  return <span class="badge replay" title={why || ""}>REPLAY{recorded && <span class="why">recorded {local(recorded)}</span>}</span>;
}
