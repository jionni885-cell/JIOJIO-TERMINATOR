# Preuves rejouables

Ces corpus existent pour qu'aucun chiffre annonce ne soit invérifiable. Les tests
mesurent ces fichiers ; `scripts/evidence.sh` rejoue l'ensemble.

| Dossier | Ce qu'il contient | Mesure verrouillee par |
|---|---|---|
| `properties/` | 8 artefacts **fautifs** (mutation d'argument, aller-retour avec perte, idempotence rompue, tri infidele) et 8 artefacts **sains** | detection 1/8 -> 8/8, **0** artefact sain accuse |
| `selfspec/` | 5 artefacts **documentes** : un correct, deux qui mentent sur leur propre docstring, deux dont la documentation decrit fidelement un contrat faux | 2 defauts sur 4 rattrapes par l'auto-controle, **0** faux rejet |
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
