# Build from the repository root:  docker build -f services/inference/Dockerfile .
FROM python:3.12-slim
WORKDIR /srv
COPY services/inference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/inference .
EXPOSE 8001
CMD ["uvicorn", "dermalens_inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
