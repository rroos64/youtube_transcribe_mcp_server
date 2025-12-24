FROM python:3.12-slim

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl nodejs \
  && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux \
    -o /usr/local/bin/yt-dlp \
 && chmod +x /usr/local/bin/yt-dlp

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py

ENV PORT=8080
ENV DATA_DIR=/data
EXPOSE 8080

CMD ["python", "/app/server.py"]

