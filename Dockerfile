# Use official Python runtime as base image
FROM python:3.11-slim

# Install system dependencies and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY package.json package-lock.json* requirements.txt ./

# Install Python and Node.js dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy the rest of the application files
COPY . .

# Ensure data directory exists
RUN mkdir -p data

# Expose port (Railway will set PORT env var dynamically, which our script reads)
EXPOSE 8000

# Start command
CMD ["python", "scripts/run_dashboard.py"]
