from __future__ import annotations

import pytest

from predixlab_campaign.config import Settings


def test_settings_use_campaign_specific_environment(monkeypatch) -> None:
    monkeypatch.setenv('AzureWebJobsStorage', 'storage')
    monkeypatch.setenv('CAMPAIGN_EVENTS_QUEUE', 'events-v2')
    monkeypatch.setenv('CAMPAIGN_DELIVERY_QUEUE', 'delivery-v2')
    monkeypatch.setenv('CAMPAIGN_DELIVERY_BACKEND', 'console')
    monkeypatch.setenv('CAMPAIGN_DELIVERIES_COLLECTION', 'deliveries-v2')
    monkeypatch.setenv('CAMPAIGN_APP_NAME', 'PredixLab Test')
    monkeypatch.setenv('CAMPAIGN_DELIVERY_LEASE_SECONDS', '120')

    settings = Settings.from_env()

    assert settings.campaign_events_queue == 'events-v2'
    assert settings.campaign_delivery_queue == 'delivery-v2'
    assert settings.campaign_delivery_backend == 'console'
    assert settings.campaign_deliveries_collection == 'deliveries-v2'
    assert settings.app_name == 'PredixLab Test'
    assert settings.delivery_lease_seconds == 120


@pytest.mark.parametrize(
    'unsubscribe_secret',
    [None, '', 'unsubscribe-test-secret'],
)
def test_settings_load_unsubscribe_secret_with_fallback(
    monkeypatch,
    unsubscribe_secret: str | None,
) -> None:
    monkeypatch.setenv('SECRET_KEY', 'api-test-secret')
    if unsubscribe_secret is None:
        monkeypatch.delenv('UNSUBSCRIBE_SECRET', raising=False)
    else:
        monkeypatch.setenv('UNSUBSCRIBE_SECRET', unsubscribe_secret)

    settings = Settings.from_env()

    assert settings.secret_key == 'api-test-secret'
    assert settings.unsubscribe_secret == (
        unsubscribe_secret or 'api-test-secret'
    )


@pytest.mark.parametrize('lease_seconds', ['0', '-1'])
def test_settings_reject_non_positive_delivery_lease(
    monkeypatch,
    lease_seconds: str,
) -> None:
    monkeypatch.setenv('CAMPAIGN_DELIVERY_LEASE_SECONDS', lease_seconds)

    with pytest.raises(ValueError, match='CAMPAIGN_DELIVERY_LEASE_SECONDS'):
        Settings.from_env()
