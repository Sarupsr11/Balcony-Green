# Use slim Python image
FROM python:3.11-slim

# --------------------------------------------------
# Set working directory
# --------------------------------------------------
WORKDIR /app
RUN echo "Working directory set to /app"

# --------------------------------------------------
# Install minimal system dependencies
# --------------------------------------------------
RUN echo "Installing system dependencies..." \
    && apt-get update \
    && apt-get install -y \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/* \
    && echo "System dependencies installed" 


# --------------------------------------------------
# Copy dependency definition files first (for caching)
# --------------------------------------------------
COPY pyproject.toml README.md ./
RUN echo "Copied pyproject.toml and README.md" && ls -la /app

# --------------------------------------------------
# Install frontend dependencies only
# --------------------------------------------------
RUN echo "Installing frontend dependencies..." \
    && pip install --upgrade pip \
    && pip install .[frontend] \
    && echo "Frontend dependencies installed"

# Copy entire package
COPY src/balconygreen ./balconygreen

# Set PYTHONPATH so Python can find the package
ENV PYTHONPATH=/app:$PYTHONPATH

# --------------------------------------------------
# Expose Streamlit port
# --------------------------------------------------
EXPOSE 8501
RUN echo "Exposed port 8501"

# --------------------------------------------------
# Start Streamlit
# --------------------------------------------------
CMD ["sh", "-c", "streamlit run balconygreen/frontend/login_page.py --server.address=0.0.0.0 --server.port ${PORT}"]
