// A typed question that cannot run here: say why, list what can, and offer the closest recorded question.
// Never shows another question's answer under this one.
export function Unanswered({ st, can, onAsk }) {
  const s = st.unanswered.suggest;
  return <div class="ask-answer unanswered">
    <div class="asked">{st.asked}</div>
    <p class="serif">{st.unanswered.why}</p>
    {can && <div><div class="label">The graph can answer</div>
      <ul class="points">{can.map(p => <li key={p}>{p}</li>)}</ul></div>}
    {s && <div><div class="label">Closest recorded question</div>
      <button class="chip" onClick={() => onAsk(s.question, s.id)}>{s.question}</button></div>}
  </div>;
}
