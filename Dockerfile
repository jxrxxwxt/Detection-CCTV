# Base Image for Python 3.10 Slim
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DETECTOR_HEADLESS=true

# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV and PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first (leveraging Docker layer cache)
COPY requirements.txt .

# Upgrade pip and install CPU-specific PyTorch (speeds up download and reduces image size)
# Then install other dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and models
COPY src/ ./src/
COPY config/ ./config/
COPY models/ ./models/
COPY main.py .

# Create directory structure for logs and video outputs
RUN mkdir -p logs/alerts vdo_outputs data

# Run main script by default
CMD ["python", "main.py"]
