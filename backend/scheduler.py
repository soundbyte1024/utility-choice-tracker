#!/usr/bin/env python3
"""
Daily scheduler — runs once a day to check for expiring contracts
and send email alerts. Invoked by cron inside the container.
"""
import requests
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(message)s"
)

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")

def run():
    logging.info("Running daily alert check...")
    try:
        r = requests.post(f"{API_BASE}/api/check-alerts", timeout=30)
        if r.ok:
            logging.info("Alert check triggered successfully.")
        else:
            logging.warning(f"Alert check returned {r.status_code}: {r.text}")
    except Exception as e:
        logging.error(f"Failed to reach API: {e}")

if __name__ == "__main__":
    run()
