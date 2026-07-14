# syntax=docker/dockerfile:1.6

FROM maven:3.9.9-eclipse-temurin-21 AS build

WORKDIR /workspace

COPY pom.xml .
COPY .mvn .mvn
COPY mvnw .

RUN chmod +x mvnw \
 && ./mvnw -B -DskipTests dependency:go-offline

COPY src src

RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre-jammy AS runtime

ARG APP_DIR=/app

ENV APP_DIR=${APP_DIR} \
    SERVER_PORT=8888 \
    BUNDLER_ARCHIVE_TEMP_DIR=/tmp/bundler

WORKDIR ${APP_DIR}

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home bundler \
 && mkdir -p /tmp/bundler \
 && chown -R bundler:bundler ${APP_DIR} /tmp/bundler

COPY --from=build --chown=bundler:bundler /workspace/target/bundler-*.jar ${APP_DIR}/bundler.jar

USER bundler

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:${SERVER_PORT}/actuator/health || exit 1

ENTRYPOINT ["java", "-jar", "/app/bundler.jar"]
