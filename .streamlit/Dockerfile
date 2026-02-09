FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Persistenz erfolgt über Volume-Mount auf /app/data
RUN mkdir -p /app/data

EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
