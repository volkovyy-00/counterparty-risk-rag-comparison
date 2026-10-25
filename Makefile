# One-command entry points. Run from the repository root.
PY ?= python
PORT ?= 8000

.PHONY: demo demo-live check build-demo screenshots check-secrets test real-run estimate label record-help \
	graph-quality graph-check graph-ab graph-qa taxo-split taxo-coverage taxo-ab

demo: check build-demo            ## offline: no network, no Neo4j
	$(PY) src/serve.py --port $(PORT)

demo-live: check build-demo       ## also enables the one live step (plain-RAG ask, 20 s deadline)
	$(PY) src/serve.py --port $(PORT) --live

check:                            ## environment check before going on stage
	@$(PY) -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ needed'"
	@test -f results/demo_run/manifest.json || (echo "results/demo_run/ is missing: nothing to show (see README)"; exit 1)
	@test -f results/demo_run/graph.json || echo "note: results/demo_run/graph.json missing - screen 4 will say so"
	@$(PY) -c "import yaml, numpy, dotenv" || (echo "pip install -r requirements.txt"; exit 1)
	@echo "check: ok (offline mode needs nothing else)"

build-demo:
	$(PY) src/build_demo.py

screenshots: build-demo           ## PNG of every screen and state -> demo/fallback/
	$(PY) demo/screenshots.py

check-secrets:                    ## run before every commit
	@if command -v gitleaks >/dev/null 2>&1; then gitleaks detect --no-banner --source . ; fi
	$(PY) src/check_secrets.py

test:
	$(PY) -m pytest tests -q

estimate:
	$(PY) src/estimate_cost.py

real-run:                         ## spends money: ARGS="--stage core|extras [--confirm-usd N]"; prints the stage estimate and stops without both gates
	$(PY) src/real_run.py $(ARGS)

graph-qa:                         ## spends money: screen-4 graph questions from Neo4j; stops unless ARGS="--confirm-usd N"
	$(PY) src/graph_qa.py $(ARGS)

graph-quality:                    ## approach 2 graph metrics from the build files (no Neo4j, no model call)
	$(PY) src/graph_quality.py

graph-check:                      ## approach 2 hand-check CSV: 30 mentions + 20 merge decisions, fill in y/n
	$(PY) src/graph_check.py

graph-ab:                         ## spends money: graph A/B (v1 vs v2) on 3 filings; stops unless ARGS="--confirm-usd N"
	$(PY) src/graph_ab.py $(ARGS)

taxo-split:                       ## approach 3 risk-factor split per filing (no model call)
	$(PY) src/approach3_taxonomy.py split-report

taxo-coverage:                    ## does the taxonomy cover the group's drivers? (no model call)
	$(PY) src/taxonomy_coverage.py

taxo-ab:                          ## spends money: approach 3 A/B (v2.0 fixed vs v3.0 heading) on NXPI, LEA; stops unless ARGS="--confirm-usd N"
	$(PY) src/taxonomy_ab.py $(ARGS)

label:                            ## hand-label the key in the browser
	$(PY) src/label_helper.py && $(PY) src/label_tool.py

record-help:
	@echo "Record the full run to MP4 (kept out of git): see docs/REHEARSAL.md 'Recording'."
	@echo "Expected path: demo/fallback/demo_run.mp4"
