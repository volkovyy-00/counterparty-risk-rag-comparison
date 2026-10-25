import { isCross } from "../lib/data.js";
import { placeNodes, wrapWords } from "../lib/layout.js";

const W = 1200, H = 640;
const ind = c => c?.industry === "semis" ? "semis" : "auto";

// The subgraph a query returned, nothing more. Hover a node to light its companies on the strip; click for quotes.
export function GraphView({ g, focus, onFocus, onOpen, empty }) {
  const comps = g.nodes.filter(n => n.type === "Company");
  const items = g.nodes.filter(n => n.type === "RiskFactor").concat(g.drivers || []);
  const edges = g.edges.concat(g.driver_edges || []);
  const pos = placeNodes(comps, items, edges, W, H);
  const rad = n => Math.min(30, 9 + 2.6 * (n.degree || 1));
  const byId = Object.fromEntries(comps.map(c => [c.id, c]));
  const lit = focus ? new Set(edges.filter(e => e.target === focus).map(e => e.source)) : null;
  return (
    <div class="graph">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Graph of the rows the query returned">
        <text x="80" y="22" text-anchor="middle" font-size="17" fill="var(--ink-3)">autos</text>
        <text x={W - 80} y="22" text-anchor="middle" font-size="17" fill="var(--ink-3)">chips</text>
        {edges.map((e, i) => {
          const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null;
          const on = focus && e.target === focus;
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={`var(--${ind(byId[e.source])})`}
            stroke-opacity={focus ? (on ? 0.95 : 0.08) : 0.25} stroke-width={on ? 3 : 1.5} />;
        })}
        {items.map((n, i) => {
          const p = pos[n.id], r = rad(n), cross = isCross(n), dim = focus && focus !== n.id;
          const lines = wrapWords(n.label, 24, 2); lines[lines.length - 1] += `  ${n.degree}`;
          const below = i % 2 === 1 ? p.y + r + 34 + 24 * lines.length < H : p.y - r - 12 - 24 * lines.length < 0;
          const y0 = below ? p.y + r + 26 : p.y - r - 12 - 24 * (lines.length - 1);
          const fill = n.generic ? "var(--ink-3)" : "var(--ink)";
          const tag = n.role && n.role !== "shared" ? n.role.toUpperCase() : n.generic ? "GENERIC" : "";
          return (
            <g key={n.id} class="node" tabIndex={0} opacity={dim ? 0.3 : 1} onMouseEnter={() => onFocus(n.id)} onMouseLeave={() => onFocus(null)}
              onFocus={() => onFocus(n.id)} onBlur={() => onFocus(null)} onClick={() => onOpen(n.id)}
              onKeyDown={e => e.key === "Enter" && onOpen(n.id)} aria-label={`${n.label}, ${n.degree} companies`}>
              {n.type === "ExposureDriver"
                ? <rect x={p.x - r} y={p.y - r} width={2 * r} height={2 * r} transform={`rotate(45 ${p.x} ${p.y})`} fill="var(--ground)"
                    stroke={fill} stroke-width="3" stroke-dasharray={n.generic ? "5 4" : null} />
                : <>{cross && <circle cx={p.x} cy={p.y} r={r + 6} fill="none" stroke="var(--ink-3)" stroke-width="2" />}
                    <circle cx={p.x} cy={p.y} r={r} fill={fill} /></>}
              <text x={p.x} y={y0} text-anchor="middle" font-size="21" font-weight="600" fill={n.generic ? "var(--ink-2)" : "var(--ink)"}
                paint-order="stroke" stroke="var(--ground)" stroke-width="7">
                {lines.map((l, k) => <tspan key={k} x={p.x} dy={k ? 24 : 0}>{l}</tspan>)}
              </text>
              {tag && <text x={p.x} y={below ? p.y - r - 12 : p.y + r + 24} text-anchor="middle" font-size="15" font-weight="700"
                letter-spacing="0.08em" fill="var(--ink-3)" paint-order="stroke" stroke="var(--ground)" stroke-width="6">{tag}</text>}
            </g>);
        })}
        {comps.map(n => {
          const p = pos[n.id], on = lit?.has(n.id), c = ind(n);
          return (
            <g key={n.id}>
              <rect x={p.x - 56} y={p.y - 22} width="112" height="44" rx="2" fill={on ? `var(--${c})` : "var(--ground)"}
                stroke={`var(--${c})`} stroke-width="2" opacity={lit && !on ? 0.35 : 1} />
              <text x={p.x} y={p.y + 7} text-anchor="middle" font-size="20" font-weight="700" font-stretch="112%"
                fill={on ? `var(--${c}-ink)` : "var(--ink)"} opacity={lit && !on ? 0.5 : 1}>{n.label}</text>
            </g>);
        })}
      </svg>
      {empty && <div class="empty"><b>{empty[0]}</b><span class="muted">{empty[1]}</span></div>}
    </div>
  );
}
