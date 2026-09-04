#!/usr/bin/env python3
"""
Docker entrypoint for RankBuilder container.
Starts a health check HTTP server on port 8080 and runs cron jobs in background.
"""

import os
import shlex
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

HEALTH_PORT = int(os.environ.get("HEALTHCHECK_PORT", 8080))
START_TIME = time.time()

def get_uptime():
    return int(time.time() - START_TIME)

def run_cron():
    """Write crontab and start cron daemon."""
    os.makedirs("/app/data/logs", exist_ok=True)

    # Dump the container env to a file cron jobs can source. vixie cron does
    # NOT pass the daemon's environment to jobs — only what's declared in the
    # crontab file. Without this, himalaya IMAP auth fails (INFO_MAIL_PASSWORD
    # missing) and every cron run silently sees 0 emails. Same applies to
    # BREVO_API_KEY, CONNECTIVELY_*, GUEST_SMTP_*, etc.
    env_file = "/app/data/env.sh"
    with open(env_file, "w") as f:
        f.write("#!/bin/bash\n")
        for key, val in os.environ.items():
            if key in ("PATH", "PWD", "SHLVL", "_", "OLDPWD"):
                continue
            f.write(f"export {key}={shlex.quote(val)}\n")
    os.chmod(env_file, 0o600)

    # Write crontab — every job sources the env dump first
    with open("/etc/crontab", "w") as f:
        f.write("""\
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# m h dom mon dow user  command
*/30 7-22 * * *   root  . /app/data/env.sh && /app/run_mode.sh haro >> /app/data/logs/haro.log 2>&1
*/30 7-22 * * *   root  . /app/data/env.sh && /app/run_mode.sh connectively >> /app/data/logs/connectively.log 2>&1
0 8,12,18 * * *   root  . /app/data/env.sh && /app/run_mode.sh guest >> /app/data/logs/guest.log 2>&1
0 0 */3 * *       root  . /app/data/env.sh && /app/run_mode.sh prospect >> /app/data/logs/prospect.log 2>&1
""")
    subprocess.run(["cron"], check=False)
    # Keep alive
    while True:
        time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write('{"status":"ok","uptime":%d}'.encode() % get_uptime())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Silent

if __name__ == "__main__":
    print("RankBuilder container starting...")
    t = threading.Thread(target=run_cron, daemon=True)
    t.start()
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), Handler)
    print(f"Health check server running on :{HEALTH_PORT}")
    server.serve_forever()
