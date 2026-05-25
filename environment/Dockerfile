FROM python:3.11-slim

WORKDIR /app

COPY runtime/ ./runtime/

RUN pip install uv

CMD ["python3", "/app/runtime/replay_engine.py"]
