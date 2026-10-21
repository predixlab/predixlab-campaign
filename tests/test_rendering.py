from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from itsdangerous import URLSafeTimedSerializer

from predixlab_campaign.contracts import parse_delivery_event
from predixlab_campaign.templates import render_campaign


def test_daily_signals_renders_dashboard_scope_and_unsubscribe_headers(
    settings,
    daily_delivery_payload: dict,
) -> None:
    rendered = render_campaign(
        parse_delivery_event(daily_delivery_payload),
        settings,
    )

    assert rendered.subject == 'PredixLab Daily Signals — 2026-08-15'
    for visible in [
        'Bullish',
        'Bearish',
        'AlphaRank',
        'Pivot',
        'AAPL',
        'TSLA',
        'NVDA',
        '77%',
        '93.4',
    ]:
        assert visible in rendered.html
    for hidden in [
        'BUY_TURN',
        'Momentum reversal',
        'Consensus',
        'Predicted excess return',
        'Top 20 probability',
        'campaign_id',
        'Confidence',
        'confidence=',
    ]:
        assert hidden not in rendered.html
        assert hidden not in rendered.text
    assert rendered.headers['List-Unsubscribe-Post'] == (
        'List-Unsubscribe=One-Click'
    )
    assert rendered.html.index('AlphaRank') < rendered.html.index('Pivot')
    assert rendered.text.index('AlphaRank') < rendered.text.index('Pivot')
    assert '<meta name="viewport"' in rendered.html
    assert '@media only screen and (max-width: 600px)' in rendered.html


def test_daily_signals_sorts_each_dashboard_list_before_rendering(
    settings,
    daily_delivery_payload: dict,
) -> None:
    daily_delivery_payload['digest']['alpha_rank'].reverse()
    daily_delivery_payload['digest']['pivot_picks'] = [
        daily_delivery_payload['digest']['pivot_picks'][1],
        daily_delivery_payload['digest']['pivot_picks'][0],
        daily_delivery_payload['digest']['pivot_picks'][2],
    ]

    rendered = render_campaign(
        parse_delivery_event(daily_delivery_payload),
        settings,
    )

    assert rendered.html.index('NVDA') < rendered.html.index('MSFT')
    bullish_start = rendered.html.index('Bullish')
    bearish_start = rendered.html.index('Bearish')
    bullish_html = rendered.html[bullish_start:bearish_start]
    assert bullish_html.index('AAPL') < bullish_html.index('NVDA')


def test_daily_signals_renders_chinese_and_api_compatible_unsubscribe(
    settings,
    daily_delivery_payload: dict,
) -> None:
    daily_delivery_payload['recipient'].update(
        {
            'name': '张三',
            'locale': 'zh',
        }
    )
    event = parse_delivery_event(daily_delivery_payload)
    rendered = render_campaign(event, settings)

    assert rendered.subject == 'PredixLab 每日信号 — 2026-08-15'
    assert '看多' in rendered.html
    assert '看空' in rendered.text
    unsubscribe_url = rendered.headers['List-Unsubscribe'][1:-1]
    assert urlparse(unsubscribe_url).path.endswith(
        '/api/v1/user/email/daily-signals/unsubscribe'
    )
    token = parse_qs(urlparse(unsubscribe_url).query)['token'][0]
    payload = URLSafeTimedSerializer(
        settings.unsubscribe_secret or settings.secret_key,
        salt='predixlab-daily-signals-email-unsubscribe',
    ).loads(token, max_age=365 * 24 * 3600)
    assert payload == {'user_id': 'u-1', 'language': 'zh'}


@pytest.mark.parametrize(
    ('locale', 'header', 'label'),
    [('en', 'Score', 'score'), ('zh', '评分', '评分')],
)
def test_daily_signals_uses_score_labels_without_changing_values(
    settings,
    daily_delivery_payload: dict,
    locale: str,
    header: str,
    label: str,
) -> None:
    daily_delivery_payload['recipient']['locale'] = locale

    rendered = render_campaign(
        parse_delivery_event(daily_delivery_payload),
        settings,
    )

    assert rendered.html.count(f'>{header}</th>') == 3
    for pick in [
        f'AAPL | {label}=77%',
        f'NVDA | {label}=69%',
        f'TSLA | {label}=66%',
        f'NVDA | {label}=93.4',
        f'MSFT | {label}=90.1',
    ]:
        assert pick in rendered.text
    for old_label in ['Confidence', 'confidence=', '置信度']:
        assert old_label not in rendered.html
        assert old_label not in rendered.text
