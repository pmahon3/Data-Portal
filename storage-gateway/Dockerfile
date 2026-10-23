FROM python:3.12-slim

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY entrypoint.sh .

# gateway: the web service (no access to the data); inndata: owns the governed files;
# posix-traverse: lets a link's temporary ID pass through data folders without listing them.
RUN groupadd --system --gid 10010 posix-traverse \
 && groupadd --system --gid 10001 gateway \
 && groupadd --system --gid 10002 inndata \
 && useradd --system --uid 10001 --gid gateway --no-create-home gateway \
 && useradd --system --uid 10002 --gid inndata --no-create-home inndata

# The helper runs as root and drops the web service to 'gateway' (see entrypoint.sh).
ENV GATEWAY_ROOT=/srv/posix/data \
    HELPER_STAGING=/srv/posix/staging \
    HELPER_STATE=/srv/posix/.helper/state.json \
    HELPER_SOCKET=/run/gateway/helper.sock \
    GATEWAY_HELPER_SOCKET=/run/gateway/helper.sock \
    GATEWAY_REQUIRE_ISOLATION=1 \
    HELPER_CLIENT_UIDS=10001 \
    HELPER_SOCKET_GID=10001

EXPOSE 9100
ENTRYPOINT ["/service/entrypoint.sh"]
