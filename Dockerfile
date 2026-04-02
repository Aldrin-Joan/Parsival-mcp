# Stage 1: builder
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME=/opt/poetry

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
# Use pip install from pyproject (PEP 517 build)
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    libreoffice-draw \
    libreoffice-base \
    libmagic1 \
    poppler-utils \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . /app

ENV LIBREOFFICE_BINARY=soffice
ENV LIBREOFFICE_TIMEOUT_SEC=30
ENV LIBREOFFICE_SECONDARY_KILL_TIMEOUT_SEC=5
ENV LIBREOFFICE_MAX_CONCURRENT=2
ENV PYTHONPATH=/app
ENV MCP_TRANSPORT=stdio

CMD ["python", "-m", "src.mcp_entrypoint"]
