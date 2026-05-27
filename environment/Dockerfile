FROM python:3.11-slim
RUN pip install uv
COPY runtime/ /app/runtime/
WORKDIR /app
CMD ["python3", "-m", "runtime.run_limiter"]
