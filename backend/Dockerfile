FROM python:3.12-slim

# Install dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/install.sh | sh

# Add Deno to PATH
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY cookies.txt .

ENV DOWNLOAD_DIR=/data/downloads
ENV LIBRARY_DIR=/music
ENV CONVERT_DIR=/data/conversions
ENV DB_PATH=/data/downloader.db

RUN mkdir -p /data/downloads /data/conversions /music

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]