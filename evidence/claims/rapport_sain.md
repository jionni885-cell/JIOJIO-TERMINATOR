# Analyse de performance

La latence mesuree est de 12 + 30 = 42 ms.

Le correctif vit dans `jio/loop/engine.py`.

```python
def moyenne(nums):
    return sum(nums) / len(nums)
```

Le gain total atteint 7 x 6 = 42 points, et la couverture 100/4 = 25 pour cent.

Le fichier `docs/VISION-ARCHITECTURE.md` decrit l'ensemble.

## Reproduire

Le protocole se rejoue en deux commandes, et l'exemple ci-dessous est du **shell** :
le compiler comme du Python serait une accusation fausse, il ne doit donc pas etre
juge du tout.

```bash
jio claims evidence/claims/rapport_sain.md --racine .
echo "code de sortie : $?"
```

## Correction d'une erreur passee

Une version precedente de ce rapport annoncait `7 x 6 = 43`, ce qui etait faux : le
produit vaut 42. La citation est VERIFIEE, puis signalee — un document qui parle d'une
erreur doit pouvoir la citer sans etre condamne pour elle.
