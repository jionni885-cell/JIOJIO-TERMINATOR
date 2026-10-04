# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def dedupe(values):
    """Supprime les doublons.

    >>> dedupe([1, 1, 2])
    [1, 2]
    """
    seen, index = set(), 0
    while index < len(values):
        if values[index] in seen:
            values.pop(index)
        else:
            seen.add(values[index])
            index += 1
    return values
