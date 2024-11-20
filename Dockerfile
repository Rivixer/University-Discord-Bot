# Use the official Python image from the Docker Hub
FROM python:3.10.14-slim-bookworm

# Set the working directory in the container
WORKDIR /app

RUN apt update && apt install dos2unix

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN python -m pip install -r requirements.txt

# Copy the plugin packages into the container
COPY plugins/packages/ /app/plugins/packages/

# Give the packages/install.sh file execute permissions and run it.
# After installation, remove the packages directory and the apt cache
RUN chmod +x /app/plugins/packages/install.sh && \
    dos2unix /app/plugins/packages/install.sh && \
    bash -x /app/plugins/packages/install.sh && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /app/plugins/packages

# Copy the plugin requirements into the container
COPY plugins/requirements/ /app/plugins/requirements/

# Give the requirements/install.sh file execute permissions, run it
# and remove the requirements directory after installation
RUN chmod +x /app/plugins/requirements/install.sh && \
    dos2unix /app/plugins/requirements/install.sh && \
    bash -x /app/plugins/requirements/install.sh && \
    rm -rf /app/plugins/requirements

# Copy the local files into the container
COPY . /app/

# Run the application
CMD ["python", "-u", "main.py"]