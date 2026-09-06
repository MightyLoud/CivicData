FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CIVICDATA_SERVICE_ENVIRONMENT=candidate

WORKDIR /app

COPY requirements-hosted-runtime.txt /app/requirements-hosted-runtime.txt
RUN pip install --no-cache-dir -r /app/requirements-hosted-runtime.txt

COPY civic_gps_runtime_parts /app/civic_gps_runtime_parts
RUN cat /app/civic_gps_runtime_parts/part.* > /app/civic_gps_runtime.zip \
    && echo '1969e0e6760bdf4e479bd01fa6976f2ea25dd5fdc14e53d0f4b861cde97549ba  /app/civic_gps_runtime.zip' | sha256sum --check --strict \
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
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).read()"

CMD ["uvicorn", "services.texas_bounded_api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
