# SideBySide

A Django starter for a platonic social-companionship marketplace. The current MVP includes public companion discovery, city/activity/budget filters, profile pages, client registration, companion applications, and booking requests. Django admin provides profile approval and moderation controls.

## Run locally

Requires Python 3.12 and pip.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate --run-syncdb
python manage.py seed_activities
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. Create companion applications through **List as a companion**; approve profiles in `/admin/` before they appear publicly. Uploaded photos are stored in the local `media/` directory during development.

## Current scope

Membership checkout and renewal, OTP verification, private ID/selfie review, email/SMS notifications, companion booking-response controls, chat, and review/report submission are not implemented yet. Do not use this development configuration for real identity documents or production traffic. Before launch, configure a strong `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, HTTPS/security settings, private media storage, backups, rate limits, and the legal/payment-provider reviews described in the PRD.