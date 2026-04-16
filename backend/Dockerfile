# AMS Backend Service Dockerfile
FROM python:3.12-slim

ARG APP_DIR=/app
ARG APP_USER=ams
ARG APP_UID=1000
ARG APP_PORT=8000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=${APP_DIR} \
    APP_DIR=${APP_DIR} \
    APP_USER=${APP_USER} \
    APP_PORT=${APP_PORT}

WORKDIR ${APP_DIR}

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      python3-dev \
      gcc g++ curl gettext-base jq \
  && rm -rf /var/lib/apt/lists/*


# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 
# \ && pip install --no-cache-dir pydevd-pycharm

# App code
COPY . .

# Create user and data dirs
RUN mkdir -p ${APP_DIR}/data/logs ${APP_DIR}/data/configs ${APP_DIR}/data/policies ${APP_DIR}/data/secrets \
 && adduser --disabled-password --gecos '' --uid ${APP_UID} ${APP_USER} \
 && chown -R ${APP_USER}:${APP_USER} ${APP_DIR}

USER ${APP_USER}

EXPOSE ${APP_PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${APP_PORT}/api/health/ready || exit 1

# Use bash (our scripts rely on bash features)
#COPY --chown=${APP_USER}:${APP_USER} entrypoint.backend.sh ${APP_DIR}/entrypoint.backend.sh
#RUN chmod +x ${APP_DIR}/entrypoint.backend.sh
#ENTRYPOINT ["bash", "/app/entrypoint.backend.sh"]
ENTRYPOINT ["python", "server.py"]
