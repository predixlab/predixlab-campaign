from __future__ import annotations

import pytest

from predixlab_campaign.delivery import (
    CampaignDeliveryRepository,
    ClaimResult,
    deliver_campaign_message,
)


class FakeRepository:
    def __init__(self, sent: bool = False) -> None:
        self.sent = sent
        self.failed: list[str] = []
        self.recorded_subjects: list[str] = []

    def claim(self, event):
        if self.sent:
            return ClaimResult(
                claimed=False,
                status='sent',
                reason='already-sent',
            )
        return ClaimResult(claimed=True, status='processing')

    def mark_sent(self, event, *, rendered, provider_result, now=None):
        self.sent = True
        self.recorded_subjects.append(rendered.subject)

    def mark_failed(self, event, *, error, now=None):
        self.failed.append(str(error))


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def send(self, event, rendered):
        self.calls.append((event, rendered))
        if self.error:
            raise self.error
        return {'id': 'acs-1'}


@pytest.mark.parametrize('lease_seconds', [0, -1])
def test_delivery_repository_rejects_non_positive_lease(
    lease_seconds: int,
) -> None:
    with pytest.raises(ValueError, match='lease_seconds'):
        CampaignDeliveryRepository(object(), lease_seconds=lease_seconds)


def test_delivery_is_idempotent(
    settings,
    daily_delivery_payload: dict,
) -> None:
    repository = FakeRepository(sent=True)
    sender = FakeSender()

    result = deliver_campaign_message(
        daily_delivery_payload,
        settings=settings,
        repository=repository,
        sender=sender,
    )

    assert result.reason == 'already-sent'
    assert sender.calls == []


def test_delivery_renders_sends_and_records_success(
    settings,
    daily_delivery_payload: dict,
) -> None:
    repository = FakeRepository()
    sender = FakeSender()

    result = deliver_campaign_message(
        daily_delivery_payload,
        settings=settings,
        repository=repository,
        sender=sender,
    )

    assert result.status == 'sent'
    assert len(sender.calls) == 1
    assert repository.recorded_subjects == [
        'PredixLab Daily Signals — 2026-08-15'
    ]


def test_delivery_records_sender_failure(
    settings,
    daily_delivery_payload: dict,
) -> None:
    repository = FakeRepository()
    sender = FakeSender(RuntimeError('ACS down'))

    with pytest.raises(RuntimeError, match='ACS down'):
        deliver_campaign_message(
            daily_delivery_payload,
            settings=settings,
            repository=repository,
            sender=sender,
        )

    assert repository.failed == ['ACS down']
