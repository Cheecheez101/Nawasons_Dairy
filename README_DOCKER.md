Nawasons Dairy — Docker + Postgres

Overview
- Dockerfile provided for production image (Gunicorn + Django)
- docker-compose.yml for local development with Postgres

Build image locally

```bash
# build image
docker build -t nawasons-django .

# run a temporary container (reads .env)
docker run -d --env-file .env -p 8000:8000 nawasons-django
```

Run with docker-compose (local PG)

```bash
# bring up Postgres and web
docker-compose up --build
```

Notes
- Ensure `.env` contains DB_* values and USE_POSTGRES=True when using Postgres (e.g. with docker-compose)
- Don't commit `.env` to version control
- Use AWS RDS for a managed Postgres; see notes in the project wiki or ask for a walkthrough for RDS setup

