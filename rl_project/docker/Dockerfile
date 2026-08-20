FROM python:3.11-slim

WORKDIR /app

# Use the single repository-level dependency manifest.
COPY requirements.txt ./requirements.txt

# Install backend runtime dependencies.
RUN pip install --no-cache-dir -r ./requirements.txt

# Copy application code and runtime data used by the backend.
COPY backend ./backend
COPY data ./data
COPY README.md ./README.md

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
