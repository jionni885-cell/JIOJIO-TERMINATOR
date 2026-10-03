# Sécurité — ce que JIO garantit, et ce qu'il ne garantit PAS

À lire avant d'utiliser JIO sur du code que tu ne contrôles pas.

## Ce qui est protégé

* **Aucun secret ne fuit vers le code testé** : la Sandbox (`jio/verify/executable.py`)
  exécute les preuves avec un environnement minimal — toute variable dont le nom contient
  KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL ou AUTH est retirée avant l'exécution ;
* **Timeout dur** : le code testé ne peut pas bloquer la mission (boucle infinie = coupure) ;
* **Répertoire de travail dédié** + sortie plafonnée (au-delà de 20 000 caractères, le
  contenu est écrit sur disque et remplacé par une référence) ;
* **Le serveur MCP est stdio uniquement** : il n'ouvre aucun port réseau, il ne répond
  qu'au client qui l'a lancé sur ta machine ;
* **Aucune clé API** n'est requise ni stockée par le dépôt ; `.env` est ignoré par git,
  seul `.env.example` (sans valeurs) est versionné.

## Ce que JIO n'est PAS — à savoir avant tout usage risqué

* **La Sandbox n'est pas une prison de sécurité.** C'est un garde-fou (timeout,
  environnement filtré, répertoire dédié) — le code exécuté tourne avec TES droits
  utilisateur et peut, en théorie, toucher le réseau et tes fichiers. **Ne fais pas
  tourner les preuves de JIO sur du code hostile** (dépôt inconnu, contenu non vérifié)
  sans une vraie isolation : conteneur Docker, machine virtuelle, ou environnement jetable.
  C'est la même doctrine que celle du dépôt : zéro confiance, et l'isolation forte est
  l'affaire du SYSTÈME, pas d'un sous-processus ;
* **Les artefacts générés orientent des agents d'IA** (CLAUDE.md, AGENTS.md...). JIO les
  audite (`jio coherence`, `jio artifacts --audit`, `jio claims`) et refuse ce qui ne tient
  pas, mais aucune défense n'immunise à 100 % contre l'injection de prompt via le contenu
  d'un dépôt hostile. Relis ce qui est généré avant de donner des droits larges à un agent ;
* **JIO n'est pas un antivirus ni un produit de sécurité certifié** : c'est un outil de
  vérification qui rend les erreurs non silencieuses. Il réduit le risque, il ne l'annule pas.

## Signaler un problème

Ouvre une issue sur le dépôt en décrivant : ce que tu as fait, ce qui s'est passé, la
commande exacte. Ne publie jamais un exploit exploitable avant qu'un correctif existe.
