FROM python:3.12-slim

# ffmpeg is required by yt-dlp for merging video+audio and audio extraction
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Persisted at runtime via volumes (see docker-compose.yml).
# DOWNLOAD_DIR is scratch space for in-progress/video downloads.
# LIBRARY_DIR should point at the same folder Navidrome scans.
ENV DOWNLOAD_DIR=/data/downloads
ENV LIBRARY_DIR=/music
ENV DB_PATH=/data/downloader.db
RUN mkdir -p /data/downloads /music

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
