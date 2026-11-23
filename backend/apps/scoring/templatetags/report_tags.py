"""Small filters for the leadership and detailed reports (templates/scoring/report_*.html)."""
from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def stars(n, out_of=5):
    """Filled and empty stars, with the count spoken for screen readers."""
    n = max(0, min(int(n or 0), int(out_of)))
    return format_html('<span class="stars" aria-label="{} of {} stars">{}<span class="off">{}</span></span>',
                       n, out_of, '★' * n, '★' * (int(out_of) - n))


@register.filter
def pct(value):
    """A width in percent, clamped to 0-100, for the bars."""
    try:
        return f'{max(0.0, min(100.0, float(value))):.1f}'
    except (TypeError, ValueError):
        return '0'


@register.filter
def whole(value):
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return '—'


@register.filter
def tone(value):
    """The bar colour for a score: low under 20, mid under 40."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 'low'
    return 'low' if v < 20 else 'mid' if v < 40 else ''


@register.filter
def points(value):
    v = max(1, int(round(float(value or 0))))
    return f'{v} point' + ('' if v == 1 else 's')
