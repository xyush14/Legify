#!/bin/bash
# Double-click to (re)start the Headnote landing preview server.
cd "$(dirname "$0")"
pkill -f "http.server 8000" 2>/dev/null
sleep 1
echo "Starting preview on http://localhost:8000 ..."
echo "Landing page:  http://localhost:8000/static/landing-new.html"
echo "(Leave this window open. Close it to stop the server.)"
python3 -m http.server 8000
