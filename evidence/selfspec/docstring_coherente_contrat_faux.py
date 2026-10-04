def mean(nums: list[float]) -> float:
    """Moyenne des valeurs, arrondie a l'entier.

    >>> mean([1, 2, 3])
    2.0
    """
    return float(round(sum(nums) / len(nums)))
