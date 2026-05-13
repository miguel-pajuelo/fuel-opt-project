FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY app/ ./app/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY main.py .

RUN mkdir -p data/db data/cache data/reports

RUN useradd -m fuelopt && chown -R fuelopt:fuelopt /app
USER fuelopt

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
