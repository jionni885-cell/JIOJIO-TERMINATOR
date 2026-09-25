# JIOJIO-TERMINATOR

> **Un système d'exploitation de l'anti-erreur pour agents d'IA.**
> Il ne remplace pas les modèles. Il rend la **vérification** indépendante de leur puissance.

```
     ██╗██╗ ██████╗      ████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ████████╗ ██████╗ ██████╗
     ██║██║██╔═══██╗     ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
     ██║██║██║   ██║        ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║   ██║   ██║   ██║██████╔╝
██   ██║██║██║   ██║        ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║   ██║   ██║   ██║██╔══██╗
╚█████╔╝██║╚██████╔╝        ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║   ██║   ╚██████╔╝██║  ██║
 ╚════╝ ╚═╝ ╚═════╝         ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
```

**Statut :** noyau **implémenté, mesuré, auto-audité et reproductible** — 187 tests verts, exécutable sans aucune clé API.
**Langue :** interface et rapports en français · prompts et agents en anglais (précision de raisonnement).

---

## La promesse — et sa limite honnête

Aucun système ne peut garantir zéro erreur. Deux théorèmes l'interdisent :
**Rice (1953)** — toute propriété non triviale d'un programme est indécidable ;
**Turing (1936)** — on ne peut pas décider si un programme termine.

Ce qui **est** atteignable, et que ce projet construit :

> **Aucune erreur ne passe silencieusement.**
> Elle est détectée, localisée, attribuée à l'agent fautif, corrigée — ou le système
> **s'abstient explicitement** en indiquant pourquoi.

C'est une garantie plus forte, et surtout **mesurable**.

---

## Pourquoi ça marche : la loi fondamentale

> *Un vérificateur ne vaut que par ce qui le distingue du générateur.*

Un modèle qui se relit partage ses biais avec lui-même : son information mutuelle avec le
générateur est élevée, il **valide ses erreurs avec confiance**. La recherche est sans ambiguïté :
l'auto-critique sans retour externe peut **dégrader** la performance.

D'où 5 conditions de décorrélation imposées par l'architecture :
**séparation de contexte · de modèle · de rôle · ancrage externe · mutation métamorphique.**

---

## Les 7 groupes de techniques

| Groupe | Techniques |
|---|---|
| **A. Casser la corrélation** | Revue aveugle · MAR (personas + juge) · hétérogénéité forcée · contextes séparés |
| **B. Prouver** | Preuve exécutable fail-closed · SPEC grounding (1 test / règle) · tests par propriétés · mutation testing · vérification formelle |
| **C. Détecter l'invisible** | MetaQA métamorphique · entropie sémantique · ClaimLedger + provenance · vérification par étape |
| **D. Garantir** | ConformalGate (`Pr[erreur ∧ accepté] ≤ α`) · conformité robuste |
| **E. Anti-triche** | Oracles cachés · rejeu déterministe (6 types d'exploit) · OccamGate (MDL) |
| **F. Apprendre** | Mémoire des échecs · skills auto-générées · évolution GEPA · synthèse CEGIS |
| **G. Stabiliser** | OscillationGuard · plafond d'itérations · non-régression obligatoire |

Détail complet, chiffres et sources : [`docs/DOSSIER-TECHNIQUES.md`](docs/DOSSIER-TECHNIQUES.md)

---

## Démarrage

Rien à installer : zéro dépendance obligatoire, Python 3.11+.

```bash
python -m jio doctor                     # état du système, fournisseurs détectés
python -m jio tasks                      # le banc d'essai : 5 tâches vérifiables
python -m jio bench --skill 0.30         # mesure le gain du harness
python -m jio audit mon_fichier.py       # audite un artefact (règles dérivées de lui-même)
python -m jio run "objectif…"            # mission complète (nécessite un CLI/une clé)
python -m jio artifacts --write          # écrit les artefacts natifs de tous les outils
python -m jio mcp --list                 # outils exposés via MCP
python -m jio trust "<objectif>"         # combien de vérification dépenser (bandit UCB1)
python -m jio memory --recall "<texte>"  # ce que le système a déjà payé comme erreurs
python -m jio learn --skill 0.15         # l'auto-amélioration paie-t-elle ? (protocole A/B/C)
```

Installation dans vos outils (ne copie que des fichiers texte, rien d'autre) :

```bash
./scripts/install.sh                      # simulation : montre ce qui serait fait
./scripts/install.sh --all --yes --project /chemin/vers/votre/projet
```

Le projet est configurable par `.env` : voir [`.env.example`](.env.example). **Aucune
variable n'est obligatoire** — sans clé, tout reste exécutable.

---

## Ce qui est mesuré (et ce qui ne l'est pas)

`jio bench` mesure quatre configurations sur le banc d'essai intégré, avec un
**bras de contrôle à budget d'appels égal** — sans lui, tout gain pourrait n'être
que du « best-of-N » déguisé.

| Configuration | Compétence 0.15 | Compétence 0.30 | Compétence 0.50 |
|---|---|---|---|
| modèle brut (1 appel) | 20,0 % | 30,0 % | 55,0 % |
| échantillonnage seul (best-of-3) | 45,0 % | 75,0 % | 85,0 % |
| **contrôle : autant d'appels, 0 vérification** | 65,0 % | 70,0 % | 90,0 % |
| **vérification exécutable + reprise** | **100,0 %** | **100,0 %** | **100,0 %** |
| JIO complet (livraison auditée) | 100,0 % | 100,0 % | 100,0 % |
| **gain isolé, à budget d'appels égal** | **+35,0 pts** | **+30,0 pts** | **+10,0 pts** |

> **Plus le modèle est faible, plus le harness vaut cher.** À budget d'appels
> strictement égal, la vérification apporte +35 points sur un modèle de
> compétence 0.15, +30 sur 0.30, et +10 sur 0.50 — face à un tirage aveugle du
> même modèle. Le gain vient de l'architecture, pas du nombre d'essais.
>
> C'est la réponse directe à la question posée au départ : *amener ses IA au
> niveau des meilleures*. Le harness ne remplace pas un meilleur modèle ; il
> récupère ce qu'un modèle moyen sait déjà faire mais ne sait pas **choisir**. Et
> c'est précisément là que l'écart était le plus grand.

**Ce que ces chiffres ne disent pas.** Les réponses sont **simulées** : le chiffre
mesure l'architecture, pas un modèle réel. La littérature mesure le harness sur
des modèles réels (+15 à +54 points selon les cas). Et la vérification n'aide que
sur les tâches **vérifiables** : ailleurs, la bonne sortie est l'abstention.

---

## Le terrain de preuve : le projet s'audite lui-même

`jio audit` dérive des règles exécutables **depuis l'artefact lui-même** — signature,
annotations, exemples de docstring, reproductibilité — puis les prouve dans un bac à
sable. Lancé sur tout le noyau :

```
blame.py 1/1 · consensus.py 3/3 · integrity.py 1/1 · oscillation.py 4/4 · panel.py 2/2
tasks.py 2/2 · cli.py 1/1 · errors.py 1/1 · journal.py 4/4 · types.py 1/1
conformal.py 4/4 · engine.py 1/1 · registry.py 2/2 · simulated.py 2/2 · compiler.py 2/2
autocheck.py 1/1 · entropy.py 2/2 · executable.py 2/2 · metamorphic.py 2/2 · emit.py 2/2
mcp_server.py 2/2        → CONFORME sur les règles vérifiables
```

Les modules de données pures renvoient **INDÉTERMINÉ**, jamais « conforme » : rien n'a
été prouvé, et le système le dit.

**Le plus coûteux n'a pas été d'écrire le vérificateur, mais de l'empêcher d'accuser
à tort.** Chaque faux positif corrigé correspond à un artefact sain déclaré coupable :

| Faux positif | Cause | Correctif |
|---|---|---|
| `ImportError` sur tout module interne | imports relatifs dans un fichier isolé | préambule de paquet (`__package__` + `sys.path`) |
| `SyntaxError` après correctif | `from __future__` n'était plus en tête | `exec(compile(...))` : la source garde son unité |
| `Calibration`, `ProgressPoint`, `Event` | dataclasses sans `__init__` dans l'AST | lecture des champs obligatoires |
| `Critic` (Protocol) | classe non instanciable par conception | détection `Protocol`/`ABC`/`@abstractmethod` |
| sonde jamais exécutée | `product(*[[]])` est vide | plan vide = un appel à zéro argument |
| `now()`, `Journal.replay()` | horloge = non-déterminisme **voulu** | détection de source → déclaré, ou **réserve** |

**Rejet contre réserve.** Une *règle dure* dont l'échec prouve un défaut condamne
l'artefact. Une règle **ADVISORY** (dépendance à l'environnement, horloge, hasard)
produit une **réserve** : elle est affichée, jamais transformée en verdict. C'est la
différence entre auditer et prétendre auditer.

---

## `jio scan` : la même preuve, appliquée à du code qui n'est pas le mien

Le vrai juge, c'est du code réel écrit par d'autres. Deux épreuves, mesurées.

**1. Un projet sain ne doit produire aucune alerte.** Sur un clone de
`python-humanize/humanize` (`jio scan src --exclude-tests`) : **0 problème**. Ce
zéro a coûté deux corrections, et la seconde est instructive :

| Fausse alerte | Ce qui se passait réellement |
|---|---|
| 7 × `ModuleNotFoundError: humanize._version` | fichier **généré à l'installation** (setuptools-scm), absent du dépôt → « non testable ici », ni défaut ni réserve |
| `AssertionError` sur 5 exemples de `time.py` | l'environnement d'audit n'avait pas `python-dateutil`. La cause réelle était **masquée** par un message générique : le contrôle de docstring effaçait la sortie de `doctest` |

Ce second point est le cœur du problème : **un vérificateur qui accuse à tort
détruit la confiance plus vite qu'il n'en crée.** Le contrôle de docstring restitue
désormais la trace réelle, et une dépendance absente est classée « non testable ici ».

**2. Un défaut injecté doit être trouvé.** Quatre bugs réalistes injectés dans
`humanize/filesize.py`, avec contrôle du projet intact :

```
bug injecte                            verdict      preuve / signalement
docstring mensongere (valeur fausse)   PROBLEME     [A-003] '3.1 MB' | Got: '3.0 MB'
non-reproductible (hasard)             SIGNALE      non-determinisme hors fonctions auditees : _jio_unstable (random.randint)
point d'entree renomme                 PROBLEME     [IMPORT] `naturalsize` importe de `humanize.filesize` mais n'y existe pas
syntaxe cassee                         PROBLEME     [SYNTAXE] la source ne compile pas : invalid syntax (ligne 113)
```

Trois verdicts, jamais deux : **PROBLEME** (prouvé), **SIGNALE** (réserve ou limite
déclarée, avec sa localisation), **silence**. Le banc refuse de compter une mutation
qui n'a rien changé au fichier — la version précédente croyait détecter deux bugs qui
n'avaient jamais été injectés, et comptait en réalité une fausse alerte.

**Ce que ces épreuves ont changé dans le produit** (chaque ligne vient d'un échec
observé, aucune n'a été décidée en théorie) :

- **l'audit couvrait UNE fonction par fichier.** Un bug dans une deuxième fonction
  documentée restait invisible : `jio scan` auditait sans auditer. Désormais toutes les
  fonctions documentées sont couvertes (plafond affiché, 8) — sur `humanize`, la
  couverture est passée de **13 à 32 vérifications** ;
- **renommer un symbole public n'était pas détecté** : l'erreur n'apparaît que chez
  l'appelant, sous forme d'`ImportError` donc classée « environnement ». Nouveau
  vérificateur de cohérence des imports (`jio/verify/imports.py`), sans exécution :
  noms importés **et** accès par attribut (`pkg.a.helper()`), résolution tolérante à la
  racine du scan ;
- **un fichier incompilable n'était signalé nulle part** : classer tout `SyntaxError`
  comme « environnement » rendait muet le pire défaut possible. Il est désormais un
  **défaut explicite** ;
- **`import random as _rnd` échappait à la règle de reproductibilité** : l'analyse
  cherchait la chaîne `random.`. Les alias sont résolus (`_rnd.randint` → `random.randint`),
  y compris `from time import monotonic as clock` ;
- **des limites honnêtes étaient calculées puis jetées** : « non couvert par cet audit :
  … », « non-déterminisme hors des fonctions auditées : … » n'étaient affichées nulle
  part. Elles sont maintenant lisibles (`jio scan -v`) et comptées dans le résumé
  — *un audit partiel n'est pas un audit complet* ;
- **`from pkg import a` (a = sous-module)** était accusé à tort, et un `__init__.py`
  résolvait ses imports relatifs vers le mauvais fichier : les deux bugs ont été
  trouvés **par JIO sur son propre code**, pas par relecture.

**3. Ne pas réinventer ce que d'autres font mieux.** Ruff, Flake8 et Pyflakes sont
l'état de l'art pour repérer les vraies erreurs en Python. `jio scan` les branche
quand ils sont présents (ruff, sinon flake8, sinon pyflakes), avec le jeu de règles
« vrais bugs » — `E9,F` : erreurs de syntaxe, noms non définis, et **code mort**
(import inutilisé, variable jamais lue, f-string sans valeur). Les règles de *style*
(ordre des imports, longueur de ligne) restent dehors : un projet qui passe ses tests ne
doit pas être déclaré fautif parce qu'il n'aime pas l'ordre de ses imports.

La porte a été élargie **après** avoir mis ce dépôt à zéro sur `F` — 24 imports morts et 2
variables mortes écartés, dont un `build_bank()` reconstruit à chaque tirage du banc. Une
porte qu'on élargit avant de nettoyer est une porte qu'on apprend à ignorer.

Chaque constat nomme son outil (`[ruff:F821]`) : c'est une preuve vérifiable, mais
elle n'est pas de JIO, et le dire est la moindre des choses. Les messages sont
expliqués en français, **le message d'origine est conservé**. Et si aucun analyseur
n'est installé, le rapport ne laisse pas croire que le code a été passé au crible :
il donne la commande exacte (`pip install ruff`).

```
3 PROBLEME(S) — avec la preuve :
    buggy.py
        [ruff:F821] nom non defini : le code ne peut pas s'executer — Undefined name `inconnue`
        [ruff:F821] nom non defini : le code ne peut pas s'executer — Undefined name `y`
        [ruff:F811] nom redefini : la definition precedente ne sert plus a rien — Redefinition of unused `doublon` from line 13
```

Vérifié : 3 défauts trouvés sur un fichier à vrais bugs, **0 faux positif** sur
`humanize` et sur le noyau, et toujours 3/4 + 1 signalé sur le banc d'injection.

L'auto-audit du noyau, après ces corrections :

```
Aucun probleme sur les regles verifiables.
47 fichier(s) Python · 72 verification(s) · 1 reserve(s) · 30 a audit partiel
```

**4. Un défaut trouvé en usage réel, pas en théorie : le journal ne vérifiait plus.**
Chaque nouveau processus repartait à `seq=0` et **ajoutait** au même fichier. Mesure
sur le journal du dépôt : **545 événements, chaîne cassée, 9 redémarrages**. Un
journal qui ne vérifie plus n'est pas un journal, c'est un fichier de texte — et
toute la promesse de transparence repose dessus.

Comportement retenu, celui d'un journal d'écriture standard : chaîne valide → reprise
exacte depuis la tête existante ; chaîne **cassée** → on n'écrit jamais à la suite
d'un journal falsifié, le fichier part en quarantaine (`journal.jsonl.corrompu-…`,
**jamais supprimé**) et une chaîne neuve commence **en le disant** ; si la
quarantaine est impossible, refus d'écrire (fail-closed). Vérifié de bout en bout :
545 événements corrompus → quarantaine → 2 exécutions → `jio trace` : *120 événements,
chaîne INTÉGRÉE*.

**5. Un code peut passer tous ses exemples et violer une propriété évidente.** C'est
la limite structurelle des tests par exemples : trente ans de littérature, et une
mesure récente — exemples seuls **68,75 %** de détection, propriétés seules 68,75 %,
**les deux combinés 81,25 %**. Le cas typique :

```python
def normalize(nums):
    """Normalise.

    >>> normalize([3, 1, 3])
    [1, 3, 3]
    """
    nums.sort()            # l'appelant ne s'attendait PAS a perdre sa liste
    return nums
```

La docstring est juste, la valeur rendue est la bonne, tous les exemples passent —
et le contrat est violé. `jio scan` dérive donc des propriétés **du code lui-même**,
sans modèle et sans réseau :

| Propriété | Ce qu'elle dit | D'où vient l'autorisation de l'affirmer |
|---|---|---|
| `P-001` non-mutation | l'argument de l'appelant reste intact | une fonction qui **rend une valeur** n'a pas à modifier son entrée ; une API « en place » (`-> None`, `sort_in_place`) n'est **jamais** accusée |
| `P-002` idempotence | `f(f(x)) == f(x)` | seulement si le **nom** ou la **docstring** le promet (`normalize`, « idempotent ») — `double(1)=2` puis `double(2)=4` : le type `int -> int` ne prouve rien, et accuser ce code serait un faux positif |
| `P-003` aller-retour | `decode(encode(x)) == x` | seulement pour les paires dont le **nom** promet l'aller-retour (`encode/decode`, `pack/unpack`, `dump/load`…), y compris en suffixe (`url_encode`/`url_decode`) |

Les entrées de test ne sont pas inventées : **annotations** d'abord, sinon les
exemples `>>>` de l'auteur (écrits et validés par lui, donc dans le domaine), et pour
une paire d'aller-retour le **type de retour de la fonction inverse** — qui est, par
définition de la propriété, le type de `x`. Chaque refus est exonéré : une exception
n'est jamais une violation (le domaine déclaré ne couvre pas forcément tous les cas).

Le défaut est livré avec son **plus petit contre-exemple**, obtenu par réduction
automatique — un rapport utilisable :

```
[P-001:normalize] l'argument a ete MODIFIE par normalize :
    le plus petit contre-exemple est ([1, 0],)
```

Mesure sur un banc de 8 artefacts fautifs (mutation d'argument, aller-retour avec
perte, idempotence rompue) et 8 artefacts sains, **classes identiques, seules les
règles changent** :

| | fautifs détectés | artefacts sains accusés |
|---|---|---|
| règles par exemples seules (A-*) | 1/8 | 0/8 |
| A-* **+ propriétés** (P-*) | **8/8** | **0/8** |

Coût : **+14 règles sur 47 fichiers**, dérivation purement statique (aucun appel
réseau, aucun modèle ; la durée de dérivation du noyau est inchangée, ~0,15 s).
Silence délibéré sur une paire comme `join_fields`/`split_fields` : elle ne promet
pas l'aller-retour (un séparateur peut apparaître dans un élément) — **on ne déclare
que ce qu'on peut prouver, et on se tait sur le reste**.

Ce chantier a trouvé deux défauts dans JIO lui-même, tous deux de la famille
« rapport inutilisable » :

- le réducteur de contre-exemple livrait `[1,1,2,2,3,3,4,4,5,5,6,6]` — une liste
  **déjà triée**, donc qui ne reproduit rien : l'appel mutait l'objet du cas de test,
  et le témoin publié était le résidu d'après mutation. Corrigé (appel sur copie,
  comparaison portant sur l'objet réellement passé) et le réducteur supprime
  désormais élément par élément au lieu de tronquer ;
- une docstring qui **mentionne** `>>>` dans sa prose déclenchait la règle
  « les exemples sont satisfaits », laquelle échouait faute d'exemple réel : mon
  propre fichier était déclaré fautif. La détection interroge maintenant l'analyseur
  de `doctest` lui-même (source de vérité unique).

**6. Quand plusieurs candidats se contredisent, le silence est le vrai danger.** Avec une
spécification incomplète — le cas normal — deux réponses peuvent satisfaire toutes les règles
et se contredire sur ce que les règles ne couvrent pas. Mesure :

```
ordre des candidats         sans comparaison  avec comparaison
le faux en premier                      FAUX             juste
le faux au milieu                      juste             juste
le faux en dernier                     juste             juste
```

Le candidat livré dépendait de **l'ordre de génération** (`_better` accepte tout candidat
dont le ratio est au moins égal : c'est donc le dernier arrivé qui gagne à égalité). JIO
compare désormais les candidats à égalité de preuves en les exécutant sur les mêmes entrées
dérivées — **coût : zéro appel de modèle**, les candidats sont déjà payés :

- un désaccord devient un constat **nommé**, avec l'entrée exacte et les valeurs obtenues ;
- quand une majorité stricte de candidats s'accorde, c'est elle qui est livrée ;
- **jamais bloquant** : un désaccord peut porter sur un comportement non spécifié, et deux
  implémentations correctes peuvent différer — l'accuser serait le faux positif que tout ce
  projet refuse.

Deux erreurs corrigées en route, et c'est la partie instructive : j'avais écrit que le moteur
gardait « le premier arrivé » — **déduction non vérifiée**, le code prend le dernier ; et mon
premier oracle de mesure comparait `mean([2, 4])`, où les deux implémentations rendent `3` :
la mesure ne mesurait rien. Les deux sont corrigés, et le test dit pourquoi.

**7. Un axe examiné puis écarté.** Pondérer les votes des critiques par leur fiabilité
mesurée était une piste séduisante. Mesure faite avant de construire : un critique **aveugle**
(taux de détection 0 %) ne change pas la décision d'un panel de trois — le vote majoritaire
l'absorbe déjà. L'axe n'a donc **pas** été construit : une brique qui ne change rien est du
poids, pas une amélioration.

**8. Les règles doivent devenir des tests — sinon ce ne sont que des slogans.** Jusqu'ici, le
compilateur énumérait des règles (« une liste vide renvoie 0 »), le moteur les faisait **lire** au
modèle… et aucune n'était jamais traduite en test exécutable. Hors banc d'essai — c'est-à-dire
dans **toute mission réelle** — la seule preuve exécutable disponible était la cohérence de
l'artefact avec sa propre documentation. Un artefact peut donc tenir parfaitement sa propre
docstring et ne rien faire de la mission demandée. Le moteur ne pouvait alors que **s'abstenir**.

JIO demande maintenant au modèle de traduire chaque règle en une assertion exécutable, avec trois
issues possibles, toutes explicites :

- la règle devient un **témoin exécutable** ;
- le modèle **avoue** ne pas savoir la traduire, avec sa raison (« aucune règle » vaut mieux qu'une
  règle fausse) ;
- le test est **refusé par les garde-fous** — un modèle est du contenu **non fiable** : ses tests
  n'entrent pas parce qu'il les a écrits, mais parce qu'ils ont passé une porte (aucun `import`,
  aucun accès fichier/réseau/processus, aucune syntaxe invalide, et le test doit réellement
  appeler l'entrée publique). Chaque refus est motivé et visible.

Mesure au banc, **sans aucun oracle**, à budget égal (3 candidats + 1 appel de traduction = 4
appels, soit exactement un best-of-4) :

```
fidelite du traducteur      juste  abstention  faux+reserve  SANS RESERVE
 100%                           5           0             0             0
  50%                           2           3             0             0
   0%                           0           5             0             0
```

Trois choses à lire dans ce tableau, et la troisième est la seule qui compte vraiment :

1. quand le modèle **lit correctement** les règles, la preuve devient possible **sans oracle** :
   5 livraisons justes sur 5, là où le moteur s'abstenait systématiquement ;
2. quand il les lit **mal**, le moteur **s'abstient** : il perd des livraisons, **jamais la
   justesse**. Traduire mal ne fait pas livrer faux, cela fait renoncer ;
3. **la dernière colonne reste à zéro** : dans aucun cas une erreur n'a été livrée **sans que rien
   ne le dise**. Le garde-fou est simple à énoncer : un témoin que **tous** les candidats échouent
   ne prouve rien sur eux — soit il est faux, soit tous les candidats sont faux, et rien ne permet
   de trancher. La règle est donc déclarée **NON PROUVÉE** : le témoin ne peut ni accuser ni
   innocenter, et son échec n'est pas effacé du verdict. Toute règle non prouvée interdit la mention
   « livré sans réserve », le rapport la nomme, et `jio trace` montre le texte exact du témoin — ce
   que le modèle a eu le droit d'affirmer.

La traduction est **robuste à l'emballage** : objet JSON, tableau d'objets (le format que le
compilateur de spécification demande juste à côté — donc la déviation la plus probable d'un vrai
modèle), objet enveloppé, bloc de code, NDJSON, clés anglaises ou françaises. Un mode de réponse
qu'on refuserait pour sa forme ferait perdre les témoins sans rien protéger : **la porte de sûreté
juge le test, pas l'emballage**. Et tout est prouvé sur le **chemin réel** — une CLI lancée en
sous-processus qui traduit les règles, et une CLI qui n'y arrive pas (aveu, abstention).

Quand la mission **fournit** ses oracles (le banc), la traduction n'est même pas demandée : un
oracle réel est la référence, le modèle ne prend pas sa place. Et quand la preuve repose sur des
témoins traduits, le rapport **le dit** : un artefact prouvé par une traduction n'est pas prouvé de
la même façon qu'un artefact prouvé par les oracles de la mission, et le lire est un droit.

Essayez-le sans clé d'API :

```sh
jio run "somme des pairs d'une liste" --simulate --task sum_even --no-oracle
```

**9. Ce qui a été prouvé une fois ne se repaie pas.** Traduire les règles en témoins est un appel
de modèle : sans mémoire, ce pari est repayé **à chaque mission identique**. La bibliothèque de
témoins conserve les traductions qui ont participé à une livraison **prouvée** :

```
execution   statut                     traductions  memoire  juste
1           delivered                            1        3    True
2           delivered                            0        3    True
3           delivered                            0        3    True
```

Trois propriétés, et la deuxième est la vraie raison d'être du module :

- **porte d'entrée** : seule une livraison `DELIVERED` alimente la mémoire. Une abstention ou une
  réserve ne prouve rien, donc elle n'a **rien à transmettre** — un faux témoin ne peut pas entrer
  par cette porte ;
- **le contenu d'une mémoire est du contenu hostile** : le fichier est vérifié par chaîne de hachage.
  Édité à la main ou écrit par un autre programme, il est mis en **quarantaine** (renommé, jamais
  supprimé) et **jamais appliqué**. La même vérification protège désormais la **mémoire des échecs**,
  dont le contenu repart dans les prompts — c'était un vecteur d'injection, pas seulement un cache ;
- **auto-réparation** : un témoin repris dans la mémoire qui se met à accuser **tous** les candidats
  est **révoqué**, et la mission suivante re-traduit. Une mémoire ne s'auto-entretient pas en
  accumulant des jugements faux.

Trois bugs réels trouvés en écrivant ce module, tous du même genre — **une clé qui ne correspondait à
rien, donc une fonction qui ne faisait rien en silence** : la révocation cherchait les règles par
**nom** alors que le magasin les indexait par **empreinte d'énoncé** (aucune révocation n'aboutissait
jamais) ; une reprise **partielle** court-circuitait la traduction des règles manquantes (une règle
modifiée n'était plus jamais traduite, et la mission ne la prouvait plus du tout) ; et le chargement
d'une mémoire utilisait `from_jsonl`, qui **lit sans vérifier** — la quarantaine n'avait donc jamais
lieu.

**10. Classes comprises, et une trappe qui a bien failli passer.** L'axe d'auto-cohérence (« un
artefact ne doit pas contredire ce qu'il affirme ») couvrait déjà les classes par leurs exemples
`>>>`. En le vérifiant, une trappe réelle est apparue :

```
>>> c.ajouter(-5)     <- sortie non annoncée : « Expected nothing »
>>> c.valeur          <- « Expected: 0, Got: -5 » : DÉCISIF
```

La première ligne suffisait à faire classer **l'ensemble** en réserve, et le mensonge du code
passait. Le tampon de doctest contient pourtant les deux échecs : il suffit de regarder si l'un
d'eux est **décisif** (`Expected:` suivi de `Got:` — et non la forme `Expected nothing`). Un échec
décisif ne se cache plus derrière un exemple pédagogique voisin.

Symétriquement, l'exemple d'**illustration seul** reste une réserve motivée : accuser toute docstring
pédagogique rendrait l'outil inutilisable sur du vrai code. Les deux comportements sont verrouillés
par des tests, le second autant que le premier. Mesure sur le corpus : **4 rejets francs, 1 réserve
motivée, 0 faux rejet**. Balayage de contrôle sur **240 doctests** de paquets publiés
(`more-itertools`, `toolz`, `python-dateutil`, `PyYAML`) : aucun échec, donc aucune accusation — la
règle ne peut pas produire de faux positif sur du code dont les exemples passent.

Le message d'échec porte maintenant la **valeur attendue**. Avant, il rapportait
`2 exemple(s) en echec : 0 | Got: | -5` : l'auteur lisait un échec sans savoir à quoi son code
devait répondre.

---

**11. Un diagnostic qui se trompe sur la cause est pire qu'un diagnostic muet.** `jio doctor`
affichait « aucun dépôt `origin` : impossible de dire si ce travail est sauvegardé ailleurs » sur un
dépôt **qui avait** `origin` configuré — et il envoyait l'utilisateur vérifier `git remote -v`, une
chose qui n'était pas en cause. Deux questions différentes étaient confondues : *un distant
existe-t-il ?* et *peut-on comparer ?*. Le diagnostic distingue maintenant les deux et donne la
commande exacte qui rend la comparaison possible :

```
branche arena/…  ·  AUCUN DISTANT COMPARABLE  (distant present)
    `origin` est configure, mais la branche arena/… n'a pas de
    reference locale : impossible de dire si ce travail est sauvegarde.
    Rendre la comparaison possible :  git fetch origin arena/…
```

Le second cas, lui, dit ce qu'il en est vraiment : « aucun dépôt distant configuré : ce travail
n'existe QUE ici ». Deux états différents, deux phrases différentes — et un test par état.

**12. Prouver ses propres CLI, avant la première mission.** « Un CLI installé » et « un CLI avec
lequel JIO peut prouver quelque chose » sont deux choses différentes : il peut n'être pas
authentifié, répondre un format inattendu — ou ne pas savoir convertir une règle en test
exécutable, ce dont dépend toute la preuve hors banc. `jio providers --prove` envoie une requête
**réelle** à chaque fournisseur détecté :

```
[ ok   ] cli::opencode (opencode/default) · repond en 0.0s · traduction : 2 temoin(s), 0 aveu(x), 0 refus
         R-001 -> assert moyenne([1, 2]) == 1.5
         R-002 -> ok = False
...
BILAN : 1/1 repondent, 1/1 savent traduire les regles en temoins.
```

Trois verdicts distincts, parce qu'ils appellent trois décisions différentes : **injoignable**
(non authentifié : rien à espérer), **répond mais ne sait pas traduire** (il peut encore écrire du
code, prouvé par des oracles), **capable de prouver sans oracle**. Les tests rendus passent la
**même** porte de sûreté que dans une mission — la sonde n'est pas plus indulgente : sinon elle
annoncerait une capacité que la mission refuserait d'utiliser. Un test hostile proposé par un vrai
CLI est compté comme **refusé**, et la sortie le montre.

---

## Le chemin réel est prouvé, pas seulement décrit

Aucune clé API dans l'environnement de développement : on ne peut donc pas mesurer un
vrai modèle. Mais on peut prouver **tout ce qui est vérifiable** — détecter une CLI
externe, lui parler, récupérer sa réponse, la vérifier, la soumettre au consensus puis
à la porte de conformité, et livrer. *Un fournisseur qui n'a jamais tourné n'est pas un
fournisseur, c'est une intention.*

Avec de faux agents au format JSON-lignes d'`opencode` (scripts, aucun réseau) :

| Configuration | Statut | Motif |
|---|---|---|
| 1 agent | `DELIVERED_WITH_RESERVATION` | « tous les agents partagent modèle et verdict — ce n'est pas un consensus, c'est un écho » |
| 2 agents | `DELIVERED_WITH_RESERVATION` | plafond inatteignable, **expliqué** (voir ci-dessous) |
| **3 agents distincts** | **`DELIVERED`** | 4/4 règles prouvées — la chaîne complète fonctionne |

### Un refus doit être calculable, sinon il est inutilisable

Le score est : `preuves × accord × décorrélation × confiance`, avec
`décorrélation = min(1 ; 0,55 + 0,15 × couples (modèle, verdict) distincts)`.

Conséquence arithmétique : **avec 2 modèles distincts, une mission parfaite plafonne à
0,85** — le seuil non calibré de 0,90 est hors d'atteinte, et *aucune* amélioration du
travail ne peut livrer. L'utilisateur n'avait aucun moyen de le savoir : le motif
s'affichait « confiance sous le seuil » et s'arrêtait là (tronqué à 200 caractères,
coupé juste avant la partie actionnable).

Désormais le refus donne **l'action d'abord**, le calcul ensuite :

```
PLAFOND INATTEIGNABLE : avec 2 modele(s) distinct(s), une mission PARFAITE plafonne a
0.850, sous le seuil 0.900 — aucune livraison ne sera acceptee. Solutions : brancher un
3e modele distinct, calibrer la porte, ou elargir l'alpha.
decompte : preuves 1.000 x accord 1.000 x decorrelation (2 couple(s) modele-verdict
distinct(s) sur 5 voix) x confiance 0.807 = 0.807
```

Le chiffre qui plafonne la confiance (`effective_panel`) était calculé puis **jeté** :
il est maintenant porté par le consensus et affiché.

---

## Quand il n'y a pas de code à exécuter : la prose a ses témoins

Tout ce qui précède prouve du **code**. Une mission généraliste — analyse, rapport,
note de synthèse — n'a rien à exécuter : JIO s'abstenait, et c'est précisément là que
se logent les hallucinations, dans du texte que personne ne recalcule.

Un document contient pourtant des affirmations **vraies ou fausses sans
interprétation**. `jio claims` en vérifie quatre genres :

| Genre | Ce qui est vérifié | Sévérité |
|---|---|---|
| Calcul annoncé | `7 × 6 = 43` → évalué par un **AST restreint** (nombres et 4 opérations, aucun `eval`) : la valeur réelle est écrite dans le refus | **bloquant** |
| Bloc présenté comme `python` | compilé : une erreur de syntaxe est un fait, pas une opinion | **bloquant** |
| Chemin cité (`` `a/b.py` ``) | existence sous `--racine` | **signalé**, jamais accusé |
| Commande citée (`` `jio scan .` ``) | **le parseur de la CLI** : la sous-commande et chaque option existent-elles ? | **bloquant** hors bloc de code |

La retenue est une décision, pas une indulgence : un document d'architecture cite des
fichiers **à créer**. Un outil qui accuse là-dessus se fait désactiver en deux jours.
Et « rien à vérifier » n'est pas un quitus — `jio claims` renvoie alors **1** en le
disant, pour qu'une note vide ne passe pas pour un document conforme.

### Les commandes citées : l'oracle est le programme lui-même

L'option correcte est `jio scan --strict`. Avec une lettre de trop, l'utilisateur tombe
droit dans un `unrecognized arguments` :

```console
$ jio scan . --stricte
error: unrecognized arguments: --stricte
```

C'est un mensonge **vérifiable**, et il ne coûte aucun modèle : le parseur d'arguments du
programme sait exactement quelles commandes existent. Pas d'heuristique, pas de confiance —
la commande existe, ou elle n'existe pas.

```
[ok ] commande citee EXISTE : `jio scan ...`
[KO ] option INCONNUE : `--stricte` sur `jio scan` — peut-etre `--strict` ?
[KO ] commande INCONNUE : `jio scna` n'existe pas dans cette version de la CLI — peut-etre `jio scan` ?
```

Deux règles de retenue, chacune payée par une mesure :

- **une commande en pleine phrase est une instruction** — le document demande de la taper,
  donc une faute y est bloquante ; **dans un bloc de code, c'est un exemple** — souvent la
  démonstration d'une erreur, donc signalée seulement. Sans cette distinction, la page qui
  documente une ancienne option fausse serait déclarée non conforme, et le seul moyen de la
  rendre conforme serait de ne plus en parler ;
- **l'analyse s'arrête à la première coquille** (`|`, `&&`, `>`, `#`) : après, la ligne de
  commande appartient à l'autre programme. Sans cela, `` `jio run "x" | jq .id` `` ferait
  chercher une option `jio` chez `jq`.

Le premier passage sur les documents de ce dépôt a trouvé **deux défauts réels** : `jio sync`
promis dans trois documents alors que la commande n'existait pas (elle existe maintenant),
et `jio --version` pris à tort pour une sous-commande (faux positif, corrigé). Sur les 30
documents du dépôt : **0 réfutation** restante.

Un document fautif est refusé avec sa preuve, un document sain reste totalement muet :

```
document               code      bilan
rapport_sain.md        code 0    6 affirmation(s) verifiee(s) · 0 refutee(s) · 0 signalee(s)
rapport_fautif.md      code 1    5 affirmation(s) verifiee(s) · 2 refutee(s) dont 2 bloquante(s)
preuve du calcul faux  7 x 6 vaut 42, le texte annonce 43
-> le fautif est REFUTE (code 1), le sain reste MUET (code 0) : le temoin discrimine.
sans affirmation       code != 0 — rien a verifier n'est pas un quitus, et c'est DIT.
```

Rejouable : `bash scripts/evidence.sh`, étape **3 quinquies** (corpus versionné dans
`evidence/claims/`).

### Quatre bugs, tous du même genre : une vérification qui ne vérifiait rien

`verifier()` rendait une liste **vide** alors que `extraction()` trouvait bien les deux
calculs du document. Un vérificateur qui ne trouve rien ne dit pas « tout va bien » : il
dit qu'il n'a rien regardé — et personne ne peut faire la différence de l'extérieur.

| Bug | Cause | Correctif |
|---|---|---|
| Le vrai signe `×` n'était pas reconnu | classe de caractères écrite **à la main** (`[-+*/×x]`) : un caractère non-ASCII s'y perd sans bruit | classe **construite** depuis la table des opérateurs |
| Tout calcul en fin de phrase échappait | regard final `(?![\w.])` : un nombre suivi d'un **point** était refusé, donc exactement la façon dont un rapport écrit ses calculs | `(?![\w])(?!\.\d)` — refuser un chiffre qui suit, pas une ponctuation |
| Aucune expression n'était acceptée | `ast.walk` visite **aussi les nœuds d'opérateur** (`ast.Add`, `ast.Mult`) : aucune catégorie autorisée ne les acceptait, donc *toute* expression était refusée | descente explicite de l'arbre, **le contrôle et le calcul dans la même fonction** |
| `eval()` sur du contenu non fiable | — | supprimé : le calcul est fait sur les seuls nœuds admis |

Le troisième est le plus instructif : la fonction de contrôle était **toujours fausse**,
et comme elle était écrite à part du calcul, rien ne le signalait. Contrôle et calcul
partagent maintenant un seul passage — un test couvre chacun des quatre bugs
(`tests/test_claims.py`).

---

## Une mission sans code : le document entre dans la même boucle

Tout ce qui précède prouve du **code**. Une mission généraliste — rapport, analyse,
note — n'a rien à exécuter : le moteur s'abstenait, honnêtement mais inutilement. Or
c'est là que se logent les hallucinations, dans du texte que personne ne recalcule.

`jio run --prose` fait traverser **la même boucle** à un document. Pas une seconde
machinerie : un vérificateur qui se présente comme un prouveur.

```
jio run --prose --simulate                 # banc de documents, sans clé API
jio run "rédige le rapport de perf" --prose   # mission réelle
jio bench --prose --runs 5                 # mesure : aveugle vs vérifié
```

| Étage | Sur du code | Sur un document |
|---|---|---|
| Spécification | dérivée de l'objectif | **statique** : la règle `P-000` est vraie par construction, la confier à un modèle serait lui demander d'autoriser sa propre existence |
| Preuve | bac à sable, tests exécutés | calculs (AST restreint), blocs annoncés comme Python, chemins cités, commandes citées |
| Auto-cohérence (`self_check`) | exemples `>>>` | **désactivé** — un document n'a pas de documentation exécutable |
| Mutation | mutants tués | **désactivé** — il n'y a pas de mutant à tuer |
| Panel, consensus, porte, journal, garde-fous | identiques | **identiques** |

Les trois étages sans objet sont coupés **dans `Engine.__post_init__`**, à un seul
endroit : les laisser actifs produirait une abstention incompréhensible, et compter
sur chaque appelant pour y penser est une erreur de conception.

### La règle `P-000` : « rien à vérifier » n'est pas un quitus

Un document sans la moindre affirmation vérifiable ne ressort pas « conforme » mais
« rien n'a été prouvé ». Sans cette règle, un vérificateur qui ne trouve rien
produirait un succès vide — exactement le silence que ce projet refuse. Elle échoue
aussi quand une affirmation est **réfutée** : un document fautif est refusé par une
règle nommée, pas par un compteur.

### Ce que le banc de documents mesure

Même définition que pour le code, et c'est la plus sévère : **erreurs livrées sans
rien dire** — un document non correct livré en `DELIVERED`.

```
bras                                   justes   comparaison
competence 0.00                          0.0%   ... SILENCIEUX : 0   sous reserve : 4  appels 10.5
competence 0.35                        100.0%   ... SILENCIEUX : 0   sous reserve : 0  appels 4.5
ERREURS LIVREES SANS RIEN DIRE : 0  <- le seul chiffre qui doit rester a zero
```

Un document non correct livré **sous réserve** n'est pas un silence : le signalement
est nommé et consultable. C'est un choix, et il est écrit dans le code.

---

## Mesurer sur TON modèle, pas sur une simulation

Le banc mesurait ses quatre bras sur une simulation déterministe : honnête, reproductible,
sans clé — mais cela ne répond pas à la seule question qui compte pour toi : **mon modèle,
avec le harness, vaut-il mieux que mon modèle seul ?**

```bash
jio bench --provider cli:opencode     # ton CLI, déjà authentifié
jio bench --provider cli:hermes
jio bench --provider cli:claude       # claude, codex, gemini, aider...
jio bench --provider openai:mon-modele  # JIO_BASE_URL + JIO_API_KEY
jio bench                             # simulation (défaut), aucune clé
```

Un outil inconnu reste utilisable, il suffit de donner sa ligne de commande :
`JIO_CLI_MON_OUTIL_ARGV='mon-outil run {prompt}'` — ou sans `{prompt}`, l'invite part sur
l'entrée standard (plus sûr pour les invites longues).

**La règle qui ne se négocie pas : un modèle demandé et indisponible ARRÊTE la mesure.**
Un repli silencieux sur la simulation produirait un rapport crédible, détaillé, avec un
modèle qui n'a jamais tourné — exactement le mensonge que ce projet existe pour empêcher.
Le message donne le chemin à installer, et rien d'autre.

Ce qui change quand tu branches ton modèle : les **générateurs** et le **panel** (le même
CLI est appelé plusieurs fois, avec des personas différentes — un panel d'une seule voix
n'est pas un panel). Ce qui ne change pas : la **vérification**, qui reste réelle et
exécutée. C'est ce qui rend la comparaison valable.

Les bras sans oracle (S4/S4b/S4c) reposent sur un *traducteur simulé* à fidélité fixée :
avec un vrai modèle, ce serait lui qui traduirait et le chiffre ne voudrait plus rien dire.
Ils ne sont donc **pas affichés** (`non mesure`), et la sortie dit pourquoi. Un chiffre
inventé vaut moins qu'une case vide.

### La preuve du câblage, sur un vrai binaire

Un faux modèle en ligne de commande (`faux-modele`) se trompe toujours sans retour d'échec
et se corrige quand on lui dit ce qui casse — le comportement d'un modèle de base. Mesure
réelle, 5 tâches, 1 tirage, CLI externe appelé par `subprocess` :

```
    config                                    reussite            IC95  appels   vs S0
    modele brut (1 appel)                        0.0%      [0% ; 43%]     1.0    n/a
    echantillonnage seul (best-of-3)             0.0%      [0% ; 43%]     3.0    n/a
    CONTROLE : autant d'appels, 0 verification     0.0%      [0% ; 43%]     6.0    n/a
    verification executable + reprise          100.0%    [57% ; 100%]     6.0    n/a
    JIO complet (livraison auditee)            100.0%    [57% ; 100%]     6.0    n/a

      sans verification    0.0%   avec verification  100.0%   ecart +100.0 points  IC95 [+100.0 ; +100.0]
      -> l'intervalle EXCLUT zero : le gain vient de la VERIFICATION, pas du nombre d'essais.
```

Même modèle, même budget d'appels : la colonne « contrôle » fait exactement autant d'appels
que le harness, sans vérifier, et ne trouve rien. Le `n/a` de la dernière colonne est
volontaire : un ratio sur une base **nulle** n'existe pas, et la première version affichait
`1000000000.00x`.

## Ce que la configuration coûte en contexte, mesuré

Un fichier de contexte trop long est **survolé, pas lu** : il occupe la fenêtre et
n'apporte rien — c'est pire que de ne pas l'avoir. Le budget n'existait ici que sous la
forme d'un test vert, ce qui ne dit rien à l'utilisateur. `jio artifacts --budget` le rend
visible :

```
  CHARGE AU DEMARRAGE — un outil n'en lit qu'UN (celui de son dialecte)

    CLAUDE.md                          136 ligne(s)    1653-2273   jetons
    AGENTS.md                          133 ligne(s)    1609-2212   jetons
    .cursor/rules/jio.mdc              134 ligne(s)    1595-2193   jetons

    Cote d'une session REELLE : ~1830 a 1914 jetons selon l'outil, pas la somme.

  DISPONIBLE A LA DEMANDE — competences
    TOTAL : 11 fichier(s), ~5715 jetons (estimation)
```

Trois choix de méthode, tous dictés par la même règle :

- **Un intervalle, pas un chiffre.** La borne basse compte 3,2 caractères par jeton
  (français, code — les accents et les indentations tokenisent mal), la haute 4,4 (prose
  anglaise). Un tokenizer réel serait une dépendance, et la mesure varie d'un modèle à
  l'autre. En dessous du seuil avec la borne **haute**, c'est bon ; au-dessus avec la
  **basse**, c'est dépassé ; entre les deux, c'est « à vérifier » — et c'est affiché ainsi.
- **Pas de total qu'aucune session ne paie.** Le premier jet annonçait « contexte injecté
  au démarrage : ~9 285 jetons » en sommant les cinq dialectes. Aucune session ne paie ce
  total : Claude lit `CLAUDE.md`, Cursor lit `.cursor/rules/jio.mdc`. Le rapport dit
  maintenant ce qu'une **session réelle** paie, et le `doctor` mesure le fichier que l'outil
  lit — pas la source qui le produit, qui contient des commentaires de maintenance jamais
  émis (cette erreur affichait « TROP LONG » pour des fichiers de 133 lignes).
- **Charger ≠ disponible.** Les 11 compétences et les 7 agents se chargent à la demande
  (révélation progressive) : les compter au démarrage ferait croire à un coût qui n'existe
  pas.

Une compétence doit aussi rester petite : au-delà d'environ 5 000 jetons, elle n'est plus
chargeable en une fois. La plus longue fait 768 jetons.

## Le hook pre-commit qui vérifie les **documents**

Le dépôt déclarait `jio-scan-strict` comme « échoue aussi si le projet est incohérent à
l'import » — avec **exactement la même commande** que le hook normal. Une promesse sans
implémentation, dans le fichier même qui prétend attraper ce genre de chose.

Le mode `--strict` existe maintenant : il fait échouer ce que le mode normal se contente
d'afficher — les **réserves** (une règle n'a pas su trancher) et les fichiers **non
testables** (la vérification n'a pas pu avoir lieu). Sur ce dépôt : code 0 sur `jio/`
seul, code 1 sur l'ensemble. Une réserve n'est pas une accusation, mais elle n'est pas un
quitus non plus : en CI, elle doit être levée ou déclarée.

Et un hook qui manquait : **`jio-claims`**, sur les documents modifiés. Le README, les
notes de conception et les rapports contiennent des calculs, des blocs et des chemins —
c'est là que vivent les erreurs qu'aucun test ne voit.

```yaml
- id: jio-claims
  entry: jio claims --hook
  files: \.(md|markdown|rst|txt|org|adoc)$
```

Le mode `--hook` a **son propre contrat**, et il est étroit à dessein : il n'échoue que sur
une affirmation **réfutée**. Sans lui, le hook aurait un choix impossible — ignorer le code
3 (et un document muet passerait pour un quitus), ou le traiter comme un échec (et un
commit serait refusé sans qu'aucune faute n'existe). `jio claims` hors hook garde les trois
codes ; le hook les absorbe pour ce qu'ils sont.

```
    [ok] README.md : 12 verifiee(s), 4 signalee(s) non concluante(s)
    [--] note_sans_affirmation.md : rien a verifier (ni succes, ni echec)
    [KO] rapport_fautif.md : 2 affirmation(s) refutee(s)
```

Ce dernier point a été trouvé par un test écrit **avant** de considérer le travail fini :
au premier jet, un document muet s'affichait `[ok] 0 vérifiée(s)` — un succès à zéro
faute, c'est-à-dire l'inverse de ce qu'il est.

## Un contenu non fiable ne fixe pas le temps de travail de l'outil

Un document est du contenu **non fiable** par défaut. Deux mesures, toutes deux
trouvées en cherchant la limite — pas en la supposant :

| Entrée hostile | Avant | Après |
|---|---|---|
| Une ligne contenant 20 000 calculs | **114 secondes** (rescan de la ligne entière pour chaque calcul) | 0,03 s, borné, et `NON verifiee(s) (limite de volume)` dans le bilan |
| `"1 + " × 50000` — une longue chaîne **sans** `=` | **plus de 600 secondes** : le moteur d'expressions régulières essayait toutes les découpées possibles d'un groupe répété | 0,006 s — **il ne peut plus y avoir de retour arrière**, la grammaire ne l'exprime plus |

Le second cas a imposé une réécriture, et elle est instructive. La détection part
désormais du **résultat annoncé** (`= 42`, `vaut 42`) et **remonte** l'expression à la
main, dans une fenêtre bornée. Une expression n'est plus une expression régulière : elle
ne peut donc plus exploser.

### Deux pièges que cette réécriture a révélés

- **Évaluer une PARTIE des termes.** Une somme de 40 termes dépasse la borne : la
  descente pouvait n'en prendre que la fin et la comparer au total — un refus inventé.
  Un contrôle de continuation à gauche l'interdit, et le calcul est compté
  « trop long pour être évalué », ni vérifié ni accusé.
- **`4 mises à jour sur 4 = 75 %`** était lu comme le calcul `4 = 75`, donc refusé :
  une accusation fausse sur une phrase correcte. Un calcul doit contenir **au moins un
  opérateur**.
- **`vaut` au milieu d'une expression.** Dans `le total vaut 7 x 6 = 43`, le mot
  `vaut` annonçait `7` — le premier *terme* de l'expression, pas un résultat. Le rapport
  déclarait alors « 1 calcul trop long pour être évalué » : une lacune **inventée**. Un
  résultat n'est jamais suivi d'une opération ; lui interdire cette suite a supprimé le
  faux motif. Une lacune fausse est pire qu'aucune : elle apprend à ignorer les vraies.
- **Une lacune inventée coûte plus cher qu'une lacune manquante.** Un compteur dédié aux
  résultats annoncés *sans expression lisible* (`le total vaut 42 ms`, `seq=0`) a
  produit **douze lacunes inventées sur le seul README de ce dépôt**. Ces cas ne sont pas
  des calculs manqués : c'est du texte, ou du code en ligne. Le compteur existe toujours
  dans le code — il sert à *classer* — mais il ne compte plus rien. Seule une chaîne
  réellement **coupée** par la borne est déclarée : là, un calcul existe et n'a pas pu
  être jugé.
- **Le `x` de « faux » n'est pas une multiplication.** La garde de continuation lisait
  le dernier caractère de la fenêtre ; le mot « f**aux** » finissait donc par le symbole
  `x`, la chaîne était déclarée coupée, et le rapport annonçait « 1 calcul trop long »
  sur une phrase qui n'en contenait aucun. Un opérateur alphabétique n'en est un que
  s'il est **détaché** : `3 x 4` oui, `faux` non.

## Un écart sans barre d'erreur n'est pas un résultat

Le banc affichait « +20,0 points » pour l'isolation de l'effet à `--runs 3`. Le chiffre
était exact — **et la conclusion, fausse**. Ce jour-là, chaque bras comptait 15 essais :
l'intervalle de confiance à 95 % de cet écart est `[-5,9 ; +48,0]`. Il **contient zéro**.
La phrase affichée disait « le gain vient bien de la VÉRIFICATION » ; la seule chose
établie était que 15 essais ne suffisent pas à le départager.

Le banc a alors été relancé plus grand, en acceptant d'avance ce qu'il dirait :

| Essais par bras | Écart « échantillonnage seul » → « vérification » | IC95 | Lecture |
|---|---|---|---|
| 15 | +20,0 points | `[-5,9 ; +48,0]` | indéterminé |
| 25 | +16,0 points | `[-5,1 ; +38,6]` | indéterminé |
| **60** | **+1,7 point** | `[-13,5 ; +16,9]` | **indéterminé — et l'effet réel est petit** |

Trois conclusions, toutes inconfortables :

1. **Le gain total du harness est démontré** : `+41,7 points`, IC95 `[+27,7 ; +59,2]`, à
   60 essais par bras. Le harness aide — la mesure le porte.
2. **L'attribution de ce gain à la vérification seule ne l'est pas.** À budget d'appels
   égal, l'écart entre « plusieurs candidats sans vérification » et « plusieurs candidats
   avec vérification » n'est pas distinguable du bruit sur ce jeu de tâches. Le récit
   précédent (« +20 points grâce à la vérification ») reposait sur 15 essais.
3. **La vérification garde un rôle prouvé, mais ce n'est pas celui-là** : c'est elle qui
   empêche une erreur d'être livrée **sans rien dire**. Ce chiffre est resté à `0` partout,
   et il ne dépend d'aucun test statistique.

Le même traitement s'applique au banc de **mémoire** (`jio learn`), qui publiait « gain
attribuable : +0,0 point » sans dire si zéro était un résultat ou une absence de
résolution. À 40 essais par bras, les deux écarts (artefact de graine et gain attribuable)
valent `+0,0` avec un intervalle `[-12,1 ; +12,1]` : le banc écrit « indéterminé à cet
échantillon », et si l'artefact de loterie devenait significatif, il prévient que le banc
est trop petit pour attribuer l'effet à la mémoire plutôt qu'à la graine.

Le banc dit maintenant son propre budget de mesure :

```
      sans vérification   73.3%   avec vérification   83.3%   écart +10.0 points  IC95 [-10.1 ; +31.0]
      -> écart POSITIF mais l'intervalle CONTIENT zéro : INDETERMINE a ce nombre d'essais.
         Pour démontrer un écart de +10.0 points : environ 352 essai(s) par bras,
         soit `--runs 71` sur ce jeu de 5 tâche(s).
```

Deux détails qui font la différence entre mesurer et croire :

- **Wilson, pas l'intervalle normal.** Le normal rend une largeur **nulle** à 0 % et à
  100 % — exactement les deux valeurs qui comptent ici (« 0 erreur livrée », « 100 % de
  réussite à haute compétence »). Il annoncerait « zéro erreur, donc zéro risque ».
- **Le quantile normal est vérifié contre la table.** Le premier jet rendait `0,24` là où
  la table dit `1,96` : des intervalles cinq fois trop étroits, donc des écarts déclarés
  significatifs qui ne l'étaient pas. Le test compare à la table connue, jamais à la
  fonction elle-même — et il a attrapé deux erreurs de signe dans les queues.

## Trois codes de sortie, parce que « rien à vérifier » n'est ni un succès ni un échec

```
0  conforme sur ce qui est verifiable
1  au moins une affirmation REFUTEE
3  RIEN a verifier — document sans matiere prouvable
```

Le `3` existe pour une raison précise : sans lui, il fallait choisir entre faire passer
un document muet pour un quitus, ou le signaler comme un défaut. Aucune des deux n'est
vraie. Dans `jio scan`, ces documents apparaissent comme « non testables ici », jamais
comme des problèmes.

---

## Un balayage doit être lisible : deux faux positifs, deux corrections

`jio scan .` sur ce dépôt — l'audit le plus simple qu'un utilisateur lance — donnait
**736 problèmes en 285 secondes**. Les deux causes, mesurées :

| Défaut | Ce qui se passait | Correctif |
|---|---|---|
| Il traversait l'**environnement virtuel** | 1363 fichiers Python au lieu de 105, des « problèmes » sur du code tiers, 285 s | dossier ignorés par défaut (`.venv`, `node_modules`, caches, `build`…), **et le dossier ignoré est affiché** ; `--tout` pour les inclure |
| Il accusait **ses propres fixtures** | le corpus de preuve est faux *à dessein* : 16 « défauts » du projet, dont `evidence/claims/rapport_fautif.md` | le fichier se **déclare** (`# jio:corpus-fautif` ou `<!-- jio:corpus-fautif -->`), et le nombre de fichiers exclus est affiché |

Après : **0 problème, 14 secondes**, et la sortie dit ce qu'elle n'a pas regardé :

```
  SCAN  .  ·  105 fichier(s) Python  ·  34 document(s)  ·  223 verification(s)
  dossiers ignores : .venv   (--tout pour les inclure)
  corpus de fautes VOLONTAIRES : 13 fichier(s) exclu(s) sur leur propre declaration
```

Un faux positif n'est pas un désagrément : une liste qu'on ne peut pas lire est
ignorée **en entier**, y compris ses vrais défauts. C'est la perte de l'outil.

### La même erreur, dans le vérificateur de prose

Le corpus de documents a révélé trois façons d'accuser à tort, toutes corrigées :

| Faux positif | Pourquoi c'était grave | Correctif |
|---|---|---|
| Un bloc **`bash`** compilé comme du Python | presque tout document technique contient une ligne de commande : chacun était déclaré invalide, **et bloquant** | seuls les blocs annoncés comme Python (`python`, `py`, `python3`) sont jugés |
| Un calcul **cité** entre `` ` `` | un texte qui explique les erreurs d'arithmétique en cite forcément — c'est-à-dire les documents les plus utiles | une citation est **signalée**, jamais bloquante |
| Un **diagramme** non marqué | 18 signalements sur le seul README de ce dépôt (tableaux ASCII, sorties de terminal) | un bloc non marqué n'est jugé que s'il est **manifestement du code** (`def `, `class `, `import `…) |

Le README de ce dépôt passe désormais son propre auditeur : **10 affirmations
vérifiées, 0 refusée**, 3 signalements — un chemin d'un autre paquet cité en exemple,
un calcul faux cité volontairement, et un chemin d'illustration. Tous les trois sont
légitimes, et c'est écrit dans le rapport.

---

## Le bug de mesure qui rendait le banc menteur

En ajoutant le banc de documents, un chiffre impossible est apparu : **100 % de
réussite à 20 % de compétence**. Cause, vérifiée : la génération utilisait
`seed=1000 * tour + i`, **sans la graine de la mission**.

Conséquence exacte, mesurée sur trois graines : les mêmes empreintes de candidats,
identiques. Autrement dit :

- les `runs` répétitions des bras S2/S3 du banc **rejouaient le même tirage** ;
- l'écart annoncé entre le harness et le modèle brut **n'était pas une moyenne** ;
- une mesure dont la variance est nulle par construction ne peut pas être présentée
  comme un résultat — et rien, dans la sortie, ne le signalait.

Corrigé par `EngineConfig.seed`, qui entre dans la graine de chaque génération. La
reproductibilité est préservée : même graine de mission, même mission ; graine
différente, tirage différent — les deux sont testés.

Les chiffres du banc ont changé après ce correctif. Ils sont plus bas, et ils sont
vrais :

| Bras | Avant (variance nulle) | Après (tirages réels) |
|---|---|---|
| Modèle brut (1 appel) | 33,3 % | 33,3 % |
| Échantillonnage seul (best-of-3) | 73,3 % | 73,3 % |
| **Isolation : vérification vs échantillonnage à budget égal** | non mesurable | **+20,0 pts** |
| Gain total du harness | +66,7 pts (surévalué) | **+60,0 pts** |
| Erreurs livrées sans réserve | 0 | **0** |

---

## Le rendre omniprésent : CI et hook standard

Un défaut prouvé ne doit jamais atteindre un commit. JIO s'installe donc là où le
code se valide déjà, au standard de l'écosystème :

- **`.pre-commit-hooks.yaml`** : JIO utilisable comme hook depuis n'importe quel
  dépôt (`repo: …/JIOJIO-TERMINATOR`). `pass_filenames: false` est volontaire — un
  renommage casse **le consommateur**, pas le fichier modifié ; une vérification
  fichier par fichier ne peut pas le voir.
- **`.pre-commit-config.yaml`** : configuration de ce dépôt (hooks standards + ruff
  sur les vrais bugs + l'auto-audit JIO).
- **`.github/ci.yml.example`** : la CI (tests + `jio scan` + reproduction du banc).
  Elle porte l'extension `.example` parce que le jeton GitHub de l'agent n'a **pas**
  la permission `workflows` : GitHub refuse la création du fichier, et ce refus est
  écrit dans le fichier lui-même. Installation en deux lignes, indiquée dedans.

---

## Reproductibilité : une preuve qu'on ne peut pas rejouer n'est pas une preuve

Le système a été non reproductible pendant un temps sans que rien ne le signale : les
résultats restaient plausibles, ils changeaient simplement d'une exécution à l'autre.
Deux causes trouvées, toutes deux invisibles à la lecture :

| Bug | Conséquence | Correctif |
|---|---|---|
| `random.Random(hash((…)))` | `hash()` sur des chaînes est randomisé **par processus** (`PYTHONHASHSEED`) : le panel votait différemment pour le même artefact et la même graine | graine stable (digest `blake2b`) |
| dossier temporaire **aléatoire** du bac à sable | son chemin apparaissait dans les traces d'erreur : l'empreinte du témoin changeait à chaque exécution, et toute décision qui en dérivait aussi | normalisation du chemin en `<sandbox>` |

`jio bench` rend désormais **exactement** les mêmes chiffres d'un processus à l'autre
(vérifié : trois exécutions identiques). Deux tests de non-régression échouent si l'un
des deux bugs revient — vérifié en cassant volontairement chaque correctif, puis en
constatant qu'un premier test était **inefficace** (il testait la fonction de graine,
pas son site d'appel) : il a été remplacé par un test bout-en-bout du verdict complet.

---

## Auto-amélioration

Deux boucles, actives à chaque mission.

**TrustRouter** (`jio trust`) — *combien* de vérification dépenser. Un harness réglé
une fois pour toutes est toujours mal réglé pour une partie des tâches. Trois
configurations (minimal / standard / renforcé) sont choisies par un **bandit UCB1**
sur la classe de la tâche, avec une récompense qui **pénalise le coût** :
`succès − 0,35 × coût`. Un bras jamais essayé passe toujours en premier : on ne juge
pas ce qu'on n'a pas mesuré.

**Mémoire des échecs** (`jio memory`) — *ne jamais repayer deux fois la même erreur*.
Chaque enregistrement porte **obligatoirement** un *garde* : le contrôle qui échouera
si l'erreur revient. Un échec sans garde est refusé — un souvenir sans garde est un
journal intime, pas une protection. La mémoire vit dans un journal **append-only
hash-chaîné** : une réécriture discrète de ses propres erreurs devient détectable.
Les souvenirs pertinents sont injectés dans le prompt de génération, étiquetés
comme *priors* — jamais comme preuves.

*Bug réel trouvé par les tests :* `Journal(path=…)` ouvre le fichier en écriture mais
**ne relit rien**. La mémoire écrivait donc sur disque et repartait vide à chaque
processus — une mémoire qui oublie. Le journal lui-même souffrait du même défaut, plus
grave encore : chaque processus **ajoutait une chaîne neuve** au même fichier, ce qui
rendait le fichier invérifiable dès la deuxième exécution (mesure : 545 événements,
chaîne cassée, 9 redémarrages). Corrigé par la reprise de chaîne et la mise en
quarantaine décrites plus haut.

### La mesure qui a retourné contre elle-même

`jio learn` compare trois bras, dont un **témoin** où la mémoire est présente mais son
effet désactivé. Ce témoin existe pour une raison précise : quand la mémoire ajoute un
bloc au prompt, le tirage change, donc tout « gain » observé pourrait n'être que du
hasard relabellisé.

| Bras | Mémoire | Effet | Rôle |
|---|---|---|---|
| **A** froid | vide | — | référence |
| **B** témoin | remplie | désactivé | isole l'artefact de loterie (attendu : ~0) |
| **C** chaud | remplie | actif | contraste **causalement propre** avec B |

**Le résultat est 0,0 point.** Sur des tâches vérifiables, la mémoire n'apporte rien de
mesurable — et le système le dit au lieu de maquiller le chiffre. La raison est
structurelle : la reprise est déjà assurée par la **largeur de tirage** (best-of-N) et
par la **vérification** qui *sélectionne* le bon candidat. Quand ces deux mécanismes
suffisent, la mémoire n'a rien à ajouter.

> En cherchant à mesurer ce gain, un défaut bien plus grave a été trouvé : le tirage du
> modèle simulé dépendait du **prompt entier**. Conséquence invisible — ajouter un
> souvenir ou un retour d'erreur rebattait **entièrement** les cartes. Le témoin B a
> affiché **+50 points d'écart alors que rien n'agissait**. Tous les effets au niveau du
> prompt étaient donc inattribuables. Le tirage ne dépend plus que d'une *disposition*
> stable (modèle, tâche, tentative), et les effets du prompt sont des mécanismes
> **déclarés** — donc mesurables.

**L'invariant central est encodé dans le simulateur, et verrouillé par un test :** les
gains sont **multiplicatifs**, jamais additifs. Un harness *amplifie* la compétence, il
n'en *crée* pas. À compétence nulle, aucun avertissement ne sauve le modèle — le système
doit **s'abstenir**, jamais livrer. La version additive de ce modèle faisait réussir un
modèle de compétence 0.0 : c'est-à-dire un harness capable d'inventer du savoir absent.

---

## Écosystème : un seul cerveau, tous tes outils

`jio artifacts --write` compile **une source de vérité** (`jio/artifacts/doctrine.py`)
vers les artefacts natifs de chaque outil :

| Outil | Artefact |
|---|---|
| **opencode** (SST) | `.opencode/agents/*.md` + `opencode.json` |
| **Hermes Agent** (Nous Research) | `~/.hermes/skills/**/SKILL.md` — tap installable |
| **Claude Code** | `CLAUDE.md` |
| **Codex / standard ouvert** | `AGENTS.md` |
| **Gemini CLI** | `GEMINI.md` |
| **Cursor** | `.cursor/rules/*.mdc` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Tout client MCP** | serveur `jio mcp` — stdio, JSON-RPC 2.0, zéro dépendance |

### Le serveur existait, et était injoignable

Écrire un serveur MCP ne le branche pas. Le dépôt émettait `.mcp.json` — le dialecte de
**Claude Code** — et rien pour les deux outils qui comptent ici : **opencode** lit
`opencode.json` sous la clé `mcp` (avec `type: "local"` et un *tableau* `command`),
**Hermes** lit `~/.hermes/config.yaml` sous la clé `mcp_servers`. Cinq outils testés,
documentés, et inaccessibles depuis ces deux clients.

`jio artifacts --mcp <dialecte>` les câble, avec une règle qui ne se négocie pas :

| Situation | Ce que fait JIO |
|---|---|
| Le fichier n'existe pas | il l'écrit |
| Le fichier existe **et** contient déjà `jio` | il ne touche à rien |
| Le fichier existe **sans** `jio` | il **n'écrit pas** : il affiche le fragment à coller |

Le troisième cas est le seul intéressant. Réécrire la configuration de quelqu'un d'autre
pour lui rendre service est exactement le comportement que ce projet reproche aux agents —
et une config utilisateur n'est pas un artefact généré par ce dépôt. C'est aussi la règle
que `scripts/install.sh` applique depuis le début.

Et parce qu'une configuration **correcte** peut ne rien brancher : `jio mcp --prove`
démarre réellement le serveur et compte les outils qu'il sert.

```
  PREUVE DU BRANCHEMENT MCP  ·  le serveur est demarre et interroge

  `python3 -m jio.mcp_server` sert 5 outil(s) [version 0.1.0] :
    - jio_prove
    - jio_audit
    - jio_contract
    - jio_claims
    - jio_skills
  (interpreteur de cette sonde : /home/user/JIOJIO-TERMINATOR/.venv/bin/python)
```

Le piège est réel : les fragments nomment `python3 -m jio.mcp_server`, or si `jio` a été
installé dans un environnement virtuel non activé, **cette commande existe et ne trouve
rien**. La configuration est juste, la branche ne l'est pas, et rien ne le dit avant la
première mission. La sonde nomme l'interpréteur qu'elle a utilisé, parce que c'est
l'information qui résout le problème.

Le serveur MCP expose cinq outils : `jio_prove` (prouver une source contre des règles
exécutables), `jio_audit` (auditer un fichier), `jio_contract` (les trois états de
livraison), `jio_skills`, et `jio_claims` — qui prend le **texte** d'un document, pas un
chemin, parce qu'une IA qui rédige tient son brouillon en contexte et lui demander
d'écrire un fichier pour pouvoir le vérifier garantirait que la vérification n'ait pas
lieu. Tout chemin est **confiné** à `JIO_ROOT` : un serveur d'outils qui lit n'importe
quel fichier sur demande est une vulnérabilité, pas une fonctionnalité.

Les 7 agents (`.opencode/agents/`) et les 11 compétences Hermes (`.hermes/skills/`)
partagent la même doctrine. Deux garde-fous structurels : le **vérificateur n'a pas
le droit d'écrire** (un vérificateur qui peut réparer ce qu'il juge finit toujours par
le déclarer conforme), et `AGENTS.md` reste **sous 150 lignes** — au-delà, un fichier
de contexte est survolé, pas lu.

---

## Documentation

| Document | Contenu |
|---|---|
| [`docs/VISION-ARCHITECTURE.md`](docs/VISION-ARCHITECTURE.md) | Vision, limites théoriques, 14 principes mathématiques, 7 couches, boucle centrale |
| [`docs/DOSSIER-TECHNIQUES.md`](docs/DOSSIER-TECHNIQUES.md) | Sources, chiffres mesurés, dépôts à intégrer, axes d'innovation originaux |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 8 phases, critères de sortie, ordre de construction |

---

## Principes de développement

1. **La preuve avant l'affirmation.** Aucune fonctionnalité déclarée faite sans commande exécutée et journalisée.
2. **Fail-closed.** En cas de doute, on bloque — on ne logge pas en espérant.
3. **Zéro dépendance obligatoire.** Le noyau tourne avec la bibliothèque standard Python.
4. **Remplaçable.** Chaque composant est un adaptateur derrière une interface.
5. **Hors-ligne d'abord.** Un mode simulé déterministe permet tout tester sans clé API.
6. **Le projet s'audite lui-même.** Ses propres techniques tournent sur son propre code.

---

## Licence

MIT
