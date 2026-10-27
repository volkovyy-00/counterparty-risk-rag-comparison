import { useState } from "preact/hooks";
import { industry } from "../lib/data.js";

// The model's words in one calm panel. With an analyst note (written from the verified claims only) the note is
// the answer: the takeaway, then each point as one plain sentence with its companies; the approach's own answer
// is one click away. Until the
// note arrives the panel only says what is happening, so nothing is typed out and then replaced.
export function Output({ text, source, streaming, note, noteText, done, wait }) {
  const [own, setOwn] = useState(false);
  if (note) return (
    <section class="output note" aria-label="Analyst note">
      <header><span class="tag">Analyst note</span><span class="src">from the {note.claims} verified claims</span></header>
      <p class={done ? "" : "streaming"}>{noteText}</p>
      {done && <>
        <ul class="points">{note.points.map(pt => (
          <li key={pt.risk}><b>{pt.risk}</b> <span class="tks">({pt.tickers.map((t, i) => <>{i ? ", " : ""}<span key={t} class={`tk ${industry(t)}`}>{t}</span></>)})</span>. {pt.why}</li>))}</ul>
        {note.caveat && <p class="caveat">{note.caveat}</p>}
        <div class="foot">
          {note.not_reached?.length > 0 && <span>Not reached: {note.not_reached.join(", ")}</span>}
          <button class="link" onClick={() => setOwn(!own)}>{own ? "Hide" : "Show"} the approach's own answer</button>
        </div>
        {own && <p class="own">{text}</p>}
      </>}
    </section>
  );
  if (wait) return (
    <section class="output" aria-label="Model answer" aria-busy="true">
      <header><span class="tag">Answer</span><span class="src">{wait}…</span></header>
      <div><div class="skeleton" style={{ width: "85%" }} /><div class="skeleton" style={{ width: "60%" }} /></div>
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
