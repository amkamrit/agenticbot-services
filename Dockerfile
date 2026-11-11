FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Ensure logs are displayed immediately
ENV PYTHONUNBUFFERED=1

# Install dependencies first for better layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start FastAPI using Uvicorn
CMD ["uvicorn", "app.main:api", "--host", "0.0.0.0", "--port", "9000", "--reload"]