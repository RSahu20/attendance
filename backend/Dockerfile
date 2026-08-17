FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN mkdir -p src/attendance \
    && touch src/attendance/__init__.py \
    && pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install ".[dev]" \
    && rm -rf src

COPY src ./src

COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "attendance.main:app", "--host", "0.0.0.0", "--port", "8000"]
