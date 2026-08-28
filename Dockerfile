FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY gemini_web2api/ ./gemini_web2api/
COPY gemini_web2api.py ./
COPY config.example.json ./config.json

ENV PORT=8081
EXPOSE 8081

CMD ["python", "gemini_web2api.py"]
