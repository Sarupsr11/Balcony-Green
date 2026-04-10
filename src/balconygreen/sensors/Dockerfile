# Use slim Python image
FROM python:3.11-slim

# --------------------------------------------------
# Set working directory
# --------------------------------------------------
WORKDIR /app
RUN echo "Working directory set to /app"

# --------------------------------------------------
# Install system dependencies
# --------------------------------------------------
RUN echo "Installing system dependencies..." \
    && apt-get update \
    && apt-get install -y \
        build-essential \
        gcc \
        libffi-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && echo "System dependencies installed"

# --------------------------------------------------
# Copy dependency definition files first (for caching)
# --------------------------------------------------
COPY pyproject.toml README.md ./
RUN echo "Copied pyproject.toml and README.md" && ls -la /app

# --------------------------------------------------
# Configure pip for PyTorch CPU wheels
# --------------------------------------------------
RUN pip install --upgrade pip \
    && pip config set global.extra-index-url https://download.pytorch.org/whl/cpu

# --------------------------------------------------
# Install worker + ML dependencies
# --------------------------------------------------
RUN echo "Installing worker + ML dependencies..." \
    && pip install .[worker,ml] \
    && echo "Worker + ML dependencies installed"


# Copy entire package
COPY src/balconygreen ./balconygreen

# Set PYTHONPATH so Python can find the package
ENV PYTHONPATH=/app:$PYTHONPATH

# Set default command
CMD ["python", "balconygreen/sensors/uninterrupted_sensor_reading.py"]
