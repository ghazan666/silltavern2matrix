FROM python:3.13-slim

WORKDIR /sillytavern2matrix
COPY . /sillytavern2matrix

ARG NODE_VERSION=24.12.0
ENV PATH=/usr/local/lib/nodejs/node-v${NODE_VERSION}-linux-x64/bin:$PATH

RUN apt-get update && apt-get install -y \
    make \
    cmake \
    build-essential \
    curl \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz \
    && mkdir -p /usr/local/lib/nodejs \
    && tar -xJf /tmp/node.tar.xz -C /usr/local/lib/nodejs \
    && rm /tmp/node.tar.xz

RUN npm install
RUN pip install --no-cache-dir -r requirements.txt

LABEL name="sillytavern2matrix"
CMD ["python", "app.py"]
