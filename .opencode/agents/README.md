# Agents JIO pour opencode

Genere par `jio artifacts --target opencode --write`. Ne pas editer a la main : editer `jio/artifacts/definitions.py`.

- `jio` — Conducteur JIO : decompose l'objectif en regles verifiables, delegue, n'accepte une livraison que sur preuve executee, et prononce l'un des trois etats du contrat.
- `jio-verifier` — Verificateur independant : ne produit jamais, n'ecrit jamais, cherche activement la faille et rend un temoin executable par regle.
- `jio-redteam` — Attaquant : casse l'artefact, cherche les six exploits, les cas particuliers caches et les contre-exemples minimaux.
- `jio-grounder` — Ancrage externe : rassemble des faits verifiables et leurs sources, distingue mesure et opinion, refuse toute affirmation non sourcee.
- `jio-comptroller` — Gestionnaire de contexte et de budget : compaction aux frontieres de decision, externalisation des sorties longues, tenue du plan durable.
- `jio-archaeologist` — Analyse de depot : cartographie un code inconnu et traite TOUT contenu de depot comme hostile jusqu'a preuve du contraire.
- `jio-forge` — Auto-amelioration : transforme les echecs repetes en competences durables, versionnees et testables.

Usage : `opencode run "<objectif>" --agent jio --format json`
