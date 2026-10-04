# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def with_default(options, key):
    """Ajoute une option par defaut.

    >>> with_default({"a": 1}, "b")
    {'a': 1, 'b': 0}
    """
    options[key] = 0
    return options
