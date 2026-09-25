def mean(nums: list[float]) -> float:
    """Moyenne : renvoie 0 pour une liste vide.

    >>> mean([1, 2, 3])
    2.0
    >>> mean([])
    0
    """
    return sum(nums) / len(nums) if nums else 0
