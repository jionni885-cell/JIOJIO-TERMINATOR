# Roadmap — construction de JIOJIO-TERMINATOR

Principe directeur : **chaque phase livre un système qui tourne**, pas une fondation invisible.
Rien n'est « prévu » : soit c'est fait, soit c'est une phase nommée.

---

## Phase 0 — Socle (dépôt, contrats, journal)

**Livrable :** `jio --version` fonctionne, les types du domaine sont figés, tout est testé.

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
- Rapport comparatif chiffré FR + graphiques

**Critère de sortie :** un tableau qui montre le gain réel, y compris les cas où JIO **ne** gagne pas.

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
