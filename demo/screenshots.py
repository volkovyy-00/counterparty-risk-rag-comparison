"""Save a PNG of every screen and governance state (visual fallback), and check the page.

    python demo/screenshots.py                   # demo/index.html via serve.py -> demo/fallback/*.png
    python demo/screenshots.py --html FILE --out DIR

Headless Chromium through Playwright, 1920x1080 (dark theme under dark/). Fails if the page logs a console
error, if any screen overflows (needs scrolling), or if text is clipped with an ellipsis, at 1920x1080 or
1280x720, in the light and the dark theme.
"""
import argparse
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402

STATES = [
    ("01_question", "screen=1"), ("02_data_quality", "screen=2"), ("03_plain_rag", "screen=3"),
    ("03b_plain_rag_quote", "screen=3&claim=1"),
    ("04_graph_qa", "screen=4"), ("04q1_gm_nxpi", "screen=4&qa=gm_nxpi"), ("04q3_bridge", "screen=4&qa=bridge"),
    ("04q3c_bridge_full_cypher", "screen=4&qa=bridge&cypher=1"), ("04q3d_bridge_quotes", "screen=4&qa=bridge&risk=1"),
    ("04q4_more", "screen=4&qa=tsla_on_txn"), ("04q4b_more_five", "screen=4&qa=five"),
    ("04q5_quotes", "screen=4&qa=gm_nxpi&risk=1"),
    ("04e_overview", "screen=4&overview=1"), ("04b_graphrag_hide_generic", "screen=4&overview=1&hide=1"),
    ("04c_graphrag_drivers", "screen=4&overview=1&hide=1&drivers=1"), ("04d_graphrag_quotes", "screen=4&overview=1&risk=1"),
    ("05_taxonomy_category", "screen=5"), ("05b_taxonomy_leaf", "screen=5&leaf=1"),
    ("05c_taxonomy_quote_panel", "screen=5&leaf=1&cell=1"), ("05d_other_driver", "screen=5&driver=1"),
    ("06_scorecard", "screen=6"), ("07_decision", "screen=7"),
    ("G0_governance", "screen=G"), ("G1_fabricated_quote", "screen=G&gov=fabricated"),
    ("G2_off_taxonomy", "screen=G&gov=fabricated,offtaxonomy"),
    ("G3_audit_trail", "screen=G&gov=fabricated,offtaxonomy,audit"),
    ("T_timer_overlay", "screen=3&timer=130"), ("D_dark_theme", "screen=5&theme=dark"),
]
CHROMIUM = "/opt/pw-browsers/chromium"


def capture(base_url, out_dir, check_sizes=((1920, 1080), (1280, 720)), themes=("light", "dark")):
    """Every state at every size and theme is checked; PNGs at 1920x1080 (dark ones under dark/)."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    errors, overflow, saved = [], [], []
    with sync_playwright() as p:
        kwargs = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
        browser = p.chromium.launch(**kwargs)
        for (w, h), theme in [(size, t) for size in check_sizes for t in themes]:
            page = browser.new_page(viewport={"width": w, "height": h})
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            for name, query in STATES:
                sep = "&" if "?" in base_url else "?"
                tq = "&theme=dark" if theme == "dark" and "theme=" not in query else ""
                page.goto(f"{base_url}{sep}{query}{tq}")
                page.wait_for_selector("body[data-ready='1']", timeout=15000)
                page.wait_for_timeout(250)
                over = page.evaluate("""() => { const s = document.getElementById('screen');
                    const st = document.getElementById('stage').getBoundingClientRect();
                    return {scroll: s.scrollHeight > s.clientHeight + 2 || s.scrollWidth > s.clientWidth + 2,
                            page: document.documentElement.scrollHeight > innerHeight + 1 ||
                                  document.documentElement.scrollWidth > innerWidth + 1,
                            fits: st.width <= innerWidth + 1 && st.height <= innerHeight + 1}; }""")
                if over["scroll"] or over["page"] or not over["fits"]:
                    overflow.append(f"{name} at {w}x{h} {theme}: {over}")
                clipped = page.evaluate("""() => [...document.querySelectorAll('#screen *')].filter(e => {
                    const cs = getComputedStyle(e); return cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1;
                    }).map(e => e.textContent.slice(0, 60))""")
                if clipped:
                    overflow.append(f"{name} at {w}x{h} {theme}: text clipped with an ellipsis: {clipped[:3]}")
                if (w, h) == (1920, 1080):
                    path = out_dir / ("dark" if theme == "dark" else "") / f"{name}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(path))
                    saved.append(path)
            page.close()
        browser.close()
    return saved, errors, overflow


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html", help="a built page to open as a file (no server; governance uses the precomputed copy)")
    parser.add_argument("--out", default=str(config.ROOT / "demo" / "fallback"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.html:
        base = Path(args.html).resolve().as_uri()
    else:
        import serve

        if not (config.ROOT / "demo" / "index.html").exists():
            raise SystemExit("demo/index.html missing - run build_demo.py first")
        server = serve.serve(args.port, live=False, open_browser=False)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://localhost:{args.port}/index.html"
    saved, errors, overflow = capture(base, Path(args.out))
    print(f"{len(saved)} screenshots -> {args.out}")
    for e in errors:
        print("CONSOLE ERROR:", e)
    for o in overflow:
        print("OVERFLOW:", o)
    os._exit(1 if errors or overflow else 0)


if __name__ == "__main__":
    main()
