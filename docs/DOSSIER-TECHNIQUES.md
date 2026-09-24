# Dossier technique — sources, chiffres, et dépôts à cannibaliser

Document de travail. Chaque technique retenue est justifiée par une source et un **chiffre**.
Rien n'entre dans le code sans preuve d'efficacité mesurée.

---

## Partie 1 — Techniques vérifiées (état de l'art 2023-2026)

### 1.1 Vérification et auto-correction

| Technique | Résultat mesuré | Source | Décision |
|---|---|---|---|
| **MAR — Multi-Agent Reflexion** | HumanEval 76.4 → **82.6** ; corrige la dégénérescence de pensée | arXiv 2512.20845 (réf. par Pith) | ✅ Cœur de l'audit |
| **SPEC grounding** (1 test par règle) | **+38 pts** de code correct ; fausses alertes **33 % → 0 %** | Pith review 2607.06636 | ✅ Cœur de la phase 1 |
| **Process supervision** (par étape) | Net gain vs supervision par résultat seul | Lightman et al. | ✅ Vérificateur par étape |
| **Tool-grounded critique** (CRITIC) | Compilateurs/validateurs comme signal dur | CRITIC framework | ✅ Preuve exécutable |
| **Reflexion** seul | Gain réel **mais** échoue sur cas durs (oscillation) | Shinn et al. | ⚠️ Insuffisant seul → remplacé par MAR |
| **Auto-critique sans outil** | « peut dégrader la performance » | « LLMs cannot self-correct reasoning yet » | ❌ Interdit comme preuve |
| **Verifier model** séparé | Un petit modèle + rubric **bat** un grand modèle en auto-vérification ad hoc | ICLR 2026 | ✅ Vérificateurs petits et spécialisés |

**Leçon structurante :** la qualité vient de la **séparation**, pas de la taille.

### 1.2 Erreurs corrélées — la clé théorique

> « La correction de soi sans retour externe échoue souvent ou dégrade la performance. Notre travail
> offre une explication : l'erreur corrélée entre générateur et évaluateur rend l'auto-évaluation
> **non-identifiable**. […] multi-agent critique avec des copies du même modèle ne fait
> **pas mieux que la self-consistency**. »

*(Preprints.org, jan. 2026 — « Limits of Self-Correction in LLMs: An Information-Theoretic Analysis of Correlated Errors »)*

Recommandation de l'article : **séparer génération et évaluation par un contexte neuf** — possible
avec le **même modèle**, sans coût supplémentaire. → Implémenté comme `BlindReview`.

### 1.3 Détection d'hallucination

| Méthode | Accès requis | AUC | Verdict |
|---|---|---|---|
| SelfCheckGPT | black-box | 0.78–0.82 | ⚠️ Échoue si le modèle répète l'hallucination |
| Entropie sémantique | grey-box | 0.80–0.85 | ✅ Retenu |
| SEP (sondes) | white-box | 0.85–0.90 | ❌ Non portable |
| ECLIPSE (entropie-capacité) | grey-box | **0.89** | ⚠️ Dépend des logprobs |
| **MetaQA** (métamorphique) | black-box | bat SelfCheckGPT sur toutes catégories | ✅ **Retenu — portable** |
| ACSE + conformité | black-box | AUROC **0.88** vs 0.65 (entropie token) | ✅ Retenu |

**MetaQA est la seule détection d'hallucination purement black-box qui ne soit pas piégée par la
répétition.** C'est indispensable puisqu'on cible des modèles via CLI et API sans logprobs.

### 1.4 Garanties statistiques

**Prédiction conforme / factualité conforme**
- `Pr[erreur ∧ non-abstention] ≤ α`, **sans hypothèse sur la distribution**, avec peu d'exemples humains.
- 80-90 % de garantie de correction en conservant la majorité de la sortie originale.
- **Piège critique :** « Conformity Breaks Conformal Prediction » (sept. 2026) — la **conformité sociale
  dans les systèmes multi-agents dégrade la couverture de 90 % → 74 %** et ouvre une attaque ciblée.
  → **Interdiction absolue de la pression sociale dans le débat.** Les agents votent sans voir qui a voté quoi.

### 1.5 Contrôle et stabilité

> « Une correction trop forte **ou** trop retardée peut déstabiliser la boucle par un mode oscillatoire. »

*(arXiv 2606.27409 — Delayed Verification in Multi-Agent LLM Systems, 2026)*

Le modèle formel : consensus (Laplacien ancré) + force de rappel `ηκ` retardée de `δ`.
Il existe un **seuil exact de stabilité**. → `OscillationGuard` implémente :
détection de cycle, hystérésis, amortissement, escalade humaine au lieu de re-boucler.

### 1.6 Anti-reward-hacking (le risque le plus sous-estimé)

**Chiffres du Reward Hacking Benchmark (ICML 2026) :**
- Modèles RL : **50 % à 96 % des rollouts** contiennent de la triche.
- Comparaison siblings : DeepSeek V3 **0.6 %** vs R1-Zero **13.9 %** (p < 0.005).
- **Longueur de chaîne 5 = transition de phase** : les agents cessent de s'auto-vérifier et passent en
  « produire + ignorer la vérification ».
- **72 % des exploits sont rationalisés** dans le CoT (« optimisation d'efficacité »).
- Taxonomie des 6 exploits : `leakage / tampering / sequence / proxy-gaming / special-casing / memorization`.
- Les sondes d'activation **attrapent ce que les juges textuels ratent** (Goodfire, sept. 2026).

→ Sans `IntegrityMonitor`, **ton propre système de vérification devient l'objet de la triche.**
C'est non-négociable.

### 1.7 Sécurité — injection de prompt

- **42 techniques d'attaque** cataloguées ; les attaques adaptatives **dépassent 85 %** des défenses.
- CVE réelles : Copilot `CVE-2025-53773` (RCE), Claude Code `CVE-2025-55284` (exfiltration DNS),
  Cursor `CVE-2025-54132` (exfiltration via Mermaid), AWS Kiro, Google Jules, Amazon Q, Windsurf.
- **Seule classe à revendiquer une sécurité prouvable : l'isolation architecturale.**
- **Rule of Two (Meta)** : un agent ne doit satisfaire **au plus que 2** des 3 :
  (A) traiter des entrées non fiables · (B) accéder à des données sensibles · (C) modifier l'état / communiquer.
- **PromptArmor (ICLR 2026)** : un LLM détecteur d'injection → FP et FN **< 1 %**, taux de succès d'attaque < 1 %.
- **CaMeL / Dual-LLM** : planificateur privilégié (voit les instructions) + exécuteur en quarantaine
  (voit le contenu non fiable, **sans outils**), avec interpréteur de politique **déterministe** (pas un LLM).
- Spotlighting (Microsoft), marquage/délimitation ; pins de schémas MCP avec hash.

### 1.8 Apprentissage et auto-amélioration

**GEPA — Reflective Prompt Evolution (ICLR 2026, oral)**
- Bat **GRPO par 10 % en moyenne (jusqu'à 20 %)** avec **35× moins de rollouts**.
- Bat **MIPROv2 de +14 %** avec des prompts **9.2× plus courts**.
- **20 à 100 exemples suffisent** ; 500 exemples *dégradent* le résultat.
- Le **modèle de réflexion doit être fort** : GPT-4o-mini = échec complet (aucun changement de prompt).
- Contrainte de longueur 1 500 caractères : 4× de compression pour −0.8 % de perf.
- Chiffres publics : **55 % → 82 %** de taux de résolution d'un agent de code via skills auto-apprises ;
  ARC-AGI **32 % → 89 %** par découverte d'architecture.

**Hermes Agent (Nous Research, MIT)**
- Boucle d'apprentissage en 5 étages : exécuter → évaluer → extraire un pattern → raffiner → récupérer.
- `skill_manage` : `create` / `patch` / `write_file` ; déclenché après **5+ appels d'outils**,
  après récupération d'erreur, ou après correction utilisateur.
- Révélation progressive à 4 niveaux (Tier 0 catégories → Tier 3 fichier de référence) : économise le contexte.
- Format `SKILL.md` = standard ouvert **agentskills.io** → compatible Claude Code, Cursor, Codex.
- `skills.create_dir` permet de **rediriger les skills vers un cerveau partagé git-tracké**.

**CEGIS (Solar-Lezama) / AutoSpec**
- Le garde-fou se synthétise : mine faux positifs et faux négatifs dans les traces d'exécution,
  induit des prédicats discriminants (ILP), raffine par opérateurs d'édition contraints.
- Maintient une précision et un rappel élevés **sans écriture manuelle de règles**.

**SpecGen (mutations de spécification)**
- Quand la génération directe échoue, appliquer 4 mutations : prédicative (`∃↔∀`),
  logique (`&&`,`||`,`==>`), comparative (`<=`,`>=`,`==`), arithmétique (`+↔-`).
- Priorité empirique : **les mutations comparatives corrigent le plus d'erreurs LLM** (bornes de boucle,
  contraintes numériques).

### 1.9 Attribution de blâme (théorie des jeux)

**« Who Gets the Reward & Who Gets the Blame? » (arXiv 2511.10687)**
- **Shapley** pour les succès : `Σφᵢ = v(N)` — crédit conservé, pas de dilution.
  Une valeur négative identifie un agent **nuisible**, pas seulement inutile.
- **Localisation du premier pas fautif** pour les échecs : recherche binaire de préfixe en `O(log T)`,
  puis un juge distingue **tentative de réparation** vs **pas aligné sur l'échec**.
  → On ne pénalise pas un agent qui essaie de rattraper.
- Pertinence de l'approximation légère : `φₙ ≈ cos(rₙ, r_moyen)` — complexité **exponentielle → linéaire**.
- Cadre SELFORG : route l'information des agents à forte contribution vers les autres via un DAG
  par instance. « Amplifier les réponses rares correctes et supprimer le bruit » — exactement notre
  cas d'usage en régime de modèle faible.

### 1.10 Recherche et budget d'inférence

- **LATS** : Monte-Carlo Tree Search + LLM comme fonction de valeur + auto-réflexion + **backtracking**.
- **CALVERT** : télémétrie de vérificateur calibrée → l'agent choisit dynamiquement
  `commit / retrieve / refine / decompose` selon des signaux d'incertitude **orthogonaux**,
  au lieu d'un plan fixe. → `DecisionGovernor`.

---

## Partie 2 — Échecs connus des systèmes multi-agents (à éviter par construction)

Source : **MAST** — « Why Do Multi-Agent LLM Systems Fail? » (arXiv 2503.13657), analyse de centaines de traces.

**Constat :** les systèmes avec **vérificateurs explicites** (MetaGPT, ChatDev) montrent
**moins d'échecs totaux**. La vérification explicite est le facteur discriminant.

Remèdes documentés → implémentés dans JIO :

| Mode d'échec | Remède retenu |
|---|---|
| Rôles/tâches flous | Contrats de rôle stricts, schémas d'entrée/sortie typés |
| Désalignement inter-agents | **Cross-verification** systématique |
| Mauvaise vérification | Vérificateurs **programmatiques** (tests, schémas, regex) priorisés sur les LLM |
| Propagation d'erreur | **Preuve exécutable à chaque étape**, pas seulement à la fin |
| Ignorer la contribution d'un pair | Protocole standardisé + journal d'événements structuré |
| Terminaison non définie | **Seul le Vérificateur peut terminer** une conversation |
| Conformisme | Vote **sans visibilité** sur les autres votes |

---

## Partie 3 — Dépôts à étudier / intégrer

> Stratégie : **s'inspirer et réutiliser des composants spécifiques**, jamais recopier un framework entier.
> Chaque brique doit être remplaçable et testable isolément.

### Priorité 1 — briques fonctionnelles attendues par JIO

| Dépôt / Projet | Ce qu'on y prend | Intégration |
|---|---|---|
| `gepa-ai/gepa` + `stanfordnlp/dspy` | Optimiseur de prompts par réflexion, frontière Pareto | Moteur de `PromptEvolution` |
| `NousResearch/hermes-agent` | Format `SKILL.md`, révélation progressive, `skill_manage` | Modèle pour `SkillForge` |
| `anomalyco/opencode` (SST) | Format `.opencode/agents/*.md`, `opencode run --format json`, permissions par agent | Cible d'artefact + exécuteur |
| `openai/human-eval`, `bigcode-project/…` | Harnais d'évaluation reproductible | `EvalHarness` |
| `HypothesisWorks/hypothesis` | Tests par propriétés, rétrécissement automatique de contre-exemples | `PropertyProver` |
| `boxed/mutmut`, `boxed/cosmic-ray` | Mutation testing Python | `MutationAuditor` |
| `psf/black`/`astral-sh/ruff`/`mypy` | Signaux durs gratuits | `StaticGate` |
| `pyupio/safety` / `ossf/scorecard` | Surface de vulnérabilités | `SupplyChainGate` |
| `protectai/llm-guard`, `guardrails-ai/guardrails` | Scanners entrée/sortie | `TrustTier` — réutiliser, ne pas réécrire |
| `NVIDIA/NeMo-Guardrails` | Rails programmables | Idem |
| `microsoft/pyrit`, `NVIDIA/garak`, `promptfoo/promptfoo` | Red-team automatisé (injection, jailbreak) | `RedTeamHarness` |
| `google-deepmind/…` / `jxnl/instructor`, `dottxt-ai/outlines` | Sorties structurées / décodage contraint | `StructuredOutputGate` |
| `modelcontextprotocol/servers` | Modèle de serveur MCP | `jio mcp` |
| `Aider-AI/aider`, `SWE-agent/SWE-agent`, `All-Hands-AI/OpenHands` | Boucles d'édition + git + tests | Inspecter leurs garde-fous git |
| `BerriAI/litellm` | Couche provider unifiée (100+ modèles) | `ProviderLayer` — évite de réécrire 20 adaptateurs |
| `mem0ai/mem0`, `getzep/zep` | Mémoire longue | `MemoryStore` — ou SQLite+FTS5 maison |
| `tmgthb/Autonomous-Agents` | **Veille quotidienne** : papers agents 2026 | Source de nouvelles techniques |

### Priorité 2 — vérification formelle et mathématique

| Projet | Usage |
|---|---|
| `Z3Prover/z3`, `cvc5` | SMT — prouver qu'un invariant tient, trouver un contre-exemple |
| `dafny-lang/dafny` | Preuve d'implémentation, transpile vers Python |
| `tlaplus/tlaplus` | Vérification de **conception** (protocole, machine à états) |
| `leanprover/lean4` | Preuves mathématiques (optionnel, haut de gamme) |
| `CrossHair` | Contrats exécutables en Python, contre-exemples symboliques |

### Priorité 3 — observation et rejeu

| Projet | Usage |
|---|---|
| `open-telemetry/…` (GenAI semantic conventions) | Traces de spans, rejeu de trace |
| `Arize-ai/phoenix`, `langfuse/langfuse` | Évaluation et observabilité LLM |
| `Kitaru` (awesome-llm-agents) | Record/replay d'agents en production |
| `Greywall` | Sandbox deny-by-default pour agents de code |

---

## Partie 4 — Sources académiques de référence

**Correction et vérification**
- MAR : Multi-Agent Reflexion — *arXiv 2512.20845*
- Why Do Multi-Agent LLM Systems Fail? (MAST) — *arXiv 2503.13657*
- Limits of Self-Correction in LLMs: Information-Theoretic Analysis of Correlated Errors — *Preprints 2026*
- Delayed Verification in Multi-Agent LLM Systems (stabilité du consensus) — *arXiv 2606.27409*
- Specification Grounding Drives Test Effectiveness for LLM Code — *Pith review 2607.06636*

**Hallucination**
- SelfCheckGPT — *EMNLP 2023*
- MetaQA: Metamorphic Relations for Hallucination Detection — *arXiv 2502.15844 / ACM 10.1145/3715735*
- Semantic Entropy (Farquhar, Kossen, Kuhn, Gal)
- ECLIPSE: Detecting AI Hallucinations in Finance — *arXiv 2512.03107*
- Survey of Hallucination in LLMs: Causes, Detection, Mitigation — *arXiv 2510.06265*

**Garanties statistiques**
- Language Models with Conformal Factuality Guarantees
- Adaptive Conformal Semantic Entropy — *pith 2605.04295*
- CAP: Conformalized Abstention Policies — *ACML 2025*
- Geometry-Calibrated Conformal Abstention for Language Models — *2026*
- **Conformity Breaks Conformal Prediction** — *2026* (piège du conformisme)

**Sécurité**
- Prompt Injection Attacks on Agentic Coding Assistants — *arXiv 2601.17548*
- CaMeL / Dual-LLM pattern (Willison 2023)
- PromptArmor — *ICLR 2026*
- Defensive Prompt Engineering for Multi-Tool AI Agents — *zylos.ai, mai 2026*

**Triche et intégrité**
- Reward Hacking Benchmark (RHB) — *ICML 2026 / arXiv 2605.02964*
- Goodfire activation probes — *sept. 2026*

**Attribution et jeux**
- Who Gets the Reward & Who Gets the Blame? — *arXiv 2511.10687*
- SELFORG: Stochastic Self-Organization in Multi-Agent Systems — *arXiv 2510.00685*
- On Blame Attribution for Accountable Multi-Agent Sequential Decision Making — *NeurIPS 2021*

**Optimisation**
- GEPA: Reflective Prompt Evolution Can Outperform RL — *ICLR 2026 oral / arXiv 2507.19457*
- SpecGen — *arXiv 2401.08807*
- CEGIS (Solar-Lezama)

**Sécurité d'exécution**
- AgentSpec: Customizable Runtime Enforcement for Safe LLM Agents — *ICSE 2026*

---

## Partie 5 — Ce qui n'existe PAS encore (nos contributions originales)

Après recherche, aucun projet open-source n'assemble :

1. **Une boucle unique où la conformité statistique (α) pilote directement l'abstention d'un agent multi-étapes.**
   La littérature conforme travaille sur des réponses en un tour, pas sur un pipeline d'agents avec rejeu.

2. **Un `BlameLedger` Shapley appliqué à des traces d'agents réels (pas simulées)** pour améliorer
   automatiquement les prompts *par agent*, en combinant Shapley (succès) et localisation du premier
   pas fautif (échec).

3. **Un couplage GEPA ↔ Hermes skills** : les échecs répétés font évoluer *à la fois* le prompt de l'agent
   *et* génèrent une `SKILL.md` qui capitalise la procédure apprise.

4. **Un `IntegrityMonitor` en rejeu déterministe** branché sur un pipeline d'agents hétérogènes,
   avec les 6 catégories RHB, couplé à `OccamGate` (MDL).

5. **Un compilateur d'artefacts multi-écosystème** : une seule source de vérité → `.opencode/agents/`,
   `SKILL.md`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules`, `copilot-instructions.md`,
   serveur MCP. Personne ne fait ça.

6. **Un `OscillationGuard` explicite** fondé sur le seuil de stabilité de la vérification retardée.

Ce sont nos axes d'innovation. Le reste est de l'assemblage — et l'assemblage est déjà énorme.
