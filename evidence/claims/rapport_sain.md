# Analyse de performance

La latence mesuree est de 12 + 30 = 42 ms.

Le correctif vit dans `jio/loop/engine.py`.

```python
def moyenne(nums):
    return sum(nums) / len(nums)
```

Le gain total atteint 7 x 6 = 42 points, et la couverture 100/4 = 25 pour cent.

Le fichier `docs/VISION-ARCHITECTURE.md` decrit l'ensemble.
