"""Small filters for the leadership and detailed reports (templates/scoring/report_*.html)."""
from django import template
from django.utils.html import format_html

from apps.scoring.capability.presentation import whole as _whole  # half up, as the screens

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
        return str(_whole(value))
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
    v = max(1, _whole(value))
    return f'{v} point' + ('' if v == 1 else 's')


@register.filter
def cssstr(value):
    """Text for a CSS string (the page footer): no quotes, backslashes or angle brackets, one line."""
    import re
    return re.sub(r'["\\<>\n\r]+', ' ', str(value or '')).strip()


STAR = ('<svg width="{s}mm" height="{s}mm" viewBox="0 0 24 24"><path d="M12 2.6l2.9 6.1 6.6.9-4.8 4.6 1.2 6.6L12 '
        '17.6 6.1 20.8l1.2-6.6L2.5 9.6l6.6-.9z" fill="{fill}" stroke="#B9A23C" stroke-width="1.6" '
        'stroke-linejoin="round"/></svg>')


@register.filter
def starsvg(n, size=4.4):
    """The v5 reports' stars: filled gold for the level, outlined for the rest."""
    from django.utils.safestring import mark_safe
    n = max(0, min(int(n or 0), 5))
    return mark_safe('<span class="stars" aria-label="%d of 5 stars">%s</span>' % (
        n, ''.join(STAR.format(s=size, fill='#B9A23C' if i < n else 'none').replace(
            'stroke="#B9A23C"', 'stroke="#B9A23C"' if i < n else 'stroke="#B9C2CC"') for i in range(5))))


@register.filter
def bar(score, extra=None):
    """The v5 reports' bar on the 0-100 scale with the four level lines; extra (to be confirmed) as a lighter part."""
    from django.utils.safestring import mark_safe
    try:
        s = max(0.0, min(100.0, float(score or 0)))
    except (TypeError, ValueError):
        s = 0.0
    w = 0.0
    try:
        w = max(0.0, min(100.0 - s, float(extra or 0)))
    except (TypeError, ValueError):
        pass
    wait = f'<b class="wait" style="width:{s + w:.1f}%"></b>' if w >= 0.5 else ''
    lines = ''.join(f'<i style="left:{x}%"></i>' for x in (20, 40, 60, 80))
    return mark_safe(f'{wait}<b style="width:{s:.1f}%"></b>{lines}')


@register.filter
def thousands(value):
    try:
        return f'{int(value):,}'
    except (TypeError, ValueError):
        return value


TILES = ['#EEF5D6', '#DCEBA8', '#BFD867', '#8DB600', '#0C4320']


@register.filter
def tilecolour(score):
    """The detailed report's map: white where nothing was found, else the topic's level from light to dark."""
    try:
        s = float(score or 0)
    except (TypeError, ValueError):
        s = 0.0
    return '#FFFFFF' if s <= 0 else TILES[min(4, int(s // 20))]
