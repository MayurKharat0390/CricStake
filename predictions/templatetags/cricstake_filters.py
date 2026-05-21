from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Retrieves an item from a dictionary dynamically using the key."""
    if not dictionary:
        return None
    # Support lookup for string representation of keys as well
    val = dictionary.get(key)
    if val is None:
        val = dictionary.get(str(key))
    return val

@register.filter(name='multiply')
def multiply(value, arg):
    """Multiplies two numbers."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter(name='subtract')
def subtract(value, arg):
    """Subtracts arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter(name='in_list')
def in_list(value, lst):
    """Checks if value is in list/set."""
    if not lst:
        return False
    return value in lst

@register.filter(name='replace')
def replace(value, arg):
    """Replaces a substring in a string. arg format is 'old,new'."""
    if not arg:
        return value
    parts = arg.split(',')
    old = parts[0]
    new = parts[1] if len(parts) > 1 else ''
    return str(value).replace(old, new)

@register.filter(name='split')
def split(value, arg):
    """Splits a string by a delimiter."""
    return str(value).split(arg)

@register.filter(name='has_badge')
def has_badge(user_badges, badge_name):
    """Checks if a badge with the given name is in the user's earned badges list."""
    if not user_badges:
        return False
    return any(ub.badge.name == badge_name for ub in user_badges)


