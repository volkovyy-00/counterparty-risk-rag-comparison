// Run by tests/test_browser_live.py: the browser port (ui/src/lib/browserLive.js) must return the same rows, prompt,
// subgraph and quote offsets as the Python pipeline for every case in argv[3] (written by the test).
import fs from "fs";
const [root, cases] = [process.argv[2], JSON.parse(fs.readFileSync(process.argv[3]))];
const { setData } = await import(root + "/ui/src/lib/data.js");
const L = await import(root + "/ui/src/lib/browserLive.js");
const D = JSON.parse(fs.readFileSync(process.argv[4])); setData(D);
const norm = rows => rows.map(r => [r.risk, r.role, !!r.generic, r.n_companies,
  r.evidence.map(e => [e.ticker, e.quotes, e.spans]).sort((a, b) => (a[0] < b[0] ? -1 : 1))]);
const bad = [];
for (const c of cases.patterns) {
  const rows = L.rowsFor(D.graph, c.t, c.p);
  if (JSON.stringify(norm(rows)) !== JSON.stringify(c.rows)) bad.push(`rows ${c.t}`);
  if (L._prompt("Q?", rows)[0] !== c.prompt) bad.push(`prompt ${c.t}`);
  if (JSON.stringify(L.toSubgraph(rows)) !== JSON.stringify(c.sub)) bad.push(`subgraph ${c.t}`);
}
for (const q of cases.quotes) { const s = L._locate(q.quote, D.texts[q.company]); if (!s || s[0] !== q.start || s[1] !== q.end) bad.push(`quote ${q.company} ${q.start}`); }
console.log(JSON.stringify(bad));
