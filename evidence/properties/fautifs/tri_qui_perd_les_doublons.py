# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def sort_values(nums):
    """Trie les valeurs.

    >>> sort_values([3, 1, 3])
    [1, 3, 3]
    """
    return sorted(set(nums))
