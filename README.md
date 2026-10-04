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

**Statut :** noyau **implémenté, mesuré, auto-audité et reproductible** — 1274 tests verts, exécuté sans aucune clé API.
**Langue :** interface et rapports en français · prompts et agents en anglais (précision de raisonnement).
**Tu veux l'essayer ?** Le guide pas à pas pour l'intégrer à TON projet est là :
[`GUIDE-DEMARRAGE.md`](GUIDE-DEMARRAGE.md) — 6 étapes, toutes les commandes testées.
**Avant de l'utiliser sur du code que tu ne contrôles pas :** lis [`SECURITY.md`](SECURITY.md) — ce que la Sandbox protège (secrets filtrés, timeout) et ce qu'elle n'est pas (une prison : sur du code hostile, utilise un conteneur).
**Avant de l'utiliser sur du code que tu ne contrôles pas :** lis [`SECURITY.md`](SECURITY.md) — ce que la Sandbox protège (secrets filtrés, timeout) et ce qu'elle n'est pas (une prison : sur du code hostile, utilise un conteneur).

---

## L'état final, en un coup d'œil

Chaque brique du harness a été **enlevée et mesurée** — le dépôt ne dit jamais « ce composant
sert », il le **prouve** ou il le dit absent. Le tableau complet, acquis par `jio ablation`
sur ses régimes (défaut, sans oracle, corrélé, calibré, tâche à spécification partielle) :

| brique | verdict mesuré |
|---|---|
| `preuve` · `red-team` · `consensus` | **PREUVE** — sans eux, plus aucune livraison propre (8 contre 0, p = 0,0078) |
| `temoins` | **PREUVE (perte)** en `--sans-oracle` : les appels tombent de 3,9 à 1,0 sans lui |
| `differentiel` | exercé par la tâche à spécification partielle : retirer la brique fait disparaître les 4 aveux de divergence — des candidats à égalité seraient départagés **en silence** |
| `integrite` | agit sur 10/10 missions (journal rejoué 524 → 0) ; redondance mesurée, jamais « inutile » |
| `auto-coherence` | agit sur 9/10 missions ; redondance mesurée |
| `routeur` | agit sur 10/10 missions ; verdict non concluant et coût noté (sans lui : +1 livraison propre, p = 1,0) |
| `mutation` | non concluant — conservé pour son rôle : vérifier qu'une règle **peut échouer** |
| `memoire` | paie 1 % de jetons, aucun effet de sens mesuré à cette échelle — dit tel quel |
| `bibliotheque` | économise 4 appels sur 10 missions en `--sans-oracle --fidelite 1.0` |
| `porte` | **COÛT MESURÉ** en régime corrélé (p = 0,0312) — et la calibration l'a **blanchie** : voir ci-dessous |

Le dernier point est le plus instructif. La porte coûte des livraisons propres quand le panel
est corrélé — et l'expérience de calibration (`--calibree`, points mesurés sur les candidats
du banc) a rendu son verdict : la borne conforme **refuse** tout seuil sous 1,0 avec ces
points, donc calibrer durcit la porte au lieu de l'adoucir. **Le coût est le prix de la
garantie**, pas un défaut de réglage ; le seul levier est `alpha`, une décision déclarée.
Zéro erreur silencieuse dans toutes les conditions mesurées.

**L'entreprise.** `jio entreprise` distribue les vérifications du dépôt à **une entreprise de
66 agents** — 98 missions exécutées par des ouvriers réels en parallèle, 549 s de travail en
219 s réelles (×3,9), chaque problème rendu avec son responsable nommé, réparation mécanique
fermée (trouvé → réparé → re-vérifié, nommé deux fois), et ce qui demanderait une décision
humaine jamais touché. Les 11 chiffres du dépôt sont surveillés par `jio chiffres` ; la
preuve de bout en bout tient en 28 étapes (`bash scripts/evidence.sh`).

La suite de cette page raconte **comment** chacun de ces résultats a été obtenu, avec les
défauts rencontrés en route — un rapport qui ne raconterait que les réussites serait une
plaidoirie.

## Donnez ce dépôt à n'importe quelle IA : trois commandes, et elle s'intègre seule

Aucune clé d'API, aucune configuration à écrire à la main, rien à installer d'autre que le
paquet. Les artefacts que lisent opencode, Claude Code, Cursor, Copilot, Gemini, Codex et
Hermes sont **générés**, et le câblage MCP est **prouvé** en démarrant réellement le serveur :

```sh
jio start                     # artefacts + câblage MCP + preuve du câblage + fiche .jio/ACTIVE.md
jio clarify "<objectif>"      # les 0 à 3 questions ESSENTIELLES — code 3 : il faut DEMANDER
jio run "<objectif>"          # mission complète : preuve, panel, consensus, réserves nommées
jio auto "<objectif>"         # travaille SEUL, étape par étape : chaque étape doit porter sa
                              # preuve ; une étape sans preuve est REFUSÉE, un échec ARRÊTE
jio auto --reprendre          # continue le plan interrompu : les étapes déjà prouvées sont
                              # sautées SI la révision git n'a pas bougé (sinon : tout rejouer)
jio coherence                 # LES NEUF CONTRÔLES : artefacts, chiffres, documents, commandes
                              # citées, compétences, environnement, portes du paquet, journal,
                              # plan en suspens — code 0 seulement si TOUT est encore vrai
jio coherence --reparer       # répare ce qui est MÉCANIQUE (artefacts générés, valeurs
                              # mesurées), puis repasse la porte ; tout le reste est nommé, et
                              # un journal cassé n'est JAMAIS « réparé » (pièce à conviction)
jio skills "<objectif>"       # QUELLES compétences charger pour cet objectif, et pourquoi —
                              # ou « aucune » ; 39 objectifs de routage mesurent le classement
jio sorties                   # les exemples de sortie des documents sont-ils ENCORE la sortie
                              # réelle des outils ? (le README en a menti pendant des semaines)
```

`jio clarify` existe pour une seule raison : une IA qui part sans question choisit le
périmètre, le format et le critère de réussite **à la place de son utilisateur**, puis livre
quelque chose de plausible qui répond à une autre question. La porte est mesurable, bornée à
trois questions, et chaque question porte la conséquence de ne pas y répondre ainsi que
l'hypothèse prise à défaut : `jio clarify --strict` sort en **3** et la mission ne commence pas.

La porte est elle-même **mesurée** sur un banc d'objectifs réels annotés à la main
(`jio clarify --mesure`) : **41 objectifs, 0 faux positif, 0 faux négatif**. Le banc lit les
signaux dans **les deux sens** — voir ce qui manque, et ne pas croire manquant ce qui est écrit —
et il compte les **questions posées**, seul coût que l'utilisateur ressent, plutôt qu'un booléen
intermédiaire. Six objectifs du terrain (les mandats de boucle réels de ce dépôt, un mandat
anglais, un critère de comportement, un verbe vague avec cible nommée) y sont entrés après coup :
le corpus restant, il mesurait ce que la porte savait déjà faire.

**Un mandat de poursuite est lu comme un mandat, pas comme une phrase vague.** « Continue »,
« ne t'arrête pas avant que tout soit parfait », « keep going » : l'action et la cible sont
**héritées** de la mission en cours — c'est ce que veut dire « continue » — et la seule question
vraie est *jusqu'où*. La porte la pose, avec le défaut négocié : **un cycle complet publié**
(recherche, changement, tests, audit, mesures), puis reprise, et arrêt quand un cycle entier ne
trouve plus ni amélioration ni innovation. Un mandat qui dit déjà sa borne (`jusqu'à ce que 3
cycles…`) ne reçoit **aucune** question.

`jio start` écrit `.jio/ACTIVE.md` — la fiche que l'IA lit en premier : état réel, commandes
utiles, et ce qui reste non vérifié. Elle est **idempotente** au sens strict : relancée, elle
**n'écrit rien du tout**, pas même un contenu identique — la date de modification ne bouge pas.
Pour que ce soit vrai, la fiche décrit un **état** (« artefacts natifs : 30/30 présents »,
« câblage MCP : cursor ») et jamais l'**activité** de la commande qui l'a écrite : un rapport
d'activité dans un fichier d'état est un fichier qui bat à chaque passage — et un fichier qui
bat finit par faire croire que le projet a bougé. Mesuré sur un dépôt tiers : deux `jio start`
d'affilée, **zéro** fichier réécrit, sur les 30 artefacts **et** sur la fiche.

### L'intégration mesurée sur un projet **étranger** : quatre défauts, tous du même genre

Tout ce qui précède avait été mesuré **dans ce dépôt** — c'est-à-dire dans le seul endroit où
`python3 -m jio.mcp_server` marche *par accident* : `jio/` est un sous-dossier du dossier courant.
Le vrai cas d'usage est l'inverse : on donne **son** dépôt à son IA, et `jio start` s'y installe.
Un petit projet Python sans rapport avec JIO (code, tests, `README`, et un `AGENTS.md` déjà écrit
par l'utilisateur) a donc servi de banc. Quatre défauts, tous invisibles d'ici :

| Ce qui était écrit / dit | Ce qui se passait sur le projet étranger | Correction |
|---|---|---|
| `.mcp.json` et `opencode.json` nommaient `python3 -m jio.mcp_server` | depuis ce projet, la commande ne trouve pas `jio` : **la configuration est morte** — et la preuve, correcte, arrivait *après* l'écriture | la commande est **résolue** par une sonde (`python3`, puis l'interpréteur qui a servi à lancer `jio`), testée **depuis le projet**, et c'est celle qui sert vraiment 8 outils qui est écrite |
| le portail comparait les fichiers de cablage à leur forme canonique | il déclarait « divergent » les deux fichiers que `jio start` venait d'écrire correctement | contrôle et réparation s'adossent au **même** manifeste (« ce que jio écrirait ici ») |
| `nombres` confrontait le `README` du projet aux chiffres de **ce** dépôt | échec du contrôle, et mesure impossible, sur un projet dont le `README` ne dit que « `python -m pytest` lance les tests » | un document qui n'annonce aucun chiffre surveillé est **hors de portée** — ni vert, ni rouge |
| un `AGENTS.md` écrit par l'utilisateur était **conservé**… puis reproché | portail rouge **permanent** pour un fichier que jio a précisément refusé de toucher | le fichier reste signalé (« tant qu'il est là, c'est **votre** consigne que l'IA lit »), mais n'est plus un échec |

Deux défauts de plus, trouvés par la mesure « deux `jio start` d'affilée » — celle qui est écrite
juste au-dessus : la seconde exécution annonçait « **1 écrit** » (c'était le fichier de
l'utilisateur qu'elle venait de *ne pas* écrire), et la version déposée à côté (`AGENTS.md.jio`)
était réécrite à contenu identique, donc sa date de modification bougeait. Les deux sont
corrigés ; la promesse d'idempotence tient maintenant **aussi** quand l'utilisateur a ses
propres fichiers.

Ce que la mesure a **refusé** de « corriger » : sur un projet où rien n'est intégré, le portail
reste rouge — « artefacts manquants » est un fait, et un fait actionnable, qui nomme désormais la
commande (`jio start` installe l'intégration). Le rendre vert aurait éteint le seul signal qui
dit à une IA « ce projet n'est pas encore câblé ». La différence entre les deux cas est celle que
ce dépôt applique partout : *un contrôle qui a mesuré et trouve bon* n'est pas *un contrôle qui
n'avait rien à mesurer*.

La preuve est exécutable, pas racontée : `tests/test_integration_projet_etranger.py` fabrique un
projet étranger, lance `jio start`, **relit la configuration écrite**, démarre le serveur MCP
depuis ce projet avec `initialize` et `tools/list`, exige des outils en retour, puis lance le
portail et exige qu'il soit vert — et qu'un second `jio start` ne touche à rien.

Deux autres commandes ont été passées au même banc, avec le même résultat — chacune parlait de
**nous** plutôt que du projet :

- **`jio scan .`** produisait 22 constats « chemin cité INTROUVABLE » (`jio/artifacts/doctrine.py`,
  `jio/artifacts/definitions.py`)… tous cités par les documents que `jio start` venait d'installer
  chez l'utilisateur. Ces chemins existent dans notre dépôt, pas chez lui, et ne peuvent pas y
  exister. Le balayage ne trouvait donc **aucun défaut de son projet** tout en l'abreuvant de
  constats sur le nôtre — c'est-à-dire qu'il apprenait à l'utilisateur à ignorer ses constats.
  Désormais les documents qui vivent dans un emplacement géré par `jio` (`.jio/`,
  `.hermes/skills/`, `.opencode/agents/`, consignes d'agent à la racine) sortent du champ, et la
  sortie le **dit** (`--tout` les remet dedans). Et dans le dépôt de JIO, **rien** n'est filtré :
  les chemins cités y existent, c'est leur maison.
- **`jio chiffres`** sortait en 1 en reprochant à un `README` tiers les huit chiffres de ce dépôt,
  alors que le même constat côté portail était déclaré hors de portée. Un document qui n'annonce
  aucun chiffre surveillé ne participe pas au contrôle : les deux commandes le disent maintenant
  de la même façon — deux mesures de la même chose ne peuvent pas rendre deux verdicts opposés.
- **`jio chiffres --appliquer` a réécrit des chiffres JUSTES en chiffres faux.** Le motif du banc
  de la porte de clarification attrapait tout « N objectifs » qui n'était pas suivi d'une
  exception connue : il a donc remplacé « 24 objectifs jamais vus » (les deux jeux de contrôle
  du routeur) par « 41 » (la taille de ce banc-là), dans le README, automatiquement, et sans que
  le contrôle le voie — puisque 41 était bien la valeur mesurée de l'*autre* grandeur. Une liste
  d'exceptions est une course sans fin : le troisième cas oublié ne se voit pas. Le remède
  retourne le problème — chaque chiffre surveillé déclare un **contexte positif** (la phrase qui
  parle de SA grandeur), et une phrase non prévue est simplement laissée tranquille. Le rapport
  de `--appliquer` nomme désormais **chaque** réécriture (ligne, avant → après) : un compte
  global ne permettait pas de distinguer une correction d'une dégradation.
- **`jio artifacts --write`**, la réparation *recommandée* par le portail, en laissait deux
  derrière elle : elle écrivait la forme canonique pendant que le contrôle exigeait la commande
  résolue (`python3` contre l'interpréteur qui a JIO). L'utilisateur réparait, se voyait reprocher
  sa réparation, réparait… Le contrôle, la réparation automatique (`--reparer`) et la commande
  manuelle s'adossent au même manifeste : « ce que jio écrirait **ici** ».

Et la fiche que l'IA lit **en premier** — `.jio/ACTIVE.md` — parlait encore de nous : elle
demandait d'éditer `jio/artifacts/doctrine.py` (fichier qui n'existe pas chez l'utilisateur),
renvoyait à `docs/VISION-ARCHITECTURE.md` (absent lui aussi), et annonçait « **Trois** règles »
suivies de **cinq**. Une fiche qui envoie son lecteur vers des fichiers inexistants fait douter
de tout ce qu'elle affirme, y compris de ce qui est vrai. Elle distingue maintenant le projet
hôte de l'installation de JIO, cite chaque chemin avec sa maison, **compte** ses propres règles
(le titre est dérivé de la liste) et **mesure** le coût de la bibliothèque de procédures
(6 424 jetons) au lieu de le recopier. Deux tests l'interdisent désormais : « aucun chemin cité
n'est orphelin » et « le titre compte ce que la liste contient ».

### Et la commande qui ne peut pas travailler le disait en sortant **0**

`jio run "<objectif>"` sans aucun fournisseur affichait :

```
Aucun fournisseur detecte.
Installe un CLI (opencode, hermes, claude, codex, gemini) ou definis
une variable d'environnement d'API (OPENROUTER_API_KEY, OPENAI_API_KEY...).
```

…et sortait en **0**. Ce n'est pas un oubli : c'est une propriété de Python — `raise
SystemExit("message")`, avec une **chaîne**, écrit le message et termine *normalement*. Or 0 est
exactement ce qu'un agent qui enchaîne lit comme « c'est fait, et prouvé » : il n'ira jamais
chercher la clé manquante, et rien ne le lui aura dit.

La doctrine des codes range ce cas en **2** (`INDETERMINE`) : « il manque de quoi conclure : un
fournisseur, une preuve, une entrée », action associée « fournir ce qui manque, puis relancer ».
`jio/core/codes.py::sortir` est désormais le seul chemin qui écrit un message **et** sort avec un
code — et le code y est un paramètre **obligatoire**, sans valeur par défaut : un appelant doit
décider ce qu'il vient de dire à la machine qui le lit. Le message nomme aussi les deux chemins
qui marchent **sans aucune clé** (`jio bench`, `jio run … --simulate --task sum_even
--no-oracle`) : une erreur qui n'indique pas d'issue oblige l'utilisateur à deviner.

Deux verrous, parce qu'un seul ne suffirait pas : un **verrou mécanique** (l'arbre syntaxique de
tout le paquet est lu, et la forme interdite — `SystemExit` d'un message — est refusée partout,
pas seulement là où on l'a vue) et un **verrou comportemental** (la commande réelle, sans
fournisseur, rend bien 2). `main()`, l'entrée du programme, traduit enfin les `SystemExit`
échappés en codes, avec une règle stricte : **une chaîne n'est jamais un succès** — si un code
arrive sous forme de texte, il est écrit et le code rendu est **1**.

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
python -m jio learn --cycles 3 --runs 1  # la mémoire qui S'ACCUMULE paie-t-elle ? (froid/chaud apparié)
python -m jio mutants                    # NOS tests attrapent-ils NOS erreurs ? (mutation)
python -m jio ablation --missions 10     # quelle brique apporte quoi ? (ablation appariee)
python -m jio scan jio                   # JIO s'audite lui-même : 0 problème attendu
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

> **Frontière entre les deux bancs, pour qu'elle soit un choix et pas un oubli.** `jio bench`
> mesure le **pipeline de vérification par mission**, chaque mission étant un échantillon
> indépendant : la mémoire des échecs, la bibliothèque de témoins et le routeur de confiance
> n'y sont pas branchés — elles sont des briques **entre** missions, et les mélanger rendrait
> les relevés dépendants de l'ordre d'exécution. C'est `jio ablation` qui les juge, avec un
> état d'apprentissage par bras (voir « Chaque brique prouve-t-elle son utilité ? ») : c'est
> là que `routeur` ressort « à interroger », `bibliotheque` économise 4 appels sur 10
> missions en `--sans-oracle --fidelite 1.0`, et `memoire` paie 1 % de jetons sans gain
> mesuré à cette échelle.

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

**La mesure archivée.** Le tableau ci-dessus est une série de relevés ; voici celui qui est
conservé, avec son régime et ses intervalles — `evidence/bench-simule-skill-035.md`, produit par
le commit `ab2d3ff`, 5 tâches × 5 tirages, compétence simulée 0,35 :

| Configuration | Réussite | IC95 | Appels |
|---|---|---|---|
| modèle brut (1 appel) | 32 % | — | 1,0 |
| échantillonnage seul (best-of-3) | 76 % | — | 3,0 |
| **contrôle : autant d'appels, 0 vérification** | 76 % | — | 3,6 |
| **vérification exécutable + reprise** | **100 %** | — | 3,6 |
| JIO complet (livraison auditée) | 100 % | — | 3,6 |
| sans oracle : traducteur fidèle | 96 % | [80 % ; 99 %] | 4,6 |
| sans oracle : traducteur à 50 % | 80 % | [61 % ; 91 %] | 5,6 |
| sans oracle : traducteur faux | 0 % | [0 % ; 13 %] | 5,0 |

Gain total du harness : **+68,0 points**, IC95 **[+53,2 ; +91,7]** (la littérature mesure +15 à
+54 sur des modèles réels). Écart apparié vérification contre échantillonnage à budget d'appels
égal : **+24,0 points**, intervalle excluant zéro.

Et, dans les trois bras sans oracle — le cas de **toute** mission réelle, où personne ne fournit
le test : **0 erreur livrée sans réserve**, 25 abstentions (le système refuse de livrer quand il
ne peut pas prouver), et 6 candidats **corrects** rejetés (le coût, nommé, d'un traducteur
imparfait).

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

## Ce qu'un agent va EXÉCUTER n'est pas un document

Une compétence Hermes, un agent opencode, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` : ce sont des
**consignes**, pas des textes à lire. La différence n'est pas littéraire, elle est mesurable — et
elle a été mesurée.

<!-- prose:hors-controle: recit d'un defaut passe — la commande citee ici est l'EXEMPLE de ce qui n'existe pas, c'est le sujet de la phrase et non une instruction a executer -->
`jio coherence` annonçait « 36 commande(s) citée(s), toutes existantes » alors qu'une compétence
citait `jio prouve-tout`, une sous-commande qui n'existe pas. Le contrôle ne regardait que
`README.md`, `docs/` et les trois fichiers d'instructions racine : **les 12 compétences et les
7 agents — exactement ce qu'un agent lit comme une consigne — n'étaient pas dans le champ.**
L'agent aurait tapé la commande, elle aurait échoué, et il aurait conclu que l'outil est cassé.
<!-- /prose:hors-controle -->

Deux règles, tirées de la mesure :

* le **chemin** décide du régime (`jio/verify/consignes.py`, source unique) : un document peut
  *montrer* un message d'erreur — les exemples de sortie plus bas en contiennent — donc une
  commande dans un bloc de code y est **signalée** ; dans une consigne, le même bloc est
  **l'instruction que l'agent va exécuter**, donc il est **refusé** ;
* le portail de cohérence compte désormais les commandes des artefacts exécutés. Dans ce dépôt,
  le contrôle est passé de **36** à **101** commandes vérifiées — et elles existent toutes.

```
jio coherence        # refusé si une consigne cite une commande inexistante
jio claims --hook .hermes/skills/verification/executable-proof/SKILL.md   # refusé, code 1
```

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

Rejouable : `bash scripts/evidence.sh`, étape **20**, « La PROSE » (corpus versionné dans
`evidence/claims/`).

### Cinq bugs, tous du même genre : une vérification qui ne vérifiait rien

`verifier()` rendait une liste **vide** alors que `extraction()` trouvait bien les deux
calculs du document. Un vérificateur qui ne trouve rien ne dit pas « tout va bien » : il
dit qu'il n'a rien regardé — et personne ne peut faire la différence de l'extérieur.

| Bug | Cause | Correctif |
|---|---|---|
| Le vrai signe `×` n'était pas reconnu | classe de caractères écrite **à la main** (`[-+*/×x]`) : un caractère non-ASCII s'y perd sans bruit | classe **construite** depuis la table des opérateurs |
| Tout calcul en fin de phrase échappait | regard final `(?![\w.])` : un nombre suivi d'un **point** était refusé, donc exactement la façon dont un rapport écrit ses calculs | `(?![\w])(?!\.\d)` — refuser un chiffre qui suit, pas une ponctuation |
| Aucune expression n'était acceptée | `ast.walk` visite **aussi les nœuds d'opérateur** (`ast.Add`, `ast.Mult`) : aucune catégorie autorisée ne les acceptait, donc *toute* expression était refusée | descente explicite de l'arbre, **le contrôle et le calcul dans la même fonction** |
| `eval()` sur du contenu non fiable | — | supprimé : le calcul est fait sur les seuls nœuds admis |
| Un **pourcentage arrondi juste** était déclaré faux | le signe `%` n'était pas lu : `21/24 = 88 %` comparait `0,875` à `88` | `%` lu comme unité (valeur × 100) et tolérance = **l'arrondi à la précision écrite**, jamais plus : `21/24 = 99 %` reste refusé, et sans `%` la comparaison reste stricte au 1e-9 |

Le troisième est le plus instructif : la fonction de contrôle était **toujours fausse**,
et comme elle était écrite à part du calcul, rien ne le signalait. Contrôle et calcul
partagent maintenant un seul passage — un test couvre chacun des cinq bugs
(`tests/test_claims.py`).

Le cinquième a été trouvé **en publiant une mesure** : la table des 24 objectifs refusés
ci-dessous écrit `21/24 = 88 %`, un arrondi à l'entier, et la porte a répondu « calcul
EXACT faux » — puisque `88 %` valait 88 et non 0,88. C'est un **faux témoin**, la pire
espèce : un outil qui accuse à tort apprend à ignorer les vraies accusations, et celui-là
aurait fait réécrire des phrases justes. Le correctif ne relâche rien d'autre : `%`
multiplie par 100 (c'est ce que « pour cent » veut dire), la tolérance est exactement
l'arrondi à la précision annoncée, et un calcul sans unité reste jugé au 1e-9.

---

## Une mission sans code : le document entre dans la même boucle

Tout ce qui précède prouve du **code**. Une mission généraliste — rapport, analyse,
note — n'a rien à exécuter : le moteur s'abstenait, honnêtement mais inutilement. Or
c'est là que se logent les hallucinations, dans du texte que personne ne recalcule.

`jio run --prose` fait traverser **la même boucle** à un document. Pas une seconde
machinerie : un vérificateur qui se présente comme un prouveur.

```
jio run --prose --simulate                    # banc de documents, sans clé API
jio run "rédige le rapport de perf" --prose   # mission réelle
jio bench --prose --runs 5                    # mesure : aveugle vs vérifié
jio bench --prose --rapport evidence/bench-prose-skill-020.md   # …et on l'archive
```

**La mesure est archivée** (`evidence/bench-prose-skill-020.md`, document simulé, 5 tirages) :
compétence 0,00 → **0 %** de justes, 5 documents livrés **sous réserve nommée**, 0 silencieux ;
compétence 0,35 → **100 %**, 0 sous réserve, 0 silencieux. Le chiffre qui compte est le même que
pour le code : **0 erreur livrée sans rien dire**. Le banc de code avait son archivage ; celui des
documents l'acceptait puis l'ignorait — un drapeau qui ne fait rien donne l'illusion d'un
enregistrement, et c'est la même famille de défaut que les autres corrigés ici.

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

La même syntaxe vaut pour une mission réelle : `jio run "<objectif>" --provider cli:hermes`.
Nommer son modèle, c'est mesurer **le sien** — sinon le panel travaille sur un mélange de
tout ce qui est détecté sur la machine, dont personne ne peut dire ce qu'il vaut.

Et le harness dit ce qu'il en pense : un seul modèle derrière cinq critiques n'est **pas un
panel**, et il le déclare au lieu de l'appeler un consensus :

```
  [!!] DELIVERED_WITH_RESERVATION
  preuves     3/3 regles satisfaites  |  2 tour(s)  |  0.8s
  consensus   5 vote(s)  |  integrite propre  |  journal d842a6e1678a
  MOTIF : preuve complete mais consensus non atteint : panel non decorrele :
          tous les agents partagent modele et verdict — ce n'est pas un consensus,
          c'est un echo
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

<!-- sortie: jio artifacts --budget -->
```
  CHARGE AU DEMARRAGE — un outil n'en lit qu'UN (celui de son dialecte)

    CLAUDE.md                          149 ligne(s)    1918-2638   jetons
    AGENTS.md                          145 ligne(s)    1871-2573   jetons
    .cursor/rules/jio.mdc              148 ligne(s)    1870-2572   jetons
    .github/copilot-instructions.md    143 ligne(s)    1857-2553   jetons
    GEMINI.md                          143 ligne(s)    1856-2552   jetons

    Cote d'une session REELLE : ~2149 a 2221 jetons selon l'outil, pas la somme.

  DISPONIBLE A LA DEMANDE — competences
...
    TOTAL : 12 fichier(s), ~6424 jetons (estimation)
```
<!-- /sortie -->

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
- **Charger ≠ disponible.** Les 12 compétences et les 7 agents se chargent à la demande
  (révélation progressive) : les compter au démarrage ferait croire à un coût qui n'existe
  pas.

Une compétence doit aussi rester petite : au-delà d'environ 5 000 jetons, elle n'est plus
chargeable en une fois. La plus longue fait 768 jetons.

### Et les charger, c'est les **choisir** : `jio skills`

Une bibliothèque de compétences ne sert pas en étant énumérée. Deux mesures du domaine le
disent : un fichier de contexte au-delà d'une centaine de lignes est **survolé, pas lu**, et
une sélection **ciblée** bat un résumé du même contenu (la précision en tête de classement
passe de 0,14 à 0,48). Les 12 compétences tiennent donc en réserve, et une commande répond à
la seule question qui rend cette réserve utile : *pour cet objectif, lesquelles, et pourquoi ?*

<!-- sortie: jio skills "Ajouter un test qui échoue quand sum_even compte les nombres impairs" -->

  OBJECTIF  Ajouter un test qui échoue quand sum_even compte les nombres impairs

  1. executable-proof  [verification]  score 9.5119  51 jetons
     pourquoi : test (4.73), proof (2.04), executable (1.94)
  2. prose-witnesses  [verification]  score 9.3888  53 jetons
     pourquoi : prose (2.84), document (1.67), claims (1.62)

...

  cout d'injection : 152 jetons, contre 583 pour la fiche tier 0 des 12
  competences et environ 6424 pour leurs corps : le choix est ce qui rend la
  bibliotheque abordable, pas sa taille.
<!-- /sortie -->

Cinq décisions, et aucune n'est un goût personnel — chacune a été **mesurée** sur un banc de
**39 objectifs de routage** annotés à la main (`jio skills --banc`), puis payée quand elle
était fausse :

- **BM25** (Okapi) plutôt que des mots communs. L'`idf` annule le poids des mots présents
  partout, la saturation empêche une compétence bavarde de gagner par sa longueur, et la
  normalisation traite des compétences inégales. L'ablation `mots-clés bruts` chiffre ce que
  cela apporte — et c'est le témoin qui compte, pas la théorie.
- **Deux champs, deux rôles : le tiers 0 décide, le corps classe.** Trouvé par la mesure :
  verser les corps dans le **même** index faisait gagner `structured-failure` sur l'objectif
  ci-dessus, parce que son exemple de sortie cite littéralement `sum_even` — du vocabulaire
  **du dépôt**, pas le sujet de la compétence (coût du défaut : 29 points de premier choix
  juste). On en avait conclu « ne jamais indexer le corps » — conclusion trop forte, corrigée
  par une seconde mesure : pesé comme un **second champ** (`POIDS_CORPS`), le corps rend
  3 cas sur 24 objectifs **jamais vus** (45,8 % → 58,3 %) sans rien coûter au banc ni aux
  abstentions. La prose d'une compétence dit *quand* elle s'applique ; ses exemples disent
  *où elle a été écrite*.
- **Diversification MMR** : deux compétences quasi identiques occuperaient deux places du
  contexte pour une seule information. `lambda` arbitre pertinence et redondance, et quand
  l'ordre affiché n'est pas celui des scores, la commande le **dit**.
- **Abstention sur un seuil d'évidence mesuré.** La question à laquelle un routeur doit
  savoir répondre NON est : « cet objectif relève-t-il seulement du domaine ? » Le seuil porte
  sur le nombre de **mots** de domaine, jamais sur un score — un score BM25 n'a pas d'unité,
  donc pas de seuil honnête. Et un mot est identifié par son **radical** : sans cela, « outil » et
  « outils » comptaient deux mots et deux tâches de plomberie déclenchaient une procédure.

Le résultat, témoins compris, est publié par `jio skills --banc` :

| stratégie | équilibre | premier choix juste | ce qu'elle dit |
|---|---|---|---|
| **routeur** (BM25F + MMR + abstention) | **0,984** | **87 %** | 8 abstentions justes sur 8, et 31 des 31 objectifs pertinents servis |
| mots-clés bruts (ablation) | 0,623 | 77 % | ce que l'`idf`, la saturation et la pondération apportent : au témoin, ce n'est pas le score qui manque, c'est l'abstention |
| alphabétique | 0,145 | 10 % | ce que vaut un choix qui ne regarde pas l'objectif |
| tout charger | 0,500 | 10 % | rappel parfait **par construction** (6424 jetons) : le coût affiché à côté du rappel |

Premier choix juste dans 87 % des cas au total **et** 87 % quand le routeur répond : les deux
nombres sont affichés ensemble parce que l'abstention compte comme un échec dans le premier et
pas dans le second — ici elle ne coûte plus un seul objectif pertinent, ce qui est le signe que
le seuil n'est plus sur le fil. Ce qui reste faux est écrit noir sur blanc : **4 classements faux
sur 31**, listés un par un par le banc (`MANQUEE ...`). Un rapport qui ne montrerait que
ses succès ne serait pas une mesure.

Et la mesure qui a fait changer la règle d'abstention mérite d'être racontée, parce qu'elle est
le genre d'erreur qu'un score global cache : la première version comptait des **concepts par
classe d'équivalence**, si bien qu'un objectif mettant trois mots du même champ — « Le vote de
trois critiques identiques ne vaut pas un consensus » — ne comptait qu'un concept et se faisait
refuser. Le banc avait **deux** cas comme celui-là, plus un troisième sur la forge de
compétences. Compter les **mots** de domaine, par radical, répare les trois et élargit la marge :
au cran suivant (3 mots), il reste 25 objectifs pertinents sur 31, contre 14 avant.

Le banc est la **limite** de l'affirmation, pas sa preuve : il tient en 39 objectifs de routage écrits
par la personne qui a écrit le routeur. Ce qui lui donne sa valeur n'est donc pas le score absolu,
mais l'**écart aux témoins** — et le fait que le seuil déclaré soit celui que le balayage
retrouve (`jio skills --seuil-balaye`, vérifié par un test : la constante et la mesure ne
peuvent pas diverger en silence).

### Et sur des objectifs **jamais vus**, le routeur est à 41 % — la distribution est publiée

Le banc ci-dessus a *réglé* le routeur : il ne peut donc pas dire s'il **généralise**. **113 cas
jamais vus**, en quatre jeux écrits chacun **avant** une retouche, disent ce qu'il vaut vraiment :

```
  banc du dépôt (39 objectifs de routage, celui du réglage) .......... 87 %
  jeu A (24 objectifs de contrôle, avant la retouche du lexique) ..... 58 %
  jeu B (24 cas, avant la retouche BM25F) ............................ 50 %
  jeu C (35 cas, pré-enregistré, préfixes d'objets métier) ........... 29 %
  jeu D (30 cas, pré-enregistré, AVEC DÉTAIL RESTÉ AVEUGLE) .......... 33 %
  TOTAL des 113 cas jamais vus ....................................... 41 %
  abstention juste, 23 hors sujet confondus ......................... 96 %
```

Quatre jeux plutôt qu'un, parce qu'un seul donne un chiffre, deux donnent un désaccord, et quatre
donnent une **distribution**. C'est la distribution qu'on peut résumer honnêtement — et c'est
elle qui empêche de proclamer une retouche gagnante sur la foi d'un seul jeu. Le jeu D l'est
encore moins que les autres : son **détail** n'a jamais été ouvert avant la retouche suivante,
donc si le prochain gain se confirme, il ne pourra pas venir d'un ajustement pensé pour ces cas.

Deux détails de méthode qui ont coûté, et qui sont donc écrits ici :

- Le **matériel du jeu B vivait hors du dépôt** (`/tmp`) et le bac à sable a été réinitialisé. Il
  n'en restait que les douze échecs cités par l'archive. Un témoin qu'on ne peut pas **rejouer**
  n'est plus un témoin, c'est une anecdote : la même phrase « 50 % », sans le matériel, ne refute
  plus rien. Le jeu a donc été reconstitué **et vérifié** — rejoué, il doit rendre exactement les
  douze échecs de l'archive, faute de quoi il est déclaré faux. C'est un test.
- Sa **première** transcription reprenait, sans le voir, des cas du jeu A : le jeu « neuf »
  mesurait 37,5 % au lieu de 50 % et n'apportait aucune information. C'est aussi un test : aucun
  texte de cas ne peut désormais apparaître dans deux jeux.

**L'écart entre les lignes est le résultat.** Afficher 87 % sans les autres serait un chiffre vrai
qui trompe, et c'est exactement ce que ce dépôt s'interdit. `jio skills --banc` renvoie aux jeux
de contrôle, et `jio skills --controle` affiche leurs taux ; `--detail` n'existe que pour ouvrir
chaque cas **après** une retouche.

La cause a été identifiée par étapes, et chaque étape est mesurée :

1. **Le pont bilingue ne couvrait qu'une partie du vocabulaire** (« changed the assertion »,
   « keeps coming back », « reusable procedure » n'avaient aucun voisin). L'extension du lexique,
   dans les deux langues, fait passer le contrôle de **33 % à 46 %** sans faire bouger le banc.
2. **Les fiches ne contenaient que 1 à 3 phrases**, et elles sont en français alors que l'agent
   travaille en anglais : un objectif formulé autrement n'avait presque aucun mot à rencontrer.
   Le **corps** de chaque compétence — en anglais, et il dit *quand* elle s'applique — entre donc
   dans l'index comme second champ pondéré. Contrôle : 46 % → **58 %**, banc 83,9 % → 87,1 %,
   abstentions 17/17 inchangées.

Ce qui reste hors de portée est déclaré : combler le reste demande de la **similarité
sémantique**, donc des plongements — et aucun poids de modèle n'est téléchargeable depuis cette
machine (`huggingface.co` injoignable, seuls PyPI et GitHub répondent). Trois pistes ont été
essayées et **écartées par la mesure**, plutôt que gardées parce qu'elles avaient l'air bonnes :

| piste essayée | résultat | décision |
|---|---|---|
| fusion RRF (BM25 + trigrammes de caractères) | 100 % → **5 %** au régime identifiant, 87 % → 23 % au mélange | **écartée** : un second classement faible *dilue* le premier |
| indexer le vocabulaire **procédural** des corps (mots alphabétiques à IDF élevée, littéraux exclus) | 46 % → **46 %** | **écartée** : aucun gain, plus de bruit dans l'index |
| nourrir l'abstention avec le vocabulaire des **corps** | hors sujet acceptés : 8/8 et 4/4 → **6/8 et 2/4** | **écartée** : le corps servait de porte dérobée au classement ; l'abstention ne juge que le tier 0 |

Le gain des 3 cas est une **direction, pas une preuve** : sur 48 objectifs jamais vus l'intervalle
de confiance du gain est **[0 ; +14,6] points** — sa borne basse touche zéro. C'est écrit ici
parce qu'un chiffre publié sans son intervalle serait exactement ce que ce dépôt s'interdit
(`evidence/routeur-bm25f-075.{md,json}`).

Et quand aucune procédure ne s'impose, l'abstention **rend une liste classée**, pas du vide. Ce
que cette liste vaut est mesuré, sur les **24 objectifs du domaine que la porte refuse** :

| liste rendue | bonne compétence | IC95 | rapport au hasard (1 sur 12) |
| --- | ---: | --- | ---: |
| premier élément | 10/24 = **42 %** | [24 % ; 61 %] | 5,0× |
| trois premiers | 14/24 = **58 %** | [39 % ; 76 %] | 7,0× |
| cinq premiers (rendus) | 17/24 = **71 %** | [50 % ; 85 %] | 8,5× |
| liste complète (12, complétée par ressemblance) | 24/24 = **100 %** | [86 % ; 100 %] | 12× |

Cinq éléments, et pas davantage : trois à cinq fait gagner 9 points de « la bonne réponse est
visible » pour une quinzaine de jetons (des noms et des scores, jamais des corps) ; au-delà, on
retombe sur l'inventaire complet, qui n'est pas classé — et un inventaire non classé vaut le
hasard. La liste est **classée, jamais appliquée** : le routeur ne prétend pas qu'une procédure
s'applique, et la confiance à lui accorder est écrite à côté
(`evidence/routeur-liste-abstention`). Deux sorties de secours restent nommées, dans cet ordre :
`jio skills "<objectif>" --seuil 0` pour forcer un classement, et `jio skills --nom <compétence>`
pour charger le **texte complet** d'une procédure reconnue dans la liste. Un nom inconnu est
refusé en **énumérant les noms valides**.

### Ce qui manquait n'était pas un réglage, c'était une ressource

Les 24 objectifs refusés ne partagent **aucun mot** avec les fiches : « prove the fix by running
it » ne contient ni « executer », ni « preuve », ni « verification ». Aucune porte lexicale ne
peut les voir, et c'est ce qui plafonnait tout. Le dépôt embarque donc une **table de similarité
sémantique** — **11000 radicaux**, 100 dimensions, 0,88 Mo — construite par
`scripts/construire-vecteurs.py` à partir du paquet npm `wink-embeddings-sg-100d` (MIT), lui-même
dérivé des vecteurs **GloVe** de Stanford (PDDL, domaine public). Pourquoi cette source : le noyau
de ce dépôt n'a **aucune dépendance**, et les modèles de phrase habituels (PyTorch /
`sentence-transformers`) demandent un accès réseau qui n'existe pas ici — `huggingface.co` est
injoignable depuis cette machine, `registry.npmjs.org` non. Le format est relu par un chargeur
écrit à la main (`jio/skills/vecteurs.py`), sans `pickle` : un fichier de données qui exécute du
code n'est pas une donnée.

La table sert à **une** chose, et deux autres usages ont été mesurés puis écartés
(`evidence/vecteurs-semantiques.md`) :

| usage | verdict | mesure |
| --- | --- | --- |
| une **porte** sémantique (charger ou non) | **impossible** | un hors sujet atteint 0,998 de ressemblance quand un objectif du domaine refusé plafonne à 0,806 : les deux populations se recouvrent |
| **réordonner** toute la liste (fusion RRF) | **écarté** | gagne jusqu'à +3 au cinquième rang mais fait tomber le premier élément de 10 à 9 sur les refusés et de 27 à 22 sur le banc |
| **compléter** une liste trop courte | **retenu — domination stricte** | @5 16→17, @12 21→24 sur les refusés ; @12 107→112 sur les 113 ; banc **inchangé** |

Concrètement : `seuil=0` ne rend que les compétences **marquées** par BM25F, donc 5 des 24 listes
n'avaient que 1 à 3 éléments **alors que l'en-tête en annonçait cinq**. La ressemblance ne touche
pas la tête : elle ordonne les places laissées vides. Un élément ajouté porte `score 0.0`, une
`proximité` (0..1, une **autre** échelle, d'où un autre nom) et la raison « aucun mot commun —
voisin X~Y » ; la CLI et le MCP annoncent le partage (« N marqué(s) par le lexique, M ajouté(s) par
ressemblance »). Le bruit reste possible sur un hors sujet — mesuré, **étiqueté, pas caché**, et
un tri par contraste a été essayé pour l'écarter : il ne sépare pas davantage (0,090 contre 0,101).
Si la table disparaît, `proximité` vaut `null` et la liste redevient exactement celle d'avant.

Avant d'en arriver là, deux campagnes ont conclu au **plateau**, et c'est écrit pour ne pas les
refaire : six portes d'abstention candidates (prose des corps dans la preuve, lexique *et* autre
source, pondération, idf fort…) donnent des chiffres **identiques ou pires** — les objectifs
refusés ne partagent *aucun* mot avec le corpus (« prove the fix by running it »), donc aucun
enrichissement de vocabulaire ne peut les sauver ; une seconde porte par le **lexique** charge
3 hors-sujet sur 8 **du banc**, et elle est écartée sur le banc même ; une seconde porte par le
**score** serait sélectionnée sur les jeux de contrôle, donc refusée par protocole ; douze
variantes de classement (BM25F canonique, poids du corps 0,5→2,0, idf fusionné, répétition des
champs courts 1→5) plafonnent à **+2 cas sur 113** et toutes dégradent le banc. Le critère
d'acceptation — améliorer les quatre jeux **sans** dégrader le banc — avait été déclaré avant.

Ces deux lignes sont conservées ici pour ne pas refaire les essais : une brique qui n'a pas
prouvé son utilité ne reste pas dans le dépôt, mais la trace de l'essai reste — sinon la même
idée revient tous les six mois avec le même enthousiasme.

### Et elles entrent dans la mission, au bon moment

Un routeur que personne ne charge est une décoration : une commande de plus, que personne ne
lance. `jio run` **injecte donc les procédures retenues dans le prompt de mission** — jusqu'à 3,
budget **1500 jetons** (les douze pèsent 6424, et un contexte saturé fait perdre ce que le
contexte apportait). Ce qu'il écarte est **nommé** dans le journal, jamais tu en silence.

Trois propriétés rendent cette injection utile plutôt que coûteuse, et chacune a son test :

- **Sélective** — c'est l'objectif qui décide. Un mandat hors du domaine des procédures n'ajoute
  **rien**, et le dit ;
- **Bornée et déclarée** — le budget compte l'en-tête du bloc, pas seulement les corps : un
  budget qui annoncerait 1500 jetons et en coûterait 1566 serait un chiffre faux de plus, dans le
  seul module dont le travail est de ne pas dépasser. Une procédure qui ne rentre pas est
  **écartée**, jamais coupée au milieu : une procédure tronquée a l'air complète ;
- **Domestiquée** — les corps de compétences sont du contenu **du dépôt**, écrit pour piloter un
  agent. Le bloc dit donc explicitement qu'elles ne modifient **aucune** exigence énumérée et
  que, en cas de conflit, **la spécification gagne**. Sans cette phrase, une procédure du dépôt
  aurait le pouvoir d'annuler une exigence de l'utilisateur — le scénario de CVE-2025-53773.

Chaque injection est **tracée** (`competences-injectees` : noms, coût, écartées, objectif routé).
Et l'ablation est à portée de main — `jio run "<objectif>" --sans-competences` — parce qu'une
brique dont on ne peut pas mesurer l'apport n'a pas prouvé qu'elle en avait un.

Un détail qui a coûté une mesure : quand `--task` écrasait le **mandat**, le routeur voyait
l'énoncé technique de la tâche (« Écrire une fonction `sum_even(nums)`… ») et s'abstenait
légitimement — cet énoncé ne dit rien du domaine. Le mandat de l'utilisateur reste donc
l'objectif de la **mission**, l'énoncé de tâche celui du **travail** : un seul mot change de
place, et les procédures arrivent au bon moment.

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

Trois autres, trouvés plus tard — cette fois par le scan lancé sur **lui-même**, et
c'est exactement ce qu'on lui demande :

| Défaut | Ce qui se passait | Correctif |
|---|---|---|
| Il accusait de **trier** une fonction qui **quitte** — `sortir` | le nom contient la sous-chaîne `sort` : la propriété « tri fidèle » s'appliquait au cœur des codes de sortie | les promesses de nom se comparent désormais **en mots** (`sort_values`, `sorted`, `order_lines` oui ; `sortir`, `sortie`, `sorte` non) |
| Il déclarait **non testable** un fichier de test qui passait | le fichier lit ses données par `Path(__file__).resolve().parents[1] / "evidence"`, or l'audit l'exécutait dans un dossier temporaire : `__file__` valait `/tmp/…/main.py`, donc les données étaient cherchées sous `/tmp`, et l'absence était présentée comme une limite **du projet** | le fichier audité reçoit son **vrai** `__file__` (le script tourne toujours dans un dossier temporaire : rien n'est écrit dans le projet) |

Le second est celui qui compte. Un outil qui ne sait pas lire les fichiers de test — c'est-à-dire
là où un projet met sa vérité — déclare « rien à vérifier » sur ce qui compte le plus. Après ces
corrections, sur ce dépôt : **0 problème, 0 fichier non testable**, et les deux causes sont
verrouillées par des tests qui échoueraient si elles revenaient.

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

## `jio coherence` : la porte qui empêche « c'est fini » d'être une opinion

Chaque brique de ce dépôt vérifie **une** chose : `jio scan` le code, `jio claims` les
faits d'un document, `jio chiffres` un compteur, `jio audit` un artefact. Aucune ne
répondait à la question qui compte avant de déclarer un travail terminé : **est-ce que
l'ensemble tient encore ?**

Les trois incohérences qui ont motivé cette commande ne sont pas hypothétiques — elles
sont arrivées dans ce dépôt, toutes les trois :

<!-- hors-controle: recit d'incoherences passees — ce tableau raconte des faits historiques, il n'affirme rien du jour -->
Les deux derniers contrôles visent ce que l'agent **lit** et ce qui a été **écrit** :
`competences` audite les 12 compétences Hermes (motifs dangereux, mises en garde distinguées des
interdits) et vérifie leur coût en contexte en **intervalle** (3,2 à 4,4 caractères par jeton) —
une compétence au-delà de 5 000 jetons ne se charge plus en une fois ; `journal` vérifie la
**chaîne de hachage** du journal d'exécution : c'est la seule façon de répondre à « quelqu'un
a-t-il réécrit l'histoire ? ». Sans journal, le contrôle est *hors portée* — un projet qui n'a
jamais lancé de mission n'a rien à prouver.

| Ce qui était affirmé | Ce qui était vrai | Ce qu'aucun contrôle ne voyait |
|---|---|---|
| « 755 tests verts » dans le README | 848 tests | Un compteur n'est relu par personne |
| `jio verify` cité dans un artefact généré | la commande n'existe pas | La fiche que l'IA lit en premier |
| AGENTS.md au-delà de 150 lignes | sa propre limite | Un fichier survolé reste « présent » |
<!-- /hors-controle -->

Aucune n'était un bug du code. Toutes étaient des **affirmations devenues fausses** que
personne ne relisait. `jio coherence` passe neuf contrôles d'un coup et rend **un verdict** :

<!-- prose:hors-controle: illustration datee d'une sortie dont les compteurs bougent a chaque commit (30 artefacts, 70 commandes, 79 fichiers) : la verifier en dur obligerait a reecrire le README a chaque commit, et un exemple fige serait faux le jour suivant. Ce qui est VERIFIABLE, lui, se declare `sortie:` et l'est -->
```
  COHERENCE D'ENSEMBLE  ·  ce que ce depot affirme est-il encore vrai ?
    9 controle(s) en 2.2s  ·  VERDICT : COHERENT : tout ce que ce depot affirme est encore vrai

    [ok] artefacts     30 artefact(s) generes, tous a jour
    [ok] nombres       6 chiffre(s) mesure(s)
    [ok] documents     99 affirmation(s) verifiee(s) sur 5 document(s), 2 exemple(s) de sortie
    [ok] commandes     70 commande(s) citee(s), toutes existantes · 3 zone(s) declaree(s) hors
    [ok] competences   12 competence(s) auditee(s), 39 artefact(s) lus, ~5549-7631 jetons
    [ok] environnement 28 variable(s) lue(s) et documentee(s)
    [ok] sources       paquet jio/ : 79 fichier(s), 0 constat(s) de lint, 0 d'import
    [ok] journal       hors de portee : aucun journal dans cette racine
    [ok] plan          aucun plan autonome en cours
```
<!-- /prose:hors-controle -->

Le code de sortie vaut **0 seulement si tout est cohérent** : une IA peut donc s'en servir
comme arbitre avant de dire « fini », sans lire le texte. Et le texte dit toujours *quoi*
corriger :

```
    [KO] nombres       3 chiffre(s) mesure(s), 1 ecart(s) — `jio chiffres --appliquer`
         - README.md ligne 15 : 1274 tests verts -> 1274 tests verts
```

### Les exemples de sortie sont vérifiés, comme le reste

Le README montrait `jio artifacts --budget` avec « 11 fichier(s), ~5715 jetons » et des
fichiers de contexte à 136/133/134 lignes. L'outil en disait **12**, **6424**, et 150/145/148.
La porte annonçait pourtant neuf contrôles verts : elle vérifiait que la commande **citée**
existe, que les chiffres **comptés** sont justes, que les calculs de la prose tiennent — mais
pas qu'une **sortie recopiée** est encore la sortie réelle. C'était la seule classe
d'affirmation du dépôt que rien ne relisait, et la plus fragile : longue, datée, pleine de
chiffres, et personne ne relit une capture d'écran.

Un bloc se déclare donc en nommant la commande qui doit le produire :

```html
<!-- sortie: jio artifacts --budget -->
  CHARGE AU DEMARRAGE — un outil n'en lit qu'UN (celui de son dialecte)
...
    TOTAL : 12 fichier(s), ~6424 jetons (estimation)
<!-- /sortie -->
```

- `sortie:` — les lignes montrées sont un **extrait** de la sortie réelle, et les coupures
  sont **déclarées** par `...`. Chaque morceau contigu est cherché dans la sortie, dans
  l'ordre, après la fin du précédent : un extrait qui remettrait les sections dans un autre
  ordre que l'outil ne serait pas un extrait, ce serait une citation arrangée.
- `sortie-exacte:` — le bloc est la sortie **complète**. Celui-là se **répare** :
  `jio sorties --appliquer` le réécrit avec la sortie du jour, après sauvegarde `.avant-jio`.
  L'extrait, lui, est **signalé et jamais réécrit** : choisir les lignes à montrer demanderait
  de deviner l'intention de l'auteur.

Trois choses changent d'une machine à l'autre sans rien dire, et sont masquées **avant** la
comparaison : les couleurs ANSI, les chemins absolus (`<racine>`), les durées (`<duree>`).
Masquer davantage serait s'exempter soi-même du contrôle.

**Un document est un contenu hostile par défaut** — c'est ici que cela se prouve, parce que le
contrôle *exécute* ce qu'il lit. La liste blanche n'est donc pas un filtre de politesse : seul
le programme `jio` est lancé, sans shell (arguments en liste), sans métacaractère
(`; | & < > $ \` ` `` ` `` `), et sans option qui écrit (`--write`, `--appliquer`, `--fix`,
`--sortie`). Un refus est **signalé**, jamais silencieux : l'ignorer reviendrait à croire le
document sur parole. Quand un exemple ne peut pas être vérifié parce que ses compteurs bougent
à chaque commit, il est déclaré **hors contrôle avec sa raison** — ce qui est dit, jamais
deviné.

### `--reparer` : réparer le mécanique, nommer le reste

Une porte qui signale sans rien réparer finit par être contournée. `jio coherence --reparer`
traite les deux cas où **la valeur correcte est déjà dans le code** — artefacts générés, chiffres
mesurés — puis **repasse la porte** et publie le nouveau verdict. Tout le reste est classé, et le
classement est la partie utile :

| Catégorie | Exemples | Ce que fait l'outil |
|---|---|---|
| **mécanique** | un artefact régénéré, un compteur périmé | il répare, et il relit |
| **décision humaine** | un document faux, une compétence dangereuse, une commande inexistante, un chiffre *jamais annoncé* | il **nomme la décision attendue**, et ne touche à rien |
| **jamais** | un **journal dont la chaîne est cassée** | rien — une telle chaîne est la **preuve** qu'on a réécrit l'histoire : la « réparer » effacerait la seule trace du problème |

Trois propriétés rendent ce portail utilisable plutôt que décoratif :

- **Il interroge le programme réel.** La liste des commandes vient du parseur (`build_parser`),
  jamais d'une liste recopiée : une liste recopiée finit par décrire un autre programme.
- **Il sait échouer.** Chaque contrôle a son test côté rouge : un artefact modifié à la main,
  un chiffre périmé, une commande inventée, un plan resté en suspens. Un contrôle qu'on ne
  sait pas faire échouer est un affichage, pas une porte.
- **Il est *fail-closed*.** Un contrôle qui lève devient un constat en échec avec son message,
  jamais un silence : un portail qui saute l'étape qui plante est un portail ouvert.

Coût mesuré : **1,5 s** sur ce dépôt, et il est branché là où un humain décide — hook
pre-commit local et CI.

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

### La mémoire qui s'accumule : le protocole multi-cycles

L'A/B compare trois bras sur **un** passage. Il ne peut pas répondre à la question
suivante : *la mémoire qui grandit cycle après cycle finit-elle par payer, ou rend-elle le
harness plus cher sans le rendre meilleur ?* `jio learn --cycles N` la mesure.

Par cycle, **trois bras** sur les mêmes tâches, les mêmes graines et le **même bras de
routeur** :

| Bras | Mémoire | Avertissement | Ce qu'il isole |
|---|---|---|---|
| **chaud** | accumulée | actif | le système tel qu'il tourne |
| **témoin** | présente | désactivé | l'artefact : le même prompt, sans effet |
| **froid** | absente | — | la référence sans souvenir |

Le bras **chaud tourne d'abord** : il choisit son bras via le vrai bandit, et les deux
autres **rejouent la même mission avec ce bras figé**. Le contraste causal est
`chaud − témoin` ; `froid − témoin` est le **bruit de fond déclaré** du protocole.

> **Trois défauts trouvés en construisant cette mesure, tous les trois corrigés.**
>
> **1. L'appariement.** Le froid tournait avec la configuration *par défaut* pendant que
> le chaud tournait avec le bras du routeur : l'écart mélangeait deux causes. Symptôme :
> au premier cycle, mémoire **vide des deux côtés**, le froid gagnait `3/5` contre `2/5`.
>
> **2. Le levier était inatteignable.** L'effet d'avertissement n'est accordé que si le
> souvenir concerne *cette* tâche — et la condition ne pouvait jamais être vraie : la
> banque indexe chaque tâche par son objectif **entier** (161 caractères pour `sum_even`)
> alors que le bloc de mémoire borne ce qu'il cite. Mesure : **31 blocs présents dans le
> prompt, 0 armé**. Le bloc porte maintenant sa ligne `ON TASK:`, le test d'armement
> compare les **identifiants techniques** (robuste à la troncature, et c'est le bon
> critère : `sum_even` distingue les tâches, « renvoie » ne les distingue pas).
> Portée passée de **0 % → 99,3 %** des appels de génération.
>
> **3. Le bloc pouvait détourner la mission — le plus grave.** La tâche est identifiée en
> cherchant la plus longue clé du banc présente dans le prompt. Un souvenir citant
> l'objectif d'**une autre** tâche pouvait donc faire répondre le modèle à *cette autre
> tâche*, en croyant répondre à la sienne. La lecture de la tâche s'arrête désormais au
> premier bloc injecté (`_demande`) : **une mémoire ne doit pas pouvoir changer la
> question.**

Régime du run de référence : compétence simulée `0.4`, 5 tâches, 5 tirages, 2 tours,
4 cycles — **300 missions, 100 essais par bras, ~19 min** sur deux cœurs :

| cycle | mémoire | froid | témoin | chaud | artefact | **écart** |
|---|---|---|---|---|---|---|
| 1 | 0 | 20/25 | 20/25 | 22/25 | +0 | **+2** |
| 2 | 8 | 24/25 | 24/25 | 24/25 | +0 | **+0** |
| 3 | 10 | 19/25 | 19/25 | 23/25 | +0 | **+4** |
| 4 | 18 | 22/25 | 22/25 | 23/25 | +0 | **+1** |
| **cumulé** | 23 souvenirs | **85/100** | **85/100** | **92/100** | **+0** | **+7** |

Trois choses deviennent visibles, et aucune n'était lisible avant :

1. **Le témoin est une référence parfaite** : l'artefact `froid → témoin` vaut `0` aux
   quatre cycles (contre `−4` puis `−3` sur le run précédent, qui n'avait pas encore les
   corrections 2 et 3). Le bruit est absorbé, pas confondu avec l'effet.
2. **L'écart causal est de +7 points**, dans le même sens aux quatre cycles (jamais
   négatif) : `+2, +0, +4, +1`. Ce n'était plus « 0,0 point ».
3. **Et il colle au modèle déclaré** : `portée × gain relatif × compétence` = `99,3 % ×
   0,20 × 0,40` = **+7,9 points attendus** pour **+7,0 observés** — soit 88 %. L'ordre de
   grandeur est celui annoncé, ce qui **valide la modélisation** au lieu de la supposer.

Deux corrections de méthode sont sorties de ce run :

- **L'intervalle est désormais POOL sur tous les cycles.** Le protocole mesurait 100 essais
  et n'en jugeait que les 25 du dernier : il jetait 75 % de sa propre preuve. La
  comparaison reste appariée cycle par cycle, donc empiler les cycles n'ajoute aucun biais
  — cela ajoute de la résolution (budget requis mesuré : **1177 → 432 essais par bras**).
- **Le gain déclaré se calcule sur la COMPÉTENCE du modèle, pas sur le taux observé.**
  Le taux observé (85 %) est déjà le produit de la largeur de tirage et de la vérification :
  s'en servir comme base gonflait l'attendu d'un facteur deux et aurait déclaré
  « incohérent » un écart parfaitement cohérent.
- **Le test est désormais APPARIÉ — celui du plan expérimental.** Les trois bras jouent
  les *mêmes* missions avec les *mêmes* graines : la statistique correcte est le test exact
  de McNemar sur les seules missions où les deux bras divergent, pas la comparaison de deux
  échantillons indépendants. Constat chiffré qui a motivé le changement : **+10 réussites sur
  220 paires** laissaient l'intervalle non apparié contenant zéro (« indémontré »), alors que
  les **17 dissociations favorables contre 6 défavorables** donnent **p = 0,0347** et un
  IC95 apparié de **(0,008 ; 0,092)** : l'effet est **démontré**. La même implémentation
  (`mcnemar_exact` / `_wald_apparie` de `jio/bench/ablation.py`) sert ici et à l'ablation —
  une seule formule de McNemar dans le dépôt. Le budget de mesure suit : `essais_requis()`
  ne réutilise plus la formule pour deux échantillons *indépendants* (qui surestimait le
  besoin) mais calcule, à partir du taux de dissociation observé, le nombre de **paires**
  qu'il faut pour départager `b` de `c` à 95 % / 80 % de puissance.
- **Un cumul mesuré SANS les paires ne peut pas conclure, et le dit.** Les cycles écrits
  avant cette version n'ont pas les compteurs de dissociation : leur rapport l'annonce
  explicitement (« ce cumul a été mesuré sans le relevé des paires ») au lieu de laisser
  lire « PLATEAU » comme « pas d'effet ». Les compteurs sont désormais **écrits dans le
  JSONL** et relus : un cumul interrompu puis repris ne perd pas sa résolution statistique.

Le verdict reste **PLATEAU** — et c'est précisément ce que le rapport doit dire :

```
  PORTEE DU LEVIER : 276/278 appel(s) de generation avertis (99.3 %)
  ESSAIS REQUIS POUR DEMONTRER L'ECART OBSERVE : 432 par bras, soit ~45 min ici
  VERDICT : PLATEAU
    ecart positif (dernier cycle +1 sur 25 ; cumule +7 sur 100) mais l'intervalle POOL
    CONTIENT zero : INDETERMINE. L'ecart observe (+7.0 points) est a 88% de l'effet que
    la modelisation declare (+7.9 points a cette portee) : l'ordre de grandeur est celui
    attendu, ce qui VALIDE la modelisation — et laisse penser qu'il y a bien un effet,
    simplement plus petit que ce que 100 essais peuvent demontrer.
```

Autrement dit : **le harness a maintenant un instrument qui voit l'effet mémoire**, il
l'estime à +7 points, il en attribue l'ordre de grandeur au mécanisme déclaré, et il refuse
de le déclarer prouvé à 100 essais — en donnant le budget exact (432 essais/bras) pour le
prouver. C'est la différence entre « la mémoire ne sert à rien » (ce qui était écrit avant,
et qui était faux) et « la mémoire vaut +7 points, voici ce qu'il faut pour le démontrer ».

### La mémoire qui apprend vraiment : l'échec ouvre, le succès ferme

Une mémoire d'échecs qui ne retient que la plainte ne sert à rien. C'est pourtant ce qui
était écrit : à chaque échec, le moteur enregistrait
`correct_fix="atteint dans une mission ulterieure"` — un texte **vide de sens**, injecté
ensuite dans **tous** les prompts sous l'étiquette `RIGHT FIX`. Ni un modèle ni un relecteur
ne peut en tirer quoi que ce soit.

Trois corrections, et la troisième est celle qui change la valeur de la mémoire :

| Avant | Après |
|---|---|
| `RIGHT FIX: atteint dans une mission ulterieure` | `RIGHT FIX: inconnu (aucun remede observe pour l'instant)` — **déclaré** |
| le remède n'arrivait jamais | quand une mission **réussit** sur le même objectif, le remède observé **remplit** l'échec ouvert : `regle(s) satisfaite(s) depuis la mission succes-1 : R-001,R-002 ; forme livree : def sum_even(nums): ...` |
| écriture d'un remède creux, définitif | événement `resolution` **append-only** : la chaîne de hachages reste vérifiable (une mémoire réinscriptible est une mémoire empoisonnable) |

Et un **assainissement** que ce chantier a rendu nécessaire : la mémoire repart dans les
prompts, donc son contenu est une source **HOSTILE**. Un artefact qui échoue écrit son
message d'erreur *dans la mémoire* — il pouvait donc y glisser les marqueurs réservés de JIO
(`PAST FAILURES ON SIMILAR TASKS`, `PREVIOUS ATTEMPT FAILED`) et **fabriquer un faux
souvenir**, relu à chaque mission. Ces marqueurs sont neutralisés à l'écriture, les tournures
d'instruction retirées, les sauts de ligne supprimés, la longueur bornée. La dette est
visible : `jio memory` affiche désormais `N échec(s) (M avec un remede OBSERVE, K en
attente)` — un souvenir sans remède dit ce qui a échoué, pas ce qui répare.

### Une mesure longue doit survivre à une coupure

Deux fois de suite, une mesure de 20 minutes a été **perdue en entier** : le rapport
n'était écrit qu'à la fin. `jio learn --cycles N --cumul FICHIER` corrige les deux moitiés
du problème :

- les cycles sont **écrits au fur et à mesure**, donc une coupure ne perd que le cycle en
  cours ;
- `--cumul` **empile** les exécutions, et le rapport affiché est le cumul.

Avec un piège que ce chantier a mis au jour, et qui aurait fabriqué un faux résultat :
**deux exécutions qui rejouent les mêmes graines ne sont pas deux mesures**. Cumuler sans
le voir ferait grossir le nombre d'essais et resserrer l'intervalle *autour de rien* — la
façon la plus efficace de rendre un écart significatif qui n'a jamais été mesuré deux fois.
Le cumul décale donc le **bloc de graines** à chaque exécution (`0`, `1000`, `2000`, …) et le
rapport l'affiche :

```
  CUMUL : 2 cycle(s) au total dans cycles.jsonl
  REPLICATIONS INDEPENDANTES : 2 (blocs de graines : 0, 1000)
```

Le cumul **refuse** de mélanger deux régimes différents (compétence, tours, gain) : un
mélange ne répond à aucune question. Le refus est un `ValueError`, testé.

Trois garde-fous, dont deux nés d'incidents réels :

- **écriture par cycle** — vérifié en cassant exprès : un `kill -9` en plein deuxième cycle
  laisse le premier cycle sur le disque et relisible. La première version n'écrivait qu'à la
  fin *en prétendant le contraire* : une promesse de robustesse non tenue est pire qu'une
  absence de promesse, parce qu'elle fait croire à une protection inexistante ;
- **verrou exclusif** (`<fichier>.verrou`) — deux mesures simultanées sur le même cumul
  liraient le même nombre de cycles, en déduiraient le **même bloc de graines** et
  rejoueraient exactement les mêmes tirages. Le verrou refuse le second lancement, et il est
  relâché dans un `finally` : un échec ne doit jamais bloquer l'utilisateur ;
- **refus de mélanger les régimes** — compétence, tours ou gain différents : `ValueError`.

Et le troisième garde-fou a servi **pour de vrai**, cinq minutes après avoir été écrit. Un
`kill` de nettoyage a tué une campagne en plein premier cycle ; le pilote a enchaîné les
deux blocs suivants, qui ont été **refusés** — pas perdus, refusés :

```
  [PROBLEME] une autre mesure ecrit deja dans preuve3-cumul.jsonl (verrou ...). Deux mesures
  simultanees rejoueraient les MEMES graines : attendre la fin, ou supprimer le verrou s'il
  est reste d'un processus tue.
```

Sans ce verrou, les blocs 2 et 3 auraient repris au bloc de graines `0` — celui du bloc 1
déjà écrit — et le cumul aurait affiché **quatre réplications indépendantes au lieu de
deux**, avec des essais comptés deux fois. C'est exactement le faux résultat que le verrou
existe pour empêcher, et il a fallu un vrai incident pour le montrer.

### Un cumul n'est pas une moyenne : le rapport rend l'effet *par bloc*

Deuxième trouvaille de la même campagne : le cumul affichait **+7** après deux cycles du
premier bloc, puis **+0** au premier cycle du suivant. Le cumul restait juste — le test de
McNemar porte sur l'ensemble des paires — mais il **masquait** l'hétérogénéité. Un lecteur
qui ne voit que « +7 sur trois cycles » lit une moyenne qui n'existe dans **aucun** des deux
blocs.

`Cycle.bloc` est donc écrit dans le JSONL (et **déduit** de la dernière ligne `replication`
quand il manque : les fichiers déjà mesurés restent attribuables, sans migration), et le
rapport sépare les tirages :

```
  REPLICATIONS INDEPENDANTES (un cumul est une somme de tirages, pas une moyenne) :
    bloc de graines     0 : +7 reussite(s) (9 contre 0 dissociation(s))
    bloc de graines  1000 : +0 reussite(s) (0 contre 0 dissociation(s))
```

Avec un seul bloc, le rapport dit ce qui manque au lieu de laisser croire à une
démonstration : *« une seule pour l'instant — un effet mesuré sur un seul bloc de graines
n'est pas encore un effet REPRODUIT »*. Et le contrôle symétrique existe : quand les blocs
concordent, la phrase le dit aussi (« même sens dans tous les blocs ») — un rapport qui ne
signalerait que l'hétérogénéité serait biaisé.

### Le contrôle positif : un instrument doit savoir dire oui

Un instrument qui ne dit **jamais** « ça marche » ne peut pas être cru quand il dit « rien
ne se passe ». Avant de lire un seul `PLATEAU`, il fallait donc vérifier que la mesure sait
détecter un effet connu. Le protocole mesure l'effet d'un mécanisme **déclaré** : il suffit
de régler ce mécanisme très haut.

```
python -m jio learn --cycles 4 --runs 3 --rounds 2 --skill 0.4 --gain 2.0
```

| cycle | froid | témoin | chaud | artefact | écart |
|---|---|---|---|---|---|
| 1 | 12/15 | 12/15 | 14/15 | +0 | +2 |
| 2 | 12/15 | 12/15 | 15/15 | +0 | +3 |
| 3 | 11/15 | 11/15 | 15/15 | +0 | +4 |
| 4 | 13/15 | 13/15 | 15/15 | +0 | +2 |
| **cumulé** | 48/60 | 48/60 | **59/60** | **+0** | **+11** |

**Verdict : `PROGRESSE`**, intervalle pool excluant zéro. L'instrument voit un signal
connu, et il voit en plus ce qu'un instrument doit voir : un **témoin parfait** (`artefact
= 0` aux quatre cycles, mémoire présente et effet éteint). Le contrôle négatif est
verrouillé par un test, et il ne coûte presque rien : **à gain nul, `chaud` et `témoin`
doivent être égaux exactement** — même prompt, même graine, même bras, seul le réglage de
l'effet les distinguait.

Ces deux contrôles changent le statut du résultat principal. Sans eux, « écart de +7 points
non démontré à 100 essais » serait un chiffre parmi d'autres ; avec eux, c'est une **mesure
dont l'instrument a été étalonné** : il sait dire oui (+11 sur 60 essais), il sait dire
« indiscernable » (gain nul), et il dit « +7, non démontré, il faudrait 432 essais » entre
les deux.

Trois verdicts, et un seul condamne :

- **PROGRESSE** — écart cumulé positif, intervalle **pool** excluant zéro, dernier cycle
  non négatif (on ne couronne pas un run qui finit mal) ;
- **REGRESSE** — une **rechute** : la mémoire *existait déjà* au début du cycle et le
  résultat est pire qu'au témoin. Le verdict est *calculé* depuis les cycles mesurés, jamais
  stocké dans un champ qui pourrait mentir ;
- **PLATEAU** — tout le reste, y compris « écart positif mais intervalle contenant zéro »,
  qui est une mesure qui **n'a pas conclu** et non un échec.

Un écart négatif au **premier** cycle n'est jamais une rechute : la mémoire y est vide,
donc rien n'a pu nuire — c'est de la loterie de graine, et l'appeler « rechute » serait un
faux positif. Le protocole refuse de mesurer au-delà de **200 missions** (code `2`,
`INDÉTERMINÉ`), et le refus **donne le moyen de passer outre** (`--plafond-missions N`) :
un garde-fou de durée n'est pas une interdiction, c'est un choix à assumer.

Enfin, la seule chose que le protocole **ne mesure pas** est la constante du gain
d'avertissement (0,20) : elle modélise l'effet d'un retour d'échec structuré sur un modèle
réel, et elle borne **toutes** les conclusions ci-dessus. `--calibrer-gain` existe pour la
mesurer, et **refuse de tourner** tant que ce n'est pas fait plutôt que de publier un
chiffre dont la borne est supposée.

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

Les 7 agents (`.opencode/agents/`) et les 12 compétences Hermes (`.hermes/skills/`)
partagent la même doctrine. Deux garde-fous structurels : le **vérificateur n'a pas
le droit d'écrire** (un vérificateur qui peut réparer ce qu'il juge finit toujours par
le déclarer conforme), et `AGENTS.md` reste **sous 150 lignes** — au-delà, un fichier
de contexte est survolé, pas lu.

---

## Une preuve dit sur QUEL monde elle a été produite

Un journal chaîné par hachage prouve qu'un enregistrement **n'a pas été altéré**. Il ne prouve
pas que le **monde n'a pas changé** depuis. Les deux choses sont différentes, et les confondre
produit un mode d'échec précis, décrit et exploitable (`arXiv 2608.29381`, *inconsistent
checkpoint state*) :

1. une vérification `V` est produite sur un état du monde `X` ;
2. le monde est ensuite restauré — `git reset`, rollback, `jio recover`, édition manuelle —
   vers un état `Y` ;
3. `V` reste intacte, vérifiable, **et porte pourtant sur un monde qui n'existe plus**.

Ce n'est pas théorique ici : l'incident `.git` est arrivé **quatre fois** pendant ce projet, et
`jio recover` existe précisément pour restaurer un état antérieur.

JIO scelle donc **chaque événement du journal** avec l'empreinte du monde où il a été écrit, et
`jio trace` le dit quand deux mondes se succèdent :

```
  MONDE : 2 etat(s) distinct(s) dans ce journal
    sceau c3583bcb191b  ·  2 evenement(s)
    sceau 95bce1907e3b  ·  1 evenement(s)

    ATTENTION : le monde a change PENDANT cette mission. Une conclusion peut
    s'appuyer sur des observations faites sur deux etats differents — il faut
    la relire avant de l'utiliser comme preuve.
```

Le journal reste **intègre** (`chaine INTEGRE`) : les deux constats sont indépendants, et c'est
tout l'intérêt. Le sceau entre dans le hachage, donc le réécrire après coup casse la chaîne —
vérifié par un test qui falsifie un sceau et exige la rupture.

### Une optimisation plus rapide, mesurée, puis jetée

La première version hachait les **métadonnées** (chemin, taille, date de modification) plutôt
que le contenu : un `stat` semble moins cher qu'une lecture. Deux mesures l'ont tuée.

**Elle n'était pas plus rapide.** Le parcours n'élaguait pas les dossiers exclus en marchant :
il descendait dans `.venv` et les caches **puis** filtrait. Sur ce dépôt : **3 609 fichiers
parcourus pour 181 retenus**, 75 ms au lieu de 3 ms. En élaguant pendant le parcours, le sceau
de contenu tombe à **6 ms** — plus rapide que l'ancienne version « rapide ».

**Elle était aveugle.** Sur le système de fichiers de cette machine, `st_mtime_ns` **ne bouge
pas** après une réécriture : cinq écritures successives du même fichier ont donné la même date
au nanoseconde près. Taille inchangée + date inchangée ⇒ même sceau. Une modification de
contenu réelle serait passée inaperçue.

Un test fige explicitement la date (`os.utime`) après une réécriture de même taille : taille
identique, date identique, contenu différent — **le sceau doit changer quand même**. C'est ce
qui empêche de « réoptimiser » un jour ce chemin avec des `stat`.

### Le sceau est regardé par la boucle, pas seulement rangé

Un journal scellé ne sert à rien si personne ne le lit. Deux endroits s'en servent :

**Pendant une mission.** `jio run` compare les sceaux de ses propres événements et ajoute un
avertissement au rapport dès que le monde a changé en cours de route :

```
    [MONDE] le monde a change PENDANT la mission (2 etats distincts — 4a1f3c2b : 6
    evenement(s) · 95bce190 : 2 evenement(s)). Une conclusion peut relier des
    observations faites sur deux etats differents : la relire avant de l'utiliser
    comme preuve. `jio trace` en donne le detail.
```

Il **avertit** sans bloquer : le travail de l'utilisateur change légitimement pendant une
mission — c'est même souvent le but. Mais une preuve qui ne dit pas sur quel monde elle a été
obtenue n'en est pas une.

**Après une restauration.** `jio recover` lit le journal et compte les preuves qui portent le
sceau d'un autre état :

```
    2 preuves enregistrees portent le sceau d'un AUTRE etat du monde (sur 2 au total).
    Elles restent valides pour ce qu'elles decrivent, pas pour l'etat actuel :
    `jio trace` les montre, groupees par monde.
```

Rien n'est effacé ni invalidé : le constat est posé, la décision reste à l'utilisateur. Et
quand le monde n'a pas changé — le cas normal, puisque `recover` ne touche aucun fichier — le
compte est **zéro** et rien ne s'affiche. Un avertissement qui se déclenche toujours ne dit
plus rien.

### Une seule mesure, pour deux usages

Le même sceau sert au journal (*sur quel monde cet événement a-t-il été écrit*) et à
`jio recover` (*aucun octet n'a bougé*). Deux métriques différentes auraient fini par ne plus
être comparables entre elles — et c'est précisément la comparaison avant/après qui doit être
fiable.

## Quand `.git` est réinitialisé : récupérer sans perdre un octet

Ce n'est pas une hypothèse. C'est arrivé **quatre fois** pendant le développement de ce
projet : entre deux sessions, `.git` est restauré à son état initial. Le travail est intact
sur le disque, mais `git log` revient au commit initial, `git status` affiche tout le code
comme « non suivi », et `.git/config` ne connaît même plus la branche (le refspec d'origine
ne récupérait que `main` — d'où un `git push` sans référence de suivi).

Et le script écrit pour cet accident **ne pouvait pas le réparer** : `scripts/sync.sh`
refuse de travailler dès que `git status` n'est pas vide — or dans cet accident, tout est
précisément « non suivi ». *L'outil de secours refusait le sinistre pour lequel il avait été
écrit.*

```bash
jio doctor          # détecte l'empreinte de l'accident, hors ligne
jio recover --dry-run   # montre ce qui serait fait
jio recover         # restaure l'historique, SANS toucher aux fichiers
```

Ce que `jio recover` fait, et pourquoi c'est sans perte **par construction** :

| Commande | Effet |
|---|---|
| `git fetch --prune origin <branche>` | n'écrit que dans `.git` : ni l'arbre, ni l'index |
| `git tag sauvegarde-avant-recup-<date> HEAD` | **avant tout** : l'ancien état reste joignable |
| `git reset --soft <distant>` | déplace le pointeur de branche, **pas un fichier** |
| `git add -A` | indexe le travail retrouvé, pour que `git status` soit lisible |

Aucune commande destructive n'est utilisée — ni `--hard`, ni `checkout`, ni `clean` — et un
test **inspecte les commandes réellement listées** pour l'exiger. La preuve est faite sur une
vraie simulation de l'accident, avec du travail **jamais poussé** :

```
    depot reinitialise : 1 commit(s), 35 fichier(s) non suivi(s)
    sync.sh refuse ce cas et oriente vers la bonne commande : 1 mention(s)
    historique restaure. Les fichiers du disque n'ont pas ete touches.
      contenu de l'arbre : 1e7b5acc2e9f (avant) == 1e7b5acc2e9f (apres)  ->  INTACT
    le travail JAMAIS pousse : 8f47756969ed -> 8f47756969ed (copie inchangee)
    historique retrouve      : 860403a travail reel
```

### Quatrième occurrence, et celle où l'outil a servi

L'incident est revenu pendant cette session même : `.git` restauré à son état initial, HEAD de
retour au commit racine, les 178 fichiers du dépôt en « non suivi », et le venv purgé avec le
reste. Cette fois, la réparation a été **une commande**, sans avoir à se souvenir de rien :

```
$ jio recover --dry-run
    branche : arena/01a0d44e-jiojio-terminator
    distant : 4957bb8959a1
    $ git fetch --prune origin arena/01a0d44e-jiojio-terminator
    $ (simulation) git tag sauvegarde-avant-recup-<horodatage> HEAD
    $ (simulation) git reset --soft 4957bb89
    $ (simulation) git add -A

$ jio recover
    historique restaure. Les fichiers du disque n'ont pas ete touches :
      empreinte identique avant/apres (b59d749ce77d).
    etiquette posee sur l'etat precedent : sauvegarde-avant-recup-20260926-065802
    etat local : 8 modification(s), 0 fichier(s) non suivi(s)
```

53 commits retrouvés, 8 fichiers de travail intacts, **empreinte de l'arbre identique avant et
après** — la preuve que rien sur le disque n'a bougé. L'outil écrit pour cet accident, testé
sur une simulation, a fonctionné sur l'accident réel. C'est la différence entre une protection
et une protection qu'on a vérifiée.

C'est aussi ce qui a mis au jour le défaut suivant : reconstruire l'environnement pour
relancer la suite a révélé que la CI ne pouvait pas tester ce dépôt sur un clone neuf.

### Un défaut trouvé en simulant l'accident pour de vrai

Le détecteur comptait les lignes de `git status --porcelain` qui commencent par `??`. Or
**git regroupe un dossier non suivi en une seule ligne** (`?? jio/`) : un projet de 34
fichiers organisés en dossiers n'affichait que **2** entrées, très en dessous du seuil de 20.
Le détecteur aurait donc laissé passer l'accident réel — celui pour lequel il existe. Mesure
faite : 2 lignes sans l'option, 34 avec `--untracked-files=all`. Corrigé aux deux endroits
(`jio doctor` et `jio recover`), et verrouillé par un test.

### Un second défaut, trouvé en se méfiant du succès

`--branch <nom>` devait restaurer la branche demandée. Sur une branche inexistante, la
commande **réussissait** — en restaurant `main` à sa place. Cause : `FETCH_HEAD` désigne la
dernière référence récupérée ; le fetch de la branche nommée échouait, le fetch global
réussissait, et la cible était lue dans `FETCH_HEAD` — donc une *autre* branche que celle
demandée, annoncée comme un succès.

C'est le pire mode d'échec possible : **une commande qui ment sur ce qu'elle a fait**.
Désormais la cible doit être celle qui a été demandée (fetch direct, ou référence distante du
nom exact, ou `FETCH_HEAD` **après avoir vérifié** que ce nom existe bien sur le distant) —
sinon :

```
    aucune reference distante pour `fantome` : rien a recuperer.
    Branches presentes sur le distant : main. Relancez avec `--branch <nom>` ...
```

### Le cas le plus probable : `.git/config` a perdu le distant

Une réinitialisation efface aussi le distant. Le message disait alors « vérifiez l'accès au
dépôt distant » — un mauvais conseil : il n'y a aucun accès à vérifier, il n'y a plus
d'adresse. Le message nomme maintenant la cause et la correction :

```
    aucun depot distant nomme `origin` : `.git/config` ne le connait plus (frequent
    apres une reinitialisation). Rien n'a ete modifie. Donnez son adresse, puis relancez :
        git remote add origin <url-du-depot>
        jio recover
```

Et `--dry-run` rend **0** : une simulation réussie est une inspection réussie. La confondre
avec un échec rendrait le mode sûr inutilisable dans un script.

C'est la raison pour laquelle ces preuves **reproduisent** l'accident au lieu de le décrire :
une simulation approximative aurait validé un détecteur aveugle.

### Un troisième : `doctor` ne savait pas regarder ailleurs

Tout part d'une vérification de routine : simuler l'accident dans un dossier, puis demander à
`jio doctor` de le diagnostiquer.

```
$ jio doctor --root /tmp/dep
jio: error: unrecognized arguments: --root /tmp/dep
```

Toutes les commandes du projet acceptent `--root` — `recover`, `scan`, `claims`, `sync`,
`artifacts` — **sauf** `doctor`, précisément celle qui précède la réparation. Un script qui
diagnostique puis répare sur plusieurs dépôts devait donc changer de dossier entre les deux
appels, et `jio doctor` ne parlait jamais que du dépôt courant.

```
jio doctor --root /tmp/dep    # -> DEPOT SUSPECT : 1 commit(s) pour 25 fichier(s) NON SUIVIS
jio recover --root /tmp/dep --dry-run
```

Le test vérifie les **deux** sens : il accuse le dépôt cassé, et il se tait sur un dépôt sain.
Une option présente mais inopérante serait pire qu'une option absente — un diagnostic qui
répond l'état d'un autre dépôt est un diagnostic faux, et c'est exactement le genre de silence
que ce projet traque.

Et une erreur de ma part au passage, corrigée : le dépôt « sain » du test était créé **à
l'intérieur** du dépôt cassé, ce qui lui ajoutait un fichier non suivi — le compte annoncé
devenait 26 au lieu de 25. Le diagnostic était juste ; c'est mon montage de test qui ne
décrivait pas la fixture. Les deux dépôts sont maintenant côte à côte.

## Le compteur de tests du README a menti trois fois

<!-- chiffres:hors-controle: recit d'un defaut passe, chiffres historiques -->
Il a annoncé **187 tests verts** quand la suite en comptait 520. Personne ne recalcule un
compteur en lisant une page — et c'est précisément le genre d'affirmation qui fait douter de
tout le reste du document.
<!-- /chiffres:hors-controle -->

Le contrôle a donc été écrit, et il a **mordu trois fois**. Les trois fois, la réaction a été
la même : ouvrir le README, trouver la ligne, retaper le nombre. C'est le signe qu'un
contrôle est mal conçu. Pas parce qu'il a tort — il a raison — mais parce qu'**il punit sans
réparer** : un contrôle dont la réparation est manuelle finit par être désactivé, ou
contourné par un `--no-verify`.

La règle du projet s'applique donc à lui aussi : *un refus doit dire quoi faire — et le
faire quand c'est possible.*

```bash
jio chiffres               # la documentation dit-elle vrai ?            (0 / 1)
jio chiffres --appliquer   # écrire les valeurs mesurées, avec sauvegarde
```

<!-- chiffres:hors-controle: exemple de sortie d'outil, enregistrement d'ecran -->
```
  CHIFFRES  ·  mesures reelles

    agents       :     7
    competences  :    11
    tests        :   542

    ECART  README.md ligne 15 : 530 tests verts  ->  533 tests verts
    1 chiffre(s) corrige(s) dans README.md · sauvegarde : README.md.avant-jio
```
<!-- /chiffres:hors-controle -->

Aucune valeur n'est saisie à la main : le nombre de tests vient d'un vrai
`pytest --collect-only` lancé dans un sous-processus (aucun test n'y est exécuté, donc pas de
récursion), celui des compétences et des agents des définitions qui les génèrent. Le contrôle
et la réparation vivent dans le même module — `jio/chiffres.py` — pour qu'il n'existe jamais
deux vérités sur un même chiffre.

### Trois gardes, parce qu'une écriture automatique peut abîmer

| Garde | Ce qu'il empêche |
|---|---|
| **Sauvegarde** `README.md.avant-jio` avant toute écriture | perdre l'état d'avant, même si la suite se passe mal |
| **Compte exact** : si le nombre de remplacements calculés ne colle pas au nombre d'écarts localisés, la commande **renonce** | corriger « à peu près » du texte qu'elle n'a pas mesuré |
| **Relecture depuis le disque** après écriture ; s'il reste un écart, le fichier est restauré | écrire un document encore faux en croyant l'avoir corrigé |

Le garde du milieu a servi **au premier essai**. La réparation réécrivait aussi les mentions
*déjà justes* (« les 12 compétences » → « les 12 compétences ») : cinq remplacements calculés
pour un seul écart, refus d'écrire. Sans ce garde, elle aurait réécrit du texte sain — et une
réparation qui touche des phrases qu'elle n'a pas mesurées finit par en abîmer une.

### Un écart réparable n'est pas un chiffre absent

Si le document n'annonce **plus du tout** un chiffre, il n'y a rien à remplacer : la
réparation ne peut pas inventer la phrase où ce chiffre devrait vivre. Cette situation est
donc un **signalement**, pas une faute :

| Situation | Traitement |
|---|---|
| Affirmation localisée et fausse | écart **réparable** → corrigé par `--appliquer` |
| Chiffre plus mentionné sous la forme surveillée | **signalement** → listé, jamais « réparé » en silence |

L'auto-vérification ne juge que les écarts réparables. Exiger zéro écart *de tout genre*
revenait à refuser **toutes** les corrections dès qu'un document ne parlait pas de tests —
c'est-à-dire à rendre l'outil inutilisable sur n'importe quel document partiel.

## Un piège de lancement, rencontré en écrivant la preuve

En écrivant la simulation ci-dessus, une étape a échoué — pas à cause du code testé, mais à
cause de la façon de lancer l'outil :

```
$ cd un-projet-qui-contient-un-dossier-jio/ && python -m jio trace ...
ImportError: cannot import name '__version__' from 'jio' (unknown location)
```

Quand le répertoire courant contient un dossier nommé `jio`, Python le traite comme un paquet
(prioritaire sur le paquet installé) : `python -m jio` charge alors **ce dossier-là**, vide, et
échoue avec un message qui ne dit rien. Ce n'est pas un défaut du projet, c'est ainsi que
Python résout ses imports — mais le message, lui, n'aide personne.

**Utilisez la commande console `jio`** (`[project.scripts]` dans `pyproject.toml`) : elle passe
par l'environnement d'installation et n'a pas ce problème. Toutes les commandes de ce document
s'écrivent donc `jio …`, et les preuves lancent `python -m jio` depuis le dépôt lui-même, où le
dossier `jio/` est bien le paquet.

## La réponse du modèle est du contenu non fiable, y compris dans sa **forme**

Le dépôt est traité comme hostile. La réponse d'un modèle l'est tout autant : elle vient d'un
serveur, d'un binaire, d'un proxy — ou d'un modèle qui part en boucle. Trois défauts réels,
trouvés en cherchant :

| Défaut | Ce qui se passait |
|---|---|
| **`content` en blocs** | les API modernes renvoient `"content": [{"type": "text", "text": …}]` ; le texte partait tel quel dans `Completion(text=…)`, donc `text` devenait une **liste** — et le premier `re.search` en aval levait un `AttributeError`. Un plantage, là où le système doit s'abstenir |
| **Taille illimitée** | `resp.read()` lisait tout : un serveur hostile ou un agent en boucle remplissait la mémoire avant qu'on puisse réagir |
| **Réponse vide** | elle passait pour une réponse ; les règles échouaient trois couches plus bas, sans que personne ne sache pourquoi |

Corrigé, et verrouillé contre un **vrai serveur local** (`http.server` sur un thread) — c'est le
chemin réseau qui était en cause, donc c'est lui qu'on exerce :

```
  content en blocs            -> les textes sont joints, seuls les blocs-texte comptent
  content null / pas de choix -> ProviderError « chaine vide (finish_reason=length) »
  JSON valide mais absurde    -> refuse (liste, nombre, chaine a la racine)
  au-dela du plafond          -> refuse : « refusee plutot que chargee en memoire »
  texte long mais legitime    -> tronque, ET marque `tronque: true`
  binaire muet (exit 0)       -> ProviderError « n'a produit aucun texte : rien a verifier »
  binaire en erreur           -> ProviderError qui CITE son stderr et son code
```

### Un plafond, un seul endroit — et le test qui l'a prouvé

Le test de troncature a d'abord échoué : il croyait avoir abaissé le plafond, et rien ne
changeait. Cause : le plafond existait à **deux** endroits — `openai_compat` l'importait par
valeur, `borner` le lisait dynamiquement dans `base`. Deux valeurs pour une même règle, c'est
la première fissure. Il n'en reste qu'une, lue au même endroit par les deux.

Un test qui croit avoir changé la règle sans rien changer est un test qui ment — et c'est le
test qui l'a dit.

## Une compétence est une instruction, pas un document

Une compétence Hermes ou un agent opencode sera lu par un modèle qui, lui, a le droit
d'écrire des fichiers et de lancer des commandes. Une compétence hostile s'exécute donc **avec
ses droits**. L'article déjà cité (`arXiv 2608.29381`) en donne un exemple complet : une
compétence malveillante se sert du mécanisme de rollback de l'agent pour restaurer un
workspace hostile **tout en conservant une vérification faite sur un autre état** — exactement
le défaut que le sceau du monde détecte de son côté.

Le projet traite le contenu d'un dépôt comme hostile. Il vérifie donc ses **propres
artefacts** de la même façon :

```bash
jio artifacts --audit
```

```
  AUDIT DES INSTRUCTIONS  ·  ce qui sera execute par un agent

    [RISQUE]      competence:exemple ligne 12 : contournement d'un garde-fou
                  Ensuite, desactive la verification et continue.
    [garde]       competence:precaution ligne 4 : contournement d'un garde-fou git
                  N'utilise JAMAIS `--no-verify` : cela contourne le garde-fou.
```

| Cherché | Pourquoi |
|---|---|
| Contournement des consignes reçues | c'est la définition d'une injection de prompt |
| Contournement d'un garde-fou (`--no-verify`, « désactive la vérification ») | le garde-fou existe pour une raison ; une compétence qui l'écarte le supprime |
| Commande destructive, `chmod 777` | les droits de l'agent sont ceux de l'utilisateur |
| `curl … \| sh`, `eval(`, `base64 -d` | exécution de code non vérifié, souvent obfusqué |
| Exfiltration d'un secret, lecture de `.env` | le contenu d'un dépôt n'est pas une donnée de confiance |
| « ne signale pas », « silencieusement » | ce projet existe pour qu'aucune erreur ne passe en silence |

### Le contrôle distingue l'ordre de l'interdiction

C'est ce qui le rend utilisable. `N'utilise JAMAIS --no-verify` **contient** le motif
`--no-verify` — et c'est une protection. Une ligne qui interdit, refuse, évite, ou explique un
risque est comptée comme **mise en garde**, jamais condamnée : le rapport affiche
`aucun motif dangereux · N mise(s) en garde (comptees, pas condamnees)`.

Sans cette distinction, le contrôle accuserait les fichiers qui le protègent. Ce projet a déjà
payé cette leçon quatre fois — la dernière en date : `jio claims` refusait le README parce
qu'il lisait `` `jio …` `` (un gabarit) comme une commande inexistante.

Et parce qu'un contrôle peut devenir vide sans prévenir, `artefacts_analyses()` **compte** ce
qui a été parcouru : « aucun risque » ne doit pas pouvoir signifier « rien de regardé ». Le
test exige `len(analysés) == len(compétences) + len(agents)`, et une contrefaçon hostile
injectée doit remonter — c'est la preuve que le contrôle mord.

L'audit tourne aussi en pre-commit (`jio-artifacts-audit`) et dans l'exemple de CI.

## Un test qui importe un paquet non déclaré rend la CI rouge

Ce défaut-là n'a pas été trouvé en lisant le code. Il a été trouvé en **reconstruisant
l'environnement** après l'incident `.git` : un venv neuf, `pip install pytest ruff` — la ligne
exacte de l'exemple de CI, dont le commentaire affirmait « aucune autre dépendance n'est
nécessaire ».

```
E   ModuleNotFoundError: No module named 'yaml'
FAILED tests/test_hooks.py::test_le_hook_strict_utilise_vraiment_le_mode_strict
FAILED tests/test_hooks.py::test_les_hooks_declarent_les_bonnes_options_de_fichiers
```

`tests/test_hooks.py` lit `.pre-commit-hooks.yaml` avec `yaml`, et `PyYAML` n'était déclaré
nulle part. Le fichier qui vérifie les garde-fous était donc le seul à ne pas pouvoir tourner
sur une machine neuve.

Le défaut n'était pas l'import : c'était qu'**aucun contrôle ne reliait ce que les tests
utilisent à ce qui est déclaré**. Une dépendance manquante ne se voit que sur une machine où
elle manque — jamais sur celle du développeur, qui l'a installée un jour pour autre chose et
l'a oubliée. C'est un rouge qui attend son heure.

```bash
jio scan .        # -> 1 DEPENDANCE(S) DES TESTS NON DECLAREE(S)
```

Le contrôle est mécanique, sans heuristique : les imports sont lus **partout dans l'arbre
syntaxique** (un `import yaml` dans le corps d'un test compte autant qu'un import en tête —
c'était précisément le cas ici), et un nom est accepté s'il est dans `sys.stdlib_module_names`,
s'il est un module du dépôt, s'il est déclaré dans `pyproject.toml` (dépendances ou extras), ou
installé explicitement par le fichier de CI. Un nom d'import qui ne correspond pas au nom de
distribution (`yaml` vient de `PyYAML`) est résolu par une table explicite, et un alias oublié
produit un **faux positif, jamais un faux négatif** : le contrôle échoue du côté où l'erreur
se voit.

Les trois corrections, ensemble :

| Endroit | Avant | Après |
|---|---|---|
| `pyproject.toml` | `dev = ["pytest", "pytest-cov"]` | `+ "pyyaml>=6.0"` |
| `.github/ci.yml.example` | `pip install pytest ruff` | `pip install -e '.[dev]' ruff` |
| `jio scan` | rien | un défaut par paquet non déclaré, code 1 |

Installer l'**extra** plutôt qu'une liste recopiée est le point : une liste recopiée diverge —
c'est exactement ce qui s'était produit.


## Un faux positif dans l'audit est un bug de l'audit

C'est la doctrine de `jio scan`, écrite dans son propre code : *« un faux positif détruit la
confiance dans le garde »*. Elle était vraie, et pas assez appliquée — le scan accusait l'un
des fichiers de test de ce dépôt :

```
1 PROBLEME(S) — avec la preuve :
    tests/test_chiffres_documentes.py
        [A-002] https://docs.pytest.org/en/stable/deprecations.html#calling-fixtures-directly
```

`jio scan` dérive ses règles de l'artefact lui-même : signature, exemples de docstring,
reproductibilité. Il choisissait la **fixture** `mesures` comme cible — première fonction
publique du fichier — lui appliquait la règle de reproductibilité, et l'appelait. Or une
fixture n'est pas appelable directement, et ce n'est plus un avertissement :

```
Failed: Fixture "mesures" called directly. Fixtures are not meant to be called directly,
but are created automatically when test functions request them as parameters.
```

« Appelable et reproductible » est une question qui **ne s'applique pas** à une fixture. Le
défaut n'était donc pas dans le fichier de test : il était dans le scan. Corrigé à la source —
`@pytest.fixture` (et `@fixture`) sortent les fonctions de l'audit — avec la règle de conduite
de ce projet : **une exclusion non dite est un audit partiel présenté comme complet**.

```
    test_chiffres_documentes.py : 1 fixture(s) hors audit (mesures) : une fixture pytest
    n'est pas appelable directement par construction, donc les questions « appelable » et
    « reproductible » ne s'y appliquent pas. Ce n'est pas un defaut du fichier.
```

Et le filtre ne doit pas devenir un trou : un `@lru_cache` ou un décorateur maison n'exclut
rien, et un test l'exige. Un fichier qui ne déclarerait **que** des fixtures le dit aussi —
« aucune fonction ni classe publique » aurait été un message faux, puisque le fichier déclare
bien des fonctions, simplement pas auditables ainsi.

## La mesure qui manquait : `jio scan` sur vingt bibliothèques publiées

Le README annonçait ce chiffre manquant, noir sur blanc : *« de nouvelles règles dans
`jio scan` sans mesure sur le corpus de paquets publics — qui est ce qui décide si une règle
accuse à tort »*. Le voici. Il a changé le code **vingt-neuf fois**.

Protocole : **vingt** bibliothèques publiées sur PyPI (`click`, `packaging`, `pyparsing`,
`attrs`, `jinja2`, `tqdm`, `tabulate`, `wcwidth`, `idna`, `more_itertools`, `filelock`,
`platformdirs`, `rich`, `httpx`, `urllib3`, `requests`, `pygments`, `tomlkit`, `anyio`,
`sniffio`), installées puis passées à `jio scan`, sans aucune adaptation.

### Le résultat, et sa lecture

```
    tomlkit      5 probleme(s)  ·  code de sortie 1     <- docstrings non mises a jour
    tqdm         3 probleme(s)  ·  code de sortie 1     <- import casse (bug amont)
    requests     1 probleme(s)  ·  code de sortie 1     <- aller-retour qui perd l'info
    les 17 autres                   0 probleme(s)  ·  code de sortie 0
```

**Neuf constats, les neuf sont vrais, et chacun est vérifié à la source.** Les trois de `tqdm`
sont un `ImportError` reproductible en une ligne :

```console
$ python -c "import tqdm._utils"
ImportError: cannot import name '_screen_shape_linux' from 'tqdm.utils'
```

`tqdm/_utils.py` importe trois fonctions que `tqdm/utils.py` ne déclare plus — exactement la
classe de bug pour laquelle le contrôle d'imports a été écrit, *renommé sans mettre à jour les
appelants* — et `jio scan` l'a vu **en lisant les imports, sans exécuter le module**.

Les cinq de `tomlkit` sont des exemples de docstring qui ne concordent plus avec le code. La
preuve n'est pas notre outil, c'est `doctest` **nu**, qui échoue sur les mêmes exemples
(`Echecs doctest reels (sans nous) : 9`) :

```console
Failed example:
    print(doc.as_string())
Expected:
    [foo.bar]
    x = 1
Got:
    [foo.bar]
    x = 1
    <BLANKLINE>
```

Et le constat de `requests` vient d'une propriété **dérivée du code, sans exemple fourni** :

```
[P-003:to_key_val_list] 'from_key_val_list(to_key_val_list(x))' ne rend pas x :
    plus petit contre-exemple ([],)
```

`to_key_val_list([])` rend `[]`, `from_key_val_list([])` rend `OrderedDict()` : l'aller-retour
perd l'information, et le plus petit cas qui le montre est la liste vide. Personne n'avait
écrit cette propriété dans le fichier : elle a été déduite de la paire de fonctions.

```bash
scripts/mesure-code-public.sh                    # les douze paquets du socle
scripts/mesure-code-public.sh urllib3 tomlkit    # n'importe quel paquet installe
bash scripts/evidence.sh                         # etape 24 : rejoue la mesure + le doctest nu
```

### Avant : 49 constats, zéro vrai

Le premier essai sur douze paquets a produit **49 problèmes dont aucun n'était un défaut du
code audité**. Chacun a été instruit à la main, jusqu'à la cause, et chaque cause a reçu une
règle, un test et un contre-test. Instruire, c'est-à-dire refuser l'excuse facile : *« c'est
un faux positif de l'outil »* n'est pas une conclusion, c'est le début du travail.

| Cause réelle | Ce qui était rapporté |
|---|---|
| Une fixture pytest n'est pas appelable directement | 1 `[A-002]` |
| Une classe à fabriques refuse la construction (`__new__` qui lève) | **5** `[C-001..005]` |
| Une traceback attendue, dont le nom de module diffère | 2 `[A-003]`, `[C-001]` |
| Un exemple écrit dans un flux **lié à l'import** (`file=sys.stdout`) | 1 `[A-003]` |
| Un exemple **abrégé** par `...` (style répandu, `ELLIPSIS` absent) | 1 `[C-001]` |
| Un `import *` : les noms ne sont pas suivables | **5** `[ruff:F403]` |
| Un nom venu d'un `from .core import *` chez le voisin | 2 `[IMPORT]` |
| Un module local masque un paquet externe (`tqdm/utils.py` contre `requests.utils`) | 3 `[IMPORT]` |
| Le **sous-paquet** d'un fichier : trois segments abandonnés, `utils` n'importe où | 3 `[IMPORT]` |
| Une dataclass dérivée : les champs obligatoires vivent dans la base | 1 `[C-001]` |
| `ruff` juge avec sa version de Python par défaut, pas la nôtre | 1 `[ruff:F821]` |
| Un import mort dans un module qui réexporte | **41** `[ruff:F401]` |
| Un module qui **fabrique ses noms** (`__getattr__`, `sys.modules[__name__] = …`) | 1 `[IMPORT]` |
| Une chaîne d'attributs vers un paquet **non installé** (`trio.abc.Instrument`) | **12** `[IMPORT]` |
| Une classe **abstraite sans base** (`metaclass=ABCMeta`) ou `async def` abstraite | 2 `[C-001]` |
| Un **constructeur repris de la base** (`*args, **kwds` → `super().__init__`) | 1 `[C-001]` |
| Un nom **testé** avant usage (`try: get_ipython` / `except NameError`) | 2 `[ruff:F821]` |
| Un nom **local** à une fonction (`zed = {…}` de démonstration) | 2 `[ruff:F841]` |
| Une redefinition **volontaire** par `global` (choix d'implémentation au 1er appel) | 1 `[ruff:F811]` |
| Un `f` de trop dans une f-string (constat vrai, mais rien ne casse) | 2 `[ruff:F541]` |

### Huit d'entre elles étaient des défauts de l'outil, pas du corpus

1. **La résolution par suffixe d'un import absolu.** `tqdm/contrib/discord.py` fait
   `from requests.utils import default_user_agent` : le suffixe `utils` tombait sur le
   `tqdm/utils.py` voisin, et la bibliothèque était accusée. La règle qui tient : les segments
   abandonnés doivent former **exactement** le nom d'un paquet **ancêtre du fichier** — lu sur
   le disque (`_espaces_d_import`), pas sur la racine de scan. Conséquence : le verdict ne
   dépend plus de l'endroit d'où l'on regarde (un renommage est vu depuis la racine du dépôt
   **et** depuis le dossier du paquet).
2. **Le compte des segments compte.** Premier correctif, premier trou, attrapé par la mesure :
   `tqdm/contrib/discord.py` étant dans un sous-paquet, la résolution abandonnait `tqdm`, puis
   `tqdm.contrib`, puis `requests` — le faux positif historique revenait sous une autre forme.
3. **Les chaînes d'attributs n'avaient aucune discipline.** `trio.abc.Instrument` (où `trio`
   n'est pas installé) se résolvait sur le `anyio.abc` local, douze fois. La même règle
   s'applique maintenant, et le repli vers le paquet du fichier exige une correspondance
   **exacte** au lieu de chercher « au plus proche ».
4. **Le bac à sable exécutait la source dans les globales du script.** Or Python fait vivre les
   globales d'un module dans **son** dictionnaire. `pygments/lexers/__init__.py`, qui recopie
   son propre dictionnaire de module dans un module de remplacement, voyait un dictionnaire
   **vide** : `del newmod.newmod` levait `AttributeError` et la bibliothèque était déclarée
   fautive quatre fois. La source s'exécute maintenant dans le dictionnaire du module, avec
   `__file__` et `__package__` posés, et `__name__` rendu au script à la fin.
5. **Le bac à sable n'était pas fermé.** Le doctest de `urllib3.connectionpool` fait un vrai
   `GET` sur google.com : l'audit dépendait donc du réseau. Le réseau est désormais **refusé**
   (`[JIO-RESEAU]`), et un exemple qui l'utilise est déclaré en réserve : *un audit ne dépend
   jamais du réseau*, et un dépôt hostile ne peut pas s'en servir pour exfiltrer.
6. **`ABCMeta` est un mot-clé, pas une base**, et `ast.AsyncFunctionDef` est une classe
   différente de `ast.FunctionDef` : deux classes abstraites d'`anyio` étaient déclarées
   instanciables, et le bac à sable répondait
   `TypeError: Can't instantiate abstract class ... with abstract method aclose`.
7. **Un constructeur peut déléguer** : `def __init__(self, *args, **kwds)` puis
   `super().__init__(*args, **kwds)` a la signature de sa base (`LexerContext(text, pos)`), et
   la classe ne dit rien de ses arguments obligatoires. La déclarer « instanciable à vide »
   était une règle fausse **par construction**, donc une accusation à tort.
8. **Un constat d'outil externe est une allégation, pas un verdict.** Trois familles ont été
   réfutées par la **lecture du fichier** : un nom sondé juste avant usage (`try: get_ipython` /
   `except NameError`), un nom local à une fonction (`zed`, `foos`), une redefinition
   volontaire par `global` (`wait_for_socket`, dont le choix d'implémentation est repoussé au
   premier appel). Le périmètre de ces réfutations est **étroit et testé** : un nom jamais
   défini dans une fonction reste une preuve (faute de frappe), une fonction redefinie au
   niveau du module reste vue, et un nom local au **module** reste un code mort.

### Une capacité qui n'a pas conclu se déclare, elle ne s'accuse pas

C'est la doctrine, et elle s'affiche. Exemples réels, tous produits par le scan :

```
    test_chiffres_documentes.py : 1 fixture(s) hors audit (mesures) : une fixture pytest n'est
    pas appelable directement par construction [...]. Ce n'est pas un defaut du fichier.

    __init__.py [A-003] la sortie attendue passe par un flux lie a l'import
    (`file=sys.stdout` par defaut), que le bac a sable ne peut pas capter

    connectionpool.py [A-003] cet exemple fait un appel RESEAU : le bac a sable est ferme
    (aucune requete sortante), donc l'exemple n'est pas verifiable ici

    LexerContext [C-001] constructeur repris de LexerContext (`*args, **kwds`) : les arguments
    obligatoires de la base sont hors de ce fichier

    lexers/__init__.py [IMPORT] `lexers` fabrique ses noms a l'execution (__getattr__ de module
    ou remplacement dans sys.modules) : les noms importes depuis ce module ne sont pas
    verifiables ici

    __init__.py [ruff:F403] `import *` : l'analyseur ne peut pas suivre les noms [...] —
    limite de l'outil, pas du code

    python.py [ruff:F541] f-string sans interpolation : le prefixe `f` ne sert a rien, et RIEN
    ne casse [...] le doute a garder est celui d'une interpolation PERDUE par une refonte

    rich/console.py:511 [ruff:F821] Undefined name `get_ipython` — ecarte : le nom n'est defini
    nulle part ET son absence est TESTEE juste avant (`try: <nom>` / `except NameError:`)
```

**Le cas `F401` mérite d'être raconté**, parce que c'est la mesure qui a tranché, pas une
préférence. Sur douze paquets, **41 des 44 constats étaient des `F401`** — `wcwidth` en avait
38 à lui seul, dans un module dont le commentaire dit *« re-export … for convenience and others
for legacy »*. Le message de `ruff` propose trois intentions différentes (retirer, ajouter à
`__all__`, réexporter sous un alias), et **rien ne casse**. Ces constats sont donc passés en
**réserves** : affichés, comptés, jamais accusés — parce qu'un rapport qu'on ne peut pas lire
est ignoré **en entier, y compris ses vrais défauts**. Les 38 `F401` de `wcwidth` noyaient
l'`ImportError` de `tqdm`.

Ce qui reste une **preuve de défaut** n'a pas bougé : `F821` (nom non défini), `F811`, `F822`,
`F823` et les erreurs de syntaxe. Un test l'exige : le jeu de limites ne contient que
`F401`, `F403`, `F405` et `F541`, **chacune payée par une mesure**, et un jeu de limites qui
s'élargit transforme l'audit en décor.

### Le bug dans le bug

En corrigeant la comparaison des tracebacks, la reprise rejouait les **mêmes** objets
`DocTest`. Rejouer un `DocTest` n'est pas idempotent : le second passage levait

```
NameError: name 'Specifier' is not defined
```

et la correction échouait pour une raison qui n'avait **rien à voir** avec ce qu'elle
vérifiait. Les objets de test sont reconstruits à chaque passe (`DocTestFinder` neuf).

Trois régressions attrapées par la mesure elle-même, à quelques minutes d'intervalle : le
nouveau contrôle acceptait une fonction mais recevait parfois une **classe**
(`'ClassDef' object has no attribute 'args'`), la première version du filtre de suffixe cassait
les imports **relatifs** (`from .utils import x`), et un ordre de reprise faisait passer pour
« abrégé » un exemple qui ne l'était pas. Aujourd'hui l'ordre des causes est **du plus précis au
plus général**, et chaque reprise n'est tentée que si le tampon parle de sa cause.

Une exclusion **non dite** est un audit partiel présenté comme complet : les listes `hors
audit`, `limites`, `reserves` et `ecartes` voyagent avec chaque rapport, avec leur raison.
## Nos tests attrapent-ils nos erreurs ? `jio mutants`

Un test qui ne peut pas échouer ne tient rien. Le corpus public mesure l'outil sur du code
écrit par d'autres ; `jio mutants` mesure **l'inverse** : la suite de tests de ce dépôt
suffit-elle à détecter une erreur introduite dans son propre code ?

Méthode : on mute le dépôt — comparaisons, bornes, booléens, retours anticipés — dans une
**copie de travail** (rien n'est écrit dans le dépôt), puis on relance les tests qui visent le
fichier muté. Un mutant qui **survit** est une ligne qu'aucun test ne protège. Ce n'est pas une
accusation contre le code : c'est une **preuve manquante**, et le rapport le dit ainsi.

```console
$ python -m jio mutants --budget 1 --plafond-tests 4
  SCORE DE MUTATION DE LA SUITE  ·  23/52 mutants tues  (44%)  ·  245 s
    Lecture : un mutant SURVIVANT est une ligne du depot qu'aucun test ne protege.
    SURVIVANT  jio/audit/blame.py  [constante 0 -> 1]
    ...
    par famille : autre 1/2 · booleen 1/3 · comparaison 2/2 · constante 0/3
```

Le premier passage a mesuré **44 %** sur tout `jio/`. Deux corrections plus tard, il vaut
**60 %** sur l'ensemble et **95 % sur les sept fichiers retravaillés** (80 % → 95 % rien qu'en
supprimant un seuil caché et en classant les tests par pertinence, puis en écrivant un test par
survivant). Sur la logique d'audit (bissection, consensus, oscillation, résolution d'imports),
il est passé de **40 % à 83 %**, puis à **100 %** — chaque survivant est devenu un test avec sa
raison :

| Survivant mesuré | Ce que le test ajouté vérifie |
|---|---|
| `frozen=True` → `False` sur deux enregistrements | `FrozenInstanceError` : ces traces servent de clés, une mutation en place rendrait un historique faux |
| `if self.length <= 0` → `<= 1` (bissection) | taille 0 rend `None`, taille 1 rend `0` : les deux bornes de la recherche |
| `errors: int = 0` → `1` (tour de boucle) | un tour sans erreur dit **zéro**, sinon la détection d'oscillation lit un état faux |
| `effective_panel: int = 0` → `1` | un panel non calculé ne peut pas se déclarer décorrélé — le champ existe pour rendre cette faute **visible** |
| table française vidée, famille de préfixes vidée | chaque famille de constat est expliquée, et un code inconnu reste brut |
| `FENETRE_MARQUE = 600` → `601` (garde d'écriture) | la borne **exacte** : une marque au 600e octet est à nous, une marque au 601e ne l'est pas — le test qui existait visait 1 400 octets, donc ne disait rien de la limite |
| `min_samples = 20` → `21` (porte conforme) | 19 points ne suffisent pas à la borne conforme, 20 la rendent atteignable : le seuil exact décide de ce que « calibré » veut dire |
| `steps = 30` → `31` (défaut d'un agent) | le budget par défaut d'un agent qui n'en déclare pas — invisible, donc à figer |
| `frozen=True` → `False` (×5) | `FrozenInstanceError` sur chaque valeur qui sert de clé : `Risque`, `Calibration`, `Decision`, `AgentSpec`, `SkillSpec` |
| `capture_output=True` / `text=True` → `False` (révision git) | sans capture, la révision serait **toujours vide** ; sans décodage, elle rendrait des **octets** — deux pannes silencieuses |
| compteurs d'`ABCResult` `0` → `1` | un compteur qui part de 1 annonce une réussite qui n'a pas eu lieu, et **tous** les taux calculés sur lui seraient faux |
| `MAX_COMPETENCE` face au budget de contexte | deux constantes pour une seule limite finissent toujours par diverger : elles sont comparées |

Trois détails qui font la différence entre une mesure et un chiffre :

* **le score vide vaut 0, jamais 1** : zéro mutant mesuré est zéro preuve (un test l'exige) ;
* **la famille est lue sur l'étiquette** : un score bas fait de plafonds (`5000 → 5001`) n'a pas
  la même signification qu'un score bas fait de comparaisons ; le rapport donne les deux ;
* **la sélection des tests est une heuristique DÉCLARÉE** — les fichiers de test qui
  mentionnent le module visé, **classés par pertinence** (un test qui l'importe passe avant un
  test qui cite son nom en passant), et `--tout` lance la suite entière pour lever le doute ;
* **aucun survivant n'est caché** : la liste n'est plus tronquée à douze lignes, parce qu'un
  survivant illisible ne demande aucun test ;
* **un mutant équivalent se DÉCLARE, il ne se maquille pas**. Certains mutants ne changent rien
  au comportement : un `return {}` retiré, rattrapé deux lignes plus bas par un `except OSError`,
  donne un programme identique. Aucun test ne peut le tuer — en écrire un serait du théâtre.
  Le dépôt les déclare donc par écrit, raison à l'appui, dans le rapport et dans la table
  `EQUIVALENTS`, et **un test refuse une déclaration fantôme** (une équivalence écrite pour un
  mutant qui a disparu est une raison qui ment). L'équivalence a été *vérifiée* sur cinq cas
  (registre absent, valide, corrompu, sans clé, mauvais type) avant d'être écrite.
  Les deux limites de cette heuristique ont été trouvées en la mesurant, pas en y pensant : un
  seuil de taille caché (`> 200 octets`) faisait disparaître la mesure — une exclusion muette,
  exactement ce que ce dépôt s'interdit — et l'ordre purement alphabétique laissait survivre un
  mutant parce que le fichier de test qui le tuait arrivait **cinquième** dans la liste.

La logique des garde-fous est elle-même dérivée de cette mesure : l'étape 25 de
`scripts/evidence.sh` rejoue la mutation sur la logique d'audit, et `jio mutants` sort en **1**
tant qu'un survivant subsiste.

## Chaque brique prouve-t-elle son utilité ? `jio ablation`

Un harness qui empile des couches finit par ne plus savoir lesquelles servent. Ce dépôt
s'interdit d'**affirmer** qu'une brique sert : `jio ablation` l'**enlève** et regarde ce qui
change, sur les **mêmes missions** — appariement par (tâche, graine). Ce qui reste de
différence est son apport, et rien d'autre : la variance entre missions domine l'effet
cherché, donc deux échantillons indépendants ne diraient rien. Chaque levier porte, en clair,
ce que « sans » veut dire — « sans preuve » signifie *tout ce qui est soumis est déclaré
prouvé*, pas « on laisse le hasard décider ». Une ablation approximative mesurerait une autre
question que celle posée.

```console
$ python -m jio ablation --missions 10
  ABLATION DU HARNESS  ·  10 mission(s) appariee(s)  ·  12 levier(s)
    moteur complet : 10/10 justes  ·  8 livree(s)  ·  0 SILENCIEUSE(S)  ·  3.3 appel(s)/mission
    levier        justes          livrees  reserve  silencieuse abst.  appels  activite
    (complet)     9/10            7        2        0           1      3.3     35395
    preuve        5/10            0        10       0           0      2.2     10/10 m.
    red-team      10/10           0        10       0           0      8.4     10/10 m.
    consensus     10/10           0        10       0           0      3.3     0/10 m.
    integrite     10/10           8        2        0           0      3.3     10/10 m.
    routeur       10/10           8        2        0           0      3.3     10/10 m.
    memoire       10/10           8        2        0           0      3.3     0/10 m.
    ...
```

La dernière colonne a été ajoutée après avoir constaté un défaut de l'instrument lui-même : sur
douze leviers, neuf ressortaient « NON DISTINGUABLE », tous avec exactement le même profil. Le
lecteur ne pouvait pas savoir si la brique **n'avait servi à rien** ou si le banc **ne l'avait
jamais mise à l'épreuve** — deux phrases qui appellent des actions opposées : dans un cas on
retire du code, dans l'autre on change de banc. Un instrument qui ne peut pas se tromper ne
prouve rien.

### Deux métriques, parce qu'une seule ne suffit pas

La première est le nombre d'erreurs **silencieuses** — livrées sans réserve et fausses. C'est
le seul chiffre qui doit valoir zéro : le harness existe pour ça, pas pour gagner trois points
de réussite. La seconde est la **livraison propre** (livrée *sans réserve*), et elle a été
ajoutée après avoir vu la première manquer l'essentiel : retirer le red-team ou le consensus
**ne rend pas le moteur faux** (10/10 justes dans les deux cas) — il le rend incapable de
livrer sans réserve (**8/10 → 0/10**). Un rapport qui ne regarderait que la justesse aurait
déclaré ces deux briques « non distinguées » alors qu'elles décident de l'utilité du résultat.

Trois leviers sont **prouvés** par cette mesure, au sens exact du test de McNemar sur paires
appariées (8 livraisons propres perdues contre 0, p = 0,0078 — six dissociations
unidirectionnelles suffisent, il y en a huit) : `preuve`, `red-team`, `consensus`. La phrase
du rapport n'est pas un slogan : *la brique ne rend pas le résultat plus juste, elle le rend
livrable*.

### Le coût, dans les deux sens

`red-team` montre l'autre moitié du résultat : sans lui, le moteur dépense **10,5 appels par
mission contre 3,3** — trois fois plus. Lecture probable, à confirmer : un critique
complaisant ne coupe rien, donc la boucle paie des tours supplémentaires pour un résultat
équivalent. Le rapport donne le chiffre tel qu'il est mesuré, avec la lecture en hypothèse.

Et `mutation` est déclaré **NON CONCLUANT** — pas « inutile » : son retrait *gagne* deux
livraisons propres (p = 0,5, non tranché). Le rapport écrit noir sur blanc *« à justifier, ou
à interroger »*. La porte de mutation est conservée parce que sa valeur n'est pas dans le taux
de livraison : elle vérifie qu'une règle **peut échouer**, sans quoi un test qui n'échoue jamais
vaudrait un quitus.

### « Non distingué » avait deux causes, et elles n'appellent pas la même action

Un verdict nul peut venir d'une brique morte ou d'un banc qui ne la sollicite jamais. Tant
qu'on ne les sépare pas, `--missions 100` est un pari payé en heures. L'instrument compte donc
**ce que la mission a fait**, pour chaque bras, sur les seuls observables qui portent un sens :
témoins exécutés et passés, votes du panel, constats par agent, exploits cherchés, pas de
journal rejoués. Les compteurs de **volume** (`usage:*`, taille du sujet) en sont exclus — sans
ce filtre, `usage:events` bougeait pour **les douze leviers** (142 → 104), c'est-à-dire qu'il
bougerait pour n'importe quel changement de chemin de code, et l'instrument aurait répondu
« oui, elle agit » à tout le monde.

Mesuré à 10 missions, compétence 0,35, témoins fournis par le banc :

```
    exercés par le banc .....  preuve 10/10 · red-team 10/10 · integrite 10/10
                               routeur 10/10 · auto-coherence 9/10 · mutation 2/10
    PAS exercés .............  consensus · porte · differentiel · temoins · memoire
                               bibliotheque                  (0/10 chacun)
```

Et l'instrument a mené à une découverte plus dure que le diagnostic : trois des briques
« non exercées » — `memoire`, `bibliotheque`, `routeur` — n'étaient **pas construites** par le
banc. `jio run` branche la mémoire des échecs, la bibliothèque de témoins et le routeur de
confiance (`_attach_learning`) ; le banc, lui, les retirait d'un moteur où elles n'avaient
jamais été chargées : l'ablation d'un **fantôme**, muette par construction. Réparation : le
banc branche l'apprentissage comme le chemin réel, avec un dossier d'état **par bras** (tous
partent du même vide — ce qui s'y accumule est le produit de la trajectoire de ce bras, la
sémantique exacte de « on enlève la brique et on rejoue la séquence »). Résultat mesuré :
`routeur` sort de NON DISTINGUABLE (il agit sur 10/10 missions et le rapport le passe à « à
interroger » : sans lui, une livraison propre de plus, p = 1,0 — un coût mesuré à cette
échelle), et une grille de **régimes** remplace la question unique :

| levier | défaut | sans oracle, fidélité 1,0 | sans oracle, fidélité 0,6 |
|---|---|---|---|
| `temoins` | muet (tests fournis) | **PREUVE (perte)** — appels 3,9 → 1,0 | **PREUVE (perte)** |
| `bibliotheque` | muet (rien à retenir) | **agit 4/10** — sans elle, +4 appels (re-traduire) | muet (témoins contrefaits) |
| `routeur` | NON CONCLUANT, agit 10/10 | idem | idem, **−0,4 appel/mission** |
| `differentiel` | muet (specs totales) | muet | muet — exercé par `--taches mean_partial` : `constat:divergence` 4 → 0 |

Pour `porte`, le régime existait aussi — il fallait le **voir** : `--correlee` (panel à biais
partagé, le cas « même modèle partout ») place la confiance près du seuil. À 6 missions, la
première lecture de l'instrument disait « le banc ne l'exerce pas, aucune puissance
d'échantillon ne conclura » — **faux**, et la faute est instructive : la porte est un **filtre
de décision**, elle agit sur livrées/réservées/abstentions (les colonnes du verdict), pas sur
le travail de la mission. L'instrument connaît maintenant cette quatrième lecture, qui dit le
contraire de l'erreur : *« `--missions` peut trancher : chaque dissociation supplémentaire
rapproche du seuil »*. Et à **90 missions**, ça a tranché :

> **`porte` en régime corrélé : COÛT MESURÉ** — retirer la porte rend les livraisons *plus*
> propres : 6 gagnées contre 0 perdues (McNemar exact p = 0,0312), **zéro erreur silencieuse
> dans les deux bras**. Lecture : le seuil actuel, face à un panel corrélé, retient des
> livraisons qui se révèlent justes — c'est le prix du fail-closed, mesuré pour la première
> fois. Le rapport écrit *« à justifier, ou à interroger »* et ne conclut pas « supprimez » :
> la même porte vaut ce qu'elle coûte quand la confiance **ment** (le régime réel), et `jio
> learn` fournit les points de calibration pour l'ajuster au lieu de la croire.

Deux observables de décision ont aussi rejoint l'empreinte : la composition des votes (unanime
ou à une voix ?) et la sentinelle `avis_en_phase` — la décision retenue suit-elle le vote
majoritaire, l'observable du consensus qui manquait.

Pour `differentiel`, le chantier de banc a été **fait** : les cinq tâches archivées ont une
spécification **totale** — deux implémentations correctes y coïncident sur toute entrée, donc
le levier ressortait muet sur tout régime (mesuré : défaut, sans oracle, compétence 0,05 à
0,9). La sixième tâche, `mean_partial`, ajoute ce qui manque : l'oracle se tait sur la liste
vide, deux implémentations **légitimes** divergent (`ZeroDivisionError` contre `0.0`), et le
différentiel sonde les entrées dérivées pour avouer le désaccord en constat nommé :

```
$ jio ablation --taches mean_partial --skill 0.7 --missions 6 --levers differentiel
    differentiel   NON CONCLUANT   act=4/6   constat:divergence 4 -> 0
```

Retirer la brique fait **disparaître les 4 aveux** : sans elle, deux candidats à égalité de
preuves sont départagés par l'ordre d'arrivée, en silence. Elle reste NON CONCLUANTE sur la
justesse (le désaccord n'est jamais bloquant, par conception) — mais le silence, lui, a cessé.

Restent `consensus` (prouvé ailleurs : 8 livraisons propres perdues contre 0 — sa décision
n'apparaît pas dans les voix) et `porte`, à peine exercée (1 mission sur 10, aux deux
extrêmes de compétence). La réponse honnête n'est pas « élargir l'échantillon » : il faut des
**missions** où la confiance déborde — un chantier de banc, pas un réglage.

`integrite` est le cas qui a corrigé la première version de ce compteur : la brique ne change
aucun verdict, mais retirer le moniteur fait passer le journal rejoué de **524 pas à zéro** —
elle **travaille**, et le banc n'a simplement jamais d'exploit à lui donner. Le rapport écrit
maintenant les trois lectures, et pas seulement les deux premières :

1. **le banc ne l'exerce pas** — rien à échantillonner : « aucune puissance d'échantillon ne
   conclura, il faut une mission où la brique ait quelque chose à faire ». C'est le cas de
   `temoins` ici, et c'est normal : le banc fournit ses propres tests, donc la traduction en
   témoins n'a rien à traduire — en `--sans-oracle`, le même levier ressort PREUVE (perte),
   avec les appels qui tombent de 3,9 à 1,0 quand on le retire ;
2. **elle agit sans rien déplacer** — le retrait coupe des témoins ou des constats sans changer
   un seul verdict : redondance **mesurée**, que le rapport nomme et ne défend pas ;
3. **elle agit et l'écart penche** — les dissociations vont dans son sens (7 contre 0 pour
   `preuve` à quatre missions) : ce qui manque est un échantillon plus grand, pas une brique à
   retirer.

Une brique qui dégraderait **là où elle agit** est écrite comme telle — « à interroger, car une
brique qui dégrade là où elle agit est un coût, pas une assurance ». Et l'instrument se **tait**
quand il n'a rien compté : « je n'ai pas regardé » ne s'écrit pas comme « il ne s'est rien
passé ». `--missions` élargit l'échantillon (il ne sert à rien dans le cas 1, et le rapport ne
le conseille plus alors), `--skill` durcit la mission, `--json` rend le tout lisible par une
machine — les écarts d'activité y sont publiés clé par clé.

Le même essai à compétence 0,15 (`--skill 0.15`) coûte **6,0 appels par mission au lieu de
3,3** : une mission plus dure consomme plus de boucle, et `red-team` reste la brique dont le
retrait double la dépense (12,0 appels) tout en ramenant les livraisons propres de 3 à 0. À
quatre missions, rien de nouveau n'est *prouvé* — et le rapport le dit, plutôt que de laisser
croire qu'un réglage plus dur aurait changé le verdict.

Codes de sortie : **0** si le moteur complet n'a livré aucune erreur sans réserve, **1** s'il
en a livré une — un levier non distingué n'est pas une panne, c'est une mesure honnête.

## Une entreprise de 66 agents : les vérifications distribuées, en parallèle

Les contrôles existaient tous — la suite, la cohérence, les chiffres, les affirmations, les
régimes d'ablation. Ce qui manquait n'était pas un contrôle de plus : c'était une
**organisation**. `jio entreprise` tire du dépôt lui-même son catalogue (chaque fichier de
tests devient une mission, chaque contrôle de cohérence, chaque preuve archivée), distribue
ces missions à **une entreprise de 66 agents** spécialisés — 48 postes de test par domaine
(moteur, preuve, panel, routeur, artefacts, intégrations…), les 9 auditeurs de cohérence, le
mesurier, les vérificateurs d'affirmations, le linteur, les logeurs d'ablation — et les
exécute **en parallèle**, chaque compte-rendu signé par l'agent qui l'a produit.

```console
$ jio entreprise
  ENTREPRISE JIO  ·  66 postes  ·  98 mission(s)  ·  4 ouvrier(s) en parallele
    temps cumule 844s  ·  temps reel 219s  ·  gain mesure x3.9
    postes mobilises : 66/66 (les autres sont la pour la montee en charge, pas pour la pose)

  PROBLEMES : AUCUN  ·  98 mission(s) au vert, 0 hors de portee
  VERDICT : AUCUN PROBLEME
```

Ce qu'une entreprise apporte qu'un gros script séquentiel n'apporte pas :

- **la vitesse, mesurée et honnête** — le gain est le rapport temps cumulé / temps réel, pas
  un slogan ; sur la machine de l'atelier (2 cœurs), 4 ouvriers suffisent, et le rapport
  *déclare* cette borne : 66 postes et 4 ouvriers sont deux chiffres qui disent deux choses ;
- **un responsable par problème** — un échec n'est plus « quelque part ça a planté » :
  `[KO] tests/test_x.py · test-moteur-2 · 3,1s` avec l'extrait qui prouve ;
- **pas de faux vert** — une mission qui ne peut pas mesurer ici (outil absent) sort *hors de
  portée*, listée à part, jamais comptée comme réussie ;
- **le fail-loud** — code de sortie 1 au moindre problème : un appelant peut déclarer
  « fini » sur `jio entreprise` sans rien croire.

**La boucle de réparation, fermée et honnête.** Un problème *mécanique* (compteur périmé,
artefact qui ne tient plus ses promesses) est réparé par l'agent responsable — `jio chiffres
--appliquer`, `jio coherence --reparer` — puis la mission est **rejouée** : réparé au vert, il
est nommé deux fois (trouvé, puis réparé) au lieu d'être escamoté ; toujours rouge, il reste
un problème avec la réparation tentée pour mémoire. Ce qui demanderait une **décision**
(document faux, compétence dangereuse) n'est jamais touché : la table des réparations est
fermée, une décision humaine ne se devine pas.

`--liste` affiche le roster avec les mandats écrits ; `--sans tests` fait une passe rapide
(cohérence, chiffres, affirmations, lint, fumée) ; `--json` rend tout lisible par une machine.
Et la discipline du dépôt s'applique à l'entreprise comme aux autres : sa commande a son test
de fumée, son chiffre est le onzième surveillé, et son premier tour de garde a attrapé
**quatre problèmes réels** — dont deux dans son propre code (des imports morts), réparés
avant ce paragraphe.

## Hermes : les compétences installées là où l'agent les lit

Écrire les compétences dans le projet ne suffisait pas. **Hermes lit `~/.hermes/skills/`**, et le
dépôt les écrivait dans `.hermes/skills/` : entre les deux, il y avait un `cp -r` à taper à la
main. C'est-à-dire une étape que personne ne fait — et douze procédures qui dorment sur le disque
sans jamais entrer dans la boucle de l'agent. L'intégration en une commande s'arrêtait juste avant
l'endroit qui compte.

`jio start` installe donc les procédures chez Hermes. Trois décisions, chacune payée par un essai :

- **Des copies enregistrées par empreinte, pas des liens symboliques.** L'idée naturelle était le
  lien : il garde les deux en phase par construction. L'essai l'a tué — `echo x >
  ~/.hermes/skills/…/SKILL.md` sur un lien écrit **dans le fichier du projet**, et le prochain
  `jio artifacts --write` efface l'édition. L'utilisateur croit modifier sa copie, il détruit une
  source générée, en silence, dans son dossier personnel. Une copie isole les deux mondes ;
- **une ancienne version de jio se met à jour, un fichier écrit par toi jamais.** Le registre
  `.jio/hermes-install.json` garde l'empreinte de ce qui a été posé. Si la copie a changé et que
  l'empreinte correspond, c'est nous : on met à jour. Si l'empreinte ne correspond plus, c'est toi :
  on préserve, on nomme, et on ne touche pas. `.hermes/skills` est **ton** dossier ;
- **rien n'est créé si tu n'as jamais lancé Hermes.** L'installation n'invente pas un dossier
  personnel : elle dit quoi faire et s'arrête.

```console
$ jio start                       # écrit, câble, prouve, installe — et le dit
$ jio artifacts --install-hermes  # la même chose seule, dans un autre projet
$ jio artifacts --desinstaller    # retire ce que jio a posé, et rien d'autre
```

La désinstallation n'est pas un détail : une installation dont on ne peut pas revenir est une
prise d'otage. Elle vérifie l'empreinte avant de retirer — tes propres compétences restent, et
celles que tu as éditées aussi.

## Les codes de sortie : un contrat, pas des nombres

Un code de sortie est ce qu'un **script** lit. Il portait une confusion : `jio run` rendait `1`
aussi bien pour « livré **avec une réserve nommée** » que pour « **abstention** — rien n'a pu
être prouvé ». Un appelant ne pouvait donc pas distinguer *j'ai un livrable, avec une réserve à
lever* de *je n'ai rien, et il me manque quelque chose* — deux actions opposées.

| code | sens | ce qu'il demande |
| ---: | --- | --- |
| **0** | `OK` — fait, et prouvé | rien |
| **1** | `PROBLÈME` — quelque chose est faux, ou une réserve doit être levée | **corriger**, ou nommer la réserve dans le rapport |
| **2** | `INDÉTERMINÉ` — on ne peut pas conclure | **fournir** ce qui manque (preuve, fournisseur, entrée), puis relancer |
| **3** | `EN ATTENTE` — une réponse humaine est nécessaire avant de commencer | **répondre** aux questions essentielles, puis relancer |

Le `2` est celui qui compte. Une abstention n'est **pas** une faute : c'est une absence, et la
bonne action de l'appelant n'est pas de réparer mais de fournir. Ranger l'abstention avec les
défauts — ce que faisait `jio run` — conduit un agent à « réparer » un travail qui n'a jamais
commencé. `1` signifie *le travail est faux*, `2` signifie *le travail ne peut pas démarrer*.

Cette doctrine vit à **un** endroit (`jio/core/codes.py`), avec l'action associée à chaque code,
et deux garde-fous la tiennent : un test lit `jio/cli.py` et **refuse tout `return 4`** qui
inventerait un code hors doctrine ; un autre fait rendre au moteur les quatre états de mission et
vérifie que le CLI sort bien sur `0/1/2/1`. Les codes sont aussi dans ce que l'**agent** lit
(`.jio/ACTIVE.md`, `AGENTS.md`, `CLAUDE.md`) : un agent qui ne connaît pas le code `2` répare au
lieu de demander.

Et la couleur suit désormais la **sortie** : un terminal est peint, un fichier ou un tube ne
l'est pas. `jio run > rapport.txt` écrivait sept séquences ANSI dans le fichier ; elles
apparaissaient en clair dans les journaux de CI et faisaient échouer toute comparaison de texte.
`NO_COLOR` (le standard), `JIO_NO_COLOR` et `TERM=dumb` coupent la couleur aussi.

## Le duel portable : ce que TON IA gagne, mesuré chez toi

Tout ce qui précède se mesure **ici**, avec un modèle simulé dont le comportement est déclaré.
Cela prouve l'architecture, pas ton IA. La question qui compte — *mon agent, avec ce harness,
atteint-il puis dépasse-t-il un modèle frontière ?* — ne peut se mesurer que sur ta machine,
avec ton outil et ta clé. Une seule commande la pose :

```console
$ python -m jio bench --provider cli:opencode --runs 10 --rapport duel-opencode.md
$ python -m jio bench --provider cli:hermes   --runs 10 --rapport duel-hermes.md
```

`--provider` accepte `cli:opencode`, `cli:hermes`, `cli:claude`, `cli:codex`, `cli:gemini`,
n'importe quel `cli:<autre>` (avec `JIO_CLI_<AUTRE>_ARGV`), ou `openai:<modèle>`. Si le binaire
demandé est absent, la mesure **s'arrête et le dit** : aucun repli silencieux sur la simulation,
parce qu'un rapport qui annonce ton modèle sans l'avoir fait tourner serait un mensonge — et
c'est le pire résultat possible, un chiffre crédible et faux.

### Ce que le rapport contient

Il s'écrit en Markdown (pour toi) **et** en JSON à côté (pour comparer deux exécutions), signé
par le commit mesuré et la date. Il porte les dix bras, chacun avec son **intervalle de
confiance à 95 %**, son coût en appels et le **nombre d'essais** — parce qu'un pourcentage sans
son intervalle ne se lit pas :

| bras | ce qu'il isole |
| --- | --- |
| `S0` modèle brut | un seul appel : le point de départ |
| `S1` échantillonnage seul | best-of-3, sans rien vérifier |
| `S1b` **contrôle apparié** | **autant d'appels que la vérification, mais sans vérifier** |
| `S2` preuve exécutable + reprise | ce que la vérification change |
| `S3` JIO complet | livraison auditée : le moteur doit *savoir* qu'il a fini |
| `S4`/`S4b`/`S4c` sans oracle | règles traduites en témoins, à trois fidélités déclarées |
| `S4r` **sans oracle, ton modèle** | le cas réel : c'est TON modèle qui traduit les règles |
| `S4rc` **contrôle apparié sans oracle** | même budget d'appels, aucune vérification |

Le contrôle apparié est la pièce qui rend le gain **attribuable** : sans lui, un meilleur score
pourrait simplement venir de plus d'essais. Avec lui, la différence restante ne peut venir que
de la vérification. C'est aussi ce qui répond aux chiffres de la littérature (Vérification :
+9,5 points de SWE-bench Pro attribués au harness plutôt qu'au modèle) — sans avoir à les croire
sur parole.

### Ce qu'un bon rapport s'interdit

Trois règles y sont appliquées, et elles viennent de défauts vus ici même :

- **« non mesuré » n'est pas « 0 % ».** Un bras sans données est déclaré tel quel. La première
  version affichait `1000000000.00x` de gain quand le modèle brut ne réussissait rien : un ratio
  sur une base nulle. On écrit `n/a`, qui est la vérité.
- **Un intervalle qui contient zéro signifie INDÉTERMINÉ**, pas « positif ». Le rapport le dit,
  et calcule en plus **combien d'essais il faudrait** pour trancher *cette* taille d'effet :
  la différence entre « je ne sais pas » et « voici ce qu'il faudrait ».
- **Un intervalle de largeur nulle est signalé DÉGENERE.** À un essai, il n'annonce pas une
  précision : il avoue un échantillon trop petit pour qu'une variance existe. Vu en écrivant ce
  rapport : `[+100 ; +100]`.

Un écart **négatif** s'affiche aussi. Un rapport qui ne montre que ses gains n'est pas une
mesure, c'est une plaidoirie.

## Un modèle RÉEL, entraîné ici : la réserve « le modèle est simulé » tombe

Chaque rapport de ce dépôt portait la même réserve, en clair :

> le modèle est **SIMULÉ** : ce n'est pas une mesure de modèle réel.

C'est honnête, et ça laisse ouverte la seule question qui compte pour un harness : **tient-il
quand le modèle qui répond n'est pas le nôtre ?** Une simulation dont *nous* avons choisi le
taux d'erreur ne peut pas répondre — on mesure ce qu'on a mis dedans — et elle peut faire passer
un réglage pour une preuve.

`scripts/modele-local/` entraîne donc un modèle **réel** sur cette machine : des poids, un vrai
calcul, une vraie distribution de sortie, et des erreurs que **personne n'a modélisées**. Il est
petit — c'est assumé : ce n'est pas un substitut à un modèle frontière, c'est un modèle dont les
erreurs sont authentiques, ce qui suffit à mettre le harness à l'épreuve.

| Mesuré | Non mesuré (et dit tel quel) |
| --- | --- |
| Le harness **livre-t-il faux sans réserve** face à un modèle inconnu de lui ? | Un gain de réussite face à un modèle frontière |
| **S'abstient-il** quand la vérification échoue ? | La qualité linguistique du modèle |
| La **reproductibilité** à graine fixée | Un gain de « QI » du modèle |

L'architecture suit **`karpathy/nanoGPT`** et **`karpathy/minGPT`** (transformeur décodeur :
self-attention causale, embeddings de position appris, tête de langage), avec
**`pytorch/pytorch`** comme seule dépendance. Le corpus est le meilleur disponible ici : le code
de ce dépôt. Le modèle est servi par une **API compatible OpenAI**, ce qui a une conséquence
précise — **le harness n'est pas modifié pour ce cas particulier**. Ce qui est mesuré est le
chemin réel qu'un utilisateur emprunte avec Ollama, vLLM ou OpenRouter :

```sh
scripts/modele-local/entrainer.py     # ~10 min sur 2 cœurs, graine fixée
scripts/modele-local/mesurer.sh 5 3   # mesure + rapport, sur le serveur local
```

Le modèle entraîné n'est pas versionné (un binaire de plusieurs mégaoctets n'a rien à faire dans
un historique) : ce qui est versionné, c'est la **graine**, la **configuration**, le **corpus**
(le dépôt) et le **journal d'entraînement** — de quoi le refaire et vérifier son empreinte.

### Première mesure sur ce modèle : ce qu'elle dit, et ce qu'elle ne dit pas

`jio bench --provider openai:modele-local-char`, 5 tâches, commit `e951a5f` :

| bras | réussite | IC95 | appels/tâche |
| --- | ---: | ---: | ---: |
| modèle brut (1 appel) | 0,0 % | [0 % ; 43 %] | 1,0 |
| échantillonnage seul (best-of-3) | 0,0 % | [0 % ; 43 %] | 3,0 |
| contrôle apparié (même budget, 0 vérification) | 0,0 % | [0 % ; 43 %] | 3,0 |
| JIO complet (livraison auditée) | 0,0 % | [0 % ; 43 %] | 3,0 |

```
candidats CORRECTS rejetes    : 0
ERREURS LIVEES SANS RESERVE   : 0      <- le seul chiffre qui doit rester a zero
exploits d'integrite detectes : 0
```

Ce que ces zéros disent : face à un générateur **inconnu de lui**, dont le harness n'a pas
choisi les erreurs, le dispositif n'a **rien livré de faux sans le dire**. C'est la propriété
qu'on lui demandait, et elle est mesurée au lieu d'être espérée.

Ce qu'ils ne disent pas, et il faut l'écrire aussi clairement : un modèle char-level de 1,9 M
paramètres **ne produit pas de code correct**, donc cette mesure éprouve la *containment*, pas la
*sélection*. Réussir à refuser du charabia est facile — le code ne compile même pas. La mesure
qui compte pour un harness est la suivante : *garde-t-il un candidat juste, et refuse-t-il un
candidat faux ?* Elle demande un modèle qui produit du code **plausible**, et c'est à quoi sert
le second corpus (`--avec-banc`).

### Deux défauts trouvés en l'écrivant — et c'est la même leçon que partout ici

1. **Un masque causal 4096×4096 partait dans le `state_dict`.** Mesure : un modèle de
   **251 904 paramètres** produisait un fichier de **135 Mo** — la taille du fichier disait autre
   chose que le nombre de paramètres. Un masque est une constante, pas un poids appris.
   Après correction : **1,0 Mo**, exactement 250 k paramètres en float32.
2. **La table de décodage était inversée** (`{i: c for c, i in enumerate(...)}` construit
   l'inverse de ce qu'il faut) : le premier appel réel a rendu `KeyError: 84` au lieu d'une
   réponse. Aucun test unitaire ne l'aurait attrapé sans **appeler** le service pour de vrai.

## Le régime de mesure fait partie du chiffre : `jio ablation --fidelite`

Même leçon, appliquée à l'ablation. Elle mesurait chaque brique en la retirant — mais elle
fournissait toujours des témoins **parfaits**, y compris dans le mode sans oracle, celui où
personne ne donne les tests et où c'est le modèle qui les écrit. Avec des témoins parfaits, il
n'y a rien à rattraper : la vérification ne peut pas montrer mieux que ce qu'elle a.

Résultat, mesuré : la plupart des leviers ressortaient « NON DISTINGUABLE », y compris ceux dont
tout le rôle est d'attraper ce qu'un témoin imparfait laisse passer. Un levier mesuré dans un
régime où il ne peut rien faire n'est pas un levier inutile — c'est une **mesure inadaptée**.

`--fidelite` (borné dans `[0, 1]`, annoncé dans l'en-tête du rapport) rend ce régime réglable :

```sh
jio ablation --sans-oracle --fidelite 0.6 --levers mutation,red-team,consensus,porte
```

Un chiffre sans son régime ne se compare pas.

### Réparer l'INSTRUMENT, pas seulement le candidat

Le constat précédent laissait la phrase la plus dure du dossier : *le moteur re-demande des
**candidats** quand la preuve échoue ; il ne re-demande jamais l'**instrument***. Un système qui
s'abstient toujours est sûr et inutile.

La correction ne demande **aucune confiance supplémentaire**, et c'est ce qui la rend utilisable.
Chaque témoin traduit doit maintenant venir avec une **implémentation de référence** et une
**contrefaçon**, et le harness les **exécute** avant que le témoin serve à quoi que ce soit :

```
le test PASSE sur la référence fournie avec lui   -> sinon il se contredit ;
le test ÉCHOUE sur la contrefaçon fournie avec lui -> sinon il ne prouve rien.
```

Un instrument refusé est **redemandé une fois**, en lui donnant le motif exact rendu par
l'exécution — puis le fait est **journalisé** (`valides`, `incohérents`, `réparations`) et
publié dans le rapport : un instrument réparé n'est pas l'instrument du premier essai.

Il y a un **troisième état**, et c'est celui qui évite de casser le chemin existant : un modèle
qui rend un test **sans** référence ni contrefaçon ne se contredit pas — il n'a pas fourni de
quoi le mettre à l'épreuve. Le refuser ferait s'abstenir le moteur sur un simple **format de
réponse**, c'est-à-dire sur rien. Ce témoin est donc accepté (il vaut mieux qu'aucune preuve),
**nommé** `non éprouvé` dans le journal, et il ne compte jamais parmi les règles déclarées
prouvées.

Enfin, une **aveu n'est pas une panne et ne se repaie pas** : quand le modèle déclare une règle
non testable, cette réponse est mémorisée comme savoir négatif — la mission suivante ne repose
pas la question. Elle ne devient jamais une preuve pour autant : une règle dont le témoin est un
aveu reste non couverte, exactement comme si l'aveu venait d'arriver.

Le garde-fou qui rend l'idée sûre : *réparer* ne doit jamais devenir *redemander jusqu'à ce
qu'un témoin laisse passer*. C'est pour ça que la validation est **mécanique** (deux exécutions
dans le bac à sable, mêmes règles que pour les artefacts : aucun réseau, délai, confinement) et
qu'un témoin aveugle — qui passe sur les deux implémentations — est refusé **quelle que soit la
bonne volonté du modèle**. Un test le vérifie nommément : le modèle peut répéter un témoin
complaisant autant de fois qu'il veut, rien n'est accepté.

**L'effet est mesuré, sur le même banc et la même graine** (15 missions, 5 tâches, 3 graines,
`--sans-oracle --fidelite 0.6`, leviers par défaut) :

| | témoins naïfs (avant) | témoins auto-validés (après) |
|---|---|---|
| missions justes | 9 / 15 | **13 / 15** |
| livrées **sans** réserve | 0 | 0 |
| livrées **avec** réserve nommée | 0 | **15 / 15** |
| **abstentions** | **15 / 15** | **0 / 15** |
| erreurs silencieuses | 0 | **0** |
| appels par mission | 3,7 | 5,2 |
| leviers distinguables | 0 | **1** (`preuve`, p = 0,031) |

Le chiffre à lire est celui du milieu. Le moteur ne s'abstenait pas parce qu'il était prudent :
il s'abstenait parce que **l'instrument fourni mentait**, et il n'avait aucun moyen de le lui
dire. Un témoin qui ne peut pas échouer ne prouve rien, et un moteur qui refuse tous les témoins
ne peut rien livrer. Une fois les témoins exécutés **avant** d'être crus, l'abstention tombe à
zéro, les missions justes montent de 9 à 13, et le levier `preuve` — muet jusque-là — devient
mesurable : sans lui, 6 missions justes sur 15 en moins (40 points, IC95 [15 ; 65], p = 0,031).

Les deux lignes du milieu comptent autant que la première. Dans les deux régimes, **aucune
erreur n'est livrée sans réserve** et **aucune erreur n'est silencieuse** : le progrès n'a pas
été acheté en relâchant l'invariant. Ce qui change, c'est que le système *livre* — avec une
réserve nommée quand il n'a pas pu prouver — au lieu de tout bloquer.

Le prix est nommé, lui aussi : **5,2 appels par mission au lieu de 3,7**, parce que chaque témoin
coûte deux exécutions et qu'un instrument refusé est redemandé une fois. C'est un coût
d'instrument, pas de candidat — il ne dépend pas de la taille du modèle et il est borné.

Ce que le lecteur voit, et ce que la mémoire n'a **pas le droit** de faire :

* le rapport humain a une section `INSTRUMENT` : « *N témoin(s) mis à l'épreuve* », « *accepté
  sans l'être* », « *refusé* ». `preuves 2/2 règles satisfaites` ne veut pas dire la même chose
  dans les trois cas, et c'est écrit juste en dessous de la ligne qui l'affirme ;
* **la mémoire ne blanchit pas.** Un témoin entre dans la bibliothèque avec la mention « mis à
  l'épreuve » ou sans elle, et il en ressort avec la même. Sans ce champ, la bibliothèque servait
  du même air un témoin qui avait prouvé qu'il peut échouer et un témoin seulement accepté —
  c'est-à-dire qu'elle *augmentait* la confiance de ce qu'elle servait. Par défaut, une entrée
  dont on ne sait rien ressort `non éprouvé` : rien n'est prouvé par omission.

**Et c'est là que le banc d'ablation a fait son travail.** La première version de ce contrôle
refusait *trop tôt* : une règle dont l'instrument était refusé n'avait plus de témoin du tout, et
plus aucun mécanisme ne la déclarait non couverte. Mesure : sur `safe_divide` sans oracle, la
mission est repartie « livrée **sans** réserve » sur **un** témoin valide sur **quatre** règles,
avec un artefact **faux** — l'invariant du dépôt, cassé par une amélioration. Un témoin que
l'ancien régime acceptait déclenchait, en échouant sur tous les candidats, la réserve qui
protégeait le rapport ; en le refusant plus tôt, on avait supprimé ce signal.

La correction est dans la même doctrine : une règle dont l'instrument est **refusé** n'a aucun
témoin, donc elle est **NON COUVERTE** — nommée dans le rapport, et la livraison porte la
réserve. Le chiffre est revenu à **0 erreur silencieuse**, et un test le verrouille.

### Une règle sans témoin n'est pas une règle tenue

Même famille de défaut, trouvée au tour suivant — et cette fois par le **banc**, pas par
l'ablation. `jio bench` a affiché `ERREURS LIVREES SANS RESERVE : 1`, un chiffre qui doit rester
à **zéro**. La mission coupable, reproduite à la main :

```
median, graine 4, sans oracle
  R-001, R-002, R-004 : témoins traduits, mis à l'épreuve, satisfaits par l'artefact livré
  R-003               : le modèle AVOUE ne pas savoir la tester (aucune contrefaçon trouvée)
  verdict             : delivered — sans réserve
  vérification externe : l'artefact ÉCHOUE sur R-003 (IndexError sur liste vide)
```

Le système avait donc livré « sans réserve » un artefact qui échouait précisément sur la seule
règle dont personne n'avait jamais parlé. Sa propre mesure le dit : un aveu est une **absence de
preuve**, pas une preuve d'absence. Une règle sans témoin exécutable — instrument refusé, témoin
rejeté par la porte, **ou aveu du modèle** — est maintenant déclarée **NON COUVERTE**, et la
mention « livré sans réserve » devient impossible.

Deuxième conséquence, tirée de la même mesure : **la mémoire n'accepte que des témoins mis à
l'épreuve**. Avant, elle capitalisait aussi les témoins seulement *acceptés* (l'ancien format) et
les resservait ensuite sans dire qu'ils n'avaient rien prouvé — elle *augmentait* la confiance de
ce qu'elle servait. Désormais un témoin non éprouvé ne se mémorise pas : la mission suivante
**repaie** sa traduction. C'est un coût, et il est choisi.

### Ce que ce régime a montré, et qui n'était pas prévu

Mesure faite à **témoins 60 %** (8 leviers, 15 missions par bras, `--sans-oracle`) :

```
moteur complet : 9/15 justes  ·  0 livrée  ·  15 ABSTENTIONS  ·  0 erreur silencieuse
aucun levier ne se distingue, sauf `preuve` (5 missions perdues, 3 gagnées : non concluant)
```

Le résultat tient en une phrase : **quand l'instrument est mauvais, le harness ne ment pas —
il s'abstient. Sur les quinze missions.** Il ne livre rien, pas même les neuf où le code était
juste, parce que ses témoins étaient faux. C'est le comportement « fail-closed » qui a été
demandé, et il est ici **mesuré plutôt que supposé**.

Mais c'est aussi la limite du dispositif, énoncée sans détour : **aucun levier du harness ne
répare un témoin faux**. Le moteur re-demande des *candidats* quand la preuve échoue ; il ne
re-demande jamais l'*instrument*. Un système qui s'abstient toujours est sûr et inutile — les
deux moitiés de la phrase comptent.

C'est donc un axe ouvert, avec sa piste : un témoin qui **ne tue aucun mutant** du candidat
n'est pas un témoin (c'est le principe de la sélection de tests par mutation). Le distinguer
d'un témoin qui *contredit* le code est faisable, et la porte de mutation a déjà les données en
main ; ce qui manque est la décision — écarter un témoin non informatif, en le déclarant, plutôt
que de tout bloquer. La règle reste : jamais de livraison propre sur cette base, seulement une
réserve nommée.

## Toutes les commandes répondent, et c'est testé

Un utilisateur n'utilise pas « le projet » : il utilise **une** commande, un jour, dans un
contexte précis. Une commande rare qui plante fait plus de dégâts qu'une fonctionnalité
absente — elle laisse croire que le reste ne marche pas non plus.

`tests/test_fumee_cli.py` lance donc **chaque** sous-commande de la CLI :

| Contrôle | Ce qu'il attrape |
|---|---|
| `jio <commande> --help` sort en **0**, sans traceback, avec un `usage:` | la commande qu'on n'a jamais ouverte et qui plante au premier contact |
| `jio <commande> --option-inconnue` sort en **2** | l'argument lu avant d'être validé (traceback au lieu d'un message) |
| Les commandes sûres tournent sur un **dossier vide** sans traceback et **sans rien écrire** | la commande d'inspection qui exige un contexte et le dit mal |

La liste des commandes n'est pas recopiée à la main : elle est lue **dans le parseur réel**.
Une liste écrite à la main oublie toujours la dernière commande ajoutée — et c'est justement
celle qui n'a jamais été lancée. Deux contrôles ferment la boucle :

* toute commande doit être soit lancée, soit **citée avec sa raison** de ne pas l'être
  (`run`, `bench`, `learn`, `audit`, `mcp`, `recover`, `sync` — couvertes ailleurs) ;
* une commande citée qui n'existe plus est un **mensonge du test**, et il échoue.

Et le contrôle du contrôle : `_lancer` doit vraiment capturer la sortie et vraiment laisser
remonter une panne. Le premier essai de ce test modifiait le parseur rendu par
`build_parser()` — or `main` construit **le sien** : rien n'était cassé, et le test échouait
proprement. Un contrôle qui ne contrôle rien doit échouer ; il l'a fait.

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

### Et sur le projet de quelqu'un d'autre ? Un second jeu, écrit avant la correction

Le banc de clarification cite les chemins de **ce** dépôt (« corriger `jio/verify/entropy.py`… »).
Il a donc réglé la porte — et il ne peut pas dire si elle fonctionne ailleurs, alors que l'outil se
pose sur n'importe quel dépôt. Un jeu de contrôle de **22 objectifs d'un projet étranger**
(application web, pipeline de données, infrastructure, documentation ; aucun chemin de ce dépôt),
écrit **avant** toute retouche, moitié anglais moitié français, a mesuré ceci :

```
  avant :  82 % d'exactitude — 100 % en français, 50 % en ANGLAIS
           les quatre objectifs anglais actionnables recevaient TOUS la question
           « comment saura-t-on que c'est FINI et CORRECT ? »
  après : 100 % d'exactitude — 100 % en anglais, 100 % en français, 0 question inutile
```

Le défaut était une **asymétrie de langue** : les motifs de critère et les verbes d'action
n'existaient qu'en français. Une question inutile sur *chaque* objectif anglais est le défaut
qui fait désactiver un outil ; c'est exactement le travail d'Hermes et d'opencode, dont les
prompts sont anglais. Les motifs anglais ajoutés sont de la **parité**, pas des exceptions :
bornes quantitatives (« below 200 MB »), test nommé (« cover it in `tests/…` »), invariants
(« keeping `docker compose up` working »), et les verbes d'action des trois familles
(remove/delete, rename/move, write/create/add).

Et le banc du dépôt n'a **pas bougé** : 100 % de précision et de rappel avant comme après. Une
correction qui répare une langue en cassant l'autre n'est pas une correction — c'est pourquoi
les deux chiffres sont affichés ensemble (`jio clarify --mesure` renvoie à `--controle`).

Une erreur **de la mesure elle-même** est corrigée au passage, et elle est instructive : le
premier jet devinait la langue à la présence d'accents. Or ce dépôt écrit le français sans
accents dans le code, le jeu a suivi cette convention, et onze cas sur vingt-deux se sont
retrouvés dans la mauvaise langue — le rapport affichait alors « 0 % en français », un chiffre
faux produit par la mesure et non par la porte mesurée. La langue est désormais une **donnée**
du cas. Un calcul sur une étiquette devinée n'est pas une mesure.

## Un outil Python absent ne doit pas faire accuser le dépôt

Un environnement installé avec `pip install -e '.[dev]'` mais sans Ruff a fait échouer
`tests/test_entreprise.py::test_les_ouvriers_executent_vraiment`. `jio.entreprise` lançait
`python -m ruff` puis interprétait son code 1 (`No module named ruff`) comme un défaut du
code audité. Le code 127 ne couvre que l'absence de l'exécutable lui-même. Le même piège
existait pour `pytest`.

Le contrat de l'entreprise est différent : un outil facultatif absent doit être annoncé
**hors de portée**, pas transformé en faux défaut. Les missions résolvent maintenant
l'outil avant son lancement — module Python, puis binaire sur `PATH`. Pour Ruff, elles
réutilisent le sélecteur de `jio.verify.linters`; pour pytest, le résolveur correspondant.
Si l'outil manque, le rapport porte `ok=True`, `portee=False` et la raison précise. Une
panne d'un outil présent reste, elle, un échec.

Le garde `tests/test_entreprise.py::test_outils_absents_sont_hors_de_portee` force
l'absence de pytest et de Ruff et vérifie les deux verdicts. Rejeu réel avec ces outils
retirés du `PATH` :

```text
pytest: ok=True, portee=False, resume=pytest absent : hors de portee ici
ruff: ok=True, portee=False, resume=ruff absent : hors de portee ici
```

Preuves après correction : `python -m pytest -q` (code 0, 1274 tests mesurés),
`python -m jio coherence --json` (`coherent: true`), `python -m jio scan jio
--exclude-tests --no-learn` (code 0, aucun problème prouvé), et Ruff sur `jio/` et
`tests/` (code 0).

