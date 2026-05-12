FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends     libpq-dev gcc &&     rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501 8502

CMD ["bash", "-c", "python3 upload_server.py & streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]
