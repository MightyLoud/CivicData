FROM python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock
RUN git clone https://github.com/MightyLoud/CivicData.git /app/CivicData && git -C /app/CivicData checkout --detach e9c11f26c0cec8acd409d92f4d4867b5ee5715f7
COPY hosted_candidate.py /app/hosted_candidate.py
RUN useradd --create-home --uid 10001 civic
ENV CIVICDATA_REPO_ROOT=/app/CivicData PORT=8080 PYTHONDONTWRITEBYTECODE=1
RUN git config --system --add safe.directory /app/CivicData
USER civic
EXPOSE 8080
CMD ["python", "/app/hosted_candidate.py"]
