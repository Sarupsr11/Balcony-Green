# --------------------------------------------------
# Base image
# --------------------------------------------------
FROM python:3.11-slim

# --------------------------------------------------
# Set working directory
# --------------------------------------------------
WORKDIR /app

# --------------------------------------------------
# Install system dependencies
# --------------------------------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# Copy dependency definition files
# --------------------------------------------------
COPY pyproject.toml README.md ./

# --------------------------------------------------
# Configure pip
# --------------------------------------------------
RUN pip install --upgrade pip \
    && pip config set global.extra-index-url https://download.pytorch.org/whl/cpu

# --------------------------------------------------
# Install backend dependencies
# --------------------------------------------------
RUN pip install --no-cache-dir .[backend]

# --------------------------------------------------
# Install PlatformIO
# --------------------------------------------------
RUN pip install --no-cache-dir platformio

# --------------------------------------------------
# Copy backend source code
# --------------------------------------------------
COPY src/balconygreen ./balconygreen

# 👉 Optional firmware files
# COPY firmware_bins ./firmware_bins

# --------------------------------------------------
# Set Python path
# --------------------------------------------------
ENV PYTHONPATH=/app

# --------------------------------------------------
# Cloud runtime port
# --------------------------------------------------
ENV PORT=8000

# --------------------------------------------------
# Start FastAPI backend
# --------------------------------------------------
CMD ["sh", "-c", "uvicorn balconygreen.backend.api:app --host 0.0.0.0 --port ${PORT}"]