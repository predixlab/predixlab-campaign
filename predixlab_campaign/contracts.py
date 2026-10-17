from __future__ import annotations

import json
from email.utils import parseaddr
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic import field_validator, model_validator

Locale = Literal['en', 'zh']
_DATE_PATTERN = r'^\d{4}-\d{2}-\d{2}$'


class EventMetadata(BaseModel):
    """Producer metadata retained across campaign fan-out and delivery."""

    model_config = ConfigDict(extra='allow')

    source: str = Field(min_length=1)

    @field_validator('source', mode='before')
    @classmethod
    def _strip_source(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CampaignEventBase(BaseModel):
    """Shared campaign entry envelope."""

    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1]
    campaign_id: str = Field(min_length=1)
    metadata: EventMetadata

    @field_validator('campaign_id', mode='before')
    @classmethod
    def _strip_campaign_id(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class DailySignalsCampaignEvent(CampaignEventBase):
    """Request a premium daily-signals campaign for one market session."""

    type: Literal['campaign.daily_signals']
    market: str = Field(min_length=1)
    date: str = Field(min_length=10, max_length=10, pattern=_DATE_PATTERN)

    @field_validator('market', mode='before')
    @classmethod
    def _normalize_market(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator('date', mode='before')
    @classmethod
    def _strip_date(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def _validate_campaign_id(self) -> 'DailySignalsCampaignEvent':
        expected = f'daily-signals:{self.market}:{self.date}'
        if self.campaign_id != expected:
            raise ValueError(
                f'daily-signals campaign_id must be {expected!r}'
            )
        return self


class CampaignRecipient(BaseModel):
    """One consented campaign recipient."""

    model_config = ConfigDict(extra='forbid')

    user_id: str = Field(min_length=1)
    email: str = Field(min_length=3)
    name: str | None = None
    locale: Locale

    @field_validator('user_id', 'name', mode='before')
    @classmethod
    def _strip_user_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator('email', mode='before')
    @classmethod
    def _validate_email(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        parsed = parseaddr(value.strip())[1]
        if not parsed or '@' not in parsed:
            raise ValueError(f'Invalid recipient address: {value!r}')
        return parsed


class DailySignalsPivotPick(BaseModel):
    """Pivot fields visible in the customer campaign."""

    model_config = ConfigDict(extra='forbid')

    symbol: str = Field(min_length=1)
    direction: Literal['long', 'short']
    rank: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator('symbol', mode='before')
    @classmethod
    def _strip_symbol(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class DailySignalsAlphaRankEntry(BaseModel):
    """AlphaRank fields visible in the customer campaign."""

    model_config = ConfigDict(extra='forbid')

    symbol: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)

    @field_validator('symbol', mode='before')
    @classmethod
    def _strip_symbol(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class DailySignalsDigest(BaseModel):
    """Same-session customer-visible signal data."""

    model_config = ConfigDict(extra='forbid')

    market: str = Field(min_length=1)
    date: str = Field(min_length=10, max_length=10, pattern=_DATE_PATTERN)
    pivot_picks: list[DailySignalsPivotPick] = Field(default_factory=list)
    alpha_rank: list[DailySignalsAlphaRankEntry] = Field(default_factory=list)

    @field_validator('market', mode='before')
    @classmethod
    def _normalize_market(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class CampaignDeliveryBase(BaseModel):
    """Shared internal delivery envelope."""

    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1]
    delivery_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    recipient: CampaignRecipient
    metadata: EventMetadata

    @field_validator('delivery_id', 'campaign_id', mode='before')
    @classmethod
    def _strip_ids(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class DailySignalsDeliveryEvent(CampaignDeliveryBase):
    """Internal per-recipient daily-signals delivery."""

    type: Literal['campaign.delivery.daily_signals']
    digest: DailySignalsDigest


CampaignEvent = DailySignalsCampaignEvent
CampaignDeliveryEvent = DailySignalsDeliveryEvent

_CAMPAIGN_EVENT_ADAPTER = TypeAdapter(CampaignEvent)
_DELIVERY_EVENT_ADAPTER = TypeAdapter(CampaignDeliveryEvent)


def _decode_payload(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f'Invalid queue JSON: {exc.msg} at line {exc.lineno} column {exc.colno}'
            ) from exc
    if isinstance(payload, dict):
        return payload
    raise TypeError(f'Unsupported queue payload type: {type(payload).__name__}')


def parse_campaign_event(
    payload: str | bytes | dict[str, Any],
) -> CampaignEvent:
    """Parse and validate a campaign entry message."""
    try:
        return _CAMPAIGN_EVENT_ADAPTER.validate_python(_decode_payload(payload))
    except ValidationError as exc:
        raise ValueError(f'Invalid campaign message: {exc}') from exc


def parse_delivery_event(
    payload: str | bytes | dict[str, Any],
) -> CampaignDeliveryEvent:
    """Parse and validate an internal campaign delivery message."""
    try:
        return _DELIVERY_EVENT_ADAPTER.validate_python(_decode_payload(payload))
    except ValidationError as exc:
        raise ValueError(f'Invalid campaign delivery message: {exc}') from exc


def event_to_payload(
    event: CampaignEvent | CampaignDeliveryEvent,
) -> dict[str, Any]:
    """Serialize a validated event for queue transport."""
    return event.model_dump(mode='json', exclude_none=True)


def metadata_to_dict(metadata: EventMetadata | None) -> dict[str, Any]:
    """Serialize metadata for persistence or forwarding."""
    return metadata.model_dump(mode='json', exclude_none=True) if metadata else {}
