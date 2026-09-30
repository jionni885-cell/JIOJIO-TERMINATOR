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

---

## Partie 6 — Dépôts GitHub vérifiés pendant les chantiers de mesure

Chaque dépôt ci-dessous a été **vérifié par l'API GitHub** (nom complet, étoiles, date de
dernière poussée) au moment de l'écrire, et il répond à un blocage **nommé**, pas à une
intuition. Conformément à la consigne : on cite les dépôts utilisés, on n'en crée pas.

| Dépôt | Étoiles | Ce qu'il débloque, précisément | Statut ici |
|---|---|---|---|
| `huggingface/sentence-transformers` | 19 137 | Le rappel de la mémoire des échecs est **lexical** (recouvrement de tokens). Sur des objectifs libres — le vrai usage — deux formulations différentes du même problème ne se retrouvent pas. Des embeddings **locaux, sans clé** donneraient un rappel sémantique. | Non installé : dépendance lourde (torch), contraire à la doctrine « zéro dépendance » du dépôt. Documenté comme option. |
| `mem0ai/mem0` | 66 320 | Couche mémoire de production : **extraction, consolidation, décroissance**. Notre mémoire ne fait ni consolidation ni oubli gradué (elle tronque par le haut). | Référence de conception. |
| `statsmodels/statsmodels` | 11 665 | `NormalIndPower` donnerait un calcul d'**analyse de puissance** complet là où nous avons une formule fermée à deux proportions. Le budget d'essais est aujourd'hui vérifié empiriquement (56 calculés, 60 mesurés). | Non installé : la formule du dépôt suffit et reste sans dépendance. |
| `harbor-framework/terminal-bench-1` | 2 597 | Comparabilité avec un **banc public** (l'ancien `laude-institute/terminal-bench`). Ses tâches sont conteneurisées (Dockerfile, docker-compose, run-tests.sh, solution.sh). | Bloqué : **aucun Docker dans cet environnement**. C'est le seul chemin pour mesurer `Astra` face à des chiffres publiés. |
| `pyupio/safety`, `ossf/scorecard` | — | Surface de vulnérabilités des dépendances (voir Partie 4). | Déjà dans la liste. |

### Ce que la mémoire a appris, chiffres en main

| Mesure | Valeur | Où c'est prouvé |
|---|---|---|
| Portée du levier mémoire (part des appels de génération avertis) | **0 % → 99,3 %** | `tests/test_trust_memory.py::test_l_armement_survit_a_la_troncature_du_bloc` |
| Effet mesuré de la mémoire, régime `skill=0.4` | **+7,0 points** (85 % → 92 %) | README, protocole multi-cycles |
| Effet déclaré par la modélisation, même régime | **+7,9 points** (`portée × gain × compétence`) | `RapportCycles.gain_declare` |
| Budget pour démontrer un tel écart | **en PAIRES** (McNemar, puissance 80 %) — l'ancienne formule « essais par bras » ignorait l'appariement | `RapportCycles.essais_requis` |
| Contrôle positif (gain déclaré énorme) | **PROGRESSE**, +11 sur 60 essais | README, « un instrument doit savoir dire oui » |
| Contrôle négatif (gain nul) | écart **exactement 0** | `tests/test_cycles.py::test_avec_un_gain_NUL_le_chaud_egale_le_temoin_exactement` |

**La règle de lecture est écrite dans le rapport lui-même** : un écart nul avec une portée
faible ne dit rien de la mémoire (le levier n'était pas armé) ; un écart nul avec une portée
forte la condamne à ce niveau ; un écart non nul mais non démontré donne un **budget**, pas
une conclusion. Un banc ne tranche pas toujours, mais il doit dire ce qu'il peut trancher.

## Partie 7 — Le rappel de la mémoire : mesure, et ce qu'elle a corrigé

### Le constat

`FailureMemory.recall()` classait par **recouvrement de mots** (`|inter| / |union|`, Jaccard).
Mesuré sur un corpus de 61 souvenirs et 21 requêtes où **un seul identifiant technique**
(`F541`, `mcnemar_exact`, `O_EXCL`) distingue la bonne cible des distracteurs qui partagent
tout le reste du vocabulaire :

| Classement | recall@1 | recall@3 | MRR |
|---|---|---|---|
| recouvrement de mots (Jaccard) — témoin | **5 %** | 5 % | 0,114 |
| **BM25 normalisé** (rareté × saturation × longueur) | **100 %** | 100 % | **1,000** |

Et la conséquence, mesurée **de bout en bout** (les 61 textes passent par la vraie
`FailureMemory`, journal chaîné compris, puis `recall()` doit ramener le bon souvenir au
premier rang) : **5 %** de réussite avant câblage — la mémoire injectait le mauvais garde
tout en ayant l'air de fonctionner.

Contrôle **anti-triche** (le banc ne doit pas être fabriqué pour faire perdre le témoin) :
sur un corpus « jumeau » où chaque cible a un sosie qui **ne diffère que par l'identifiant**,
Jaccard réussit 100 % — l'échec du premier corpus ne vient donc pas du banc mais du régime
réel : plusieurs souvenirs partagent le vocabulaire d'un même sous-système, et seul
l'identifiant rare les sépare. C'est le régime où la mémoire devient utile *parce qu'elle
grandit*, celui qu'un score sans IDF ne peut pas atteindre.

### Pourquoi BM25, et pas des plongements vectoriels

- **Les identifiants techniques sont le signal.** BM25 place le bon document au rang 1 dans
  **40 requêtes sur 40** de type identifiant, là où un plongement dense y parvient 14 fois et
  en perd 8 complètement ([sesen.ai, BM25 vs Embeddings](https://sesen.ai/blog/bm25-vs-embeddings-hybrid-retrieval)).
- **La précision lexicale gagne sur la terminologie.** Sur des documents à terminologie
  précise, BM25 dépasse `text-embedding-3-large` sur toutes les métriques sauf `recall@20` ;
  la fusion hybride (RRF) est la meilleure ([From BM25 to Corrective RAG, arXiv 2604.01733](https://arxiv.org/pdf/2604.01733)).
- **La bascule à l'échelle se fait en faveur de BM25** : sur 28 paliers imbriqués (≈450×),
  BM25 dépasse la recherche agentique vers **10 M de jetons de corpus** et mène ensuite de
  près de 20 points ([aiweekly.co](https://aiweekly.co/alerts/bm25-beats-dense-retrieval-and-agents-by-20-points-at-scale)).
- **Zéro dépendance, zéro GPU, zéro clé.** Ici, aucune des deux n'est disponible : un
  plongement dense exigerait `sentence-transformers` + `torch`, soit ~2 Go absents de cette
  machine. BM25 tient en 80 lignes de Python pur, hors-ligne, et reste explicable dans un
  rapport (`idf × tf saturé`) — une exigence du dépôt depuis le premier jour.
- **Le score est normalisé dans [0, 1]** (part du meilleur score atteignable par la requête)
  pour que le seuil `min_score` garde le même sens d'une requête à l'autre ; un score brut de
  BM25 dépend du nombre de termes et de leurs IDF, et un seuil dessus se déplace en silence.

### Piste écartée par la mesure : la fusion hybride (RRF)

La littérature est claire : la **fusion RRF** de deux classements bat chacun isolément
(BM25 0,661 / dense 0,645 / **fusion 0,694** nDCG@10 ; BM25 parfait sur les identifiants,
le dense meilleur sur les paraphrases). Elle a donc été essayée ici, avec un « dense » sans
modèle : **cosinus de trigrammes de caractères**, qui ne demande ni `torch` ni clé API.

| Régime (recall@1) | BM25 seul | trigrammes de caractères | **fusion RRF** |
|---|---|---|---|
| (a) requêtes-identifiant | **100 %** | 5 % | 5 % |
| (b) requêtes-paraphrase | **60 %** | 60 % | 60 % |
| (c) mélange | **87 %** | 23 % | 23 % |

**Écartée.** La fusion ne gagne que si les deux classements se valent ; ici le second est
si faible qu'il *dilue* un classement déjà parfait (100 % → 5 % au régime qui compte). La
bonne conclusion n'est pas « RRF ne marche pas » mais « RRF a besoin d'un second retriever
comparable » — donc d'un vrai plongement dense, qui exige `sentence-transformers` + `torch`
(≈2 Go, absents de cette machine). Le résultat est conservé ici pour ne pas refaire
l'essai : c'est exactement le genre de brique qui a l'air d'aider et qui coûte.

**Limite résiduelle déclarée** : BM25 ne retrouve que **60 %** des paraphrases (aucun mot
rare partagé). C'est le seul régime où un plongement dense apporterait quelque chose — et
il est inatteignable ici, pas contournable par une astuce.

### Ce que la recherche a apporté d'autre (nouveaux dépôts à étudier)

| Dépôt | Ce qu'il apporte | Décision |
|---|---|---|
| [`ai-boost/awesome-harness-engineering`](https://github.com/ai-boost/awesome-harness-engineering) | Recensement daté des primitives de harnais : compaction progressive en 5 étapes, isolation des sous-agents, *Evidence-Preserving Reducer* (une citation n'est gardée que si elle correspond littéralement à la source archivée), `ObservationPack` (les gros résultats deviennent des poignées paginées) | Piste suivante : le réducteur de preuve recoupe `jio trace` et la chaîne de hachage du journal. |
| [`HKUDS/OpenHarness`](https://github.com/HKUDS/OpenHarness) | Harnais open-source complet : compactage automatique, MEMORY.md, reprise de session, règles de permission par chemin, hooks `PreToolUse`/`PostToolUse` | Comparaison de conception ; nos garde-fous sont déjà sur disque et vérifiables. |
| [`affaan-m/ECC`](https://github.com/affaan-m/ECC) | Boucle `plan → test → implement → review → verify → remember → improve`, revue en **contexte neuf** (« le même contexte écrit et relit son propre code ») | Confirme le choix du vérificateur séparé ; la revue à contexte neuf est déjà celle de l'ablation `S1b`. |
| [`bradagi/awesome-cli-coding-agents`](https://github.com/bradagi/awesome-cli-coding-agents) | Inventaire des harnais CLI (dont compression de contexte « Headroom », mémoire en anneaux, oplog à recherche hybride) | Veille : c'est la liste à relire quand un axe de compaction sera ouvert. |

## Partie 8 — La généralisation du routeur de compétences : 87 % n'est pas 46 %

### Le chiffre, et pourquoi il fallait un second jeu

| Jeu | Objectifs | Premier choix juste |
|---|---|---|
| Banc du dépôt (celui du réglage) | 39 | **87 %** |
| **Jeu de contrôle (jamais vus, écrits avant la retouche)** | **24** | **46 %** |
| — dont anglais (langue de travail de Hermes/opencode) | 12 | 50 % |
| — dont français | 12 | 42 % |
| Abstention sur 4 objectifs hors sujet | 4 | 100 % |

Le banc ne peut pas mesurer la généralisation : il a servi à régler le routeur, et la fiche des
compétences est **l'entrée** du routeur — l'améliorer en regardant ce banc serait de
l'entraînement sur le jeu de test. Le second jeu, écrit avant toute retouche, est un **jeu de
contrôle** (déclaré comme tel : même auteur, donc pas un banc externe).

### La cause, et le remède mesuré

Les deux tiers des échecs étaient des **mots absents du pont bilingue** : « changed the
assertion » (il faut « cheat », « disable », « bypass »), « keeps coming back » (« repay »,
« recurring »), « reusable procedure » (« fiche », « playbook », « recette »). L'extension des
classes de synonymes de domaine fait passer le jeu de contrôle de **33 % à 46 %** — anglais
42 % → 50 % — **sans déplacer le banc** (87,1 % avant et après), ce qui est le contrôle
anti-sur-ajustement. Un test existant a d'ailleurs attrapé une entrée interdite introduite par
l'extension (« deux fois », une expression) : le lexique ne contient que des mots.

### Deux pistes écartées, par la mesure

| Piste | Attendu (littérature) | Mesuré ici | Décision |
|---|---|---|---|
| **Fusion RRF** BM25 + trigrammes de caractères | la fusion bat chacun isolément (0,661 / 0,645 / **0,694** nDCG@10) | 100 % → **5 %** au régime identifiant ; 87 % → 23 % au mélange | écartée : un second classement faible **dilue** le premier. La RRF exige un second retriever *comparable* — donc un vrai plongement dense |
| **Vocabulaire procédural des corps** (mots alphabétiques à IDF élevée, littéraux du dépôt exclus) | corriger l'échec mesure jadis (indexer le corps entier coûtait 29 points) | 46 % → **46 %** | écartée : aucun gain, plus de bruit |

### Ce qui manque, et où il faudrait aller le chercher

La limite du pont est la **paraphrase sans mot rare partagé** : BM25 ne la voit pas, même
excellente soit sa pondération. Les dépôts qui la traitent, et qui restent inaccessibles **depuis
cette machine** (poids hébergés hors de PyPI/GitHub : `huggingface.co` injoignable,
`cdn-lfs.huggingface.co` injoignable, `raw.githubusercontent.com` injoignable) :

| Dépôt | Ce qu'il apporterait | Pourquoi inaccessible ici |
|---|---|---|
| [`huggingface/sentence-transformers`](https://github.com/huggingface/sentence-transformers) (19 137★) | plongements locaux multilingues, sans clé (`paraphrase-multilingual-MiniLM`) | poids sur HF (bloqué) et `torch` (≈2 Go, non installable) |
| [`facebookresearch/fastText`](https://github.com/facebookresearch/fastText) (26 524★) | vecteurs de mots alignés bilingues (`cc.fr.300.vec`) | poids sur fasttext.cc / HF (bloqué) |
| [`globalwordnet/english-wordnet`](https://github.com/globalwordnet/english-wordnet) (888★) via `wn` | synonymes anglais généraux (pas de domaine à écrire à la main) | `wn.download('oewn:2024')` → *download failed at 0 bytes* (bloqué) |

Ces trois dépôts **ferment** la question : les deux premières lignes remplaceraient le pont
bilingue par de la similarité réelle, la troisième élargirait les classes sans les écrire à la
main. Chacune est vérifiée comme inaccessible **ici**, et aucune ne l'est en général — sur une
machine avec accès à Hugging Face, `pip install sentence-transformers` suffit et le score du jeu
de contrôle est la mesure qui dit si le remplacement vaut le coût.

**Conclusion honnête** : 87 % était un chiffre vrai sur un jeu écrit par son auteur ; 46 % est la
généralisation mesurée. Les deux sont désormais affichés ensemble, et l'écart n'est plus caché.
