PY ?= .venv/bin/python
PROJECT ?= fixtures/samples/project.yaml
PKG ?= fixtures/evidence/pkg-A01
PACK ?= packs/linux_os
ASSETS ?= fixtures/samples/asset_record.xlsx
OUT ?=
FAMILY ?= server
LEVEL ?= 3

.PHONY: setup setup-gui syntax lint library-lint contracts test check parse run explain lint-rules export assets ui-lint golden capture records build package-macos

setup:
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev]"

setup-gui:
	$(PY) -m pip install -e ".[gui]"

syntax:
	$(PY) -m compileall -q core packs app adapters tools

lint:
	$(PY) -m core.contracts.selfcheck

library-lint:
	$(PY) -m core.cli lint-library --pack packs/linux_os

contracts:
	$(PY) -m core.contracts.check --templates templates --pack packs/linux_os

test:
	$(PY) -m pytest -q

check: syntax lint library-lint contracts test

parse:
	$(PY) -m core.cli parse --pkg $(PKG) --pack $(PACK)

capture:
	$(PY) -m core.cli capture --pack packs/linux_os --family $(FAMILY) --level $(LEVEL)

records:
	$(PY) -m core.cli records --project $(PROJECT) $(if $(OUT),--out $(OUT),)

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

build: package-macos

# 在当前 macOS 架构构建自包含应用包；交付物不依赖接收方的 Python 或 .venv。
# PyInstaller 产物随带规则包和 Excel 母版；项目数据保存在用户目录。
package-macos:
	$(PY) -m pip install -e ".[gui,build]"
	$(PY) -m PyInstaller --noconfirm --clean packaging/Caliper.spec
	ditto -c -k --sequesterRsrc --keepParent dist/Caliper.app dist/Caliper-macos-$$(uname -m).zip
