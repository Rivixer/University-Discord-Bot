# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY microservices/voice-channel-service/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code and install it
COPY shared/python ./shared/
RUN pip install --no-cache-dir -e shared[proto] shared[redis] shared[pydantic]

# Copy application code
COPY microservices/voice-channel-service ./

# Run the bot
CMD ["python", "-m", "voice_channel_service.main"]
