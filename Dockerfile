FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=10000

# Create working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure videos and thumbnails directories exist
RUN mkdir -p videos static/thumbnails

# Expose port
EXPOSE $PORT

# Command to run the application
CMD uvicorn app:app --host 0.0.0.0 --port $PORT