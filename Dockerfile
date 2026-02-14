FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (if needed for psutil or others)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port (though host mode ignores this)
EXPOSE 8899

# Environment variable to unbuffer Python output
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
