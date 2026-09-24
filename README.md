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
« vrais bugs » de la littérature CI — `E9,F63,F7,F811,F82`, **aucune règle de style** :
un projet qui passe ses tests ne doit pas être déclaré fautif parce qu'il n'aime pas
l'ordre des imports.

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
27 fichier(s) verifiable(s) · 1 reserve(s) · 27 a audit partiel
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

Le serveur MCP expose `jio_prove` (prouver une source contre des règles exécutables),
`jio_audit` (auditer un fichier), `jio_contract` (les trois états de livraison) et
`jio_skills`. Tout chemin est **confiné** à `JIO_ROOT` : un serveur d'outils qui lit
n'importe quel fichier sur demande est une vulnérabilité, pas une fonctionnalité.

Les 7 agents (`.opencode/agents/`) et les 10 compétences Hermes (`.hermes/skills/`)
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
