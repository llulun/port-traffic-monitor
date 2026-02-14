FROM python:3.9-alpine

WORKDIR /app

# Install system dependencies
# gcc, musl-dev, linux-headers are needed for psutil
RUN apk add --no-cache gcc musl-dev linux-headers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory
RUN mkdir -p data

# Expose the port (though host mode ignores this)
EXPOSE 8899

# Environment variable to unbuffer Python output
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
