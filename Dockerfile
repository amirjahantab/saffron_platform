FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies required for psycopg, Pillow, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    libwebp7 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -g 10001 appgroup && useradd -u 10001 -g appgroup -d /app -s /sbin/nologin appuser

# Install Python dependencies
COPY requirements/ /app/requirements/
ARG ENVIRONMENT=development
RUN pip install --upgrade pip && \
    pip install -r /app/requirements/${ENVIRONMENT}.txt

# Copy project source code
COPY . /app/

# Prepare runtime directories with proper ownership
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
