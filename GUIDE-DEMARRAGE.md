# GUIDE DE DÉMARRAGE — intégrer JIO à TON projet, étape par étape

> Ce guide est écrit pour **toi**, pas pour un expert. Chaque étape dit : la commande
> exacte à taper, ce qui va s'afficher, et quoi faire si ça bloque. Toutes les commandes
> ont été exécutées réellement sur un projet d'essai avant d'écrire ce document.

---

## ⚡ LA VOIE RAPIDE — 2 actions, testées, ~10 secondes

**1. Télécharge le SEUL fichier dont tu as besoin** :
[`installer-jio.py`](https://github.com/jionni885-cell/JIOJIO-TERMINATOR/blob/arena/01a0d44e-jiojio-terminator/installer-jio.py)
(bouton « Download raw file » ou copie-colle son contenu dans un fichier du même nom)

**2. Depuis le dossier de TON projet :**

```sh
python installer-jio.py --projet .
```

C'est tout. Mesuré en réel : il télécharge JIO depuis GitHub, l'installe, intègre ton projet
(30 artefacts, câblage MCP prouvé, fiche `.jio/ACTIVE.md`) et affiche la commande pour
travailler. Sur ton projet, ton IA lira ensuite automatiquement `CLAUDE.md` / `AGENTS.md` /
`.opencode/` — passe directement à **l'étape 4** (brancher ton modèle) et **l'étape 5**
(travailler).

> Windows : remplace `python3` par `python`. Le script ne touche qu'au dossier que tu lui
> donnes, et tu peux le lire avant de l'exécuter — c'est la règle du dépôt.

La suite du guide détaille chaque étape (utile pour comprendre, ou si tu préfères tout
faire à la main).

---

## Étape 0 — Ce qu'il te faut (5 minutes de préparation)

| besoin | comment vérifier |
|---|---|
| **Python 3.10 ou plus** | tape `python --version` (Windows) ou `python3 --version` (Linux/Mac). Si rien ne s'affiche : télécharge Python sur https://www.python.org/downloads/ et coche **"Add Python to PATH"** à l'installation |
| **Ton projet** | n'importe quel dossier avec ton code |
| **(recommandé) un CLI d'IA** | opencode, claude, codex, gemini ou aider — voir étape 4. SANS ça, JIO marche en mode vérification, mais ne peut pas écrire de code pour toi |

---

## Étape 1 — Récupérer JIOJIO-TERMINATOR

**Option A — télécharger (le plus simple)**

1. Va sur https://github.com/jionni885-cell/JIOJIO-TERMINATOR/pull/1
2. Clique sur l'onglet **Files changed**, puis sur **…** → ou plus simple : ouvre le dépôt,
   change de branche vers `arena/01a0d44e-jiojio-terminator`, bouton vert **Code** →
   **Download ZIP**
3. Décompresse le ZIP, par exemple dans `C:\JIO\JIOJIO-TERMINATOR` (Windows) ou
   `~/JIOJIO-TERMINATOR` (Linux/Mac). Retiens ce chemin, on en a besoin à l'étape 2.

**Option B — avec git (si tu l'as)**

```sh
git clone -b arena/01a0d44e-jiojio-terminator https://github.com/jionni885-cell/JIOJIO-TERMINATOR.git
```

> ⚠️ Tout le travail est sur la branche `arena/01a0d44e-jiojio-terminator` (elle porte la
> pull request #1). Si tu clones sans `-b` et que le dossier semble presque vide, c'est
> que tu es sur `main` — utilise la commande avec `-b`.

---

## Étape 2 — Installer `jio` (UNE seule fois pour tous tes projets)

Ouvre un terminal **dans le dossier JIOJIO-TERMINATOR**, puis :

**Windows (PowerShell ou CMD) :**
```bat
cd C:\JIO\JIOJIO-TERMINATOR
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\jio --version
```

**Linux / Mac :**
```sh
cd ~/JIOJIO-TERMINATOR
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/jio --version
```

Tu dois voir : `jio 0.1.0`. C'est tout — **rien d'autre à installer** (aucune clé API).

**Astuce pour ne pas taper le chemin complet à chaque fois :**

- Linux/Mac — ajoute cette ligne à la fin du fichier `~/.bashrc` ou `~/.zshrc` :
  ```sh
  alias jio="$HOME/JIOJIO-TERMINATOR/.venv/bin/jio"
  ```
  puis ferme et rouvre ton terminal. Ensuite tu tapes juste `jio`.
- Windows — ajoute le dossier `C:\JIO\JIOJIO-TERMINATOR\.venv\Scripts` à ta variable
  d'environnement PATH (menu démarrer → « variables d'environnement » → Path → modifier →
  nouveau). Ensuite tu tapes juste `jio`.

---

## Étape 3 — Intégrer JIO à TON projet (une commande)

Ouvre un terminal **dans le dossier de TON projet**, puis :

```sh
jio start
```

Ce que tu verras (extrait réel) :

```
30 artefacts natifs écrits
CABLAGE MCP : opencode, cursor
PREUVE DU CABLAGE : le serveur est réellement démarré, 8 outils : jio_prove, jio_audit, ...
fiche d'intégration : .jio/ACTIVE.md (l'IA la lit en premier)
COHÉRENCE DU DÉPÔT : COHERENT (9 contrôles)
```

Ce que ça a créé dans ton projet — **ce sont les instructions que ton IA lira
automatiquement** :

| fichier | qui le lit |
|---|---|
| `CLAUDE.md` | Claude Code |
| `AGENTS.md` | opencode, Codex et les autres agents génériques |
| `GEMINI.md` | Gemini CLI |
| `.opencode/` + `opencode.json` | opencode (5 agents spécialisés) |
| `.cursor/` + `.mcp.json` | Cursor, Copilot (serveur MCP) |
| `.hermes/skills/` | Hermes |
| `.jio/ACTIVE.md` | tous — c'est LA fiche d'état |

**Committe ces fichiers dans ton projet** (ils sont faits pour ça) :

```sh
git add CLAUDE.md AGENTS.md GEMINI.md .jio .opencode .cursor .mcp.json opencode.json .hermes
git commit -m "Intégration de JIO (anti-erreur) dans le projet"
```

**À savoir** : relancer `jio start` ne réécrit **rien** (mesuré : le fichier `.jio/ACTIVE.md`
a la même empreinte après un second passage). Tu ne peux rien casser en le relançant.

---

## Étape 4 — Brancher ton IA (pour que JIO pilote VRAIMENT ton modèle)

`jio doctor` dit toujours la vérité sur ce qui est détecté :

```sh
jio doctor
```

Si tu vois `aucun CLI externe trouvé`, installe-en un (au choix) :

- **opencode** : https://opencode.ai — puis `npm install -g opencode-ai`
- **Claude Code** : `npm install -g @anthropic-ai/claude-code`
- ou codex, gemini, aider, hermes — tous reconnus

Relance `jio doctor` : ton CLI doit apparaître dans « Fournisseurs détectés ». C'est
**ton** modèle qui travaillera — JIO ne remplace pas le modèle, il le **vérifie**.

---

## Étape 5 — Travailler avec ton IA (le quotidien)

Toujours dans ton projet :

**1. Pose les questions ESSENTIELLES avant de travailler :**
```sh
jio clarify "ajoute une remise de 10% si le panier dépasse 100 euros, avec des tests"
```
- `0 question` → l'objectif est assez précis, tu peux travailler ;
- code de sortie **3** → il liste les 1 à 3 questions vitales. Réponds-y dans l'objectif :
  `jio clarify "... même objectif ... la remise s'applique AVANT la TVA, au format fonction Python"`.

**2. Lance la mission :**
```sh
jio run "ajoute une remise de 10% si le panier dépasse 100 euros, la remise s'applique avant la TVA"
```
Ton modèle écrit le code → JIO le **prouve** (tests exécutés), le fait **attaquer** par un
panel de critiques, le fait **voter** par un consensus, puis :
- **livre sans réserve** (code 0) : tout est prouvé ;
- **livre avec réserves nommées** (code 1) : ça marche, mais voici exactement ce qui reste fragile ;
- **s'abstient** (code 2) : rien n'est livré, et le rapport dit QUOI manque et QUI a fauté
  en premier. Relance après avoir fourni ce qui manque.

**3. Objectif plus large, en plusieurs étapes :**
```sh
jio auto "mets en place la facturation avec tests"
```
Chaque étape doit porter sa **preuve** : une étape sans preuve est refusée, un échec arrête
le plan (jamais d'empilement sur une base fausse). Tu interromps ? `jio auto --reprendre`
continue là où c'était prouvé.

---

## Étape 6 — Avant de dire « c'est fini »

```sh
jio coherence        # tout ce que le projet affirme est-il encore vrai ? (code 0 = oui)
jio scan .           # audit du projet : n'affiche que les problèmes réels, avec preuve
jio entreprise       # la passe complète : 90+ vérifications en parallèle, un responsable par problème
```

`jio entreprise` seul suffit comme verdict final : **code 0 = aucun problème**, chaque
problème éventuel porte le nom de l'agent qui l'a trouvé et l'extrait qui le prouve.

---

## Si quelque chose bloque

1. **Lis le message** : JIO ne dit jamais « erreur » sans dire **quoi** manque et **quoi
   faire** (« installez X », « branchez un modèle », « élargissez alpha »...) ;
2. `jio doctor` — l'état réel en une commande ;
3. `jio auto --reprendre` — reprend le plan après avoir corrigé ce qui bloquait ;
4. `jio trace` — rejoue le journal de ce qui s'est passé.

---

## Plus tard : mettre à jour JIO

```sh
cd ~/JIOJIO-TERMINATOR            # (ou C:\JIO\JIOJIO-TERMINATOR)
git pull                          # ou re-télécharge le ZIP
.venv/bin/pip install -e .        # (Windows : .venv\Scripts\pip install -e .)
```

Puis `jio start` dans ton projet : il met à jour ce qui a changé, ne touche pas à ce que
TU as édité, et ne réécrit rien qui n'a pas bougé.

---

*Cette page fait partie du dépôt JIOJIO-TERMINATOR. Sa promesse, comme celle du projet :
tout ce qui est écrit ici a été exécuté avant d'être écrit — la vérification avant
l'affirmation, toujours.*
