import { useState } from "preact/hooks";
import { Search, CornerDownLeft } from "lucide-preact";

// Chips for the fixed questions plus a typed question. onAsk(text, chipId|null).
export function Ask({ chips = [], current, onAsk, placeholder, busy, inputRef }) {
  const [text, setText] = useState("");
  const submit = e => { e.preventDefault(); if (text.trim() && !busy) onAsk(text.trim(), null); };
  return (
    <div class="stack">
      <form class="ask" onSubmit={submit}>
        <label class="field"><Search />
          <input ref={inputRef} value={text} onInput={e => setText(e.currentTarget.value)} placeholder={placeholder}
            aria-label="Ask a question" disabled={busy} /></label>
        <button class="btn primary" type="submit" disabled={busy || !text.trim()}>Ask <CornerDownLeft /></button>
      </form>
      {chips.length > 0 && <div class="row">
        {chips.map(c => <button key={c.id} class="chip" aria-pressed={current === c.id} disabled={busy}
          onClick={() => onAsk(c.question, c.id)}>{c.label}</button>)}
      </div>}
    </div>
  );
}
