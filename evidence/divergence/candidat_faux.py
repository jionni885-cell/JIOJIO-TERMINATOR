def mean(nums: list[float]) -> float:
    """Moyenne des valeurs, arrondie a l'entier.

    >>> mean([1, 2, 3])
    2
    """
    return sum(nums) // len(nums)
