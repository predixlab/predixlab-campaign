from __future__ import annotations

import pytest

from predixlab_campaign.contracts import (
    event_to_payload,
    parse_campaign_event,
    parse_delivery_event,
)


def test_daily_signals_campaign_contract_normalizes_market() -> None:
    event = parse_campaign_event(
        {
            'schema_version': 1,
            'type': 'campaign.daily_signals',
            'campaign_id': 'daily-signals:us:2026-08-15',
            'market': ' US ',
            'date': '2026-08-15',
            'metadata': {'source': 'predixlab-signals'},
        }
    )

    assert event.market == 'us'
    assert event_to_payload(event)['schema_version'] == 1


def test_delivery_contract_contains_only_campaign_visible_signal_fields(
    daily_delivery_payload: dict,
) -> None:
    event = parse_delivery_event(daily_delivery_payload)
    payload = event_to_payload(event)

    assert payload['type'] == 'campaign.delivery.daily_signals'
    assert payload['recipient']['email'] == 'alice@example.com'
    assert set(payload['digest']['pivot_picks'][0]) == {
        'symbol',
        'direction',
        'rank',
        'confidence',
    }
    assert set(payload['digest']['alpha_rank'][0]) == {
        'symbol',
        'rank',
        'score',
    }


@pytest.mark.parametrize(
    'type_name',
    [
        'email.send.login_verification',
        'email.send.subscription_success',
        'email.send.collector_job_status',
        'email.send.signals_job_status',
    ],
)
def test_transactional_and_operator_email_types_are_rejected(
    type_name: str,
) -> None:
    with pytest.raises(ValueError, match='Invalid campaign message'):
        parse_campaign_event(
            {
                'schema_version': 1,
                'type': type_name,
                'campaign_id': 'not-a-campaign',
                'metadata': {'source': 'legacy-producer'},
            }
        )


def test_delivery_rejects_invalid_recipient_email(
    daily_delivery_payload: dict,
) -> None:
    daily_delivery_payload['recipient']['email'] = 'not-an-email'

    with pytest.raises(ValueError, match='Invalid campaign delivery message'):
        parse_delivery_event(daily_delivery_payload)


def test_daily_signals_requires_deterministic_campaign_id() -> None:
    with pytest.raises(ValueError, match='campaign_id'):
        parse_campaign_event(
            {
                'schema_version': 1,
                'type': 'campaign.daily_signals',
                'campaign_id': 'daily-signals:wrong',
                'market': 'us',
                'date': '2026-08-15',
                'metadata': {'source': 'predixlab-signals'},
            }
        )
