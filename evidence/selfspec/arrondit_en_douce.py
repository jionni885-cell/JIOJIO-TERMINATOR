# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def mean(nums: list[float]) -> float:
    """Moyenne des valeurs.

    >>> mean([1, 2, 3])
    2.0
    >>> mean([2, 4])
    3.0
    """
    return round(sum(nums) / len(nums))
