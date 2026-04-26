# Playto Pay Payout Engine

Minimal payout engine for the Playto Founding Engineer Challenge 2026.

## What Is Included

- Django + DRF API
- PostgreSQL-backed merchant ledger and payout holds
- Celery task for background payout processing
- React + Tailwind merchant dashboard
- Seed command for demo merchants, bank accounts, and credits
- Tests for idempotency, concurrency, and illegal state transitions

## Local Setup

Start PostgreSQL and Redis:

```bash
docker compose up -d
```

Create a virtual environment and install backend dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run migrations and seed the challenge data. This creates 3 merchants with credit ledger history:

```bash
cd backend
POSTGRES_PORT=5433 python manage.py migrate
POSTGRES_PORT=5433 python manage.py seed
POSTGRES_PORT=5433 python manage.py runserver 0.0.0.0:8000
```

For a fuller local demo with extra studios and bank accounts, run:

```bash
cd backend
POSTGRES_PORT=5433 python manage.py seed --rich
```

In another terminal, run the payout worker:

```bash
cd backend
CELERY_BROKER_URL=redis://localhost:6380/0 CELERY_RESULT_BACKEND=redis://localhost:6380/1 celery -A playto worker -B --loglevel=info
```

For a one-shot local simulation without waiting for Celery beat:

```bash
cd backend
POSTGRES_PORT=5433 python manage.py process_payouts
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## API

The demo uses `X-Merchant-ID` as a lightweight stand-in for authentication.

Create a payout:

```bash
curl -X POST http://localhost:8000/api/v1/payouts \
  -H "Content-Type: application/json" \
  -H "X-Merchant-ID: 1" \
  -H "Idempotency-Key: 3baf8ae2-8e4c-4037-a8df-e10806c0ec4f" \
  -d '{"amount_paise":50000,"bank_account_id":1}'
```

Dashboard data:

```bash
curl -H "X-Merchant-ID: 1" http://localhost:8000/api/v1/dashboard
```

## Tests

```bash
cd backend
POSTGRES_PORT=5433 python manage.py test
```

The concurrency test intentionally runs only on PostgreSQL because `SELECT ... FOR UPDATE` is the database primitive under test.

## Deployment Notes

Use PostgreSQL and Redis in production. This repo includes `render.yaml` for Render Blueprint deploys:

- `playto-pay-api`: Django + DRF API
- `playto-pay-dashboard`: React static frontend
- `playto-pay-worker`: Celery worker + beat scheduler
- `playto-pay-db`: PostgreSQL
- `playto-pay-redis`: Redis-compatible key-value instance

### Render Blueprint Deploy

1. Push this repo to GitHub.
2. In Render, choose **New > Blueprint**.
3. Connect `RITIKYADAV0070/Playto-Payout-Engine`.
4. Select the repo's `render.yaml`.
5. Apply the blueprint.
6. After the first deploy, open the dashboard service URL.

Expected URLs if Render keeps the service names:

- Frontend: `https://playto-pay-dashboard.onrender.com`
- API: `https://playto-pay-api.onrender.com/api/v1`

If Render gives the services different URLs, update:

- API service `CORS_ALLOWED_ORIGINS`
- Dashboard service build command `VITE_API_BASE=...`

The backend supports these environment variables:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `DATABASE_URL`
- `REDIS_HOST`
- `REDIS_PORT`

For Render/Railway/Fly, run:

```bash
cd backend && gunicorn playto.wsgi:application
```

Run a separate worker process:

```bash
cd backend && celery -A playto worker -B --loglevel=info
```
