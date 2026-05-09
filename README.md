# Utility Choice Tracker 🔌🔥

A self-hosted Docker container for managing energy supplier contracts in states that
allow customers to choose their own electric and gas supplier. Track your rates,
contract terms, and receive email alerts before a contract expires — so you can
shop for a better rate before being rolled onto a variable rate that can increase
significantly.

Originally built for Ohio's energy choice program, but works for any state with a
deregulated energy market.

**Current version: 1.1.0**

---

## Features

- **Multiple addresses** — manage separate electric and gas contracts for each property; switch between them via a dropdown in the sidebar
- **Dashboard** — dedicated Electric and Gas panels showing your current contract, rate, term progress, and days remaining at a glance
- **Upcoming contract slot** — enter your next supplier ahead of time so it appears alongside the current one
- **Track electric & gas suppliers** — rate (¢/kWh for electric, $/Ccf, $/Mcf, or $/therm for gas), term dates, account number, and notes
- **Term-length slider** — pick a contract length (1–60 months) and the end date is calculated automatically
- **Upload documents** — store contracts, enrollment letters, and bills alongside each supplier
- **Expiration alerts** — configurable email warnings sent automatically (default: 90, 60, and 30 days before expiry)
- **Comparison site link** — configurable link to your state's supplier comparison website, shown in the sidebar and in alert emails
- **Daily scheduler** — alert checks run automatically at 8 AM Eastern inside the container
- **SMTP email** — works with Gmail, Outlook, Yahoo, or any SMTP provider
- **Multi-architecture** — runs on x86 servers and Raspberry Pi 4, Pi 5, Pi 400, CM4, and Zero 2 W (64-bit OS)

---

## Quick Start

### Option A — Pull from Docker Hub (recommended)

No source code needed. Create a `docker-compose.yml` anywhere on your server:

```yaml
services:
  utility-tracker:
    image: yourname/utility-choice-tracker:latest
    container_name: utility-choice-tracker
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /opt/utility-tracker/data:/data
      - /opt/utility-tracker/uploads:/uploads
    environment:
      - TZ=America/New_York
```

Then:

```bash
sudo mkdir -p /opt/utility-tracker/data /opt/utility-tracker/uploads
docker compose up -d
```

### Option B — Build from source

```bash
git clone <your-repo>
cd utility-choice-tracker
docker compose up -d
```

Open **http://localhost:8000** in your browser.

---

## First-Time Setup

1. Open the app and go to **Settings** in the sidebar
2. Enter your SMTP details and click **Send Test Email** to verify
3. Set your **Comparison Website URL** to your state's energy supplier comparison site
4. Configure your **Alert Days** (type a number and press Enter — defaults are 30, 60, 90)
5. Click **Save Settings**
6. Go to **Suppliers** and add your first contract

---

## Configuration

All configuration is done through the **Settings** page in the UI. No environment
variables or config files are required.

### SMTP Setup (Gmail)

1. Enable 2-Factor Authentication on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. In Settings:
   - SMTP Host: `smtp.gmail.com`
   - SMTP Port: `587`
   - SMTP Username: `your@gmail.com`
   - SMTP Password: your App Password
   - STARTTLS: ✅ enabled
   - Alert Recipient: the address to send alerts to

### SMTP Setup (Outlook/Hotmail)

- Host: `smtp-mail.outlook.com`
- Port: `587`
- STARTTLS: ✅

### SMTP Setup (Yahoo)

- Host: `smtp.mail.yahoo.com`
- Port: `587`
- STARTTLS: ✅
- Use an App Password (not your regular password)

---

## State Comparison Websites

Set your state's energy comparison URL in Settings. A few examples:

| State | URL |
|-------|-----|
| Ohio | https://www.energychoice.ohio.gov/ApplestoApples.aspx |
| Pennsylvania | https://www.papowerswitch.com |
| Illinois | https://www.pluginillinois.org |
| New York | https://www.powertochooseny.com |
| Texas | https://www.powertochoose.org |

---

## Alert Schedule

In Settings, configure how many days before expiration to send an alert email.
Type a number and press **Enter** to add it. Multiple thresholds are supported.
The default is 90, 60, and 30 days.

Alerts are checked once daily at **8:00 AM Eastern**. You can also trigger a
manual check from the Settings page at any time.

---

## Data Storage

### Named volumes (default)

By default, Docker stores data in named volumes:

| Volume | Default path on Linux | Contents |
|--------|----------------------|----------|
| `utility-data` | `/var/lib/docker/volumes/utility-data/_data` | SQLite database |
| `utility-uploads` | `/var/lib/docker/volumes/utility-uploads/_data` | Uploaded documents |

Inspect the exact path with:
```bash
docker volume inspect utility-data
```

### Bind mounts (recommended for Linux servers)

For a more predictable location that is easy to back up, use bind mounts in
`docker-compose.yml`:

```yaml
volumes:
  - /opt/utility-tracker/data:/data
  - /opt/utility-tracker/uploads:/uploads
```

### Backup & restore

```bash
# Backup database
docker run --rm -v utility-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/utility-data-backup.tar.gz /data

# Restore database
docker run --rm -v utility-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/utility-data-backup.tar.gz -C /
```

---

## Publishing to Docker Hub (multi-architecture)

The included `build-multiarch.sh` script builds and pushes images for all
supported platforms in a single step using Docker Buildx:

| Platform | Covers |
|----------|--------|
| `linux/amd64` | x86_64 servers and desktops |
| `linux/arm64` | Raspberry Pi 4, Pi 5, Pi 400, CM4, Zero 2 W (64-bit OS), Apple Silicon |

> **Note:** Raspberry Pi 1, 2, 3, Pi Zero, and Pi Zero W are not supported. Pi 3 users can switch to a 64-bit OS (64-bit Raspberry Pi OS or Ubuntu Server) to use the `arm64` image.

```bash
# One-time setup
docker login

# Build and push all platforms
chmod +x build-multiarch.sh
./build-multiarch.sh yourname/utility-choice-tracker 1.1.0
```

Docker automatically pulls the correct architecture for whatever machine is running it.

### Updating to a new release

On any machine running the container:

```bash
docker compose pull
docker compose up -d
```

---

## External Access & Security

To make the app accessible outside your local network, place it behind a reverse
proxy with HTTPS. Never expose port 8000 directly to the internet.

**Caddy** is the simplest option — it handles HTTPS automatically:

```
your.domain.com {
  basicauth {
    username <bcrypt-hashed-password>
  }
  reverse_proxy utility-choice-tracker:8000
}
```

[Nginx Proxy Manager](https://nginxproxymanager.com/) is a good GUI alternative.

---

## Project Structure

```
utility-choice-tracker/
├── Dockerfile                  # Multi-arch compatible build
├── docker-compose.yml          # Local development / self-hosted
├── build-multiarch.sh          # Build & push amd64 + arm64 to Docker Hub
├── README.md
├── backend/
│   ├── main.py                 # FastAPI REST API + static file serving
│   ├── scheduler.py            # Daily alert check (called by cron)
│   ├── entrypoint.sh           # Starts cron daemon + uvicorn on boot
│   └── requirements.txt
└── frontend/
    └── index.html              # Single-file SPA (no build step required)
```

---

## Energy Choice

Many U.S. states allow residential and small business customers to choose their
own electric and gas supplier in place of the utility's default "standard offer"
rate. After a fixed-rate contract ends, customers are typically moved to a
variable rate that can increase significantly. This tool helps you stay ahead of
that by tracking your contracts and alerting you in time to shop for a new rate.

Check your state's public utility commission website to see if energy choice is
available in your area.
