FROM python:3.12-slim

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Run as an ordinary account, like the proxy account on a real POSIX machine.
RUN useradd --system --uid 10001 --no-create-home gateway
USER gateway

EXPOSE 9100
CMD ["uvicorn", "--factory", "app.main:app_from_env", "--host", "0.0.0.0", "--port", "9100", "--no-access-log"]
