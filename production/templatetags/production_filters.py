from django import template

register = template.Library()


@register.filter
def split(value, arg):
    """Split a string by a separator."""
    return value.split(arg)


@register.filter(name="add_class")
def add_class(field, css):
    """Append CSS class(es) to a form field widget when rendering."""
    if not hasattr(field, "as_widget"):
        return field
    attrs = field.field.widget.attrs.copy()
    existing = attrs.get("class", "")
    merged = f"{existing} {css}".strip() if existing else css
    attrs["class"] = merged
    return field.as_widget(attrs=attrs)
