FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CLAW_PARSER_STATE_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --upgrade pip wheel \
    && pip install .

RUN useradd --system --uid 10001 --gid 0 --home-dir /data claw \
    && mkdir -p /data \
    && chown -R 10001:0 /data

USER 10001

ENTRYPOINT ["claw-parser"]
CMD ["serve"]
