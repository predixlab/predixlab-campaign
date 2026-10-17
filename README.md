# PredixLab Campaign

[Contributing](CONTRIBUTING.md) | [Security](SECURITY.md) | [Apache-2.0](LICENSE)

Azure Functions application for PredixLab opt-in customer campaigns.

This project is intentionally **not** a general email service. Verification
codes, billing receipts, account-security mail, and operator notifications stay
with their owning systems. `predixlab-campaign` owns only consented marketing
deliveries such as the premium daily-signals digest.

## Quick start

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/). Tests use mocks and do not
require a running Functions host, MongoDB, ACS, or a storage account:

```bash
git clone https://github.com/predixlab/predixlab-campaign.git
cd predixlab-campaign
uv sync --frozen --extra test
uv run python -m pytest
```

For a local Functions host, install Azure Functions Core Tools v4, run Azurite
and an isolated MongoDB instance, then create local configuration:

```bash
cp local.settings.json.example local.settings.json
```

Edit that ignored file before starting the host. Keep
`CAMPAIGN_DELIVERY_BACKEND=console`, use only synthetic recipients and isolated
queues, set `PUBLIC_API_URL` to your local API, and replace `SECRET_KEY` with
the same strong JWT/unsubscribe signing key used by that API. Do not confuse it
with the API's independent OAuth `SESSION_SECRET_KEY`.

```bash
uv run func start
```

This host consumes queue messages; do not point local testing at production
queues or customer databases. It is not an HTTP campaign-submission API.

## Architecture

```text
campaign producer
  -> campaign-events
  -> validate campaign + load audience/content
  -> campaign-delivery (one message per recipient)
  -> consented/idempotent render + ACS delivery
```

- `campaign-events` accepts campaign entry events.
- `campaign-delivery` contains internal per-recipient deliveries.
- MongoDB stores delivery leases and final status in `campaign_deliveries`.
- All HTML/text templates, subjects, unsubscribe links, and RFC 8058 headers
  are owned by this project.
- Delivery is at-least-once. A deterministic `delivery_id` prevents ordinary
  queue retries from sending the same campaign twice.

## Scope

Currently supported:

- `campaign.daily_signals`: premium daily Pivot and AlphaRank digest.

Explicitly out of scope:

- login or registration verification codes;
- subscription success, renewal, cancellation, or payment receipts;
- collector and signals job-status notifications;
- arbitrary producer-supplied HTML or text.

New campaign types must add a typed entry contract, audience policy, internal
delivery contract, Function-owned HTML/text templates, and tests.

## Daily-signals contract

Publish this message to `CAMPAIGN_EVENTS_QUEUE`:

```json
{
  "schema_version": 1,
  "type": "campaign.daily_signals",
  "campaign_id": "daily-signals:us:2026-08-15",
  "market": "us",
  "date": "2026-08-15",
  "metadata": {
    "source": "predixlab-signals"
  }
}
```

The producer supplies no recipients, HTML, subject, or signal rows. The
Function:

1. loads the exact requested session from MongoDB;
2. validates a stable active AlphaRank generation;
3. loads public Pivot events only (`BUY_TURN`, `SELL_TURN`, `TREND_BUY`, `BASE_BREAKOUT`);
4. selects active premium and admin users subscribed to Daily Signals mail;
5. emits deterministic `campaign.delivery.daily_signals` messages;
6. renders localized HTML/text and sends through ACS.

The campaign never falls back to an older signal date. Missing or inconsistent
data raises an error so Azure Queue retry handling can retry the campaign.

## Customer-visible data

The digest follows the dashboard list scope and presentation order:

- AlphaRank: top 15 rank, symbol, score.
- Pivot: bullish/bearish grouping, position, symbol, confidence.

Model internals and unpublished event types are not included.

## Consent and unsubscribe

Daily signals require:

- `role` is `premium` or `admin`;
- `is_active != false`;
- `daily_signals_email_enabled != false`;
- premium users have no expired `premium_expires_at` (admins do not require one).

Missing `daily_signals_email_enabled` defaults to enabled for premium/admin
users. This preference is independent of general marketing email consent.
Every delivery includes a Daily Signals-specific unsubscribe URL plus
`List-Unsubscribe` and `List-Unsubscribe-Post` headers.

## Environment variables

- `AzureWebJobsStorage`
- `CAMPAIGN_EVENTS_QUEUE` (default `campaign-events`)
- `CAMPAIGN_DELIVERY_QUEUE` (default `campaign-delivery`)
- `CAMPAIGN_DELIVERY_BACKEND` (`acs` or `console`, default `acs`)
- `CAMPAIGN_DELIVERIES_COLLECTION` (default `campaign_deliveries`)
- `CAMPAIGN_DELIVERY_LEASE_SECONDS` (default `300`)
- `CAMPAIGN_APP_NAME` (default `PredixLab`)
- `ACS_CONNECTION_STRING`
- `ACS_SENDER`
- `MONGODB_URL`
- `DATABASE_NAME`
- `USERS_COLLECTION` (default `users`)
- `PIVOT_PICKS_COLLECTION` (default `pivot_picks`)
- `ALPHARANK_COLLECTION` (default `alpharank`)
- `ALPHARANK_GENERATIONS_COLLECTION` (default `alpharank_generations`)
- `PUBLIC_API_URL`
- `SECRET_KEY`

Use `CAMPAIGN_DELIVERY_BACKEND=console` for local rendering without ACS.

## Tests

```bash
uv run --extra test python -m pytest
```

## CI/CD

`.github/workflows/ci-cd.yml` runs the locked test suite for pull requests and
pushes to `main`. After a successful `main` test run, GitHub Actions deploys the
repository to the production `predixlab-campaign` Azure Function App using
GitHub OIDC and an Azure identity scoped to that Function App. The deploy job
builds `.python_packages` on the Linux runner before publishing so the
run-from-package artifact contains all production dependencies.

## Contributing and support

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and safe fixture
requirements. Use [GitHub Issues](https://github.com/predixlab/predixlab-campaign/issues)
for bugs and proposals, and [SECURITY.md](SECURITY.md) for private reports.
Preserve consent, unsubscribe, retry, and idempotency behavior when changing delivery.

## License

Copyright 2026 PredixLab contributors.

Project source is licensed under the [Apache License 2.0](LICENSE). Third-party
dependencies and services retain their own terms. The source license does not
grant access to mailing lists, customer records, or hosted infrastructure.
