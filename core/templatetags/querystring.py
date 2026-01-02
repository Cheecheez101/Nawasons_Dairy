from django import template
from django.http import QueryDict

register = template.Library()


def _is_empty(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == '':
        return True
    return False


@register.simple_tag(takes_context=True)
def url_with_query(context, **overrides):
    request = context.get('request')
    if request is not None:
        query = request.GET.copy()
    else:
        query = QueryDict('', mutable=True)
    query = query.copy()
    for key, value in overrides.items():
        if _is_empty(value):
            if key in query:
                query.pop(key, None)
        else:
            query[key] = value
    encoded = query.urlencode()
    return f"?{encoded}" if encoded else ''
