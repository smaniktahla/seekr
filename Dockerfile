FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils antiword catdoc unrtf ffmpeg libimage-exiftool-perl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 ARCHIVE_DB=/data/archive.sqlite
CMD ["python", "start.py"]
