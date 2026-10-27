import { useState } from "preact/hooks";
import { industry } from "../lib/data.js";

// The model's own words, set apart from everything the code computed: a panel that names its source.
// While the approach answers, it shows that answer; once an analyst note exists (written from the verified
// claims only), the note leads and the approach's own answer is one click away. Quotes stay below, in the findings.
export function Output({ text, source, streaming, note, noteText, done }) {
  const [own, setOwn] = useState(false);
  if (note) return (
    <section class="output note" aria-label="Analyst note">
      <header><span class="tag">Analyst note</span><span class="src">written from the {note.claims} verified claims only</span></header>
      <p class={done ? "" : "streaming"}>{noteText}</p>
      {done && <>
        <ul class="points">{note.points.map(pt => (
          <li key={pt.risk}><div class="ph"><b>{pt.risk}</b>
            <span class="tks">{pt.tickers.map(t => <span key={t} class={`tk ${industry(t)}`}>{t}</span>)}</span></div>
            <span class="why">{pt.why}</span></li>))}</ul>
        <div class="foot">
          {note.caveat && <span>{note.caveat}</span>}
          {note.not_reached?.length > 0 && <span><b>Not reached:</b> {note.not_reached.join(", ")}</span>}
          <button class="link" onClick={() => setOwn(!own)}>{own ? "Hide" : "Show"} the approach's own answer</button>
        </div>
        {own && <p class="own">{text}</p>}
      </>}
    </section>
  );
  return (
    <section class="output" aria-label="Model answer" aria-busy={streaming || text == null}>
      <header><span class="tag">Model answer</span><span class="src">{source}</span></header>
      {text == null
        ? <div><div class="skeleton" style={{ width: "85%" }} /><div class="skeleton" style={{ width: "60%" }} /></div>
        : <p class={streaming ? "streaming" : ""}>{text}</p>}
    </section>
  );
}
