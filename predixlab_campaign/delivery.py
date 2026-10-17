from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings, load_settings
from .contracts import CampaignDeliveryEvent, metadata_to_dict, parse_delivery_event
from .templates import RenderedCampaign, render_campaign

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimResult:
    """Result of trying to acquire a delivery lease."""

    claimed: bool
    status: str
    document: dict[str, Any] | None = None
    reason: str | None = None


class AcsCampaignSender:
    """Synchronous ACS sender for one campaign delivery."""

    def __init__(self, client: Any, sender_address: str):
        self.client = client
        self.sender_address = sender_address

    @classmethod
    def from_connection_string(
        cls,
        connection_string: str,
        sender_address: str,
    ) -> 'AcsCampaignSender':
        if not connection_string or not sender_address:
            raise ValueError('ACS_CONNECTION_STRING and ACS_SENDER are required for delivery')
        from azure.communication.email import EmailClient

        client = EmailClient.from_connection_string(connection_string)
        return cls(client=client, sender_address=sender_address)

    def send(
        self,
        event: CampaignDeliveryEvent,
        rendered: RenderedCampaign,
    ) -> Any:
        """Send one rendered campaign message through ACS."""
        message: dict[str, Any] = {
            'senderAddress': self.sender_address,
            'recipients': {
                'to': [{'address': event.recipient.email}],
            },
            'content': {
                'subject': rendered.subject,
                'html': rendered.html,
                'plainText': rendered.text,
            },
        }
        if rendered.headers:
            message['headers'] = rendered.headers
        poller = self.client.begin_send(message)
        return poller.result()


class ConsoleCampaignSender:
    """Development sender that logs campaigns instead of calling ACS."""

    def send(
        self,
        event: CampaignDeliveryEvent,
        rendered: RenderedCampaign,
    ) -> Any:
        logger.info(
            '[console campaign backend] delivery_id=%s campaign_id=%s type=%s to=%s subject=%s headers=%s text=%s',
            event.delivery_id,
            event.campaign_id,
            event.type,
            event.recipient.email,
            rendered.subject,
            rendered.headers,
            rendered.text.strip(),
        )
        return {'id': f'console:{event.delivery_id}'}


class CampaignDeliveryRepository:
    """Persist campaign delivery state with a short processing lease."""

    def __init__(self, collection: Any, lease_seconds: int = 300, owner_id: str | None = None):
        if lease_seconds <= 0:
            raise ValueError('lease_seconds must be greater than zero')
        self.collection = collection
        self.lease_seconds = lease_seconds
        self.owner_id = owner_id or str(uuid.uuid4())

    def claim(
        self,
        event: CampaignDeliveryEvent,
        now: datetime | None = None,
    ) -> ClaimResult:
        """Claim a campaign delivery unless it was already sent."""
        now = now or datetime.now(timezone.utc)
        if self.collection.find_one({'_id': event.delivery_id, 'status': 'sent'}):
            return ClaimResult(claimed=False, status='sent', reason='already-sent')

        seed = {
            '_id': event.delivery_id,
            'delivery_id': event.delivery_id,
            'campaign_id': event.campaign_id,
            'type': event.type,
            'locale': event.recipient.locale,
            'status': 'queued',
            'recipient': event.recipient.model_dump(mode='json', exclude_none=True),
            'metadata': metadata_to_dict(event.metadata),
            'created_at': now,
            'updated_at': now,
            'attempt_count': 0,
        }
        from pymongo.errors import DuplicateKeyError

        try:
            self.collection.insert_one(seed)
        except DuplicateKeyError:
            pass

        filter_doc = {
            '_id': event.delivery_id,
            'status': {'$ne': 'sent'},
            '$or': [
                {'lease_expires_at': {'$exists': False}},
                {'lease_expires_at': None},
                {'lease_expires_at': {'$lte': now}},
            ],
        }
        update_doc = {
            '$set': {
                'type': event.type,
                'campaign_id': event.campaign_id,
                'locale': event.recipient.locale,
                'status': 'processing',
                'lease_owner': self.owner_id,
                'lease_expires_at': now + timedelta(seconds=self.lease_seconds),
                'updated_at': now,
                'last_attempt_at': now,
                'recipient': event.recipient.model_dump(
                    mode='json',
                    exclude_none=True,
                ),
                'metadata': metadata_to_dict(event.metadata),
            },
            '$inc': {'attempt_count': 1},
        }
        return_document = _return_document_after()
        document = self.collection.find_one_and_update(
            filter_doc,
            update_doc,
            return_document=return_document,
        )
        if document is None:
            existing = self.collection.find_one({'_id': event.delivery_id})
            if existing and existing.get('status') == 'sent':
                return ClaimResult(
                    claimed=False,
                    status='sent',
                    document=existing,
                    reason='already-sent',
                )
            return ClaimResult(
                claimed=False,
                status='processing',
                document=existing,
                reason='lease-active',
            )
        return ClaimResult(claimed=True, status='processing', document=document)

    def mark_sent(
        self,
        event: CampaignDeliveryEvent,
        *,
        rendered: RenderedCampaign,
        provider_result: Any,
        now: datetime | None = None,
    ) -> None:
        """Persist successful delivery and release the lease."""
        now = now or datetime.now(timezone.utc)
        update_result = self.collection.update_one(
            {'_id': event.delivery_id, 'lease_owner': self.owner_id},
            {
                '$set': {
                    'type': event.type,
                    'campaign_id': event.campaign_id,
                    'locale': event.recipient.locale,
                    'subject': rendered.subject,
                    'status': 'sent',
                    'sent_at': now,
                    'updated_at': now,
                    'provider_message_id': _provider_message_id(provider_result),
                    'provider_result': provider_result,
                    'last_error': None,
                },
                '$unset': {
                    'lease_owner': '',
                    'lease_expires_at': '',
                    'failed_at': '',
                },
            },
        )
        if not _was_modified(update_result):
            raise RuntimeError(
                f'Could not mark {event.delivery_id} as sent; lease was lost'
            )

    def mark_failed(
        self,
        event: CampaignDeliveryEvent,
        *,
        error: Exception,
        now: datetime | None = None,
    ) -> None:
        """Persist failure details and release the lease before retry."""
        now = now or datetime.now(timezone.utc)
        update_result = self.collection.update_one(
            {'_id': event.delivery_id, 'lease_owner': self.owner_id},
            {
                '$set': {
                    'type': event.type,
                    'campaign_id': event.campaign_id,
                    'locale': event.recipient.locale,
                    'status': 'failed',
                    'failed_at': now,
                    'updated_at': now,
                    'last_error': str(error),
                },
                '$unset': {
                    'lease_owner': '',
                    'lease_expires_at': '',
                },
            },
        )
        if not _was_modified(update_result):
            raise RuntimeError(
                f'Could not mark {event.delivery_id} as failed; lease was lost'
            )


def deliver_campaign_message(
    payload: str | bytes | dict[str, Any],
    *,
    settings: Settings | None = None,
    repository: CampaignDeliveryRepository | None = None,
    sender: AcsCampaignSender | ConsoleCampaignSender | Any | None = None,
) -> ClaimResult:
    """Deliver one campaign payload with idempotency."""
    settings = settings or load_settings()
    event = parse_delivery_event(payload)
    own_client = None
    if repository is None:
        if not settings.mongodb_url or not settings.database_name:
            raise ValueError('MONGODB_URL and DATABASE_NAME are required for delivery')
        from pymongo import MongoClient

        own_client = MongoClient(settings.mongodb_url)
        repository = CampaignDeliveryRepository(
            own_client[settings.database_name][
                settings.campaign_deliveries_collection
            ],
            lease_seconds=settings.delivery_lease_seconds,
        )
    if sender is None:
        sender = build_sender(settings)
    try:
        claim = repository.claim(event)
        if not claim.claimed:
            return claim
        try:
            rendered = render_campaign(event, settings)
            provider_result = sender.send(event, rendered)
        except Exception as exc:
            repository.mark_failed(event, error=exc)
            raise
        repository.mark_sent(event, rendered=rendered, provider_result=provider_result)
        return ClaimResult(claimed=False, status='sent', reason='sent')
    finally:
        if own_client is not None:
            own_client.close()


def build_sender(settings: Settings) -> AcsCampaignSender | ConsoleCampaignSender:
    """Build the configured delivery backend."""
    if settings.campaign_delivery_backend == 'console':
        return ConsoleCampaignSender()
    if settings.campaign_delivery_backend != 'acs':
        raise ValueError(
            'Unsupported CAMPAIGN_DELIVERY_BACKEND: '
            f'{settings.campaign_delivery_backend!r}'
        )
    return AcsCampaignSender.from_connection_string(
        settings.acs_connection_string,
        settings.acs_sender,
    )


def _provider_message_id(result: Any) -> str | None:
    if isinstance(result, dict):
        value = result.get('id')
        return str(value) if value is not None else None
    if hasattr(result, 'get'):
        value = result.get('id')
        return str(value) if value is not None else None
    value = getattr(result, 'id', None)
    return str(value) if value is not None else None


def _return_document_after() -> Any:
    from pymongo import ReturnDocument

    return ReturnDocument.AFTER


def _was_modified(update_result: Any) -> bool:
    modified = getattr(update_result, 'modified_count', None)
    matched = getattr(update_result, 'matched_count', None)
    if modified is not None:
        return modified > 0
    if matched is not None:
        return matched > 0
    return bool(update_result)
