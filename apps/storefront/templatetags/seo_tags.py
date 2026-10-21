import json

from django import template
from django.utils.safestring import mark_safe

from apps.storefront.seo import metadata

register = template.Library()


@register.simple_tag(takes_context=True)
def page_seo(context):
    return metadata(context)


@register.filter
def json_ld(value):
    # Escape HTML-significant characters even inside script raw text.
    encoded = json.dumps(value, ensure_ascii=False).translate({
        ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026",
    })
    return mark_safe(encoded)


@register.simple_tag(takes_context=True)
def page_link(context, number):
    query = context["request"].GET.copy()
    query["page"] = str(number)
    return "?" + query.urlencode()
