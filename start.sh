#!/bin/bash
cd "$(dirname "$0")"

pkill -f "python3 server.py" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 0.5

echo "Starting SimTrack..."
python3 server.py &

sleep 1

echo "Starting tunnel..."
/tmp/cloudflared tunnel --url http://localhost:8080 2>&1 | while IFS= read -r line; do
  if [[ "$line" == *"trycloudflare.com"* ]]; then
    URL=$(echo "$line" | grep -oE 'https://[^[:space:]|]+trycloudflare\.com')
    if [ -n "$URL" ]; then
      echo ""
      echo "========================================"
      echo "  Mac demo:  http://localhost:8080/demo.html"
      echo ""
      echo "  iPhone:    ${URL}/index.html"
      echo "========================================"
      echo ""
    fi
  fi
done
