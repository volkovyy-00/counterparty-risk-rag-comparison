// Deterministic graph layout (ported from demo/template.html): companies in two outer columns (autos left, chips
// right); risks linked to one side only next to it; risks that link both sides in two middle columns, in rank order.
export function placeNodes(comps, items, edges, W, H) {
  const left = comps.filter(c => c.industry !== "semis"), right = comps.filter(c => c.industry === "semis");
  const pos = {};
  const place = (arr, x) => arr.forEach((c, i) => pos[c.id] = { x, y: 60 + (H - 120) * (arr.length === 1 ? .5 : i / (arr.length - 1)) });
  place(left, 80); place(right, W - 80);
  const nb = {};
  edges.forEach(e => (nb[e.target] = nb[e.target] || []).push(e.source));
  const side = n => {
    const inds = new Set((nb[n.id] || []).map(s => (comps.find(c => c.id === s) || {}).industry));
    return inds.has("semis") && inds.size > 1 ? "mid" : inds.has("semis") ? "right" : inds.size ? "left" : "mid";
  };
  const cols = { left: [], mid0: [], mid1: [], right: [] };
  let k = 0;
  items.forEach(n => { const s = side(n); if (s === "mid") cols[k++ % 2 ? "mid1" : "mid0"].push(n); else cols[s].push(n); });
  const X = { left: W * 0.27, mid0: W * 0.42, mid1: W * 0.6, right: W * 0.75 };
  if (!cols.left.length && !cols.right.length) { X.mid0 = W * 0.38; X.mid1 = W * 0.62; }
  if (cols.mid0.length + cols.mid1.length <= 1 && !cols.left.length && !cols.right.length) X.mid0 = W / 2;
  Object.entries(cols).forEach(([c, arr]) => arr.forEach((n, i) =>
    pos[n.id] = { x: X[c], y: 80 + (H - 140) * (arr.length === 1 ? .5 : i / (arr.length - 1)) }));
  return pos;
}

// Up to `max` lines of about `width` characters, broken between words (a long word is never cut).
export function wrapWords(text, width = 28, max = 2) {
  const lines = [];
  for (const w of String(text ?? "").split(/\s+/).filter(Boolean)) {
    const cur = lines[lines.length - 1];
    if (cur != null && (cur + " " + w).length <= width) lines[lines.length - 1] = cur + " " + w; else lines.push(w);
  }
  if (lines.length > max) { lines.length = max; lines[max - 1] += "…"; }
  return lines.length ? lines : [""];
}

// Whole-graph overview: top-ranked shared risks only, so ten companies stay readable.
export function overviewItems(g, { hideGeneric, showDrivers }) {
  const shared = g.nodes.filter(n => n.type === "RiskFactor" && n.degree >= 2);
  const generic = shared.filter(n => n.generic);
  const cross = n => n.industries.includes("auto") && n.industries.includes("semis");
  const rank = (a, b) => (cross(b) - cross(a)) || (b.degree * (b.idf ?? 1) - a.degree * (a.idf ?? 1)) || (b.degree - a.degree) || a.label.localeCompare(b.label);
  let risks = shared.filter(n => !n.generic).sort(rank).slice(0, showDrivers ? 12 : 18)
    .concat(hideGeneric ? [] : generic.slice().sort((a, b) => b.degree - a.degree).slice(0, 5));
  if (showDrivers) risks = risks.concat((g.drivers || []).filter(n => n.degree >= 2).slice(0, 6));
  const ids = new Set(risks.map(r => r.id));
  return {
    nodes: g.nodes.filter(n => n.type === "Company").concat(risks.filter(r => r.type !== "ExposureDriver")),
    drivers: risks.filter(r => r.type === "ExposureDriver"),
    edges: g.edges.filter(e => ids.has(e.target)), driver_edges: (g.driver_edges || []).filter(e => ids.has(e.target)),
    hiddenSingles: g.nodes.filter(n => n.type === "RiskFactor" && n.degree < 2).length,
    notDrawn: shared.length - risks.filter(r => r.type !== "ExposureDriver").length,
  };
}
