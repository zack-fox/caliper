PY ?= .venv/bin/python
PROJECT ?= fixtures/samples/project.yaml
PKG ?= fixtures/evidence/pkg-A01
ASSETS ?= fixtures/samples/asset_record.xlsx

.PHONY: setup setup-gui syntax lint contracts test check parse run explain lint-rules export assets ui-lint golden build

setup:
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev]"

setup-gui:
	$(PY) -m pip install -e ".[gui]"

syntax:
	$(PY) -m compileall -q core packs app adapters

lint:
	$(PY) -m core.contracts.selfcheck

contracts:
	$(PY) -m core.contracts.check --templates templates --pack packs/linux_os

test:
	$(PY) -m pytest -q

check: syntax lint contracts test

parse:
	$(PY) -m core.cli parse --pkg $(PKG)

run:
	$(PY) -m core.cli run --project $(PROJECT)

explain:
	$(PY) -m core.cli explain --project $(PROJECT) --item $(ITEM)

lint-rules:
	$(PY) -m core.cli lint-rules --pack packs/linux_os

export:
	$(PY) -m core.cli export --project $(PROJECT) --table $(TABLE)

assets:
	$(PY) -m core.cli export --project $(PROJECT) --table asset --assets $(ASSETS)

ui-lint:
	$(PY) -m app.theme.ui_lint

golden:
	$(PY) -m core.cli golden

build:
	$(PY) -m PyInstaller --noconfirm --onedir --windowed --name caliper app/main.py
