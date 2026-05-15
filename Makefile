.PHONY: build build-frontend tag push publish test localdocker lint format check fix dev dev-prod seed seed-if-empty frontend-install frontend-build

TAG ?= latest

frontend-install:
	npm --prefix frontend install

dev: frontend-install
	uv run python manage.py migrate
	uv run python manage.py seed_demo --if-empty
	uv run honcho start

dev-prod: export DJANGO_DB_PATH = $(PWD)/prod-db.sqlite3
dev-prod: export CALIBRE_ROOT = $(HOME)/books/calibre-all
dev-prod: frontend-install
	uv run python manage.py migrate
	uv run python manage.py refresh_calibre
	uv run honcho start -f Procfile.web

frontend-build:
	npm --prefix frontend ci
	npm --prefix frontend run build

seed:
	uv run python manage.py seed_demo --force-config

seed-if-empty:
	uv run python manage.py seed_demo --if-empty

build:
	docker build -t cookmarks .

build-frontend:
	docker build -t cookmarks-frontend ./frontend

tag:
	docker tag cookmarks ghcr.io/elgrove/cookmarks:$(TAG)
	docker tag cookmarks-frontend ghcr.io/elgrove/cookmarks-frontend:$(TAG)

push:
	docker push ghcr.io/elgrove/cookmarks:$(TAG)
	docker push ghcr.io/elgrove/cookmarks-frontend:$(TAG)

publish: build build-frontend tag push

test:
	uv run pytest

localdocker:
	sudo docker compose -f docker-compose.local.yml up -d

format:
	uv run ruff format .

fix:
	-uv run ruff check --fix .
	uv run ruff format .
