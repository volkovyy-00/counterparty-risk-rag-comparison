// The model's own words, set apart from everything the code computed: a panel with its source named.
// The filings' sentences stay in the quote face (Literata italic) in the findings below.
export function Output({ text, source, streaming }) {
  return (
    <section class="output" aria-label="Model answer" aria-busy={streaming || text == null}>
      <header><span class="tag">Model answer</span><span class="src">{source}</span></header>
      {text == null
        ? <div><div class="skeleton" style={{ width: "85%" }} /><div class="skeleton" style={{ width: "60%" }} /></div>
        : <p class={streaming ? "streaming" : ""}>{text}</p>}
    </section>
  );
}
