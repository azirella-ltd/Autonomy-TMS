FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV MYSQL_SERVER=db
ENV MYSQL_PORT=3306
ENV MYSQL_USER=autonomy_user
ENV MYSQL_PASSWORD=Autonomy@2025
ENV MYSQL_DB=autonomy

# The command to run the script
CMD ["python", "scripts/create_users.py"]
