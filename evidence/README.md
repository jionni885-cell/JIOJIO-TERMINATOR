# Preuves rejouables

Ces corpus existent pour qu'aucun chiffre annonce ne soit invérifiable. Les tests
mesurent ces fichiers ; `scripts/evidence.sh` rejoue l'ensemble.

| Dossier | Ce qu'il contient | Mesure verrouillee par |
|---|---|---|
| `properties/` | 8 artefacts **fautifs** (mutation d'argument, aller-retour avec perte, idempotence rompue, tri infidele) et 8 artefacts **sains** | detection 1/8 -> 8/8, **0** artefact sain accuse |
| `selfspec/` | 9 artefacts **documentes** : fonctions et **classes**, dont un menteur dont un exemple pedagogique masquait l'echec decisif, une pile LIFO qui depile par le bas, et un artefact sain | **4** rejets francs, **1** reserve motivee, **0** faux rejet ; 240 doctests de paquets publies balayes en plus, sans une seule accusation |
| `witness/` | les 3 modes d'echec d'un **traducteur de regles** (valeur d'un distracteur, contrat d'erreur inverse, regle lue a l'envers), sur les 22 regles du banc | la contrefacon est **refusee par l'implementation correcte** et satisfaite par une fausse ; sans oracle, 5/5 livraisons justes a fidelite 100 %, et **0** erreur livree sans reserve a fidelite 0 |
| `witness/` | **+ bibliotheque de temoins** : la même mission répétée 3 fois, la mémoire étant le seul changement | 1 traduction payée, puis **0** ; une mémoire forgée est mise en quarantaine et jamais appliquée |
| `divergence/` | 2 candidats a la meme tache (vraie moyenne, division entiere), tous deux acceptes par une specification reduite au cas nominal | le livrable ne depend plus de l'ordre d'arrivee, et le desaccord est **avoue** avec l'entree exacte |

Regles d'ecriture de ces corpus — elles sont le sujet autant que les fichiers :

1. **un corpus ne contient que du code plausible** : chaque artefact fautif est le
   type de bug qu'un modele produit vraiment (off-by-one, division entiere, oubli du
   cas vide), pas une faute grossiere ecrite pour se donner raison ;
2. **les artefacts sains sont aussi importants que les fautifs** : une fausse
   accusation coute plus cher qu'un defaut manque, parce qu'un outil qui accuse a
   tort est desactive au bout de deux jours ;
3. **quand un cas n'est pas juge, on l'ecrit** : `hors_promesse_join_split.py`
   (`echo`/`split`) doit rester MUET, parce que cette paire ne promet pas un
   aller-retour — un separateur peut apparaitre dans un element.

```sh
scripts/evidence.sh                 # tout, sans cle API ni reseau
scripts/evidence.sh --third-party   # + balayage de paquets publies (reseau requis)
```
