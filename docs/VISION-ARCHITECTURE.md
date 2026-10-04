# JIOJIO-TERMINATOR — Vision & Architecture

> **But :** faire qu'un système d'IA cesse de se tromper — pas « un peu moins », mais *d'une manière
> qu'on peut borne*r, mesurer, prouver et corriger automatiquement.
> **Moyen :** un noyau d'orchestration + vérification + audit qui transforme n'importe quel modèle
> (même un modèle local gratuit) en un système de niveau frontière, puis au-delà.

---

## 0. La limite théorique — il faut la regarder en face

Avant de promettre quoi que ce soit, il faut nommer le mur.

**Théorème de Rice (1953).** Toute propriété non triviale d'un programme est indécidable.
**Problème de l'arrêt (Turing, 1936).** On ne peut pas décider si un programme termine.

Conséquences directes et non négociables :

1. **« Zéro erreur » absolu est mathématiquement impossible à garantir.** Quiconque te le vend ment.
2. Ce qui est **atteignable**, et ce que JIOJIO-TERMINATOR construit :

| Garantie atteignable | Fondement mathématique |
|---|---|
| **Borne supérieure de taux d'erreur** sur les réponses acceptées | Prédiction conforme (couverture finie, sans hypothèse de distribution) |
| **Consensus correct malgré f agents défaillants** | Tolérance aux pannes byzantines : `n ≥ 3f + 1` |
| **Détection puis correction** d'une erreur quelconque | Codes correcteurs : redondance + distance de Hamming |
| **Probabilité d'erreur qui décroît exponentiellement** avec l'effort | Théorie de l'information + agrégation de vérificateurs indépendants |
| **Détection de toute erreur introduite** (pas de non-détection silencieuse) | Oracles cachés + rejeu déterministe des journaux |

La formulation honnête et vérifiable de ton objectif est donc :

> **JIOJIO-TERMINATOR ne promet pas zéro erreur. Il garantit qu'aucune erreur ne passe
> silencieusement : elle est détectée, localisée, attribuée, corrigée, ou le système s'abstient
> explicitement en le disant.**

C'est infiniment plus fort qu'« ça se trompe jamais », et c'est **démontrable**.

---

## 1. Le vrai problème : les erreurs corrélées

La raison pour laquelle « demande au modèle de se relire » ne marche pas est mathématique, pas empirique.

Soit `G` le générateur et `C` le critique. Si `C` est le **même modèle**, dans le **même contexte**,
avec les **mêmes biais**, alors l'information mutuelle `I(G;C)` est élevée : le critique ne sait
rien de plus que le générateur. Il **valide l'erreur avec confiance**.

> **Loi fondamentale de JIOJIO-TERMINATOR :**
> *Un vérificateur ne vaut que par ce qui le distingue du générateur.*

Donc tout vérificateur doit satisfaire au moins une **condition de décorrélation** :

- **D1 — Séparation de contexte** : le critique ne voit que l'artefact, jamais la chaîne de raisonnement.
  (revue aveugle)
- **D2 — Séparation de modèle** : famille, taille ou fournisseur différents.
- **D3 — Séparation de rôle** : persona adversariale, objectif explicitement opposé.
- **D4 — Ancrage externe** : le critique exécute, compile, mesure, cherche — il ne *croit* pas.
- **D5 — Séparation métamorphique** : le critique transforme l'entrée et teste l'invariance.

C'est la différence entre « relis-toi » (inutile) et un vrai système de vérification.

---

## 2. Les 14 principes mathématiques fondateurs

Ceux-ci ne sont pas décoratifs : chacun est implémenté par un composant précis.

| # | Principe | Fondement | Composant JIO |
|---|---|---|---|
| 1 | **Décorrélation** | Théorie de l'information (erreurs corrélées) | `BlindReview`, registre de diversité |
| 2 | **Redondance + distance** | Codes correcteurs, distance de Hamming | Consensus n agents, `HammingGate` |
| 3 | **Quorum byzantin** | `n ≥ 3f+1` (Lamport) | `ConsensusEngine` : seuil dynamique selon f estimé |
| 4 | **Couverture garantie** | Prédiction conforme (Vovk) | `ConformalGate` : `Pr[erreur ∧ accepté] ≤ α` |
| 5 | **Entropie sémantique** | Shannon sur clusters de sens | `SemanticEntropy` (clustering par entailment bidirectionnel) |
| 6 | **Invariance métamorphique** | Test métamorphique (Chen, 1998) | `MetaQA` : 12 mutants de requête, échec si non-invariance |
| 7 | **Attribution de blâme** | Jeux coopératifs — Shapley (`Σφᵢ = v(N)`) | `BlameLedger` : localisation du premier pas fautif |
| 8 | **Exploration/exécution optimale** | Bandits, UCT (Monte-Carlo Tree Search) | `LATSSearch` : budget d'inférence alloué, pas gaspillé |
| 9 | **Stabilité de la correction** | Théorie du contrôle (systèmes à retard) | `OscillationGuard` : hystérésis, amortissement, escalade |
| 10 | **Évolution Pareto** | Optimisation multi-objectif | `PromptEvolution` (GEPA) : frontière de prompts, pas un seul |
| 11 | **Synthèse par contre-exemples** | CEGIS (Solar-Lezama) | `GuardrailSynthesis` : génère → trouve un contre-exemple → raffine |
| 12 | **Causalité vs corrélation** | Calcul du (do-calculus, Pearl) | `CounterfactualProbe` : « et si cet agent avait été retiré ? » |
| 13 | **Description minimale** | MDL / Kolmogorov | `OccamGate` : rejette les solutions taillées pour les tests |
| 14 | **Confiance bayésienne** | Inférence bayésienne, Thompson sampling | `TrustRouter` : apprend quel modèle est fiable *sur quel type de tâche* |

---

## 3. Architecture en 7 couches

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ L7  INTERFACES        CLI `jio`  ·  TUI ASCII-art  ·  Dashboard web  ·  API   │
├──────────────────────────────────────────────────────────────────────────────┤
│ L6  ÉCOSYSTÈME        Écrit les artefacts natifs :                           │
│                       .opencode/agents/*.md · Hermes SKILL.md tap ·          │
│                       CLAUDE.md · AGENTS.md · GEMINI.md · .cursor/rules ·    │
│                       .github/copilot-instructions.md · MCP servers          │
│                       → TOUS tes outils partagent le même cerveau            │
├──────────────────────────────────────────────────────────────────────────────┤
│ L5  MÉMOIRE           skills auto-générées · erreurs passées · kalim         │
│                       frontière Pareto de prompts · TrustRouter bayésien     │
├──────────────────────────────────────────────────────────────────────────────┤
│ L4  AUDIT             Red-team adversarial · BlameLedger (Shapley) ·         │
│                       IntegrityMonitor (anti-reward-hacking) ·               │
│                       ConformalGate · OscillationGuard                       │
├──────────────────────────────────────────────────────────────────────────────┤
│ L3  VÉRIFICATION      Preuve exécutable (tests/lint/typecheck/mutation) ·    │
│                       MetaQA métamorphique · SemanticEntropy ·               │
│                       ClaimLedger (claims atomiques + provenance) ·          │
│                       LATSSearch (best-of-N vérifié)                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ L2  ORCHESTRATION     Boucle générer→vérifier→auditer→corriger→re-vérifier · │
│                       ConsensusEngine (quorum 3f+1) · MAR (critiques à      │
│                       personas) · Scheduler · Budget d'inférence             │
├──────────────────────────────────────────────────────────────────────────────┤
│ L1  SÉCURITÉ          Trust tiers (system/user/externe) · Spotlighting ·     │
│                       Dual-LLM planificateur/exécuteur · Capability gating · │
│                       Rule of Two · Hachage des schémas MCP                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ L0  SOCLE             Providers (API · CLI subprocess · Ollama · simulé) ·   │
│                       Journal d'événements rejouable · Hash-chaîne d'audit   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Pourquoi L1 (Sécurité) est sous L2 (Orchestration)

Parce qu'un dépôt que l'IA lit **est une surface d'attaque**. Les CVE 2025-2026 sont sans ambiguïté :
GitHub Copilot (CVE-2025-53773), Claude Code (CVE-2025-55284), Cursor (CVE-2025-54132) — toutes des
injections indirectes via des fichiers du dépôt, menant à RCE ou exfiltration.
Les attaques adaptatives dépassent **85 %** des défenses par détection.

> **Seule classe de défense avec une revendication de sécurité prouvable : l'isolation architecturale.**
> Pas le filtrage. Pas la modération. L'architecture.

Donc : contenu externe → **quarantaine**. Un tour qui a ingéré du contenu non fiable ne peut pas
appeler un outil d'écriture ou d'exécution sans confirmation. C'est la **Rule of Two** de Meta,
appliquée en dur.

---

## 4. La boucle centrale (le cœur)

```
                  ┌───────────────────────────────────────────┐
                  │            MISSION (objectif)             │
                  └────────────────────┬──────────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
              ┌────►│  1. SPÉCIFICATION (SPEC grounding)   │
              │     │  Découper en RÈGLES ÉNUMÉRÉES         │
              │     │  → 1 test par règle (spec-complete)  │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │     ┌──────────────────────────────────────┐
              │     │  2. GÉNÉRATION (N candidats)         │
              │     │  best-of-N, températures variées,    │
              │     │  modèles hétérogènes                 │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │     ┌──────────────────────────────────────┐
              │     │  3. PREUVE EXÉCUTABLE  ⟵ FAIL-CLOSED │
              │     │  compile · tests · types · lint ·    │
              │     │  mutation · property-based           │
              │     │  Pas de témoin ⇒ REJET, pas "peut-être" │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │     ┌──────────────────────────────────────┐
              │     │  4. AUDIT MULTI-AGENTS (décorrélé)   │
              │     │  Verifier · Skeptic · Logician ·     │
              │     │  Red-Team · Historien                │
              │     │  Revue AVECULE · contextes séparés   │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │     ┌──────────────────────────────────────┐
              │     │  5. CONSENSUS (quorum n ≥ 3f+1)      │
              │     │  désaccord ⇒ escalade, JAMAIS de    │
              │     │  moyenne silencieuse                 │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │     ┌──────────────────────────────────────┐
              │     │  6. GARDE CONFORME + OSCILLATION     │
              │     │  Pr[erreur ∧ accepté] ≤ α ?          │
              │     │  Amélioration monotone ?             │
              │     │  Sinon ⇒ ABSTENTION EXPLICITE        │
              │     └──────────────────┬───────────────────┘
              │                        ▼
              │              ┌─────────────────┐
              │              │  ACCEPTÉ ?      │
              │              └────┬───────┬────┘
              │             NON   │       │  OUI
              └───────────────────┘       ▼
        (Consensus Reflection MAR)  ┌──────────────────────────┐
        (blâme + correction ciblée) │ 7. INTÉGRITÉ + MÉMOIRE  │
                                    │ Oracles CACHÉS (rejeu)   │
                                    │ → triche détectée ?      │
                                    │ → skill auto-générée     │
                                    │ → prompt évolué (GEPA)   │
                                    │ → TrustRouter mis à jour │
                                    └────────────┬─────────────┘
                                                 ▼
                                         LIVRAISON
```

**Différence clé avec tout ce qui existe :** à chaque tour de boucle, le système **apprend**.
Une erreur produit simultanément (a) une correction ciblée, (b) un blâme attribué mathématiquement,
(c) une entrée de mémoire, (d) un candidat de règle de garde, (e) un signal pour l'évolution des prompts.
L'erreur ne peut pas se reproduire à l'identique.

---

## 5. Les 24 techniques anti-erreur (implémentées, pas citées)

### Groupe A — Casser la corrélation
1. **Revue aveugle** — le critique n'a jamais accès au raisonnement du générateur.
2. **MAR (Multi-Agent Reflexion)** — personas divergentes + juge qui synthétise une
   *Consensus Reflection*. Corrige la « dégénérescence de pensée » (HumanEval 76.4 → 82.6).
3. **Hétérogénéité forcée** — refus d'exécuter un consensus si tous les agents partagent le modèle.
4. **Contextes séparés** — génération et évaluation dans des fenêtres distinctes.

### Groupe B — Prouver plutôt que croire
5. **Preuve exécutable obligatoire** — aucun claim sans commande + sortie + hash.
6. **SPEC grounding** — 1 test par règle énumérée. Effet mesuré : **+38 pts** de code correct,
   fausses alertes **33 % → 0 %**. C'est l'optimisation la plus rentable connue.
7. **Tests par propriétés** (Hypothesis) — cherche les contre-exemples, ne les attend pas.
8. **Mutation testing** — teste la *qualité des tests* : un mutant qui survit = trou dans la suite.
9. **Vérification formelle optionnelle** — Dafny/Lean/TLA+/Z3 pour les invariants critiques.
10. **Contrats d'exécution** (design by contract) — pré/postconditions transformées en assertions.

### Groupe C — Détecter ce qui échappe au test
11. **MetaQA / métamorphique** — 12 mutations (paraphrase, négation, unités, ordre, contrefactuel,
    perturbation d'entité). SelfCheckGPT échoue car le modèle **répète** son hallucination ;
    la mutation casse la répétition.
12. **Entropie sémantique** — clustering par entailment bidirectionnel, puis entropie de Shannon
    sur les clusters. Haute entropie = confabulation probable.
13. **ClaimLedger / ProvenanceGuard** — décomposition en claims atomiques, routage de chacun vers
    sa preuve, vérification d'attribution, **fail-closed** si un claim n'est pas ancré.
14. **Process reward (vérification par étape)** — pas seulement le résultat : chaque étape est notée.
    Remède documenté à l'accumulation d'erreurs sur horizon long.

### Groupe D — Garanties statistiques
15. **ConformalGate** — abstention calibrée : `Pr[erreur ∧ accepté] ≤ α`, sans hypothèse de
    distribution, avec peu d'exemples étiquetés. **C'est la seule vraie garantie du système.**
16. **Calibration conformité-robuste** — la conformité sociale entre agents **casse** la couverture
    conforme (90 % → 74 %). D'où l'interdiction de la pression sociale dans le débat.

### Groupe E — Anti-triche et anti-Goodhart
17. **Oracles cachés** — suite de tests dans un répertoire hors sandbox, jamais lisible par l'agent.
18. **Rejeu déterministe du journal** — classification automatique de 6 types d'exploit :
    leakage de métadonnées · altération de vérificateur · manipulation de séquence ·
    proxy gaming (JSON minimal) · special-casing · copie mémorisée.
    Les modèles RL-hackent dans **50-96 %** des rollouts : ce n'est pas théorique.
19. **OccamGate (MDL)** — la solution qui passe les tests *visible* mais est anormalement
    courte/spécifique est suspectée de special-casing.
20. **Test de généralisation** — les tests cachés utilisent des entrées **différentes** de celles vues.

### Groupe F — Apprendre de chaque erreur
21. **Mémoire des échecs** — base indexée par signature d'erreur, réinjectée dans les prompts.
22. **Skills auto-générées** (modèle Hermes) — après 5+ appels d'outil ou une correction utilisateur,
    une `SKILL.md` est écrite : Procédure, Pièges, Vérification.
23. **Évolution de prompts GEPA** — réflexion sur les traces d'échec + sélection Pareto.
    Bat le RL (GRPO) de 10-20 % avec **35× moins de rollouts**. 20-100 exemples suffisent.
24. **Synthèse de garde-fous par CEGIS** — mine les faux positifs/négatifs des traces, induit
    un prédicat, raffine. Les règles de sécurité s'écrivent toutes seules.

### Groupe G — Stabilité et non-régression
25. **OscillationGuard** — la dose de vérification a un **seuil de stabilité** (résultat de théorie
    du contrôle sur systèmes à retard). Trop corriger déstabilise par un mode oscillatoire.
    → hystérésis, détection de flip-flop, escalade au lieu de boucler.
26. **Plafond d'itérations + meilleur effort** — jamais de boucle infinie, toujours un résultat
    avec indicateur d'échec explicite.
27. **Non-régression obligatoire** — toute correction doit passer *en plus* toute la suite existante.

---

## 6. L'amplificateur de capacité (le point qui répond à ton objectif)

Tu veux que les IA atteignent le niveau des meilleurs modèles, **et aillent plus loin**.

Ce n'est pas de la magie : c'est du **scaling au temps d'inférence** bien organisé.
Un modèle donné a une distribution de réussite `p` par tentative. Les leviers :

| Levier | Effet | Coût |
|---|---|---|
| `best-of-N` + vérificateur | `1-(1-p)^N` sur les tâches vérifiables | ×N appels |
| Recherche arborescente (LATS)  | Explore, évalue, **backtrack** | ×N + évaluation |
| Décomposition en sous-tâches | Réduit la profondeur de raisonnement requise | faible |
| Évolution de prompts (GEPA) | Améliore la *distribution* `p` elle-même | hors-ligne, amorti |
| Mémoire de skills | Amortit les tâches récurrentes | une fois puis gratuit |
| Consensus décorrélé | Corrige les cas où `p` est moyenne | ×3 à ×5 |

**Résultat visé :** un modèle local à `p = 0.35` sur une tâche de code, passé dans la boucle complète
(best-of-5 + preuve exécutable + audit + consensus), produit une réponse finale correcte dans une
large majorité des cas. Ce n'est pas du niveau « Opus », c'est **au-dessus sur cette tâche**, parce que
la vérification est *externe* et *adversariale* — ce qu'aucun modèle seul ne peut faire sur lui-même.

> La force de JIOJIO-TERMINATOR n'est pas de remplacer les grands modèles.
> C'est de rendre la **vérification** indépendante de la puissance du modèle.

---

## 7. Carte d'écosystème : où JIO s'installe

| Outil | Artefact produit | Bénéfice |
|---|---|---|
| **opencode** | `.opencode/agents/*.md` + `opencode.json` | 20 sous-agents (red-team, verifier, spec-writer…) utilisables directement |
| **Hermes Agent** | `~/.hermes/skills/<cat>/<skill>/SKILL.md` (tap installable) | Skills anti-erreur + auto-génération + cron/blueprints |
| **Claude Code** | `CLAUDE.md` | Le protocole anti-erreur à chaque session |
| **Codex / agents génériques** | `AGENTS.md` | Standard ouvert, même cerveau |
| **Gemini CLI** | `GEMINI.md` | idem |
| **Cursor** | `.cursor/rules/*.mdc` | idem |
| **GitHub Copilot** | `.github/copilot-instructions.md` | idem |
| **N'importe quel client MCP** | serveur MCP `jio` | `jio_verify`, `jio_audit`, `jio_consensus`, `jio_prove` en outils |

**Un seul `jio sync` propage le cerveau anti-erreur dans tout l'écosystème.** (Il écrit les artefacts de tous les dialectes et branche le serveur MCP ; il préserve tout fichier qui ne porte pas sa marque.)

---

## 8. Ce que JIOJIO-TERMINATOR n'est PAS

- ❌ Un wrapper qui appelle 5 LLM en parallèle et fait une moyenne.
- ❌ Un « framework multi-agents » de plus (il y en a 200).
- ❌ Un système qui prétend ne jamais se tromper.
- ❌ Un outil lié à un fournisseur.

## 9. Ce qu'il EST

- ✅ Un **noyau de vérification** fail-closed, indépendant du modèle.
- ✅ Une **boucle auto-correctrice** qui apprend de chaque erreur.
- ✅ Une **couche de sécurité architecturale** contre l'injection de prompt.
- ✅ Un **hub** qui donne le même cerveau à tous tes outils.
- ✅ Une **implémentation des meilleures techniques 2023-2026**, assemblées pour la première fois.

---

*Suite : [`DOSSIER-TECHNIQUES.md`](DOSSIER-TECHNIQUES.md) (sources et preuves),
[`ROADMAP.md`](ROADMAP.md) (plan de construction par phases).*
