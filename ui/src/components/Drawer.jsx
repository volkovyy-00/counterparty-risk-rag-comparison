import { useEffect, useRef } from "preact/hooks";
import { X, ExternalLink, FileText, ArrowLeft } from "lucide-preact";
import { NAMES, catName, context, edgarLink, filing, fullText, industry, leafName } from "../lib/data.js";
import { useApp } from "../store.js";

// Quote drawer: every claim with its sentence highlighted in the company's own Item 1A, plus EDGAR and a local copy.
export function Drawer() {
  const { S, set } = useApp(), d = S.drawer, ref = useRef();
  useEffect(() => { if (d) ref.current?.focus(); }, [d]);
  return (
    <>
      <div class={`scrim ${d ? "open" : ""}`} onClick={() => set({ drawer: null })} />
      <aside class={`drawer ${d ? "open" : ""}`} aria-hidden={!d} aria-label="Quotes">
        {d && <>
          <header>
            <h2 tabIndex={-1} ref={ref}>{d.title}
              <div class="sub">{NAMES[d.approach] || d.approach} · {d.claims.length} verified claim{d.claims.length === 1 ? "" : "s"} · each quote located verbatim in the company's own Item 1A</div>
            </h2>
            <button class="btn ghost" onClick={() => set({ drawer: null })} aria-label="Close"><X /> <span class="kbd">Esc</span></button>
          </header>
          <div class="body">
            {d.claims.map((c, i) => <Claim key={i} c={c} onFull={() => set({ full: c })} />)}
          </div>
        </>}
      </aside>
      {S.full && <FullText c={S.full} onBack={() => set({ full: null })} />}
    </>
  );
}

function Claim({ c, onFull }) {
  const f = filing(c.company), x = context(c), url = edgarLink(c);
  return (
    <div class="claim">
      <div class="who">
        <span class={`tk ${industry(c.company)}`}>{c.company}</span>
        <b>{leafName(c.leaf)}</b>
        {String(c.leaf).includes(".") && <span class="xs dim">{catName(c.leaf.split(".")[0])}</span>}
        {c.secondary && <span class="xs dim">second label</span>}
      </div>
      {c.driver && <div class="small">Driver: <b>{c.driver}</b> <span class="dim">(shown, not scored)</span></div>}
      <div class="src">10-K {f.accession} · Item 1A characters {c.start}–{c.end}{c.source_ref ? ` · ${c.source_ref}` : ""}{c.fallback ? " · label from keyword fallback" : ""}</div>
      <div class="ctx">{x.before}<mark>{x.hit}</mark>{x.after}</div>
      <div class="links">
        {url && <a href={url} target="_blank" rel="noopener"><ExternalLink size="0.9em" /> SEC EDGAR at this quote</a>}
        {c.start != null && <a href="#" onClick={e => { e.preventDefault(); onFull(); }}><FileText size="0.9em" /> Full Item 1A (local copy)</a>}
      </div>
    </div>
  );
}

function FullText({ c, onBack }) {
  const t = fullText(c), hit = useRef();
  useEffect(() => { hit.current?.scrollIntoView({ block: "center" }); }, [c]);
  return (
    <div class="full" role="dialog" aria-label={`${c.company} Item 1A`}>
      <div class="bar"><button class="btn" onClick={onBack}><ArrowLeft /> Back <span class="kbd">Esc</span></button>
        <h2>{filing(c.company).short_name || c.company} · Item 1A Risk Factors (local copy)</h2></div>
      {t.before}<mark ref={hit}>{t.hit}</mark>{t.after}
    </div>
  );
}
