.PHONY: build tag push publish test localdocker lint format check fix dev dev-prod seed seed-if-empty

TAG ?= latest

dev:
	uv run python manage.py migrate
	uv run python manage.py seed_demo --if-empty
	uv run honcho start

dev-prod: export DJANGO_DB_PATH = $(PWD)/prod-db.sqlite3
dev-prod: export CALIBRE_ROOT = $(HOME)/books/calibre-all
dev-prod:
	uv run python manage.py migrate
	uv run python manage.py refresh_calibre
	uv run honcho start -f Procfile.web

seed:
	uv run python manage.py seed_demo --force-config

seed-if-empty:
	uv run python manage.py seed_demo --if-empty

build:
	docker build -t cookmarks .

tag:
	docker tag cookmarks ghcr.io/elgrove/cookmarks:$(TAG)

push:
	docker push ghcr.io/elgrove/cookmarks:$(TAG)

publish: build tag push

test:
	uv run pytest

localdocker:
	sudo docker compose -f docker-compose.local.yml up -d

format:
	uv run ruff format .

fix:
	-uv run ruff check --fix .
	uv run ruff format .
