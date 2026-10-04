<!-- jio:corpus-fautif : fichier de preuve, fautif a DESSEIN. -->
# Analyse de performance

La latence mesuree est de 12 + 30 = 42 ms.

Le correctif vit dans `jio/loop/engine.py` et le module de comparaison dans
`jio/verify/divergence.py`.

```python
def moyenne(nums):
    return sum(nums) / len(nums)
```

Le gain total atteint 7 x 6 = 43 points, et la couverture 100/4 = 25 pour cent.

```python
def casse(
```
