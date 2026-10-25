import { useState } from "preact/hooks";
import { Search, CornerDownLeft } from "lucide-preact";

// A typed question plus chips for the fixed ones. onAsk(text, chipId|null).
export function Ask({ chips = [], current, onAsk, placeholder, busy, inputRef, extra }) {
  const [text, setText] = useState("");
  const submit = e => { e.preventDefault(); if (text.trim() && !busy) onAsk(text.trim(), null); };
  return (
    <div class="askrow">
      <form class="ask" onSubmit={submit}>
        <label><Search />
          <input id="ask" ref={inputRef} value={text} onInput={e => setText(e.currentTarget.value)} placeholder={placeholder}
            aria-label="Ask a question" disabled={busy} /></label>
        <button class="btn primary" type="submit" disabled={busy || !text.trim()}>Ask <CornerDownLeft /></button>
      </form>
      {(chips.length > 0 || extra) && <div class="chips">
        {chips.map(c => <button key={c.id} class="chip" aria-pressed={current === c.id} disabled={busy}
          onClick={() => onAsk(c.question, c.id)}>{c.label}</button>)}
        {extra}
      </div>}
    </div>
  );
}
