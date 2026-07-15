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

# uncomment if you want to use cookies for private content
# COPY cookies.txt .

ENV LIBRARY_DIR=/music
ENV DOWNLOAD_DIR=/data/downloads
ENV CONVERT_DIR=/data/conversions
ENV DB_PATH=/diwan-data/downloader.db

RUN mkdir -p /diwan-data /data/downloads /data/conversions /music

EXPOSE 4633

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4633", "--reload"]