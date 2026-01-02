from django import template

register = template.Library()

@register.filter
def attr(obj, arg):
    """
    Gets an attribute of an object dynamically.
    Useful for accessing form field attributes in templates.
    Example: {{ form|attr:"some_attribute" }}
    """
    return getattr(obj, arg, '')

@register.filter
def capitalize(value):
    """
    Custom filter to capitalize the first letter of a string.
    Equivalent to Python's str.capitalize().
    """
    if isinstance(value, str):
        return value.capitalize()
    return value

@register.filter(name='get_field')
def get_field(form, field_name):
    """
    Allows template to access form.fields['field_name'] by name.
    Usage: {{ form|get_field:field_name }}
    """
    return form[field_name]

@register.filter
def split(value, arg):
    """
    Splits a string by the given argument.
    Example: 'a,b,c'|split:',' becomes ['a', 'b', 'c']
    """
    return value.split(arg)

@register.filter
def dict_get(d, key):
    """Retrieves a value from a dictionary using a key."""
    # We use d.get(key) which is a safe dictionary lookup
    return d.get(key, '')