# Ilyon AI Bot - Production Dockerfile
# Multi-stage build for optimized image size

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Production image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Fonts for report card generation
    fonts-dejavu-core \
    fonts-dejavu-extra \
    # For healthchecks
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/

# Create directories
RUN mkdir -p logs

# Set Python environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Non-root user for security (optional)
# RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
# USER botuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${WEB_API_PORT:-8080}/health || exit 1

# Default command
CMD ["python", "-m", "src.main"]

# Labels
LABEL maintainer="Ilyon AI Team"
LABEL version="2.0"
LABEL description="AI-powered Solana token analysis API"
