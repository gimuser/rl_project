FROM python:3.11-slim

WORKDIR /app

# copy only requirements first to leverage Docker layer caching
COPY backend/requirements.txt ./backend/requirements.txt

# install all backend requirements
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# copy application code
COPY backend ./backend
COPY data ./data
COPY README.md ./README.md

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
