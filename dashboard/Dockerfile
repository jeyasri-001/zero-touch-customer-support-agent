FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .

# Render provides $PORT; default to 8501 for local
ENV PORT=8501
EXPOSE 8501

# Run Streamlit (shell form so $PORT expands)
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
