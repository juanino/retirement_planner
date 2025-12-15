# Simple Makefile for retirement_planner

.PHONY: clean clean-dry run install

# Use local venv python if available
PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

install:
	$(PY) -m pip install -r requirements.txt

run:
	$(PY) retirement_planner.py --config config.yaml

clean:
	chmod +x clean_reports.sh
	NO_CONFIRM=1 ./clean_reports.sh --path $(PWD)

clean-dry:
	chmod +x clean_reports.sh
	./clean_reports.sh --dry-run --path $(PWD)
