FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY gemini_web2api/ ./gemini_web2api/

COPY config.example.json ./config.json

COPY start.sh ./start.sh

RUN chmod +x ./start.sh

EXPOSE 8081

CMD ["./start.sh"]
