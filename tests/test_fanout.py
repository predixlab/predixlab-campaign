from __future__ import annotations

from datetime import timedelta

import pytest

from predixlab_campaign.contracts import DailySignalsCampaignEvent
from predixlab_campaign.fanout import (
    build_daily_signals_user_filter,
    dispatch_daily_signals_campaign,
    user_is_eligible,
)


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def send_json(self, queue_name: str, payload: dict) -> None:
        self.messages.append((queue_name, payload))


class FakeUsersCollection:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.last_filter = None

    def find(self, filter_doc, projection):
        self.last_filter = filter_doc
        return list(self.documents)


class FakeDigestRepository:
    def __init__(self, digest: dict) -> None:
        self.digest = digest
        self.calls: list[tuple[str, str]] = []

    def load_digest(self, *, market: str, date: str):
        self.calls.append((market, date))
        return self.digest


def test_daily_signals_fanout_applies_consent_premium_and_admin_rules(
    settings,
    daily_digest_payload: dict,
    utc_now,
) -> None:
    users = FakeUsersCollection(
        [
            {
                '_id': 'u-en',
                'email': 'alice@example.com',
                'name': 'Alice',
                'role': 'premium',
                'is_active': True,
                'marketing_emails_enabled': True,
                'daily_signals_email_enabled': True,
                'preferred_language': 'en',
                'premium_expires_at': None,
            },
            {
                '_id': 'u-zh',
                'email': 'zhang@example.com',
                'name': '张三',
                'role': 'premium',
                'preferred_language': 'zh-CN',
                'premium_expires_at': utc_now + timedelta(days=30),
            },
            {
                '_id': 'free',
                'email': 'free@example.com',
                'role': 'free',
            },
            {
                '_id': 'admin',
                'email': 'admin@example.com',
                'name': 'Admin',
                'role': 'admin',
                'is_active': True,
                'marketing_emails_enabled': True,
                'daily_signals_email_enabled': True,
                'preferred_language': 'en',
                'premium_expires_at': utc_now - timedelta(days=30),
            },
            {
                '_id': 'marketing-unsubscribed',
                'email': 'marketing-unsub@example.com',
                'role': 'premium',
                'marketing_emails_enabled': False,
            },
            {
                '_id': 'daily-unsubscribed',
                'email': 'daily-unsub@example.com',
                'role': 'premium',
                'daily_signals_email_enabled': False,
            },
            {
                '_id': 'expired',
                'email': 'expired@example.com',
                'role': 'premium',
                'premium_expires_at': utc_now - timedelta(seconds=1),
            },
        ]
    )
    repository = FakeDigestRepository(daily_digest_payload)
    publisher = FakePublisher()
    event = DailySignalsCampaignEvent(
        schema_version=1,
        type='campaign.daily_signals',
        campaign_id='daily-signals:us:2026-08-15',
        market='us',
        date='2026-08-15',
        metadata={'source': 'predixlab-signals'},
    )

    count = dispatch_daily_signals_campaign(
        event,
        settings=settings,
        publisher=publisher,
        users_collection=users,
        daily_signals_repository=repository,
        now=utc_now,
    )

    assert count == 4
    assert repository.calls == [('us', '2026-08-15')]
    assert users.last_filter == build_daily_signals_user_filter(utc_now)
    assert [queue for queue, _ in publisher.messages] == [
        'campaign-delivery',
        'campaign-delivery',
        'campaign-delivery',
        'campaign-delivery',
    ]
    first = publisher.messages[0][1]
    second = publisher.messages[1][1]
    third = publisher.messages[2][1]
    fourth = publisher.messages[3][1]
    assert first['delivery_id'] == 'daily-signals:us:2026-08-15:u-en'
    assert first['type'] == 'campaign.delivery.daily_signals'
    assert first['recipient'] == {
        'user_id': 'u-en',
        'email': 'alice@example.com',
        'name': 'Alice',
        'locale': 'en',
    }
    assert second['recipient']['locale'] == 'zh'
    assert third['recipient'] == {
        'user_id': 'admin',
        'email': 'admin@example.com',
        'name': 'Admin',
        'locale': 'en',
    }
    assert fourth['recipient']['user_id'] == 'marketing-unsubscribed'
    assert first['metadata']['source'] == 'predixlab-campaign'
    assert first['metadata']['origin_source'] == 'predixlab-signals'


def test_user_guard_accepts_admin_without_premium_expiry(utc_now) -> None:
    assert user_is_eligible(
        {
            'role': 'admin',
            'premium_expires_at': utc_now - timedelta(days=1),
        },
        utc_now,
    )


def test_user_guard_rejects_invalid_expiry_type(utc_now) -> None:
    with pytest.raises(ValueError, match='premium_expires_at'):
        user_is_eligible(
            {
                'role': 'premium',
                'premium_expires_at': '2026-09-01',
            },
            utc_now,
        )
