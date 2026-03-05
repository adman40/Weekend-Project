# UT CrimeScope

A full-stack web application that scrapes, stores, and visualizes crime data from the UTPD daily crime log. Built with Django and PostgreSQL, deployed on AWS.

**Live demo:** http://utcrimescope.mooo.com/

---

## Overview

UT CrimeScope automatically fetches the UTPD crime log PDF each morning, parses it, and loads the records into a PostgreSQL database. Registered users can explore incidents on an interactive dashboard, set up location-based alerts, and receive email notifications when crimes are reported near a watched address.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Django |
| Database | PostgreSQL (AWS RDS) |
| PDF Parsing | pdfplumber, regex |
| Geocoding | geopy / Nominatim |
| Frontend | Django templates, Bootstrap 5, Chart.js |
| Static Files | AWS S3 + django-storages |
| Web Server | Gunicorn + Nginx |
| Hosting | AWS EC2 (Ubuntu 22.04) |
| Auth | Django custom user model, session auth |
| Secrets | python-decouple (.env locally, /etc/environment on EC2) |

---

## Features

- **Automated daily scraping** — cron job fetches and parses the UTPD PDF every morning; duplicate incidents are skipped automatically
- **PostgreSQL backend** — normalized schema with `Incident`, `Building`, `UserProfile`, `WatchedLocation`, and `AlertLog` models
- **User authentication** — register, login, logout with a custom `UserProfile` model extending Django's `AbstractUser`
- **Location-based alerts** — users pin addresses and choose a radius; the scraper emails them when a new incident falls within range
- **Interactive dashboard** — toggle between crimes-by-type, crimes-by-hour, and crimes-by-week charts; recent incidents table below
- **Secure secrets management** — no credentials committed to version control; environment variables drive all configuration

---

## Database Schema

```
Incident          — one row per offense (incident_id, crime_type, dates, times, location, lat/lon, disposition)
Building          — campus buildings with coordinates and zone
UserProfile       — extends AbstractUser; tracks watched buildings and alert preferences
WatchedLocation   — user-defined address + radius for proximity alerts
AlertLog          — idempotent record of every alert email sent (prevents duplicate notifications)
```

---

## Project Structure

```
ut-crimescope/
├── crimescope/               # Django project settings, URLs, WSGI
├── crimes/
│   ├── models.py             # Database models
│   ├── views.py              # Dashboard, alerts, registration
│   ├── urls.py
│   ├── admin.py
│   ├── management/
│   │   └── commands/
│   │       └── scrape_utpd.py   # PDF scraper + geocoder + alert sender
│   └── templates/crimes/
│       ├── base.html
│       ├── dashboard.html
│       └── alerts.html
├── .env.example              # Required environment variables (no secrets)
├── requirements.txt
└── manage.py
```

---

## Local Development

```bash
git clone https://github.com/YOUR_USERNAME/ut-crimescope.git
cd ut-crimescope

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # Fill in your local DB credentials
python manage.py migrate
python manage.py scrape_utpd    # Populate the database
python manage.py runserver
```

---

## AWS Deployment

- **EC2** (Ubuntu 22.04) — runs Gunicorn behind Nginx, both enabled as systemd services
- **RDS** (PostgreSQL) — SSL-required connection via `sslmode: require`
- **S3** — static files collected and served via `django-storages` + `boto3`
- **IAM role** attached to EC2 for S3 access (no access keys stored on the server)
- **Secrets** loaded from `/etc/environment` at boot; picked up automatically by python-decouple

---

## Requirements

```
Django
psycopg2-binary
pdfplumber
requests
geopy
django-storages
boto3
python-decouple
gunicorn
```
