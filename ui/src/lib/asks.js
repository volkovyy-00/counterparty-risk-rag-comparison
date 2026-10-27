// Shared by the plain-RAG and GraphRAG screens: match a typed question to a recorded ask, and replay a recorded
// run step by step at a pace the room can follow. A replay never pretends to be live: the badge says REPLAY.

const STOP = new Set("a an and are as at be by do does each for from how in is it of on or the their these this to what which who with all its".split(" "));
const words = s => new Set(String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(w => w && !STOP.has(w)));

// Similarity of two questions: share of content words in common (Jaccard). 1 = same words.
export function similarity(a, b) {
  const A = words(a), B = words(b); if (!A.size || !B.size) return 0;
  let n = 0; A.forEach(w => B.has(w) && n++);
  return n / (A.size + B.size - n);
}

// {ask, score} for the recorded ask closest to `text`; `exact` when it is the same question in other words.
export function closest(asks, text, q = a => a.question) {
  let best = null, score = -1;
  for (const a of asks) { const s = similarity(q(a), text); if (s > score) { best = a; score = s; } }
  return { ask: best, score, exact: score >= 0.6 };
}

// Run `steps` one after another: each is {ms, run(set)}; returns a cancel function. Used for replays only.
export function play(steps, done) {
  let alive = true, t = null, i = 0;
  const next = () => {
    if (!alive) return;
    if (i >= steps.length) return done?.();
    const s = steps[i++]; s.run?.();
    t = setTimeout(next, s.ms || 0);
  };
  next();
  return () => { alive = false; clearTimeout(t); };
}

// Text typed out over `ms`, a few characters per frame; returns a cancel function.
export function typeOut(text, ms, onText, done) {
  const start = performance.now(); let alive = true;
  const frame = now => {
    if (!alive) return;
    const n = Math.min(text.length, Math.ceil(text.length * (now - start) / ms));
    onText(text.slice(0, n));
    if (n < text.length) requestAnimationFrame(frame); else done?.();
  };
  requestAnimationFrame(frame);
  return () => { alive = false; };
}

// Verified claims grouped into findings: one row per risk (taxonomy leaf), companies in filing order.
export function findings(claims, label) {
  const g = new Map();
  for (const c of claims || []) {
    const k = c.leaf, e = g.get(k) || { leaf: k, label: label(c), claims: [], tickers: [] };
    e.claims.push(c); if (!e.tickers.includes(c.company)) e.tickers.push(c.company);
    g.set(k, e);
  }
  return [...g.values()].sort((a, b) => b.tickers.length - a.tickers.length || b.claims.length - a.claims.length || a.label.localeCompare(b.label));
}
