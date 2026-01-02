from django import template

register = template.Library()

@register.filter
def add_class(field, css):
    return field.as_widget(attrs={"class": css})


@register.filter
def split(value, arg):
    """
    Splits a string by the given argument.
    Example: 'a,b,c'|split:',' becomes ['a', 'b', 'c']
    """
    return value.split(arg)