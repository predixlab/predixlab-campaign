from __future__ import annotations

import azure.functions as func

from predixlab_campaign.config import load_settings
from predixlab_campaign.delivery import deliver_campaign_message
from predixlab_campaign.queues import decode_queue_text, process_campaign_event

settings = load_settings()
app = func.FunctionApp()


@app.queue_trigger(
    arg_name='message',
    queue_name=settings.campaign_events_queue,
    connection='AzureWebJobsStorage',
)
def campaign_events_queue_trigger(message: func.QueueMessage) -> None:
    """Validate and fan out campaign entry messages."""
    process_campaign_event(decode_queue_text(message), settings=settings)


@app.queue_trigger(
    arg_name='message',
    queue_name=settings.campaign_delivery_queue,
    connection='AzureWebJobsStorage',
)
def campaign_delivery_queue_trigger(message: func.QueueMessage) -> None:
    """Render and deliver one consented campaign message."""
    deliver_campaign_message(decode_queue_text(message), settings=settings)
