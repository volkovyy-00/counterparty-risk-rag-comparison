import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { Maximize, Minus, Plus } from "lucide-preact";
import { isCross } from "../lib/data.js";
import { wrapWords } from "../lib/layout.js";

// A Neo4j-browser style view of exactly the rows a query returned: drag nodes (they stay where dropped,
// double-click to release), drag the background to pan, wheel or +/- to zoom, click a node to select it.
// `reveal` (0..1) grows the graph in while a run is replayed. Nothing here adds a node the rows did not hold.
const RT = { Company: "COMPANY", RiskFactor: "FACES_RISK", ExposureDriver: "NAMES" };
const ind = n => n.industry === "semis" ? "semis" : "auto";
export const radius = n => n.type === "Company" ? 34 : Math.min(30, 15 + 2.4 * (n.degree || 1));

export function ForceGraph({ g, selected, onSelect, reveal = 1, height }) {
  const box = useRef(null), svg = useRef(null);
  const [size, setSize] = useState({ w: 900, h: 600 });
  const [, tick] = useState(0);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [hover, setHover] = useState(null);
  const sim = useRef(null), nodesRef = useRef([]), linksRef = useRef([]), drag = useRef(null);

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  // (Re)build the simulation when the subgraph changes; keep positions of nodes that stay.
  const key = useMemo(() => g.nodes.map(n => n.id).concat((g.drivers || []).map(n => n.id)).join("|"), [g]);
  useEffect(() => {
    const old = Object.fromEntries(nodesRef.current.map(n => [n.id, n]));
    const all = g.nodes.concat(g.drivers || []);
    const { w, h } = size;
    const nodes = all.map((n, i) => {
      const o = old[n.id];
      if (o) return Object.assign(o, { data: n });
      const side = n.type === "Company" ? (ind(n) === "semis" ? 0.72 : 0.28) : 0.5;
      const a = (i / Math.max(1, all.length)) * Math.PI * 2;
      return { id: n.id, data: n, x: w * side + Math.cos(a) * 60, y: h / 2 + Math.sin(a) * 60 };
    });
    const ids = new Set(nodes.map(n => n.id));
    const links = g.edges.concat(g.driver_edges || []).filter(e => ids.has(e.source) && ids.has(e.target))
      .map(e => ({ source: e.source, target: e.target, data: e }));
    nodesRef.current = nodes; linksRef.current = links;
    sim.current?.stop();
    const dense = nodes.length > 30;
    // Companies are pulled to two loose columns (autos left, chips right), spread top to bottom; risks float between.
    const col = {}; ["auto", "semis"].forEach(k => { const cs = nodes.filter(n => n.data.type === "Company" && ind(n.data) === k);
      cs.forEach((n, i) => col[n.id] = 0.16 + 0.68 * (cs.length === 1 ? 0.5 : i / (cs.length - 1))); });
    sim.current = forceSimulation(nodes)
      .force("link", forceLink(links).id(d => d.id).distance(dense ? 90 : 140).strength(dense ? 0.25 : 0.5))
      .force("charge", forceManyBody().strength(dense ? -520 : -800).distanceMax(600))
      .force("collide", forceCollide(d => radius(d.data) + (d.data.type === "Company" ? 16 : dense ? 22 : 58)).strength(0.9))
      .force("x", forceX(d => d.data.type === "Company" ? w * (ind(d.data) === "semis" ? 0.86 : 0.14) : w / 2)
        .strength(d => d.data.type === "Company" ? 0.5 : 0.02))
      .force("y", forceY(d => d.data.type === "Company" ? h * col[d.id] : h / 2).strength(d => d.data.type === "Company" ? 0.5 : dense ? 0.1 : 0.05))
      .stop();
    // Settle before the first frame, so the room sees a calm graph, not a spinning hairball; drags restart it.
    for (let i = 0; i < 320; i++) sim.current.tick();
    // A force layout comes out round; the pane is wide. Stretch it sideways (at most 1.7x) to use the width.
    const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
    const bw = Math.max(...xs) - Math.min(...xs) || 1, bh = Math.max(...ys) - Math.min(...ys) || 1, cx = (Math.max(...xs) + Math.min(...xs)) / 2;
    const sx = Math.min(1.7, Math.max(1, (w / h) / (bw / bh)));
    nodes.forEach(n => { n.x = cx + (n.x - cx) * sx; if (n.fx != null) n.fx = n.x; });
    sim.current.alpha(0.02).alphaDecay(0.04).on("tick", () => tick(t => t + 1)).restart();
    fitNow();
    return () => sim.current?.stop();
  }, [key, size.w > 0 && size.h > 0]);

  function fitNow() { fit(); }
  useEffect(() => { const t = setTimeout(fit, 400); return () => clearTimeout(t); }, [size.w, size.h]);
  function fit() {
    const ns = nodesRef.current; if (!ns.length) return;
    const pad = 70, xs = ns.map(n => n.x), ys = ns.map(n => n.y);
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad + 30;
    const k = Math.min(1.4, size.w / (x1 - x0), size.h / (y1 - y0));
    setView({ k, x: size.w / 2 - k * (x0 + x1) / 2, y: size.h / 2 - k * (y0 + y1) / 2 });
  }

  const toGraph = (cx, cy) => { const r = svg.current.getBoundingClientRect();
    return [(cx - r.left - view.x) / view.k, (cy - r.top - view.y) / view.k]; };
  const zoomAt = (f, cx, cy) => setView(v => {
    const k = Math.max(0.3, Math.min(3, v.k * f)), r = svg.current.getBoundingClientRect();
    const px = cx == null ? size.w / 2 : cx - r.left, py = cy == null ? size.h / 2 : cy - r.top;
    return { k, x: px - (px - v.x) * (k / v.k), y: py - (py - v.y) * (k / v.k) };
  });

  const down = (e, n) => {
    e.stopPropagation(); e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = n ? { n, moved: false } : { pan: true, sx: e.clientX, sy: e.clientY, v: view, moved: false };
    if (n) { n.fx = n.x; n.fy = n.y; sim.current.alphaTarget(0.25).restart(); }
  };
  const move = e => {
    const d = drag.current; if (!d) return;
    if (d.pan) { const dx = e.clientX - d.sx, dy = e.clientY - d.sy; if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
      setView({ ...d.v, x: d.v.x + dx, y: d.v.y + dy }); return; }
    const [x, y] = toGraph(e.clientX, e.clientY); d.moved = true; d.n.fx = x; d.n.fy = y;
  };
  const up = () => {
    const d = drag.current; drag.current = null; if (!d) return;
    if (d.n) { sim.current.alphaTarget(0); if (!d.moved) onSelect(selected === d.n.id ? null : d.n.id); }
    else if (!d.moved) onSelect(null);
  };

  const nodes = nodesRef.current, links = linksRef.current;
  const shown = new Set(nodes.filter((n, i) => n.data.type === "Company" || i < Math.ceil(reveal * nodes.length) + 1).map(n => n.id));
  const dense = nodes.length > 30;
  const topIds = new Set(nodes.filter(n => n.data.type !== "Company").sort((a, b) => (b.data.degree || 0) - (a.data.degree || 0)
    || (!a.data.generic && isCross(a.data) ? -1 : 1)).slice(0, dense ? 8 : 99).map(n => n.id));
  const nb = selected ? new Set(links.filter(l => l.source.id === selected || l.target.id === selected)
    .flatMap(l => [l.source.id, l.target.id])) : null;
  return (
    <div class="fgraph" ref={box} style={height ? { height } : null}>
      <svg ref={svg} width={size.w} height={size.h} onPointerDown={e => down(e, null)} onPointerMove={move} onPointerUp={up}
        onWheel={e => { e.preventDefault(); zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY); }}
        role="img" aria-label="Graph of the rows the query returned. Drag to move, click a node to see its links.">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--rule-2)" /></marker>
          <marker id="arr-on" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--ink)" /></marker></defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {links.map((l, i) => {
            const a = l.source, b = l.target; if (!shown.has(a.id) || !shown.has(b.id) || a.x == null) return null;
            const on = selected && (a.id === selected || b.id === selected), dim = selected && !on;
            const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
            const ra = radius(a.data) + 2, rb = radius(b.data) + 4;
            const x1 = a.x + dx / len * ra, y1 = a.y + dy / len * ra, x2 = b.x - dx / len * rb, y2 = b.y - dy / len * rb;
            const ang = Math.atan2(dy, dx) * 180 / Math.PI, flip = ang > 90 || ang < -90;
            return <g key={i} opacity={dim ? 0.12 : 1}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={on ? "var(--ink)" : "var(--rule-2)"} stroke-width={on ? 2.2 : 1.3}
                stroke-opacity={on ? 1 : dense ? 0.45 : 0.8}
                marker-end={`url(#${on ? "arr-on" : "arr"})`} />
              {on && len > 120 && <text class="rel" transform={`translate(${(x1 + x2) / 2},${(y1 + y2) / 2}) rotate(${flip ? ang + 180 : ang})`}
                text-anchor="middle" dy="-6">{RT[b.data.type] || "LINK"}</text>}
            </g>;
          })}
          {nodes.map(n => {
            if (!shown.has(n.id) || n.x == null) return null;
            const d = n.data, r = radius(d), sel = selected === n.id, dim = nb && !nb.has(n.id);
            const company = d.type === "Company", driver = d.type === "ExposureDriver";
            const fill = company ? `var(--${ind(d)})` : d.generic ? "var(--node-generic)" : driver ? "var(--node-driver)" : "var(--node-risk)";
            const labelled = !dense || topIds.has(n.id) || sel || hover === n.id || (nb && nb.has(n.id));
            const lines = company || !labelled ? [] : wrapWords(d.label, 18, 2);
            return (
              <g key={n.id} class={`fnode ${sel ? "sel" : ""}`} onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)} transform={`translate(${n.x},${n.y})`} opacity={dim ? 0.22 : 1}
                onPointerDown={e => down(e, n)} onDblClick={e => { e.stopPropagation(); n.fx = n.fy = null; sim.current.alpha(0.3).restart(); }}
                tabIndex={0} onKeyDown={e => e.key === "Enter" && onSelect(n.id)} aria-label={`${d.label}${company ? "" : `, ${d.degree} companies`}`}>
                {sel && <circle r={r + 7} fill="none" stroke="var(--focus)" stroke-width="3" />}
                {driver ? <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} transform="rotate(45)" fill={fill} />
                  : <circle r={r} fill={fill} stroke="var(--ground)" stroke-width="2" />}
                {company ? <text class="cap-in" dy="0.35em" text-anchor="middle" fill={`var(--${ind(d)}-ink)`}>{d.label}</text>
                  : <>
                    <text class="cap-n" dy="0.35em" text-anchor="middle">{d.degree}</text>
                    <text class="cap" text-anchor="middle" y={r + 20}>{lines.map((t, k) => <tspan key={k} x="0" dy={k ? "1.15em" : 0}>{t}</tspan>)}</text>
                  </>}
              </g>);
          })}
        </g>
      </svg>
      <div class="zoom">
        <button class="btn icon" onClick={() => zoomAt(1.2)} aria-label="Zoom in"><Plus /></button>
        <button class="btn icon" onClick={() => zoomAt(1 / 1.2)} aria-label="Zoom out"><Minus /></button>
        <button class="btn icon" onClick={fit} aria-label="Fit to screen"><Maximize /></button>
      </div>
    </div>
  );
}
