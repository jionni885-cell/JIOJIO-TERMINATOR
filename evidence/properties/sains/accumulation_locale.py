def collect(items, seen):
    """Collecte les elements et note la taille vue.

    >>> collect([1, 2], [])
    [1, 2]
    """
    seen = seen or []
    return list(items)
