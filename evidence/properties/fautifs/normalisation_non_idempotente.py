# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def normalize_text(text: str) -> str:
    """Normalise un texte (idempotent).

    >>> normalize_text("ab")
    'aab'
    """
    return "a" + text
