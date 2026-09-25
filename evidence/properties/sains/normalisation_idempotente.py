def normalize_text(text: str) -> str:
    """Normalise un texte (idempotent).

    >>> normalize_text("ab")
    'ab'
    """
    return "a" + text.lstrip("a")
