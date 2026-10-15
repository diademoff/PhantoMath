# Сборка mymath: Flutter-приложение со встроенным Python-решателем и раздача.
#
# Цели:
#   make help            — этот список
#   make icon            — launcher-иконки из app/logo.png
#   make python-bundle   — упаковать решатель (sympy + mymath_backend) для Android
#   make apk             — собрать release APK с встроенным Python
#   make serve           — раздать APK по tailnet (статика на tailnet-IP)
#   make backend         — поднять FastAPI-бэкенд (для разработки, хост)
#   make run             — запустить приложение на подключённом устройстве
#   make test / lint     — тесты и проверки (backend + app)
#   make device          — запустить локальный сервер решателя (как на устройстве)
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
# Порт раздачи APK в tailnet.
SERVE_PORT ?= 8090

APK_DIR := app/build/app/outputs/flutter-apk
APK := $(APK_DIR)/app-release.apk
EXPLANATIONS := truth/data/explanations.json

.DEFAULT_GOAL := help

.PHONY: help icon python-bundle apk serve backend run device test lint clean

help:
	@echo "make icon          — launcher-иконки из app/logo.png"
	@echo "make python-bundle — собрать Python-решатель для устройства"
	@echo "make apk           — release APK со встроенным Python"
	@echo "make serve         — раздать APK по tailnet (порт $(SERVE_PORT))"
	@echo "make backend       — FastAPI-бэкенд на хосте (порт 8000)"
	@echo "make device        — локальный сервер решателя (порт $(PORT))"
	@echo "make run           — запустить на устройстве/эмуляторе"
	@echo "make test          — тесты backend и app"
	@echo "make lint          — ruff, mypy, flutter analyze"
	@echo "make clean         — очистить сборку"

icon:
	cd app && $(FLUTTER) pub get && dart run flutter_launcher_icons

# Копирует решатель и словарь в app/python и упаковывает их вместе с sympy.
python-bundle:
	rm -rf app/python/mymath_backend app/python/assets
	mkdir -p app/python/assets
	cp -r backend/mymath_backend app/python/mymath_backend
	find app/python/mymath_backend -name '__pycache__' -type d -prune -exec rm -rf {} +
	cp $(EXPLANATIONS) app/python/assets/explanations.json
	cd app && $(FLUTTER) pub get
	cd app && dart run serious_python:main package python -p Android -r 'sympy>=1.14' \
		--cleanup \
		--cleanup-package-files '**/tests' \
		--cleanup-package-files '**/benchmarks' \
		--cleanup-package-files '**.md'

apk: python-bundle
	cd app && $(FLUTTER) build apk --release
	@echo "APK: $(APK)"

serve: apk
	@IP=$$(tailscale ip -4 | head -n1); \
		echo "APK:     $(APK)"; \
		echo "Tailnet: http://$$IP:$(SERVE_PORT)/$$(basename $(APK))"; \
		echo "Ставьте APK по этой ссылке с телефона в tailnet."; \
		$(PYTHON) -m http.server $(SERVE_PORT) --bind 0.0.0.0 --directory $(APK_DIR)

backend:
	cd backend && $(UV) run uvicorn mymath_backend.api:app --host 0.0.0.0 --port 8000 --reload

device:
	cd backend && MYMATH_EXPLANATIONS=$(ROOT)/$(EXPLANATIONS) MYMATH_PORT=$(PORT) \
		$(UV) run python -m mymath_backend.device

run:
	cd app && $(FLUTTER) run

test:
	cd backend && $(UV) run pytest
	cd app && $(FLUTTER) test

lint:
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy mymath_backend
	cd app && $(FLUTTER) analyze

clean:
	cd app && $(FLUTTER) clean
	rm -rf app/python/mymath_backend app/python/assets
