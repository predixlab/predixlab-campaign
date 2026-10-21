from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from itsdangerous import URLSafeTimedSerializer

from predixlab_campaign.config import Settings
from predixlab_campaign.templates import build_unsubscribe_url

_UNSUBSCRIBE_SALT = 'predixlab-daily-signals-email-unsubscribe'
_UNSUBSCRIBE_MAX_AGE = 365 * 24 * 3600


@pytest.mark.parametrize(
    ('secret_key', 'unsubscribe_secret'),
    [
        ('api-test-secret', None),
        ('api-test-secret', ''),
        ('api-test-secret', 'unsubscribe-test-secret'),
        ('api-test-secret', 'api-test-secret'),
        ('', 'unsubscribe-test-secret'),
    ],
)
def test_unsubscribe_signing_matches_shared_api_spec(
    monkeypatch,
    secret_key: str,
    unsubscribe_secret: str | None,
) -> None:
    monkeypatch.setenv('SECRET_KEY', secret_key)
    if unsubscribe_secret is None:
        monkeypatch.delenv('UNSUBSCRIBE_SECRET', raising=False)
    else:
        monkeypatch.setenv('UNSUBSCRIBE_SECRET', unsubscribe_secret)
    issued_at = 1_800_000_000
    monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda self: issued_at)
    settings = Settings.from_env()

    url = build_unsubscribe_url(settings, 'u-1', 'zh')
    token = parse_qs(urlparse(url).query)['token'][0]
    keys = list(dict.fromkeys(
        key for key in [secret_key, unsubscribe_secret] if key
    ))
    payload, timestamp = URLSafeTimedSerializer(
        keys,
        salt=_UNSUBSCRIBE_SALT,
    ).loads(token, max_age=_UNSUBSCRIBE_MAX_AGE, return_timestamp=True)

    assert payload == {'user_id': 'u-1', 'language': 'zh'}
    assert timestamp == datetime.fromtimestamp(issued_at, tz=timezone.utc)
    assert URLSafeTimedSerializer(
        unsubscribe_secret or secret_key,
        salt=_UNSUBSCRIBE_SALT,
    ).loads(token, max_age=_UNSUBSCRIBE_MAX_AGE) == payload

    wrong_keys = ['wrong-test-secret']
    if secret_key and unsubscribe_secret and secret_key != unsubscribe_secret:
        wrong_keys.append(secret_key)
    for wrong_key in wrong_keys:
        with pytest.raises(BadSignature):
            URLSafeTimedSerializer(
                wrong_key,
                salt=_UNSUBSCRIBE_SALT,
            ).loads(token, max_age=_UNSUBSCRIBE_MAX_AGE)

    verifier = URLSafeTimedSerializer(keys, salt=_UNSUBSCRIBE_SALT)
    monkeypatch.setattr(
        TimestampSigner,
        'get_timestamp',
        lambda self: issued_at + _UNSUBSCRIBE_MAX_AGE,
    )
    assert verifier.loads(token, max_age=_UNSUBSCRIBE_MAX_AGE) == payload
    monkeypatch.setattr(
        TimestampSigner,
        'get_timestamp',
        lambda self: issued_at + _UNSUBSCRIBE_MAX_AGE + 1,
    )
    with pytest.raises(SignatureExpired):
        verifier.loads(token, max_age=_UNSUBSCRIBE_MAX_AGE)
