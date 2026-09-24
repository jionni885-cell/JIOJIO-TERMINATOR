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

**Statut :** noyau **implémenté, mesuré et auto-audité** — 125 tests verts, exécutable sans aucune clé API.
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
```

---

## Ce qui est mesuré (et ce qui ne l'est pas)

`jio bench` mesure quatre configurations sur le banc d'essai intégré, avec un
**bras de contrôle à budget d'appels égal** — sans lui, tout gain pourrait n'être
que du « best-of-N » déguisé.

| Configuration | Compétence 0.15 | Compétence 0.30 |
|---|---|---|
| modèle brut (1 appel) | 15,0 % | 20,0 % |
| échantillonnage seul (best-of-3) | 35,0 % | 60,0 % |
| **contrôle : autant d'appels, 0 vérification** | 75,0 % | 75,0 % |
| **vérification exécutable + reprise** | **85,0 %** | **100,0 %** |
| JIO complet (livraison auditée) | 85,0 % | 100,0 % |

> **À budget d'appels strictement égal, la vérification apporte +10,0 points
> (compétence 0.15) et +25,0 points (compétence 0.30)** par rapport à un tirage
> aveugle du même modèle. Le gain vient donc de l'architecture de vérification,
> pas du nombre d'essais.

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
processus — une mémoire qui oublie.

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
