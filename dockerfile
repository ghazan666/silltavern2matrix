FROM python:3.13-slim

WORKDIR /sillytavern2matrix
COPY . /sillytavern2matrix

RUN apt-get update && apt-get install -y \
    make \
    cmake \
    build-essential \
    curl \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

LABEL name="sillytavern2matrix"
CMD ["python", "app.py"]
