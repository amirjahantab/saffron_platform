from django import template
register = template.Library()


@register.inclusion_tag("components/_icon.html")
def icon(name, css=""):
    return {"name": name, "css": css}
