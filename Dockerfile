FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (maximises layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (data/*.db files are NOT committed — mount via Docker volume)
COPY . .

# Default DB paths — override via .env or Docker volume mounts in production
ENV MERIDANT_FRAMEWORKS_DB_PATH=/app/data/meridant_frameworks.db
ENV MERIDANT_ASSESSMENTS_DB_PATH=/app/data/meridant.db

# Mount point for optional local volume override
RUN mkdir -p /data

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
