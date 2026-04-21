FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY disease-detection /app/disease-detection

RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000 8501
