# Roadmap — construction de JIOJIO-TERMINATOR

Principe directeur : **chaque phase livre un système qui tourne**, pas une fondation invisible.
Rien n'est « prévu » : soit c'est fait, soit c'est une phase nommée.

---

## Phase 0 — Socle (dépôt, contrats, journal)

**Livrable :** `jio version` fonctionne, les types du domaine sont figés, tout est testé.

- Structure du paquet Python `jio/` (installable, `pyproject.toml`, zéro dépendance obligatoire)
- **Types du domaine** (`jio/core/types.py`) : `Mission` · `Spec` · `Rule` · `Artifact` ·
  `Claim` · `Witness` · `Verdict` · `Vote` · `AuditFinding` · `Blame` · `Trace` · `TrustLevel`
- **Journal d'événements append-only, rejouable** (`jio/core/journal.py`) — hash-chaîné,
  chaque entrée lie le hash de la précédente (détection d'altération)
- Registre de composants + chargement par configuration
- Suite de tests `pytest` avec couverture sur le noyau

**Critère de sortie :** `pytest` vert, `jio doctor` liste l'environnement.

---

## Phase 1 — Moteur d'exécution (le cœur)

**Livrable :** `jio run "mission"` exécute la boucle complète et produit un rapport.

- `ProviderLayer` : adaptateurs **API** (OpenAI-compatible → OpenRouter/Ollama/vLLM),
  **CLI subprocess** (opencode, hermes, claude, codex, gemini), **et mode `simulé` déterministe**
  (aucune clé requise — c'est ce qui permet de tout tester immédiatement)
- `SpecCompiler` : découpe une mission en **règles énumérées** + un test par règle (SPEC grounding)
- `Generator` : `best-of-N` avec diversité forcée (température, modèle, angle)
- `ExecutableProver` : compile / tests / types / lint / **fail-closed**
- `AuditPanel` : Verifier · Skeptic · Logician · Red-Team · Historien — **revue aveugle**
- `ConsensusEngine` : quorum `n ≥ 3f+1`, désaccord → escalade, jamais de moyenne
- `ReflectionLoop` (MAR) : Consensus Reflection réinjectée
- `OscillationGuard` : détection de cycle + hystérésis + plafond d'itérations
- **Rapport de mission** déterministe et lisible (FR) + journal complet

**Critère de sortie :** une mission réelle sur un dépôt de test est résolue, et une erreur
**volontairement injectée** est détectée, blâmée, corrigée.

---

## Phase 2 — Couche anti-erreur avancée (les techniques uniques)

**Livrable :** les techniques que personne n'assemble sont actives.

- `MetaQA` : 12 mutations de requête + vérification d'invariance
- `SemanticEntropy` : clustering par entailment, entropie de Shannon
- `ClaimLedger` : claims atomiques + routage de provenance + **fail-closed**
- `ConformalGate` : abstention calibrée `Pr[erreur ∧ accepté] ≤ α`
- `IntegrityMonitor` : rejeu déterministe, 6 catégories d'exploit RHB
- `OccamGate` : MDL — réputation de special-casing
- `BlameLedger` : Shapley (succès) + premier pas fautif (échec), `O(log T)`
- `LATSSearch` : recherche arborescente avec backtracking + budget d'inférence
- `TrustRouter` : bandit bayésien — quel modèle est fiable sur quel type de tâche

**Critère de sortie :** un agent qui triche est détecté ; une hallucination cohérente est détectée.

---

## Phase 3 — Sécurité architecturale

**Livrable :** tout dépôt lu est traité comme hostile, sans casser l'ergonomie.

- `TrustTier` : system / user / externe — séparation **architecturale**, pas textuelle
- `Spotlighting` : marquage/délimitation du contenu non fiable
- `DualLLM` : planificateur privilégié ↔ exécuteur en quarantaine, politique **déterministe**
- `CapabilityGate` : **Rule of Two** en dur — pas de write/exec dans un tour ayant ingéré
  du contenu non fiable, sans confirmation
- `McpPin` : hachage des schémas d'outils MCP, alerte sur modification
- `InjectionScanner` : détecteur PromptArmor-style + patterns connus (42 techniques)
- Red-team automatisé : `pyrit`/`garak`-style adapté, en self-test du système

**Critère de sortie :** une injection plantée dans un fichier de test ne provoque **aucune**
action d'écriture/exécution non autorisée.

---

## Phase 4 — Écosystème multi-outils (le hub)

**Livrable :** `jio sync` propage le cerveau anti-erreur dans tout l'écosystème.

C'est fait : `jio sync` écrit les artefacts natifs de tous les dialectes sous la racine visée, branche le serveur MCP pour chaque outil, et n'écrase jamais un fichier qui ne porte pas la marque de jio (le vôtre est préservé, la version jio est écrite à côté, suffixe `.jio`). Le dépôt lui-même se synchronise avec `scripts/sync.sh`, qui a ses propres garde-fous git.

Une **source de vérité unique** (`jio/ecosystem/` + YAML) compile vers :

```
.opencode/agents/*.md          + opencode.json      → opencode (SST)
~/.hermes/skills/<cat>/<skill>/SKILL.md             → Hermes Agent (tap installable)
CLAUDE.md                                           → Claude Code
AGENTS.md                                           → Codex / standard ouvert
GEMINI.md                                           → Gemini CLI
.cursor/rules/*.mdc                                 → Cursor
.github/copilot-instructions.md                     → GitHub Copilot
jio mcp (serveur MCP)                               → tout client MCP
```

- 20+ sous-agents prédéfinis : `spec-writer`, `red-team`, `verifier`, `blamer`,
  `fact-checker`, `metamorphic-tester`, `occam`, `historian`, `security-auditor`,
  `integrity-monitor`, `architect`, `minimalist`, …
- Bibliothèque de **skills anti-erreur** (format `SKILL.md` / agentskills.io)
- **Bibliothèque de prompts** versionnée, en anglais (précision), avec métadonnées et tests

**Critère de sortie :** ouvrir opencode dans le dépôt → les 20 sous-agents sont disponibles.
Installer le tap Hermes → les skills anti-erreur sont actives.

---

## Phase 5 — Apprentissage continu

**Livrable :** le système s'améliore seul, sans intervention.

- `SkillForge` : auto-génération de `SKILL.md` après 5+ appels d'outil / récupération d'erreur /
  correction utilisateur
- `FailureMemory` : base d'échecs indexée par signature, réinjection ciblée
- `PromptEvolution` (GEPA) : réflexion sur traces + frontière Pareto
- `GuardrailSynthesis` (CEGIS) : mine les faux positifs/négatifs, induit des règles
- `Curator` : tâches planifiées (cron) — consolidation, déduplication, archivage des skills
- `TrustRouter` mis à jour après chaque mission

**Critère de sortie :** sur 20 missions répétées, le taux de réussite au premier essai augmente
et le coût par mission diminue — **mesuré, pas supposé**.

---

## Phase 6 — Interfaces et observabilité

**Livrable :** tout est visible et pilotable.

- **CLI `jio`** avec bannière ASCII-art, sous-commandes : `run`, `audit`, `verify`, `consensus`,
  `sync`, `skills`, `evolve`, `doctor`, `report`, `trace`, `blame`, `mcp`
- **Dashboard web** (live preview) : missions en cours, votes, désaccords, audits,
  entropie sémantique, taux de réussite, frontière Pareto, journal d'intégrité
- **Rapports** HTML/Markdown/JSON, en français
- Export OpenTelemetry (GenAI semantic conventions)

**Critère de sortie :** le dashboard montre une mission se dérouler en direct.

---

## Phase 7 — Preuve d'efficacité (benchmark interne)

**Livrable :** des chiffres, pas des promesses.

- `jio bench` : suite de tâches à difficulté croissante **avec oracles cachés**
- Mesure sur le **même modèle** : baseline (1 appel) vs JIO complet
- Métriques : taux de réussite, taux d'erreurs non détectées, coût, latence, taux d'abstention
- `jio mutants` : la suite de tests de ce dépôt attrape-t-elle une erreur injectée dans son
  propre code ? Un survivant est une preuve manquante ; un survivant **équivalent** se déclare,
  avec sa raison, et un test refuse une déclaration fantôme
- `jio ablation` : quelle brique apporte quoi ? On l'enlève et on compare sur les **mêmes
  missions** (appariement par tâche et par graine). Deux métriques — erreurs silencieuses, et
  livraisons **sans réserve** — parce que retirer le red-team ne rend pas le résultat faux, il
  le rend non livrable. Un levier sans effet mesuré est déclaré **NON DISTINGUABLE**, jamais
  « inutile », avec le nombre de dissociations qu'il faudrait pour trancher
- Rapport comparatif chiffré FR + graphiques

**Critère de sortie :** un tableau qui montre le gain réel, y compris les cas où JIO **ne** gagne
pas — et, pour chaque brique, une ligne qui dit ce qu'elle coûte et ce qu'elle rapporte.

---

## Ordre de construction et dépendances

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3
                │            │           │
                └────────────┴───────────┴──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7
```

Les phases 4 et 5 peuvent démarrer en parallèle de la 3 si nécessaire.

---

## Règle de non-régression du projet lui-même

JIOJIO-TERMINATOR **s'applique ses propres techniques** :

- Chaque composant a des tests, et **les tests sont audités par mutation testing**
- Aucune fonctionnalité n'est déclarée terminée sans **preuve exécutable** dans le journal
- Le `IntegrityMonitor` tourne **sur le développement de JIO lui-même**
- Les échecs réels rencontrés pendant le développement deviennent des **skills** et des **règles de garde**

Si le système n'est pas capable de s'auditer lui-même, il n'est pas prêt à auditer autre chose.

## Boucle d'amélioration contrôlée

`jio evolve compare` compare maintenant deux rapports d'évaluation appariés sur holdout : même modèle, budget, dataset, tâches et graines. La baseline doit être rescorrée trois fois sans évolution avec graines distinctes; un candidat ne passe que si le gain dépasse le bruit observé sur la baseline gelée. Il bloque aussi les gains obtenus en augmentant les erreurs silencieuses, les violations de sécurité ou les abstentions; McNemar exact décide si le gain de réponses correctes est concluant. Les souvenirs d'échec sans remède confirmé restent en quarantaine et ne sont pas réinjectés dans les prompts. `PROMOTE_ELIGIBLE` autorise uniquement une revue/staging, jamais une activation automatique. La conception, les limites, le schéma JSON et les éléments non automatisés sont dans [`BOUCLE-AMELIORATION-CONTROLEE.md`](BOUCLE-AMELIORATION-CONTROLEE.md). Le comparateur ne crée pas encore le benchmark privé, les propositions de patch ni le déploiement canari : ces étapes restent explicitement à construire.

## Doctrine de livraison — objectif zéro erreur acceptée

La doctrine détaillée est dans [`DOCTRINE-INFAILLIBILITE.md`](DOCTRINE-INFAILLIBILITE.md) : l'objectif est zéro erreur livrée comme correcte sans réserve ; en cas d'incertitude détectée, la réponse doit être une abstention explicite. `jio run --zero-reserve` rend cette règle stricte pour les incertitudes connues : le panel doit être unanime ; en cas de désaccord, JIO continue jusqu'au budget `--rounds`, puis s'abstient plutôt que de forcer un verdict. Toute livraison avec réserve devient également une abstention journalisée. Ce mode réduit les livraisons, sans garantir l'absence d'erreurs inconnues.

## Extension — Harness engineering : diagnostic et performance locale

`jio perf --runs 10` compare à poids constants le lancement direct de Python et celui du runner JIO, sur un no-op et une petite sortie ; affiche médiane et p95, avec JSON disponible. Cette micro-mesure n'appelle aucun modèle et n'écrit pas dans le dépôt ; elle ne prédit pas le temps d'une mission complète.

La commande `jio harness --root <depot>` audite des signaux observables avant de lancer un agent :
présence et taille des fichiers d'instructions, présence de tests et de configuration projet,
commandes de vérification reconnues statiquement (pytest, npm test, cargo test, go test, make test)
et disponibilité de Git et pytest. Par défaut, elle n'exécute aucune commande du dépôt. Avec
`--run-checks`, elle lance explicitement les commandes reconnues via argv fixe (sans shell), une à
une, avec délai et sorties bornés ; tout échec rend le code de commande non nul. Ce mode exécute
néanmoins du code arbitraire du dépôt, dans une copie temporaire qui exclut `.git`, les environnements
virtuels et caches ; les liens symboliques sont refusés pour éviter qu'une copie ne pointe vers
l'arbre d'origine. Cela protège des effets de bord accidentels sur les fichiers du dépôt, mais ne
constitue PAS une frontière de sécurité : réseau et autres chemins de l'hôte restent accessibles.
À réserver aux dépôts de confiance. `--timeout` règle le délai par commande (1–900 secondes). Le
rapport JSON (`--json`) inclut le statut, la durée et les sorties tronquées de chaque vérification.
Le score de préparation reste une checklist, pas une mesure de compétence ni une garantie.

La reprise `jio auto` checkpoint maintenant son état **après chaque étape** par remplacement de
fichier atomique. Un arrêt brutal conserve ainsi le plan complet, les étapes déjà prouvées et
celles encore non tentées ; seule une preuve enregistrée pour la même révision est réutilisable.

La Sandbox vide stdout/stderr en continu vers des fichiers temporaires, avec un plafond strict de
2 Mo par flux ; un dépassement est un échec explicite (code 125), pas une preuve tronquée acceptée.
Elle tue également le groupe entier des processus sous POSIX au timeout, afin qu'un enfant ne
poursuive pas la preuve après le verdict. Cela réduit les risques d'épuisement mémoire/disque et de
processus orphelins, mais n'isole toujours pas le filesystem ni le réseau : conteneur ou VM restent
nécessaires pour du code hostile.

Ce score ne mesure ni la compétence du modèle ni la qualité réelle des tests : il sert de checklist
reproductible, pas de promesse de performance. Les étapes suivantes envisagées sont l'inspection
du statut de travail et des commandes de vérification documentées, puis la collecte de traces de
mission pour comparer des variantes de harness sur les mêmes tâches.
