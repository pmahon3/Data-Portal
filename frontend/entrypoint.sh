#!/bin/sh
set -eu

API_GATEWAY="${API_GATEWAY:-}"
if [ -z "$API_GATEWAY" ]; then
  echo "ERROR: API_GATEWAY must be set (e.g., http://api-gateway.service.consul:8000)"
  exit 1
fi

# SERVER_NAME="${SERVER_NAME:-_}"

# Render the template with only the vars we use
envsubst '${API_GATEWAY}' \
  < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

echo "Contents of /etc/nginx/conf.d/ and /etc/nginx/sites-enabled/:"
find /etc/nginx/conf.d /etc/nginx/sites-enabled -maxdepth 1 -name "*.conf" -type f 2>/dev/null | while read -r conf_file; do
    echo "==> $conf_file"
    cat "$conf_file"
    echo ""
done

conf_file=/etc/nginx/nginx.conf
echo "==> $conf_file"
cat "$conf_file"
echo ""

# Test nginx configuration after processing all configs
# This validates the final configuration with all environment variables substituted
echo "Testing nginx configuration..."
nginx -t

# Run Nginx in foreground
echo Starting NGINX...
exec nginx -g 'daemon off;'
