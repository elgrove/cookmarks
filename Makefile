.PHONY: build tag push publish test localdocker lint format check fix

TAG ?= latest

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
