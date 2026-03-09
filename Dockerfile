FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (maximises layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Mount point for the external SQLite database
RUN mkdir -p /data

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
