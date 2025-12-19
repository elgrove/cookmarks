from django import template
from django.utils.http import urlencode

register = template.Library()


@register.simple_tag(takes_context=True)
def preserve_query_params(context, **kwargs):
    request = context.get("request")
    if not request:
        return "?" + urlencode(kwargs, doseq=True) if kwargs else ""

    params = request.GET.copy()

    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value

    if not params:
        return ""

    return "?" + params.urlencode()
