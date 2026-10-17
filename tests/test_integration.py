from __future__ import annotations

from predixlab_campaign.delivery import ClaimResult, deliver_campaign_message
from predixlab_campaign.queues import process_campaign_event


class Publisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def send_json(self, queue_name: str, payload: dict) -> None:
        self.messages.append((queue_name, payload))


class Users:
    def find(self, filter_doc, projection):
        return [
            {
                '_id': 'u-1',
                'email': 'alice@example.com',
                'name': 'Alice',
                'role': 'premium',
                'is_active': True,
                'marketing_emails_enabled': True,
                'preferred_language': 'en',
                'premium_expires_at': None,
            }
        ]


class DigestRepository:
    def __init__(self, digest: dict) -> None:
        self.digest = digest

    def load_digest(self, *, market: str, date: str):
        return self.digest


class DeliveryRepository:
    def __init__(self) -> None:
        self.subject = None

    def claim(self, event):
        return ClaimResult(claimed=True, status='processing')

    def mark_sent(self, event, *, rendered, provider_result, now=None):
        self.subject = rendered.subject

    def mark_failed(self, event, *, error, now=None):
        raise AssertionError(f'Unexpected delivery failure: {error}')


class Sender:
    def __init__(self) -> None:
        self.rendered = None

    def send(self, event, rendered):
        self.rendered = rendered
        return {'id': 'acs-integration'}


def test_campaign_entry_fans_out_and_delivers(
    settings,
    daily_digest_payload: dict,
) -> None:
    publisher = Publisher()
    count = process_campaign_event(
        {
            'schema_version': 1,
            'type': 'campaign.daily_signals',
            'campaign_id': 'daily-signals:us:2026-08-15',
            'market': 'us',
            'date': '2026-08-15',
            'metadata': {'source': 'predixlab-signals'},
        },
        settings=settings,
        publisher=publisher,
        users_collection=Users(),
        daily_signals_repository=DigestRepository(daily_digest_payload),
    )

    assert count == 1
    queue_name, payload = publisher.messages[0]
    assert queue_name == 'campaign-delivery'

    repository = DeliveryRepository()
    sender = Sender()
    result = deliver_campaign_message(
        payload,
        settings=settings,
        repository=repository,
        sender=sender,
    )

    assert result.status == 'sent'
    assert repository.subject == 'PredixLab Daily Signals — 2026-08-15'
    assert sender.rendered.headers['List-Unsubscribe-Post'] == (
        'List-Unsubscribe=One-Click'
    )
