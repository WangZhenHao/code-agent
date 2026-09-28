
FROM --platform=$BUILDPLATFORM golang:1.26.5 AS sandboxd


RUN apt-get update \
  && apt-get install -y --no-install-recommends util-linux \
    ca-certificates \
    curl \
    unzip \
    procps \
    git \
    python3 \
    build-essential \
    dumb-init \
  && rm -rf /var/lib/apt/lists/*

EXPOSE 8080 9090
