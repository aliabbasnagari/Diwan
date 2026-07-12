FROM python:3.12-slim

# ffmpeg is required by yt-dlp for merging video+audio and audio extraction
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Persisted at runtime via volumes (see docker-compose.yml)
ENV DOWNLOAD_DIR=/data/downloads
ENV DB_PATH=/data/downloader.db
RUN mkdir -p /data/downloads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
