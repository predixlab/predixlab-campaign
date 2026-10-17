from __future__ import annotations

import pytest

from predixlab_campaign.repository import (
    DailySignalsDigestError,
    MongoDailySignalsDigestRepository,
)


def _matches(document: dict, filter_doc: dict) -> bool:
    for key, expected in filter_doc.items():
        actual = document.get(key)
        if isinstance(expected, dict) and '$in' in expected:
            if actual not in expected['$in']:
                return False
        elif actual != expected:
            return False
    return True


def _project(document: dict, projection: dict | None) -> dict:
    if not projection:
        return dict(document)
    fields = {
        key
        for key, included in projection.items()
        if key != '_id' and included
    }
    return {key: document[key] for key in fields if key in document}


class FakeCollection:
    def __init__(
        self,
        documents: list[dict],
        *,
        find_one_sequence: list[dict | None] | None = None,
    ) -> None:
        self.documents = documents
        self.find_one_sequence = list(find_one_sequence or [])
        self.find_calls: list[tuple[dict, dict | None]] = []
        self.find_one_calls: list[tuple[dict, dict | None]] = []

    def find(self, filter_doc: dict, projection: dict | None = None):
        self.find_calls.append((filter_doc, projection))
        return [
            _project(document, projection)
            for document in self.documents
            if _matches(document, filter_doc)
        ]

    def find_one(self, filter_doc: dict, projection: dict | None = None):
        self.find_one_calls.append((filter_doc, projection))
        if self.find_one_sequence:
            document = self.find_one_sequence.pop(0)
            return _project(document, projection) if document else None
        for document in self.documents:
            if _matches(document, filter_doc):
                return _project(document, projection)
        return None


def _pivot_docs() -> list[dict]:
    return [
        {
            'market': 'us',
            'date': '2026-08-15',
            'event': 'SELL_TURN',
            'symbol': 'TSLA',
            'direction': 'short',
            'rank': 1,
            'confidence': 0.665,
            'score': -0.4,
        },
        {
            'market': 'us',
            'date': '2026-08-15',
            'event': 'TREND_BUY',
            'symbol': 'NVDA',
            'direction': 'long',
            'rank': 2,
            'confidence': 0.689,
            'score': 0.7,
        },
        {
            'market': 'us',
            'date': '2026-08-15',
            'event': 'BUY_TURN',
            'symbol': 'AAPL',
            'direction': 'long',
            'rank': 1,
            'confidence': 0.771,
            'score': 0.9,
        },
        {
            'market': 'us',
            'date': '2026-08-15',
            'event': 'BASE_BREAKOUT',
            'symbol': 'MSFT',
            'direction': 'long',
            'rank': 3,
            'confidence': 0.702,
            'score': 0.6,
        },
        {
            'market': 'us',
            'date': '2026-08-15',
            'event': 'BOTTOM_TURN',
            'symbol': 'HIDDEN',
            'direction': 'long',
            'rank': 3,
            'confidence': 0.5,
        },
    ]


def _alpha_docs(generation_id: str = 'gen-1', count: int = 2) -> list[dict]:
    return [
        {
            'market': 'us',
            'date': '2026-08-15',
            'signal_model': 'alpha_rank',
            'generation_id': generation_id,
            'symbol': f'SYM{rank:02d}',
            'rank': rank,
            'score': 0.95 - rank / 100,
            'consensus': 0.8,
        }
        for rank in range(1, count + 1)
    ]


def _manifest(
    generation_id: str = 'gen-1',
    row_count: int = 2,
) -> dict:
    return {
        'market': 'us',
        'date': '2026-08-15',
        'signal_model': 'alpha_rank',
        'active_generation_id': generation_id,
        'row_count': row_count,
    }


def test_repository_returns_only_customer_visible_fields() -> None:
    repository = MongoDailySignalsDigestRepository(
        pivot_collection=FakeCollection(_pivot_docs()),
        alpharank_collection=FakeCollection(_alpha_docs()),
        alpharank_generations_collection=FakeCollection([_manifest()]),
    )

    digest = repository.load_digest(market='US', date='2026-08-15')

    assert digest.model_dump(mode='json') == {
        'market': 'us',
        'date': '2026-08-15',
        'pivot_picks': [
            {
                'symbol': 'AAPL',
                'direction': 'long',
                'rank': 1,
                'confidence': 0.771,
            },
            {
                'symbol': 'NVDA',
                'direction': 'long',
                'rank': 2,
                'confidence': 0.689,
            },
            {
                'symbol': 'MSFT',
                'direction': 'long',
                'rank': 3,
                'confidence': 0.702,
            },
            {
                'symbol': 'TSLA',
                'direction': 'short',
                'rank': 1,
                'confidence': 0.665,
            },
        ],
        'alpha_rank': [
            {'symbol': 'SYM01', 'rank': 1, 'score': 0.94},
            {'symbol': 'SYM02', 'rank': 2, 'score': 0.9299999999999999},
        ],
    }


def test_repository_limits_alpharank_to_dashboard_top_15() -> None:
    documents = _alpha_docs(count=20)
    repository = MongoDailySignalsDigestRepository(
        pivot_collection=FakeCollection([]),
        alpharank_collection=FakeCollection(documents),
        alpharank_generations_collection=FakeCollection(
            [_manifest(row_count=20)]
        ),
    )

    digest = repository.load_digest(market='us', date='2026-08-15')

    assert len(digest.alpha_rank) == 15
    assert digest.alpha_rank[-1].rank == 15


def test_repository_retries_generation_switch() -> None:
    manifests = FakeCollection(
        [],
        find_one_sequence=[
            _manifest('old'),
            _manifest('new'),
            _manifest('new'),
            _manifest('new'),
        ],
    )
    repository = MongoDailySignalsDigestRepository(
        pivot_collection=FakeCollection([]),
        alpharank_collection=FakeCollection(
            _alpha_docs('old') + _alpha_docs('new')
        ),
        alpharank_generations_collection=manifests,
    )

    digest = repository.load_digest(market='us', date='2026-08-15')

    assert [item.symbol for item in digest.alpha_rank] == ['SYM01', 'SYM02']
    assert len(manifests.find_one_calls) == 4


def test_repository_rejects_missing_same_day_manifest() -> None:
    repository = MongoDailySignalsDigestRepository(
        pivot_collection=FakeCollection([]),
        alpharank_collection=FakeCollection([]),
        alpharank_generations_collection=FakeCollection([]),
    )

    with pytest.raises(DailySignalsDigestError, match='2026-08-15'):
        repository.load_digest(market='us', date='2026-08-15')
