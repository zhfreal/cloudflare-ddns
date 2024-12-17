# Base image with Python 3.10
FROM python:3.10-alpine

# fix dns
RUN echo 'nameserver 8.8.8.8' >> /etc/resolve.conf && echo 'nameserver 8.8.4.4' >> /etc/resolve.conf

# make work folder
RUN mkdir /app

# Working directory within the container
WORKDIR /app

# Copy source files
COPY src /app/src
COPY setup.py /app/
COPY cloudflare-ddns.py /app/
COPY requirements.txt /app/

# Install dependencies using a separate RUN step for clarity
RUN pip install -r /app/requirements.txt && rm /app/requirements.txt

# ENTRYPOINT for flexibility in passing arguments
# RUN pip install -e .

# Set PYTHONPATH just to be sure
ENV PYTHONPATH=.

ENTRYPOINT ["python", "/app/cloudflare-ddns.py"]
CMD []

# Example usage with arguments:
# docker run -it <image_name> arg1 arg2 arg3
