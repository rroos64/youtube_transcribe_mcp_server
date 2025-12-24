PYTHON ?= python3
VENV ?= .venv
DATA_DIR ?= ./data
PORT ?= 8080
IMAGE ?= yt-dlp-transcriber:local

.PHONY: venv install run docker-build docker-run clean

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(VENV)/bin/pip install -r requirements.txt

run: install
	mkdir -p $(DATA_DIR)
	DATA_DIR=$(DATA_DIR) PORT=$(PORT) $(VENV)/bin/python server.py

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
