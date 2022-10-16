def all_choices(choices):
    """Recursively extract the choices from a potentially nested set of choices."""
    for left, right in choices:
        if isinstance(right, str):
            # Right side is the label, left side is the value
            yield left
            continue

        # Left side is a name for the group.
        # Right side is either:
        # - another named group (nesting up to twice)
        # - an iterable of (value, label) tuples
        yield from all_choices(right)
