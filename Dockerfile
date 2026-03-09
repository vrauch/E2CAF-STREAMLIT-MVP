FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (maximises layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (includes data/e2caf.db, baked into the image)
COPY . .

# Default DB path — testers get this automatically; local dev overrides via .env
ENV TMM_DB_PATH=/app/data/e2caf.db

# Mount point for optional local volume override
RUN mkdir -p /data

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
