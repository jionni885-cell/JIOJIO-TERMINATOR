def with_default(options, key):
    """Ajoute une option par defaut.

    >>> with_default({"a": 1}, "b")
    {'a': 1, 'b': 0}
    """
    merged = dict(options)
    merged[key] = 0
    return merged
