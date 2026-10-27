import { Check } from "lucide-preact";

// The pipeline as it runs: done steps are checked and keep their result, the active one pulses, the rest wait.
// `at` = index of the active step; steps.length = all done; -1 = not started.
export function Steps({ steps, at }) {
  return (
    <ol class="steps" aria-label="What the pipeline is doing">
      {steps.map((s, i) => {
        const st = at < 0 || i > at ? "wait" : i < at ? "done" : "run";
        return (
          <li key={s.label} class={st} aria-current={st === "run" ? "step" : null}>
            <span class="dot">{st === "done" ? <Check /> : i + 1}</span>
            <div><b>{s.label}</b><span>{st === "done" ? s.done || s.detail : s.detail}</span></div>
          </li>);
      })}
    </ol>
  );
}
