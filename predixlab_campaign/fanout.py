from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .config import Settings, load_settings
from .contracts import (
    CampaignRecipient,
    DailySignalsCampaignEvent,
    DailySignalsDeliveryEvent,
    event_to_payload,
    metadata_to_dict,
)
from .repository import MongoDailySignalsDigestRepository
from .templates import normalize_language

DAILY_SIGNALS_ROLES = ('premium', 'admin')


def build_daily_signals_user_filter(now: datetime) -> dict[str, Any]:
    """Return the MongoDB filter for eligible daily-signals recipients."""
    return {
        '$and': [
            {'role': {'$in': list(DAILY_SIGNALS_ROLES)}},
            {'$or': [{'is_active': {'$exists': False}}, {'is_active': {'$ne': False}}]},
            {
                '$or': [
                    {'daily_signals_email_enabled': {'$exists': False}},
                    {'daily_signals_email_enabled': None},
                    {'daily_signals_email_enabled': {'$ne': False}},
                ]
            },
            {
                '$or': [
                    {'role': 'admin'},
                    {'premium_expires_at': {'$exists': False}},
                    {'premium_expires_at': None},
                    {'premium_expires_at': {'$gt': now}},
                ]
            },
        ]
    }


def user_is_eligible(user: Mapping[str, Any], now: datetime) -> bool:
    """Apply daily-signals audience rules in Python as a guardrail."""
    role = user.get('role')
    if role not in DAILY_SIGNALS_ROLES:
        return False
    if user.get('is_active') is False:
        return False
    if user.get('daily_signals_email_enabled') is False:
        return False
    if role == 'admin':
        return True
    expires_at = user.get('premium_expires_at')
    if expires_at in (None, ''):
        return True
    if not isinstance(expires_at, datetime):
        raise ValueError('premium_expires_at must be a datetime when present')
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = expires_at.astimezone(timezone.utc)
    return expires_at > now


def dispatch_daily_signals_campaign(
    event: DailySignalsCampaignEvent,
    *,
    settings: Settings | None = None,
    publisher: Any,
    users_collection: Any | None = None,
    daily_signals_repository: Any | None = None,
    now: datetime | None = None,
) -> int:
    """Fan out a daily-signals campaign to eligible premium and admin users."""
    settings = settings or load_settings()
    now = now or datetime.now(timezone.utc)
    own_client = None
    if users_collection is None or daily_signals_repository is None:
        if not settings.mongodb_url or not settings.database_name:
            raise ValueError('MONGODB_URL and DATABASE_NAME are required for campaign fan-out')
        from pymongo import MongoClient

        own_client = MongoClient(settings.mongodb_url)
        database = own_client[settings.database_name]
        users_collection = users_collection or database[settings.users_collection]
        daily_signals_repository = daily_signals_repository or (
            MongoDailySignalsDigestRepository.from_database(database, settings)
        )

    sent = 0
    try:
        digest = daily_signals_repository.load_digest(
            market=event.market,
            date=event.date,
        )
        entry_metadata = metadata_to_dict(event.metadata)
        for user in users_collection.find(
            build_daily_signals_user_filter(now),
            {
                '_id': 1,
                'email': 1,
                'name': 1,
                'role': 1,
                'is_active': 1,
                'daily_signals_email_enabled': 1,
                'preferred_language': 1,
                'premium_expires_at': 1,
            },
        ):
            if not user_is_eligible(user, now):
                continue
            user_id = str(user['_id'])
            payload = DailySignalsDeliveryEvent(
                schema_version=1,
                type='campaign.delivery.daily_signals',
                delivery_id=f'{event.campaign_id}:{user_id}',
                campaign_id=event.campaign_id,
                recipient=CampaignRecipient(
                    user_id=user_id,
                    email=str(user['email']),
                    name=user.get('name'),
                    locale=normalize_language(user.get('preferred_language')),
                ),
                digest=digest,
                metadata={
                    **entry_metadata,
                    'origin_source': entry_metadata['source'],
                    'source': 'predixlab-campaign',
                    'campaign_id': event.campaign_id,
                    'user_id': user_id,
                },
            )
            publisher.send_json(
                settings.campaign_delivery_queue,
                event_to_payload(payload),
            )
            sent += 1
        return sent
    finally:
        if own_client is not None:
            own_client.close()
