# Use the official Python 3.8 slim image as the base image
FROM python:3.10.12-slim

# Set the working directory within the container
WORKDIR /Docker_Flask_App_Test

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt ./

# Upgrade pip and install dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
#RUN pip install -r requirements.txt

# Copy the application files
COPY . .

# Copy environment variables
COPY .env .env

# Expose port 5000 for Flask
EXPOSE 5000

# Start Gunicorn with the correct entry point
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "4", "--timeout", "120", "application:create_app()"]

