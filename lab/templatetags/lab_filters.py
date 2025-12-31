from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """Split the value by the argument."""
    return value.split(arg)

