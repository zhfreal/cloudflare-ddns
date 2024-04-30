# Base image with Python 3.10
FROM python:3.10

# fix dns
RUN echo 'nameserver 8.8.8.8' >> /etc/resolve.conf && echo 'nameserver 8.8.4.4' >> /etc/resolve.conf

# make work folder
RUN mkdir /app

# Working directory within the container
# WORKDIR /app

# Copy requirements file
COPY requirements.txt . /app/

# Install dependencies using a separate RUN step for clarity
RUN pip install -r /app/requirements.txt && rm /app/requirements.txt

# Copy your source code directory
COPY src /app/

# ENTRYPOINT for flexibility in passing arguments
ENTRYPOINT ["python", "/app/src/cloudflare_ddns.py"]

# Optional CMD for default behavior (can be overridden at runtime)
CMD []

# Example usage with arguments:
# docker run -it <image_name> arg1 arg2 arg3
