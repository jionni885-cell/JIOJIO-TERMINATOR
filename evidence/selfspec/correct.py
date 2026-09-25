def mean(nums: list[float]) -> float:
    """Moyenne des valeurs.

    >>> mean([1, 2, 3])
    2.0
    >>> mean([2, 4])
    3.0
    """
    if not nums:
        raise ValueError("mean: liste vide")
    return sum(nums) / len(nums)
