FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080

# Cloud Run inyecta PORT; gunicorn debe escucharlo.
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 60 app:app
