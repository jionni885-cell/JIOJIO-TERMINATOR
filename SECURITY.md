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

## Ce que JIO propose pour aller plus loin : deux backends, jamais confondus

Le backend **par défaut** (`process`) est un garde-fou, pas une prison. Le backend
**`container`** (opt-in, `JIO_SANDBOX_BACKEND=container` ou `Sandbox(backend="container")`)
ajoute une frontière réelle :

| mesure | backend `process` (défaut) | backend `container` |
|---|---|---|
| timeout dur | oui | oui |
| environnement filtré | oui | oui, plus réseau et capacités du noyau |
| répertoire de travail dédié | oui | volume temporaire + `--tmpfs /tmp` |
| accès réseau | **possible** | `--network=none` (aucune interface) |
| écriture dans le projet | **possible** (mêmes droits que toi) | projet monté **`:ro`** au même chemin |
| privilèges | les tiens | `--cap-drop=ALL`, `--security-opt=no-new-privileges` |
| ressources | non bornées | `--cpus=2`, `--memory=1024m`, `--pids-limit=512` |
| si le moteur manque | — | **échec 126 explicite**, jamais de repli silencieux sur `process` |

Le point le plus important est le dernier : demander `container` puis retomber en
silence sur `process` produirait une **confiance sans isolement**, c'est-à-dire exactement
la classe d'erreur que ce dépôt traque. Le projet est donc monté en lecture seule sous le
même chemin absolu — l'artefact audité retrouve son vrai `__file__`, mais ne peut pas
réécrire le dépôt qui l'audite. `jio doctor` affiche le backend actif et, quand
`container` est demandé sans moteur disponible, le dit avant la première vérification.

## Ce que JIO n'est PAS — à savoir avant tout usage risqué

* **La Sandbox backend `process` n'est pas une prison de sécurité.** C'est un garde-fou
  (timeout, environnement filtré, répertoire dédié) — le code exécuté tourne avec TES droits
  utilisateur et peut, en théorie, toucher le réseau et tes fichiers. **Ne fais pas
  tourner les preuves de JIO sur du code hostile** (dépôt inconnu, contenu non vérifié)
  sans une vraie isolation : le backend `container` ci-dessus, une machine virtuelle, ou un
  environnement jetable. C'est la même doctrine que celle du dépôt : zéro confiance, et
  l'isolation forte est l'affaire du SYSTÈME, pas d'un sous-processus ;
* **L'export d'une trace ne publie rien par défaut, mais reste à relire.** `jio trace
  --html` et `--otlp` masquent les secrets et données personnelles *reconnaissables* : les
  champs nommés (clé, jeton, mot de passe, e-mail, téléphone...), les motifs de jetons connus
  (`sk-…`, `ghp_…`, `AKIA…`, JWT), les adresses e-mail, les numéros de téléphone et les clés
  privées sont remplacés par `[REDACTED]`. C'est une politique de motifs, **pas un détecteur
  universel** : un identifiant libre écrit dans un champ au nom anodin peut passer au
  travers. L'export OTLP n'inclut aucun contenu d'événement sauf demande explicite
  (`--otlp-contenu`), et `--sans-redaction` existe pour les cas assumés — il est alors dit
  dans la sortie ;
* **Les artefacts générés orientent des agents d'IA** (CLAUDE.md, AGENTS.md...). JIO les
  audite (`jio coherence`, `jio artifacts --audit`, `jio claims`) et refuse ce qui ne tient
  pas, mais aucune défense n'immunise à 100 % contre l'injection de prompt via le contenu
  d'un dépôt hostile. Relis ce qui est généré avant de donner des droits larges à un agent ;
* **JIO n'est pas un antivirus ni un produit de sécurité certifié** : c'est un outil de
  vérification qui rend les erreurs non silencieuses. Il réduit le risque, il ne l'annule pas.

## Signaler un problème

Ouvre une issue sur le dépôt en décrivant : ce que tu as fait, ce qui s'est passé, la
commande exacte. Ne publie jamais un exploit exploitable avant qu'un correctif existe.
