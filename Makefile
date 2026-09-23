PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: setup build site validate test fetch draft serve clean

setup:            ## one-time: venv + deps + Chromium
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium

build: validate   ## validate, then build every edition (pages + PDFs) into site/
	$(PY) build.py

site:             ## pages only, reuse existing PDFs
	$(PY) build.py --no-pdf

validate:         ## schema + publish rules for every data file
	$(PY) validate.py

test:
	$(PY) -m pytest -q

fetch:            ## first-print actuals from FRED/ALFRED -> out/actuals_<today>.csv
	$(PY) fetch_actuals.py

draft:            ## draft next edition from last week's file + FRED
	$(PY) draft_edition.py

serve:            ## preview site/ at http://localhost:8765
	$(PY) -m http.server 8765 --directory site

clean:
	rm -rf site .cache
