FROM python:3.12-slim

WORKDIR /app

# System deps for playwright and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directories and non-root user
RUN mkdir -p data/skills data/chromadb \
    && useradd --create-home appuser \
    && chown -R appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
