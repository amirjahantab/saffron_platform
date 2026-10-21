# Production deployment and recovery

This runbook accompanies `compose.production.yml`. Public deployment has **not**
been performed. The tested stack runs on loopback with a local self-signed TLS
certificate. Those smoke credentials/certificates are not a live configuration.

## First deployment

1. Use a fresh production PostgreSQL volume, separate from development. Never
   seed demo data there. `verify_launch` rejects databases marked as demo.
2. Copy `.env.production.example` to `.env.production`; generate independent
   Django, database and URL-safe Redis secrets. Never reuse the generated local
   smoke `.env.production`. Store the real file outside version control with
   restricted permissions. Set the actual HTTPS `SITE_URL`, matching payment
   callback origin, allowed hosts and CSRF origins. Wildcard hosts, HTTP CSRF
   origins, missing Redis authentication and placeholder Django secrets fail.
3. Provide the actual Zarinpal merchant configuration and Kavenegar key/template.
   Disable sandbox payments; keep AI and optional notifications disabled until
   their providers have been tested. A merchant's entitlement to automated refunds
   is separate from payment acceptance. This adapter never invents refund success.
4. Place the real CA-issued TLS chain and key at `deploy/certs/fullchain.pem` and
   `deploy/certs/privkey.pem`. Arrange certificate renewal with your infrastructure
   provider. Give Nginx UID 101 read access to the private key without making it
   publicly readable. The self-signed test certificate is deliberately short-lived.
5. Build CSS before packaging; generated image sources live in
   `assets/source-images/`, web encodings in `static/images/`. Run:

```sh
npm ci --ignore-scripts
npm run build:css
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d db redis
docker compose --env-file .env.production -f compose.production.yml run --rm release
docker compose --env-file .env.production -f compose.production.yml run --rm web python manage.py createsuperuser
```

The release job applies migrations once, collects static files and runs Django's
deployment checks. It must finish successfully before the web service starts.
Schema changes in this task are additive or nullable-compatible; existing orders
and prices are preserved. Back up before any migration on an existing database.

6. Bootstrap the store's actual catalog, contact profile and published policies
   using a private/staging admin session. For a first setup, restrict incoming
   connections at the host firewall or publish the proxy on loopback through
   `compose.smoke.yml` while configuring the store; do not use its self-signed
   certificate publicly. Use an SSH tunnel for a remote private admin. Enter real
   inventory and verified laboratory documents, not demo article/product evidence.
7. Keep `STORE_OPEN=False` while bootstrapping. Run the live-launch gate, then set
   `STORE_OPEN=True` for controlled real acceptance tests before public traffic.
   The web startup runs `verify_launch` before Gunicorn when opening checkout;
   missing prerequisites prevent the web process starting. A closed live store
   rejects new checkout submissions while leaving admin and existing payment
   processing available. Test a controlled real OTP and payment with your
   merchant account. Confirm server verification, cancellation and receipt privacy.
   Validate public TLS trust, canonical URLs and sitemap host on the actual domain.

```sh
docker compose --env-file .env.production -f compose.production.yml run --rm web python manage.py verify_launch
docker compose --env-file .env.production -f compose.production.yml up -d
docker compose --env-file .env.production -f compose.production.yml ps
```

The live gate also requires real published contact, terms, shipping, returns and
privacy pages, public contact phone/address and sellable inventory. Code cannot
verify legal adequacy, ownership of a contact number or merchant entitlement;
the operator must review these facts before opening sales.

## Runtime and security boundaries

- Only Nginx publishes ports. Gunicorn and data stores stay on the Compose network.
  Gunicorn, application worker, Nginx and backup commands run without root where
  supported. App filesystem is read-only except named media/static volumes and `/tmp`.
- PostgreSQL data and authenticated Redis AOF use durable volumes. Redis has
  `noeviction`, a 256 MB configured limit and fail-closed authentication/rate limits.
  Monitor memory before scaling; session loss logs customers out, so Redis is not
  a disposable cache in this configuration.
- Nginx replaces forwarding headers; `TRUST_PROXY_HEADERS=True` is safe only when
  the application port is inaccessible to untrusted clients. Nginx enforces general
  and login request budgets in addition to application-level OTP/action limits.
- Raw certificate storage is never public. Verified, current documents are sent
  by Django through an attachment endpoint after checking active catalog records.
- Sessions and CSRF cookies require HTTPS in production. HTML/JSON private routes
  send noindex, and private transactional pages are not cached.
- Proxy/Gunicorn access logs omit query strings and private URL paths. Application
  logs avoid OTPs/API keys. Do not add request-body logging at a CDN or proxy.
- `DEMO_MODE=False` and `ALLOW_SANDBOX_PAYMENTS=False` apply to production. Demo
  seed commands cannot be used to initialize a live shop.
- Sensitive financial records are read-only in admin. Order fulfillment actions
  invoke the transactional state service; changing a status field cannot fabricate
  payment. Restrict staff permissions and use separate individual operator accounts.

## Background jobs and message delivery

The `worker` container checks expired reservations every 30 seconds, queues
abandoned-cart reminders hourly, and applies retention daily. Notifications are
dispatched only when `NOTIFICATIONS_ENABLED=True`; configure a real sender first.
Abandoned-cart reminders require current explicit marketing consent, a nonempty
active cart and a last item update at least 24 hours ago. The queue deduplicates
per cart and rechecks consent/cart state immediately before delivery.

Order events/outbox rows commit atomically with order state. Notification workers
lock the outbox row, retry at most three attempts and skip delivered rows. An SMS
provider accepting a message and losing its network acknowledgement can still
produce a duplicate on retry: delivery is at-least-once, not exactly-once across
an external network. Monitor failed/ambiguous attempts before resending manually.

Retention defaults: behavioral analytics and AI usage 90 days, queued/delivered
message data 90 days, closed support tickets 365 days. The pruning command keeps
financial orders/payments/refunds. Set financial record retention with the business's
accounting/legal requirements; this project does not invent a jurisdictional term.
Revoking behavioral consent deletes the current visitor's telemetry and removes
purchase attribution, without erasing financial accounting records.

## Backups

Create the host `backups/` folder with write access for the backup image's `postgres`
user (UID 70 on the tested Alpine image). Restrict access to the deployment owner
and backup operator. For example, on Linux, create/chown this one explicitly named
directory after verifying the deployment path; never recursively change the host root.

```sh
docker compose --env-file .env.production -f compose.production.yml run --rm backup
```

This produces a custom-format PostgreSQL dump, matching media archive and SHA-256
files. It checks archive structure before renaming temporary outputs. Files use
restrictive creation permissions. Static assets are reproducible from the image
and need no separate backup. Uploaded originals/certificates are in the media
archive; derivatives can be regenerated.

Install the provided `deploy/systemd/jahantab-backup.{service,timer}` on a Linux
host after adapting the deployment path and the `deploy` service account. The timer
is daily at 03:00 Asia/Tehran with a short randomized delay and catch-up for missed
runs. The timer files were authored here; they were not installed on this Windows
machine. On another scheduler, invoke the same backup command daily.

Policy: retain at least 30 daily and 12 monthly verified copies, keep an encrypted
off-host copy, and rehearse recovery monthly. Use your organization's encryption
and storage system; no off-site destination or key was supplied or configured.
Never delete a last known-good copy before verifying its replacement. Keep secret
configuration in a separate restricted secret store; do not bundle `.env` with
web-accessible media or plaintext public artifacts.

## Restore rehearsal

Always restore into a new database first; preserve the live database and archive.
Validate the checksum and `pg_restore --list`, create a new staging database, then:

```sh
docker compose --env-file .env.production -f compose.production.yml run --rm --entrypoint pg_restore backup --exit-on-error --no-owner --no-acl --dbname=NEW_RESTORE_DATABASE /backups/SELECTED.dump
```

Restore the paired media archive into a new staging volume, not directly over
live media. Verify migration count, representative order/payment/refund totals,
owner access checks and actual uploaded document bytes. Start a staging app
against that database/volume with external notifications and AI disabled. Promote
only after validation; arrange a maintenance window before switching traffic.

For the isolated local smoke environment only:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/prepare_smoke.py
docker compose --env-file .env.production -f compose.production.yml -f compose.smoke.yml up -d --build
docker compose --env-file .env.production -f compose.production.yml -f compose.smoke.yml up -d --no-deps --force-recreate nginx
.\.venv\Scripts\python.exe -X utf8 scripts/verify_smoke.py --restore
```

`prepare_smoke.py` preserves existing files and creates local-only credentials.
`verify_smoke.py` refuses a non-loopback origin. It verifies HTTPS using the local
certificate as a trusted test CA, HTTP health/static endpoints, raw certificate
blocking, non-root identity, Nginx and Django checks, and restores a fresh dump
into a uniquely named staging database. It compares source/restored migration and
probe counts and verifies a file from the paired media archive. The source DB is
never dropped or overwritten. Results are saved to
`artifacts/verification/tls-and-restore.json`. Test restore databases/archives are
left for inspection; clean them up deliberately after reviewing their exact names.

## Updates, rollback and monitoring

1. Tag/store the current application image immutably and take a fresh paired backup.
2. Build/test the next image, inspect its migration plan, then run the release job.
3. Start the new web/worker image and check readiness, login, catalog, checkout,
   payment callbacks and private receipt access. Nginx resolves the application
   service through Docker DNS so container IP changes do not require stale upstreams.
4. If application code regresses and the schema is compatible, switch `APP_IMAGE`
   to the previous immutable image and recreate web/worker. Re-run its compatible
   static collection. Never run a blind reverse migration on paid-order data.
5. If schema/data recovery is needed, use a maintenance window, restore into new
   database/media volumes, validate, and switch. Keep the failed volumes intact for
   investigation. Reconcile any bank transactions accepted after the backup.

Monitor `/health/` (503 if PostgreSQL or Redis fails), container restarts, error
rate, p95 response time, database storage, Redis memory, failed payment verification,
expiring reservations, notification failures, AI token usage and backup age. Point
your monitoring system at these signals; no external monitoring account was given.
Rotate logs at the Docker host and never retain request bodies or OTP values.
