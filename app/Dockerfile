# ADK / Agent Runtime Dockerfile
# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the agent application code
COPY . .

# Expose the default port (Vertex AI Agent Engine uses 8080)
EXPOSE 8080

# CRITICAL: Start the Google ADK standard FastAPI server, NOT your main app
CMD ["python", "-m", "google.adk.cli", "api_server", "--host", "0.0.0.0", "--port", "8080"]
