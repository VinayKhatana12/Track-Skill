FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Production image: runtime dependencies only (dev/test tools live in CI).
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# start.sh applies migrations + the idempotent seed, then serves on $PORT.
RUN chmod +x start.sh     && useradd --create-home appuser     && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["bash", "start.sh"]
