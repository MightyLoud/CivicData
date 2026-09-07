FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CIVICDATA_SERVICE_ENVIRONMENT=candidate \
    PORT=8080

WORKDIR /app

COPY requirements-hosted-runtime.txt /app/requirements-hosted-runtime.txt
RUN pip install --no-cache-dir -r /app/requirements-hosted-runtime.txt

COPY civic_gps_runtime_parts /app/civic_gps_runtime_parts
RUN cat /app/civic_gps_runtime_parts/part.* > /app/civic_gps_runtime.zip \
    && echo '32828535194b669f425f31dfcee6c986b139479b4d1317114461396022f5c797  /app/civic_gps_runtime.zip' | sha256sum --check --strict \
    && python -c "import zipfile; zipfile.ZipFile('/app/civic_gps_runtime.zip').extractall('/app')"

COPY civic_gps_extensions /app/civic_gps_extensions
COPY consumers /app/consumers
COPY tools /app/tools
COPY schemas /app/schemas
COPY data/packages/tx/legislative /app/data/packages/tx/legislative
COPY services /app/services

RUN useradd --create-home --uid 10001 civicdata \
    && chown -R civicdata:civicdata /app

USER civicdata
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/healthz', timeout=4).read()"

CMD ["sh", "-c", "exec uvicorn services.texas_bounded_api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
