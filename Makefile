# One-command entry points. Run from the repository root.
PY ?= python
PORT ?= 8000

.PHONY: demo demo-live check build-demo screenshots check-secrets test real-run estimate label record-help

demo: check build-demo            ## offline: no network, no Neo4j
	$(PY) serve.py --port $(PORT)

demo-live: check build-demo       ## also enables the one live step (plain-RAG ask, 20 s deadline)
	$(PY) serve.py --port $(PORT) --live

check:                            ## environment check before going on stage
	@$(PY) -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ needed'"
	@test -f results/demo_run/manifest.json || (echo "results/demo_run/ is missing: nothing to show (see README)"; exit 1)
	@test -f results/demo_run/graph.json || echo "note: results/demo_run/graph.json missing - screen 4 will say so"
	@$(PY) -c "import yaml, numpy, dotenv" || (echo "pip install -r requirements.txt"; exit 1)
	@echo "check: ok (offline mode needs nothing else)"

build-demo:
	$(PY) build_demo.py

screenshots: build-demo           ## PNG of every screen and state -> demo/fallback/
	$(PY) demo/screenshots.py

check-secrets:                    ## run before every commit
	@if command -v gitleaks >/dev/null 2>&1; then gitleaks detect --no-banner --source . ; fi
	$(PY) check_secrets.py

test:
	$(PY) -m pytest tests -q

estimate:
	$(PY) estimate_cost.py

real-run:                         ## spends money: prints the estimate and stops if it is over $$5
	$(PY) real_run.py $(ARGS)

label:                            ## hand-label the key in the browser
	$(PY) label_helper.py && $(PY) label_tool.py

record-help:
	@echo "Record the full run to MP4 (kept out of git): see REHEARSAL.md 'Recording'."
	@echo "Expected path: demo/fallback/demo_run.mp4"
