from __future__ import annotations

from datetime import datetime, timezone

import pytest

from predixlab_campaign.config import Settings


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        storage_connection_string='UseDevelopmentStorage=true',
        campaign_events_queue='campaign-events',
        campaign_delivery_queue='campaign-delivery',
        campaign_delivery_backend='console',
        acs_connection_string='endpoint=https://example.invalid/;accesskey=fake',
        acs_sender='no-reply@predixlab.test',
        mongodb_url='mongodb://unused',
        database_name='predixlab',
        users_collection='users',
        pivot_picks_collection='pivot_picks',
        alpharank_collection='alpharank',
        alpharank_generations_collection='alpharank_generations',
        campaign_deliveries_collection='campaign_deliveries',
        app_name='PredixLab',
        public_api_url='https://api.predixlab.test',
        secret_key='unit-test-secret',
        delivery_lease_seconds=300,
    )


@pytest.fixture()
def utc_now() -> datetime:
    return datetime(2026, 8, 15, 0, 10, tzinfo=timezone.utc)


@pytest.fixture()
def daily_digest_payload() -> dict:
    return {
        'market': 'us',
        'date': '2026-08-15',
        'pivot_picks': [
            {
                'symbol': 'AAPL',
                'direction': 'long',
                'rank': 1,
                'confidence': 0.771,
            },
            {
                'symbol': 'NVDA',
                'direction': 'long',
                'rank': 2,
                'confidence': 0.689,
            },
            {
                'symbol': 'TSLA',
                'direction': 'short',
                'rank': 1,
                'confidence': 0.665,
            },
        ],
        'alpha_rank': [
            {'symbol': 'NVDA', 'rank': 1, 'score': 0.934},
            {'symbol': 'MSFT', 'rank': 2, 'score': 0.901},
        ],
    }


@pytest.fixture()
def daily_delivery_payload(daily_digest_payload: dict) -> dict:
    return {
        'schema_version': 1,
        'type': 'campaign.delivery.daily_signals',
        'delivery_id': 'daily-signals:us:2026-08-15:u-1',
        'campaign_id': 'daily-signals:us:2026-08-15',
        'recipient': {
            'user_id': 'u-1',
            'email': 'alice@example.com',
            'name': 'Alice',
            'locale': 'en',
        },
        'digest': daily_digest_payload,
        'metadata': {
            'source': 'predixlab-campaign',
            'user_id': 'u-1',
        },
    }
