FROM python:3.11-slim

WORKDIR /app

# Install dependencies in a separate layer for better cache reuse
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Reports land here; mount a volume in production to persist them
RUN mkdir -p reports

EXPOSE 8000 8082
