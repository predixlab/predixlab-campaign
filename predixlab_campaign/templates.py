from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from itsdangerous import URLSafeSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Settings
from .contracts import CampaignDeliveryEvent, DailySignalsDeliveryEvent

_UNSUBSCRIBE_SALT = 'predixlab-daily-signals-email-unsubscribe'
_TEMPLATE_ROOT = Path(__file__).with_name('template_assets') / 'email'
_TEXTS = {
    'en': {
        'subject': '{app_name} Daily Signals — {date}',
        'intro': 'Here is your premium signal digest for {date}.',
        'greeting_named': 'Hello {name},',
        'greeting_generic': 'Hello,',
        'summary_title': 'Daily summary',
        'market': 'Market',
        'date': 'Signal date',
        'pivot_title': 'Pivot',
        'pivot_long_title': 'Bullish',
        'pivot_short_title': 'Bearish',
        'alpha_title': 'AlphaRank',
        'alpha_empty': 'No AlphaRank results for this session.',
        'pivot_empty': 'No Pivot signals for this session.',
        'pivot_symbol': 'Symbol',
        'pivot_rank': 'Rank',
        'pivot_confidence': 'Confidence',
        'alpha_rank_label': 'Rank',
        'alpha_symbol': 'Ticker',
        'alpha_score': 'Score',
        'disclaimer': (
            'These model-generated signals are for informational purposes only '
            'and are not investment advice.'
        ),
        'unsubscribe': 'Unsubscribe from Daily Signals emails',
    },
    'zh': {
        'subject': '{app_name} 每日信号 — {date}',
        'intro': '以下是 {date} 的高级会员每日信号摘要。',
        'greeting_named': '{name}，您好：',
        'greeting_generic': '您好：',
        'summary_title': '每日摘要',
        'market': '市场',
        'date': '信号日期',
        'pivot_title': 'Pivot',
        'pivot_long_title': '看多',
        'pivot_short_title': '看空',
        'alpha_title': 'AlphaRank',
        'alpha_empty': '当日无 AlphaRank 结果。',
        'pivot_empty': '当日无 Pivot 信号。',
        'pivot_symbol': '代码',
        'pivot_rank': '排名',
        'pivot_confidence': '置信度',
        'alpha_rank_label': '排名',
        'alpha_symbol': '代码',
        'alpha_score': '评分',
        'disclaimer': (
            '这些由模型生成的信号仅供参考，不构成任何投资建议。'
        ),
        'unsubscribe': '退订每日信号邮件',
    },
}


@dataclass(frozen=True)
class RenderedCampaign:
    """Rendered campaign content and delivery headers."""

    subject: str
    html: str
    text: str
    headers: dict[str, str]


@lru_cache(maxsize=1)
def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_ROOT)),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def normalize_language(value: Any) -> str:
    """Normalize recipient language preferences to en/zh."""
    language = str(value or 'en').lower()
    return 'zh' if language.startswith(('zh', 'cn')) else 'en'


def build_unsubscribe_url(
    settings: Settings,
    user_id: str,
    language: str,
) -> str:
    """Build the API-compatible Daily Signals unsubscribe URL."""
    serializer = URLSafeSerializer(settings.secret_key, salt=_UNSUBSCRIBE_SALT)
    token = serializer.dumps({'user_id': user_id, 'language': language})
    base = settings.public_api_url.rstrip('/')
    return (
        f'{base}/api/v1/user/email/daily-signals/unsubscribe'
        f'?token={quote(token)}'
    )


def unsubscribe_headers(
    settings: Settings,
    user_id: str,
    language: str,
) -> dict[str, str]:
    """Return RFC 8058 headers required for campaign deliveries."""
    url = build_unsubscribe_url(settings, user_id, language)
    return {
        'List-Unsubscribe': f'<{url}>',
        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    }


def render_campaign(
    event: CampaignDeliveryEvent,
    settings: Settings,
) -> RenderedCampaign:
    """Render one internal campaign delivery."""
    if isinstance(event, DailySignalsDeliveryEvent):
        return _render_daily_signals(settings, event)
    raise ValueError(f'Unsupported campaign delivery type: {event.type}')


def _render_daily_signals(
    settings: Settings,
    event: DailySignalsDeliveryEvent,
) -> RenderedCampaign:
    recipient = event.recipient
    digest = event.digest
    text_map = _TEXTS[recipient.locale]
    name = _display_name(recipient.name, recipient.email)
    greeting = (
        text_map['greeting_named'].format(name=name)
        if name
        else text_map['greeting_generic']
    )
    unsubscribe_url = build_unsubscribe_url(
        settings,
        recipient.user_id,
        recipient.locale,
    )
    subject = text_map['subject'].format(
        app_name=settings.app_name,
        date=digest.date,
    )
    context = {
        'greeting': greeting,
        'subject_line': subject,
        'intro': text_map['intro'].format(date=digest.date),
        'summary_title': text_map['summary_title'],
        'summary_rows': [
            {'label': text_map['market'], 'value': digest.market.upper()},
            {'label': text_map['date'], 'value': digest.date},
        ],
        'pivot_title': text_map['pivot_title'],
        'pivot_empty': text_map['pivot_empty'],
        'has_pivot': bool(digest.pivot_picks),
        'pivot_headers': [
            text_map['pivot_rank'],
            text_map['pivot_symbol'],
            text_map['pivot_confidence'],
        ],
        'pivot_groups': [
            _pivot_group(
                digest.pivot_picks,
                direction='long',
                title=text_map['pivot_long_title'],
            ),
            _pivot_group(
                digest.pivot_picks,
                direction='short',
                title=text_map['pivot_short_title'],
            ),
        ],
        'alpha_title': text_map['alpha_title'],
        'alpha_headers': [
            text_map['alpha_rank_label'],
            text_map['alpha_symbol'],
            text_map['alpha_score'],
        ],
        'has_alpha': bool(digest.alpha_rank),
        'alpha_empty': text_map['alpha_empty'],
        'alpha_rank': [
            {
                'rank': str(item.rank),
                'symbol': item.symbol,
                'score': _format_number(item.score * 100, 1),
            }
            for item in sorted(
                digest.alpha_rank,
                key=lambda entry: (entry.rank, entry.symbol),
            )
        ],
        'disclaimer': text_map['disclaimer'],
        'unsubscribe_label': text_map['unsubscribe'],
        'unsubscribe_url': unsubscribe_url,
    }
    html, text = _render_template_pair(
        'daily_signals',
        recipient.locale,
        context,
    )
    return RenderedCampaign(
        subject=subject,
        html=html,
        text=text,
        headers=unsubscribe_headers(
            settings,
            recipient.user_id,
            recipient.locale,
        ),
    )


def _pivot_group(
    picks: list[Any],
    *,
    direction: str,
    title: str,
) -> dict[str, Any]:
    visible = sorted(
        (pick for pick in picks if pick.direction == direction),
        key=lambda pick: (pick.rank, pick.symbol),
    )
    return {
        'title': title,
        'items': [
            {
                'rank': str(position),
                'symbol': pick.symbol,
                'confidence': _format_ratio_as_percent(pick.confidence, 0),
            }
            for position, pick in enumerate(visible, start=1)
        ],
    }


def _render_template_pair(
    template_name: str,
    locale: str,
    context: Mapping[str, Any],
) -> tuple[str, str]:
    env = _template_env()
    html = env.get_template(f'{locale}/{template_name}.html').render(
        **context
    )
    text = env.get_template(f'{locale}/{template_name}.txt').render(
        **context
    )
    return html.strip(), text.strip()


def _display_name(name: str | None, email: str) -> str:
    cleaned = str(name or '').strip()
    if cleaned:
        return cleaned
    return email.split('@', 1)[0] if '@' in email else ''


def _format_number(value: float | None, decimals: int) -> str:
    if value is None:
        return '—'
    return f'{value:,.{decimals}f}'


def _format_ratio_as_percent(value: float | None, decimals: int) -> str:
    if value is None:
        return '—'
    return f'{value * 100:,.{decimals}f}%'
