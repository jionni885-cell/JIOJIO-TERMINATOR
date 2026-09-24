# Le harness vaut plus que le modèle — et comment JIO atteint le niveau frontière

Document de cadrage stratégique. C'est ici que se joue l'objectif : **amener n'importe quel modèle
au niveau de GPT-6 Astra / Claude Opus 5.5, puis au-delà.**

---

## 1. La preuve que c'est possible

La littérature 2026 est sans ambiguïté : **entre le modèle et le résultat, il y a le harness — et
les mesures montrent qu'il pèse davantage.**

| Résultat mesuré | Chiffre | Source |
|---|---|---|
| Variance du harness vs variance du modèle (étude factorielle) | **7,8× supérieure** — et le changement de scaffold **inverse 6 des 9 classements de modèles** | Zhang et al., 2026 |
| Même modèle, seul l'adaptateur change | **19,1 % → 73,4 %** (+54 pts) | Claw-SWE-Bench |
| Même modèle, même benchmark, deux scaffolds | **34 pts** de swing | SWE-bench Verified Mini sous HAL |
| Six modèles frontière sous le même harness | **4,9 pts** d'écart seulement (41,0 → 45,9) | SWE-bench Pro / SEAL |
| Le **meilleur** de ces six, harness changé | **+9,5 pts** (45,9 → 55,4) — *plus que l'écart entre six modèles* | idem, Claude Code |
| Harness auto-évolué (modèle gelé) | **69,7 % → 77,0 %** — **bat** le scaffold Codex-CLI réglé à la main, et les gains **se transfèrent à d'autres modèles** (+10,1 sur deepseek-v4-flash) | AHE, 2026 |
| Modèle **plus faible**, meilleur scaffold | Sonnet 4.5 + Confucius = **52,7 %** > Opus 4.5 + scaffold Anthropic = **52,0 %** | Meta / Harvard |
| Six modèles frontière sur SWE-bench Verified | **0,8 pt** d'écart (79,6 → 80,9) | leaderboard 2026 |
| Harness seul, Terminal Bench 2.0 | **52,8 % → 66,5 %** (top 30 → top 5) | LangChain |
| Récupération ciblée 5K tokens vs résumé 100K | **5K gagne** | Sourcegraph |

**Conclusion opérationnelle :** les modèles frontière sont convergés. Le différentiateur n'est plus
le modèle. Il est **le harness, la gestion du contexte, et la qualité du vérificateur.**

> Note honnête : le harness ne crée pas de connaissance absente. Snell et al. montrent que sur les
> problèmes les plus difficiles, **aucun temps de réflexion** n'aide un petit modèle qui n'a pas le
> savoir requis. Le harness convertit la *capacité latente* en *performance* — il ne la fabrique pas.

---

## 2. Ce que le harness doit contenir (les 7 leviers mesurés)

### Levier 1 — Sélection et structure du contexte
- **Récupération structurelle > recherche par embeddings** pour du code : renvoyer la définition d'un
  symbole + ses sites d'appel fait passer la précision@5 de **0,14 → 0,48** (Sourcegraph).
- **Charger juste à temps** : les schémas d'outils MCP restent différés par défaut (noms seulement).
- **Bannir le remplissage** : `AGENTS.md` **> 150 lignes** = l'agent survole. Une étude ETH Zurich
  montre même que les fichiers de contexte de dépôt **n'améliorent pas** le succès et coûtent
  **+20 à +23 %**.

### Levier 2 — Compaction et discipline du contexte
- **Compaction : +29 % de performance** mesuré en interne chez Anthropic ; **+39 %** avec un outil mémoire.
- Compaction = **checkpoint**, pas résumé narratif. Ce qu'on garde : objectif et contraintes,
  décisions prises (une ligne de justification chacune), artefacts produits (chemins/IDs),
  ce qui a été **vérifié**, ce qui reste. Ce qu'on jette : les tentatives échouées, les dumps.
- **Offload avant compaction** : tout résultat d'outil > 20 000 tokens part sur disque, remplacé par une référence.
- **Budget, pas plafond** : la dégradation commence vers **50 000 tokens** de contenu pertinent,
  même dans une fenêtre de 1M. On budgète une fraction de la fenêtre.

### Levier 3 — Isolation par sous-agents
- Chaque sous-agent explore dans une fenêtre propre (dizaines de milliers de tokens),
  puis retourne un résumé de **1 000 à 2 000 tokens**.
- **Le conflit d'informations est mesuré** : le découpage multi-tours a causé une chute moyenne de
  **39 %** (o3 : 98,1 → 64,1) quand les contextes se mélangeaient. → **Isoler, pas fusionner.**
- Coût caché : ne pas donner de sous-agents à des tâches triviales.

### Levier 4 — État externalisé (la vérité hors du transcript)
- Le plan vit dans un **fichier que l'agent réécrit** à chaque étape (`todo.md`), ce qui **récite
  l'objectif dans la fenêtre d'attention récente** et combat la dérive « perdu au milieu ».
- Les produits intermédiaires vivent sur disque ; le contexte ne contient que des **pointeurs**.
- La progression est un **registre** mis à jour à chaque étape : n'importe quel appel de modèle
  ne voit que la tranche de travail devant lui.

### Levier 5 — Qualité de rétroaction d'erreur
- Le harness qui **fournit la sortie de test échouée des tentatives précédentes** produit
  **5 à 10 points** de gain apparent sans changer les poids.
- → Chaque échec est renvoyé **structuré** : commande, code de sortie, stderr tronqué, diff, étape fautive.

### Levier 6 — Budget d'itération adaptatif
- **Le ratio optimal séquentiel/parallèle dépend de la difficulté** :
  - Question **facile** → **révisions séquentielles** (polir un brouillon déjà correct).
  - Question **difficile** → **hybride** séquentiel + parallèle.
  - **Beam search** gagne aux petits budgets, **Best-of-N** aux gros.
- Avec allocation adaptative : **4× moins de compute**, et à budget FLOPs égal un petit modèle
  **bat un modèle 14× plus gros**.
- **Limite de raison** : **GenRM n'égale la self-consistency qu'après 8× le compute.** Donc par défaut :
  échantillonner plus, vérificateur ensuite.

### Levier 7 — Auto-évolution du harness
- AHE montre qu'un harness **peut s'améliorer lui-même** et que les gains **se transfèrent à d'autres
  modèles avec 12 % de tokens en moins**. C'est notre `PromptEvolution` + `TrustRouter`.

---

## 3. La spécification du harness JIO

### 3.1 Gestionnaire de contexte (`ContextBudget`)

```
Budget d'une mission = fraction de la fenêtre du modèle (défaut 40 %), réparti :
  ├─ System + règles durables ................ ≤ 2 000 tokens
  ├─ Plan courant (recité chaque tour) ....... ≤ 1 000 tokens
  ├─ Connaissance procédurale (skills JIT) ... ≤ 5 000 tokens
  ├─ Faits du dépôt (récupérés structurellement) ≤ 15 000 tokens
  ├─ Résultats d'outils récents .............. ≤ 10 000 tokens
  └─ Marge de sécurité ....................... ≥ 20 %
```

Trois déclencheurs :
- **Offload** à 20 000 tokens dans un seul résultat d'outil → écrit sur disque + référence.
- **Compaction** à 85 % du budget → checkpoint structuré, pas un résumé.
- **Recitation** à chaque tour → le plan est réécrit en fin de contexte.

### 3.2 Sélection structurelle du contexte

Pas d'embeddings pour du code. Un index de symboles (`ast` Python, regex multi-langage en repli) :
- définitions + sites d'appel + tests associés + dernières modifications git,
- score = proximité dans le graphe d'appel + récence + spécificité de la règle visée.

### 3.3 Rétroaction d'échec structurée

Chaque échec produit un objet, jamais du texte brut :

```json
{
  "stage": "tests",
  "command": "pytest -q tests/test_x.py::test_y",
  "exit_code": 1,
  "failing_rule": "R-004",
  "assertion": "expected 42, got 41",
  "file": "src/mod.py",
  "line": 87,
  "diff_of_attempt": "...",
  "previously_failed_same_way": true
}
```

### 3.4 Allocation adaptative du budget d'inférence

```
difficulté estimée d  ←  heuristique pré-vol : taille du contexte requis, nombre de règles,
                        échecs passés sur une tâche similaire (FailureMemory), TrustRouter

si d faible   → 1 candidat, jusqu'à 3 révisions séquentielles
si d moyen    → 3 candidats, 2 révisions chacun, beam search sur les preuves
si d élevé    → 5 à 8 candidats hétérogènes, puis consensus n ≥ 3f+1 sur les survivants
si d inconnu  → échelle progressive : on commence bas et on monte tant que ça progresse
                (arrêt dès que le gain marginal < coût, garde anti-oscillation)
```

### 3.5 Le contrat de sortie

Aucune mission ne se termine sans :
- un **témoin exécutable par règle** (commande + code de sortie + hash de sortie),
- un **verdict de consensus** avec votes individuels conservés,
- un **statut d'intégrité** (aucun exploit détecté dans le rejeu du journal),
- une **décision explicite** : `LIVRÉ` · `LIVRÉ_SOUS_RÉSERVE` · `ABSTENTION` — jamais un silence.

---

## 4. Trajectoire chiffrée visée

| Scénario | Modèle | Sans JIO | Avec JIO (cible) |
|---|---|---|---|
| Tâche de code vérifiable (tests disponibles) | local 12B | ~30 % | **~70 %** |
| Tâche de code vérifiable | Sonnet-class | ~55 % | **~80 %** (niveau frontière) |
| Question factuelle complexe | local 12B | ~40 % | **~70 %** (avec abstention calibrée sur le reste) |
| Tâche longue, 50+ étapes | tout modèle | chute 39 % mesurée | **stabilisée** par compaction + sous-agents |
| Tâche **hors de portée du modèle** | local 12B | — | **ABSTENTION explicite** (pas d'hallucination) |

**La dernière ligne est la plus importante.** Un système qui dit « je ne sais pas » avec une
garantie de couverture statistique est plus fiable qu'un système qui a toujours l'air sûr de lui —
**y compris les modèles frontière.**

---

## 5. Comment on saura que ça marche

`jio bench` mesure, sur le **même modèle gelé**, quatre configurations croissantes :

| Config | Contenu |
|---|---|
| **S0 — brut** | 1 appel, pas de contexte structuré |
| **S1 — contexte** | + sélection structurelle + compaction + recitation |
| **S2 — vérification** | + preuve exécutable + SPEC grounding + rétroaction structurée |
| **S3 — JIO complet** | + audit décorrélé + consensus + intégrité + évolution |

Le tableau S0→S3 **est** la mesure du harness. C'est ce que personne ne publie, et c'est ce que
ce projet produira — gains **et** échecs inclus.
