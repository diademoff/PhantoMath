# Сборка PhantoMath: Flutter-приложение со встроенным Python-решателем.
#
# Цели:
#   make help            — этот список
#   make icon            — launcher-иконки из app/logo.png
#   make python-bundle   — упаковать решатель (sympy + mymath_backend) для Android
#   make apk             — собрать release APK с встроенным Python
#   make backend         — поднять FastAPI-бэкенд (для разработки, хост)
#   make run             — запустить приложение на подключённом устройстве
#   make test / lint     — тесты и проверки (backend + app)
#   make device          — запустить локальный сервер решателя (как на устройстве)
#   make site            — собрать сайт для GitHub Pages в build/site
#   make clean           — убрать сборочные артефакты

SHELL := /bin/bash
ROOT := $(CURDIR)
PYTHON ?= python3
UV ?= uv
FLUTTER ?= flutter

# Flutter SDK кладём в PATH: dart и flutter лежат рядом.
FLUTTER_BIN := $(HOME)/.local/share/flutter/bin
export PATH := $(FLUTTER_BIN):$(PATH)

# serious_python: версия CPython для обеих фаз (пакеты и сборка APK).
export SERIOUS_PYTHON_VERSION ?= 3.12
# Куда serious_python складывает установленные пакеты и приложение.
SERIOUS_PYTHON_SITE_PACKAGES := $(ROOT)/app/build/site-packages
SERIOUS_PYTHON_APP := $(ROOT)/app/build/python-app
export SERIOUS_PYTHON_SITE_PACKAGES
export SERIOUS_PYTHON_APP

# Порт локального сервера решателя (совпадает с app/lib/src/api/embedded_backend.dart).
PORT ?= 8770

APK_DIR := app/build/app/outputs/flutter-apk
APK := $(APK_DIR)/app-release.apk

.DEFAULT_GOAL := help

.PHONY: help icon python-bundle apk backend run device test lint audit cards site clean

help:
	@echo "make icon          — launcher-иконки из app/logo.png"
	@echo "make python-bundle — собрать Python-решатель для устройства"
	@echo "make apk           — release APK со встроенным Python"
	@echo "make backend       — FastAPI-бэкенд на хосте (порт 8000)"
	@echo "make device        — локальный сервер решателя (порт $(PORT))"
	@echo "make run           — запустить на устройстве/эмуляторе"
	@echo "make test          — тесты backend и app"
	@echo "make lint          — ruff, mypy, flutter analyze"
	@echo "make audit         — все формулы ответов через TeX-парсер приложения"
	@echo "make cards         — карточки решения текстом и раскладкой (TASKS=… OUT=…)"
	@echo "make site          — сайт для GitHub Pages в build/site"
	@echo "make clean         — очистить сборку"

icon:
	cd app && $(FLUTTER) pub get && dart run flutter_launcher_icons

# Копирует решатель (со словарём пояснений) в app/python и упаковывает его вместе с sympy.
python-bundle:
	rm -rf app/python/mymath_backend
	cp -r backend/mymath_backend app/python/mymath_backend
	find app/python/mymath_backend -name '__pycache__' -type d -prune -exec rm -rf {} +
	cd app && $(FLUTTER) pub get
	cd app && dart run serious_python:main package python -p Android -r 'sympy>=1.14' \
		--cleanup \
		--cleanup-package-files '**/tests' \
		--cleanup-package-files '**/benchmarks' \
		--cleanup-package-files '**.md'

apk: python-bundle
	cd app && $(FLUTTER) build apk --release
	@echo "APK: $(APK)"

backend:
	cd backend && $(UV) run uvicorn mymath_backend.api:app --host 0.0.0.0 --port 8000 --reload

device:
	cd backend && MYMATH_PORT=$(PORT) \
		$(UV) run python -m mymath_backend.device

run:
	cd app && $(FLUTTER) run

test:
	cd backend && $(UV) run pytest
	cd app && $(FLUTTER) test

# Все формулы ответов решателя через настоящий TeX-парсер приложения.
audit:
	backend/.venv/bin/python tools/audit/dump_contracts.py build/contracts.json
	cd app && CONTRACTS=$(ROOT)/build/contracts.json $(FLUTTER) test test/formula_audit_test.dart

# Карточки решения без телефона: текст (transcript) и раскладка на Pixel 4a.
#   make cards TASKS=backend/tests/inputs.json OUT=build/cards
cards:
	@test -n "$(TASKS)" -a -n "$(OUT)" || { echo "usage: make cards TASKS=TASKS.json OUT=DIR"; exit 2; }
	mkdir -p $(OUT)
	backend/.venv/bin/python tools/audit/dump_cards.py $(TASKS) $(OUT)/cards.json
	cd app && CARDS=$(abspath $(OUT))/cards.json CARDS_OUT=$(abspath $(OUT)) \
		$(FLUTTER) test test/card_transcript_test.dart test/card_layout_test.dart

lint:
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy mymath_backend
	cd app && $(FLUTTER) analyze

# Сайт-визитка: site/ + скриншоты и логотип из репозитория (не дублируем их в site/).
#   просмотр: make site && python3 -m http.server -d build/site
site:
	rm -rf build/site
	mkdir -p build
	cp -r site build/site
	cp -r docs/screenshots build/site/screenshots
	cp app/logo.png build/site/logo.png

clean:
	cd app && $(FLUTTER) clean
	rm -rf app/python/mymath_backend
