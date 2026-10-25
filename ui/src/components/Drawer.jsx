import { useEffect, useRef } from "preact/hooks";
import { X, ExternalLink, FileText, ArrowLeft } from "lucide-preact";
import { NAMES, catName, context, edgarLink, filing, fullText, industry, leafName } from "../lib/data.js";
import { useApp } from "../store.js";

function Shell({ open, cls = "", title, sub, onClose, children }) {
  const ref = useRef();
  useEffect(() => { if (open) ref.current?.focus(); }, [open, title]);
  return (
    <aside class={`drawer ${cls} ${open ? "open" : ""}`} aria-hidden={!open}>
      {open && <>
        <header>
          <h2 tabIndex={-1} ref={ref}>{title}{sub && <div class="sub">{sub}</div>}</h2>
          <button class="btn" onClick={onClose} aria-label="Close"><X /> <span class="kbd">Esc</span></button>
        </header>
        <div class="body">{children}</div>
      </>}
    </aside>
  );
}

// Quote drawer: every claim with its sentence highlighted in the company's own Item 1A, plus EDGAR and a local copy.
export function Drawers({ detail }) {
  const { S, set } = useApp(), d = S.drawer;
  return (
    <>
      <div class={`scrim ${d || (S.detail && detail) ? "open" : ""}`} onClick={() => set({ drawer: null, detail: false })} />
      <Shell open={!!d} title={d?.title} onClose={() => set({ drawer: null })}
        sub={d && `${NAMES[d.approach] || d.approach} · ${d.claims.length} verified claim${d.claims.length === 1 ? "" : "s"} · each quote located verbatim in the company's own Item 1A`}>
        {d?.claims.map((c, i) => <Claim key={i} c={c} onFull={() => set({ full: c })} />)}
      </Shell>
      <Shell open={!d && S.detail && !!detail} cls="detail" title="Details" sub="What the speaker does not point at: the machinery behind this screen."
        onClose={() => set({ detail: false })}>{detail}</Shell>
      {S.full && <FullText c={S.full} onBack={() => set({ full: null })} />}
    </>
  );
}

function Claim({ c, onFull }) {
  const f = filing(c.company), x = context(c, 360), url = edgarLink(c), hit = useRef();
  useEffect(() => { const el = hit.current, box = el?.closest(".ctx"); if (box) box.scrollTop = el.offsetTop - box.offsetTop - box.clientHeight / 3; }, [c]);
  return (
    <div class="claim">
      <div class="who">
        <span class={`tk ${industry(c.company)}`}>{c.company}</span>
        <b>{leafName(c.leaf)}</b>
        {String(c.leaf).includes(".") && <span class="meta">{catName(c.leaf.split(".")[0])}</span>}
      </div>
      {c.driver && <div class="meta">Driver: {c.driver} (shown, not scored)</div>}
      <div class="src">10-K {f.accession} · Item 1A chars {c.start}–{c.end}{c.source_ref ? ` · ${c.source_ref}` : ""}</div>
      <div class="ctx">{x.before}<mark ref={hit}>{x.hit}</mark>{x.after}</div>
      <div class="links">
        {url && <a href={url} target="_blank" rel="noopener"><ExternalLink /> SEC EDGAR at this quote</a>}
        {c.start != null && <a href="#" onClick={e => { e.preventDefault(); onFull(); }}><FileText /> Full Item 1A</a>}
      </div>
    </div>
  );
}

function FullText({ c, onBack }) {
  const t = fullText(c), hit = useRef();
  useEffect(() => { hit.current?.scrollIntoView({ block: "center" }); }, [c]);
  return (
    <div class="full" role="dialog" aria-label={`${c.company} Item 1A`}>
      <div class="bar"><button class="btn big" onClick={onBack}><ArrowLeft /> Back <span class="kbd">Esc</span></button>
        <h2>{filing(c.company).short_name || c.company} · Item 1A Risk Factors</h2></div>
      {t.before}<mark ref={hit}>{t.hit}</mark>{t.after}
    </div>
  );
}
