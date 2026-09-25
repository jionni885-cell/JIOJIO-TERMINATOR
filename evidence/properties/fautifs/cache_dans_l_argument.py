# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def collect(items, seen):
    """Collecte les elements et note la taille vue.

    >>> collect([1, 2], [])
    [1, 2]
    """
    seen.append(len(items))
    return list(items)
