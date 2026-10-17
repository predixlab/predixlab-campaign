from __future__ import annotations

from predixlab_campaign.queues import decode_queue_text, process_campaign_event


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def send_json(self, queue_name: str, payload: dict) -> None:
        self.messages.append((queue_name, payload))


class FakeUsers:
    def find(self, filter_doc, projection):
        return []


class FakeRepository:
    def load_digest(self, *, market: str, date: str):
        return {
            'market': market,
            'date': date,
            'pivot_picks': [],
            'alpha_rank': [],
        }


class QueueMessage:
    def get_body(self):
        return b'campaign'


def test_campaign_queue_dispatches_daily_signals(settings) -> None:
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
        publisher=FakePublisher(),
        users_collection=FakeUsers(),
        daily_signals_repository=FakeRepository(),
    )

    assert count == 0


def test_decode_queue_text_supports_azure_message_shape() -> None:
    assert decode_queue_text(QueueMessage()) == 'campaign'
