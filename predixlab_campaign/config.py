from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Campaign Function configuration sourced from environment variables."""

    storage_connection_string: str
    campaign_events_queue: str
    campaign_delivery_queue: str
    campaign_delivery_backend: str
    acs_connection_string: str
    acs_sender: str
    mongodb_url: str
    database_name: str
    users_collection: str
    pivot_picks_collection: str
    alpharank_collection: str
    alpharank_generations_collection: str
    campaign_deliveries_collection: str
    app_name: str
    public_api_url: str
    secret_key: str
    delivery_lease_seconds: int = 300

    @classmethod
    def from_env(cls) -> 'Settings':
        """Load settings with production defaults for queue names."""
        lease_seconds = int(os.getenv('CAMPAIGN_DELIVERY_LEASE_SECONDS', '300'))
        if lease_seconds <= 0:
            raise ValueError(
                'CAMPAIGN_DELIVERY_LEASE_SECONDS must be greater than zero'
            )
        return cls(
            storage_connection_string=os.getenv('AzureWebJobsStorage', ''),
            campaign_events_queue=os.getenv(
                'CAMPAIGN_EVENTS_QUEUE',
                'campaign-events',
            ),
            campaign_delivery_queue=os.getenv(
                'CAMPAIGN_DELIVERY_QUEUE',
                'campaign-delivery',
            ),
            campaign_delivery_backend=(
                os.getenv('CAMPAIGN_DELIVERY_BACKEND', 'acs') or 'acs'
            ).lower(),
            acs_connection_string=os.getenv('ACS_CONNECTION_STRING', ''),
            acs_sender=os.getenv('ACS_SENDER', ''),
            mongodb_url=os.getenv('MONGODB_URL', ''),
            database_name=os.getenv('DATABASE_NAME', ''),
            users_collection=os.getenv('USERS_COLLECTION', 'users'),
            pivot_picks_collection=os.getenv(
                'PIVOT_PICKS_COLLECTION',
                'pivot_picks',
            ),
            alpharank_collection=os.getenv(
                'ALPHARANK_COLLECTION',
                'alpharank',
            ),
            alpharank_generations_collection=os.getenv(
                'ALPHARANK_GENERATIONS_COLLECTION',
                'alpharank_generations',
            ),
            campaign_deliveries_collection=os.getenv(
                'CAMPAIGN_DELIVERIES_COLLECTION',
                'campaign_deliveries',
            ),
            app_name=os.getenv('CAMPAIGN_APP_NAME', 'PredixLab'),
            public_api_url=os.getenv('PUBLIC_API_URL', ''),
            secret_key=os.getenv('SECRET_KEY', ''),
            delivery_lease_seconds=lease_seconds,
        )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Return a cached settings instance for Azure Functions imports."""
    return Settings.from_env()
