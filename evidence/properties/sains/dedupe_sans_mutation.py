def dedupe(values):
    """Supprime les doublons.

    >>> dedupe([1, 1, 2])
    [1, 2]
    """
    return list(dict.fromkeys(values))
