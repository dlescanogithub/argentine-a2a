# Hosting image for the local gate. Build does not publish a URL.
FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --shell /bin/sh --uid 10001 gate

COPY argentine ./argentine
COPY agent-card.json ./agent-card.json
COPY config ./config
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    ARGENTINE_BIND=0.0.0.0 \
    ARGENTINE_PORT=8080 \
    ARGENTINE_LOG_PATH=/data/gate-log.jsonl \
    ARGENTINE_DIEGO_OFF_FILE=/data/diego.off \
    ARGENTINE_STDOUT_LOG=1 \
    ARGENTINE_LOG_MAX_BYTES=5242880 \
    ARGENTINE_LOG_BACKUPS=3 \
    ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-m", "argentine", "serve"]
