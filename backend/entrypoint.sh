#!/bin/bash
set -e

# Setup daily cron job for alert checks (runs at 8am)
echo "0 8 * * * root /usr/local/bin/python /app/scheduler.py >> /var/log/scheduler.log 2>&1" > /etc/cron.d/utility-alerts
chmod 0644 /etc/cron.d/utility-alerts
crontab /etc/cron.d/utility-alerts

# Start cron daemon
service cron start

# Start FastAPI
echo "Starting Ohio Utility Tracker..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
