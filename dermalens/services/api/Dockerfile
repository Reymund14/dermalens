# Build from the repository root:  docker build -f services/api/Dockerfile .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY services/inference/requirements.txt services/inference/requirements.txt
COPY services/api/requirements.txt services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt
COPY packages/rules packages/rules
COPY services/inference services/inference
COPY services/api services/api
ENV PYTHONPATH=/srv/packages/rules:/srv/services/inference:/srv/services/api
WORKDIR /srv/services/api
EXPOSE 8000
CMD ["sh", "start.sh"]
