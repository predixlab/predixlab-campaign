from __future__ import annotations

import json
from typing import Any

from .fanout import dispatch_daily_signals_campaign
from .config import Settings, load_settings
from .contracts import DailySignalsCampaignEvent, parse_campaign_event


class CampaignQueuePublisher:
    """UTF-8 JSON publisher for internal campaign queues."""

    def __init__(self, connection_string: str):
        if not connection_string:
            raise ValueError('AzureWebJobsStorage is required for queue publishing')
        self.connection_string = connection_string
        self._clients: dict[str, Any] = {}

    def send_json(self, queue_name: str, payload: dict[str, Any]) -> None:
        """Send one JSON message to the named storage queue."""
        message_text = json.dumps(payload, ensure_ascii=False)
        self._client_for(queue_name).send_message(message_text)

    def _client_for(self, queue_name: str) -> Any:
        client = self._clients.get(queue_name)
        if client is None:
            from azure.storage.queue import QueueClient

            client = QueueClient.from_connection_string(
                self.connection_string,
                queue_name,
            )
            self._clients[queue_name] = client
        return client


def decode_queue_text(message: Any) -> str:
    """Decode Azure Functions queue payloads to UTF-8 text."""
    if isinstance(message, str):
        return message
    if isinstance(message, bytes):
        return message.decode('utf-8')
    if hasattr(message, 'get_body'):
        body = message.get_body()
        if isinstance(body, bytes):
            return body.decode('utf-8')
        return str(body)
    raise TypeError(f'Unsupported queue message type: {type(message).__name__}')


def process_campaign_event(
    payload: str | bytes | dict[str, Any],
    *,
    settings: Settings | None = None,
    publisher: Any | None = None,
    users_collection: Any | None = None,
    daily_signals_repository: Any | None = None,
) -> int:
    """Validate and fan out one campaign entry message."""
    settings = settings or load_settings()
    event = parse_campaign_event(payload)
    publisher = publisher or CampaignQueuePublisher(
        settings.storage_connection_string
    )
    if isinstance(event, DailySignalsCampaignEvent):
        return dispatch_daily_signals_campaign(
            event,
            settings=settings,
            publisher=publisher,
            users_collection=users_collection,
            daily_signals_repository=daily_signals_repository,
        )
    raise ValueError(f'Unsupported campaign type: {event.type}')
