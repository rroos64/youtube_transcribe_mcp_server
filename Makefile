PYTHON ?= python3
VENV ?= .venv
DATA_DIR ?= ./data
PORT ?= 8080
IMAGE ?= yt-dlp-transcriber:local

.PHONY: venv install run test docker-build docker-run clean

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install -r requirements.txt

run: install
	mkdir -p $(DATA_DIR)
	DATA_DIR=$(DATA_DIR) PORT=$(PORT) PYTHONPATH=src $(VENV)/bin/python -m yt_dlp_transcriber.server

test: install
	$(VENV)/bin/pip install -r requirements-dev.txt
	PYTHONPATH=src $(VENV)/bin/pytest

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	mkdir -p $(DATA_DIR)
	docker run --rm -p $(PORT):8080 \
		-v $(DATA_DIR):/data \
		-e PORT=8080 \
		$(IMAGE)

clean:
	rm -rf $(VENV)
