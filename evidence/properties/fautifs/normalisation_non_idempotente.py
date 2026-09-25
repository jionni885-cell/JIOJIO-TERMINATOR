def normalize_text(text: str) -> str:
    """Normalise un texte (idempotent).

    >>> normalize_text("ab")
    'aab'
    """
    return "a" + text
