"""The console's in-browser live mode (ui/src/lib/browserLive.js) against the Python pipeline it ports.

Same rows for every graph pattern, the same answer prompt byte for byte, the same subgraph, and the same quote
offsets from the verifier. Needs Node and a built data.json; skipped without them. No model call.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "ui" / "public" / "data.json"


@pytest.mark.skipif(not shutil.which("node") or not DATA.exists(), reason="needs node and ui/public/data.json")
def test_browser_port_matches_the_python_pipeline(tmp_path):
    import graph_local
    import graph_parity
    import graph_qa
    from corpus import load_corpus

    g, filings, data = graph_local.load(), load_corpus(), json.loads(DATA.read_text())
    cases = graph_parity.CASES + [("WHO_FACES", {"risks": ["Cybersecurity breach of information systems"]})]
    out = {"patterns": [], "quotes": [c for q in data["graph_qa"]["questions"] for c in q.get("claims") or []]}
    for name, params in cases:
        rows = graph_local.rows_for(g, name, params)
        out["patterns"].append({"t": name, "p": params, "rows": graph_parity.norm(rows),
                                "prompt": graph_qa.prompt({"question": "Q?"}, rows, filings)[0],
                                "sub": graph_qa.to_subgraph(rows, filings)})
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(out))
    res = subprocess.run(["node", str(ROOT / "tests" / "browser_parity.mjs"), str(ROOT), str(path), str(DATA)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout.strip().splitlines()[-1]) == []
