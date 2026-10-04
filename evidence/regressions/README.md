# Le jeu de regression : les echecs REELS, figes pour ne pas revenir en silence

Chaque fichier `*.json` de ce dossier est un echec **observe** — pas imagine — devenu
rejouable. Le corpus est ce qui manquait entre deux versions : sans lui, une fuite
refermee a la version N peut revenir a la version N+1 sans qu'aucun controle ne bronche,
et rien ne permet de comparer deux versions sur les **memes** cas.

## Les deux genres, parce qu'ils n'appellent pas le meme geste

| Genre | Ce qu'il exige | S'il ne se declenche plus |
|---|---|---|
| `temoin` | ces regles doivent **encore echouer** sur cet artefact | `SILENCE` : un defaut, a corriger |
| `securite` | ces valeurs **ne doivent jamais sortir** d'un export | `FUITE` : **BLOQUANT**, la livraison est refusee |

## Comment un cas nait — et pourquoi un humain est dans la boucle

```console
$ python -m jio eval --proposer --journal .jio/journal.jsonl
$ python -m jio eval --geler T-R-001-4 --candidat 1b550ccddc8b21e9 --controles controles.json
$ python -m jio eval --geler S-telephone-63
$ python -m jio eval                       # rejoue le corpus, publie le taux de silence
```

1. `--proposer` lit une trace **verifiee** (chaine de hashes) et liste les echecs reels :
   une regle qui a echoue, un champ sensible exporte. Le rapport donne la provenance
   (evenement, monde, revision) et **jamais** la valeur sensible observee ;
2. `--geler` fige une proposition. L'oracle (`--controles`) n'est **pas** dans la trace —
   un controle cache est un secret, il ne se journalise pas : c'est la partie humaine.
   Le gel est **refuse** si l'echec ne se reproduit pas ici, maintenant ;
3. `jio eval` rejoue le corpus et publie le **taux de silence** : la part de defauts reels
   que la version courante ne detecte plus.

## Trois refus qui font la valeur du corpus

* **un cas dont l'attente est fausse des sa creation** est refuse : il occuperait la place
  d'un garde sans rien garder ;
* **un cas de securite gele alors que la redaction laisse deja passer la valeur** est
  refuse : on n'archive pas un defaut en cours, on le corrige ;
* **un cas edite a la main** est vu : l'artefact est lie par empreinte, et une valeur
  interdite qui n'est pas dans la charge brute est declaree « cas VIDE ».

## Ce que ce corpus n'est pas

Ce n'est pas un banc de performance : chaque cas est un **fait passe**, pas une moyenne.
Il ne remplace pas `jio bench` (le harness face a un modele) ni `jio mutants` (la suite
face a son propre code) : il garde ce qu'une trace a appris, et seulement cela.
