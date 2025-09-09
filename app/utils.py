from datetime import datetime

def format_datetime_filter(iso_string):
    """Jinja2 filter to format an ISO datetime string."""
    if not iso_string:
        return ''
    try:
        return datetime.fromisoformat(iso_string).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return iso_string
