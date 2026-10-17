from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings
from .contracts import (
    DailySignalsAlphaRankEntry,
    DailySignalsDigest,
    DailySignalsPivotPick,
)

PUBLIC_PIVOT_EVENTS = (
    'BUY_TURN',
    'SELL_TURN',
    'TREND_BUY',
    'BASE_BREAKOUT',
)
_PIVOT_DIRECTION_ORDER = {'long': 0, 'short': 1}
_PIVOT_PROJECTION = {
    '_id': 0,
    'symbol': 1,
    'direction': 1,
    'rank': 1,
    'confidence': 1,
}
_ALPHARANK_PROJECTION = {
    '_id': 0,
    'symbol': 1,
    'rank': 1,
    'score': 1,
}
_ALPHARANK_MANIFEST_PROJECTION = {
    '_id': 0,
    'active_generation_id': 1,
    'row_count': 1,
}
_ALPHARANK_MAX_READ_ATTEMPTS = 3


class DailySignalsDigestError(RuntimeError):
    """Raised when a campaign cannot build a same-day digest safely."""


@dataclass
class MongoDailySignalsDigestRepository:
    """Read the daily signals digest once per campaign from MongoDB."""

    pivot_collection: Any
    alpharank_collection: Any
    alpharank_generations_collection: Any

    @classmethod
    def from_database(
        cls,
        database: Any,
        settings: Settings,
    ) -> 'MongoDailySignalsDigestRepository':
        return cls(
            pivot_collection=database[settings.pivot_picks_collection],
            alpharank_collection=database[settings.alpharank_collection],
            alpharank_generations_collection=database[
                settings.alpharank_generations_collection
            ],
        )

    def load_digest(self, *, market: str, date: str) -> DailySignalsDigest:
        normalized_market = str(market).strip().lower()
        normalized_date = str(date).strip()
        return DailySignalsDigest(
            market=normalized_market,
            date=normalized_date,
            pivot_picks=self._load_pivot_picks(
                market=normalized_market,
                date=normalized_date,
            ),
            alpha_rank=self._load_alpha_rank(
                market=normalized_market,
                date=normalized_date,
            ),
        )

    def _load_pivot_picks(
        self,
        *,
        market: str,
        date: str,
    ) -> list[DailySignalsPivotPick]:
        documents = list(
            self.pivot_collection.find(
                {
                    'market': market,
                    'date': date,
                    'event': {'$in': list(PUBLIC_PIVOT_EVENTS)},
                },
                _PIVOT_PROJECTION,
            )
        )
        documents.sort(
            key=lambda document: (
                _PIVOT_DIRECTION_ORDER.get(
                    str(document.get('direction') or '').strip().lower(),
                    99,
                ),
                int(document.get('rank') or 0),
                str(document.get('symbol') or ''),
            )
        )
        return [self._pivot_pick_from_document(document) for document in documents]

    def _pivot_pick_from_document(
        self,
        document: dict[str, Any],
    ) -> DailySignalsPivotPick:
        return DailySignalsPivotPick(
            symbol=str(document['symbol']),
            direction=str(document['direction']),
            rank=int(document['rank']),
            confidence=float(document['confidence']),
        )

    def _load_alpha_rank(
        self,
        *,
        market: str,
        date: str,
    ) -> list[DailySignalsAlphaRankEntry]:
        for _ in range(_ALPHARANK_MAX_READ_ATTEMPTS):
            manifest = self.alpharank_generations_collection.find_one(
                {
                    'market': market,
                    'date': date,
                    'signal_model': 'alpha_rank',
                },
                _ALPHARANK_MANIFEST_PROJECTION,
            )
            if manifest is None:
                raise DailySignalsDigestError(
                    f'Missing AlphaRank manifest for {market} on {date}'
                )

            generation_id = manifest.get('active_generation_id')
            row_count = manifest.get('row_count')
            if not generation_id:
                raise DailySignalsDigestError(
                    f'AlphaRank manifest missing active_generation_id for {market} on {date}'
                )
            if not isinstance(row_count, int) or row_count <= 0:
                raise DailySignalsDigestError(
                    f'AlphaRank manifest has invalid row_count for {market} on {date}'
                )

            documents = list(
                self.alpharank_collection.find(
                    {
                        'market': market,
                        'date': date,
                        'signal_model': 'alpha_rank',
                        'generation_id': generation_id,
                    },
                    _ALPHARANK_PROJECTION,
                )
            )
            committed = self.alpharank_generations_collection.find_one(
                {
                    'market': market,
                    'date': date,
                    'signal_model': 'alpha_rank',
                },
                _ALPHARANK_MANIFEST_PROJECTION,
            )
            if (
                committed
                and committed.get('active_generation_id') == generation_id
                and committed.get('row_count') == row_count
                and len(documents) == row_count
            ):
                documents.sort(
                    key=lambda document: (
                        int(document.get('rank') or 0),
                        str(document.get('symbol') or ''),
                    )
                )
                return [
                    DailySignalsAlphaRankEntry(
                        symbol=str(document['symbol']),
                        rank=int(document['rank']),
                        score=float(document['score']),
                    )
                    for document in documents[:15]
                ]

        raise DailySignalsDigestError(
            f'Could not read a complete stable AlphaRank generation for {market} on {date}'
        )
