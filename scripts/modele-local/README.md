# Un modèle réel, entraîné ici — pour arrêter de mesurer sur une simulation

## Le problème que ce dossier règle

Chaque rapport de ce dépôt porte la même réserve, écrite en clair :

> le modèle est **SIMULÉ** : ce n'est pas une mesure de modèle réel.

C'est honnête, et ça laisse ouverte la seule question qui compte pour un harness :
**tient-il quand le modèle qui répond n'est pas le nôtre ?** Une simulation dont *nous* avons
choisi le taux d'erreur ne peut pas répondre : on mesure ce qu'on a mis dedans. Pire, elle
peut faire passer pour une preuve ce qui n'est qu'un réglage.

Ici, le modèle est réel au sens strict : des **poids**, un vrai calcul, une vraie
distribution de sortie, et des erreurs que **personne n'a modélisées**. Il est petit — c'est
assumé et déclaré : ce n'est pas un substitut à un modèle frontière, c'est un modèle dont les
erreurs sont authentiques, ce qui suffit à mettre le harness à l'épreuve.

## Ce qui est mesuré, et ce qui ne l'est pas

| Mesuré | Non mesuré |
|---|---|
| Le harness **livre-t-il faux sans réserve** face à un modèle dont on ne contrôle pas les erreurs ? | Le taux de réussite face à un modèle frontière |
| Le système **s'abstient-il** quand la vérification échoue ? | La qualité linguistique du modèle |
| La **reproductibilité** d'une mesure à graine fixée | Un gain de « QI » du modèle |

Le chiffre qui compte ici est **erreurs silencieuses** : missions livrées *sans réserve* et
*fausses*. C'est le seul qui doit valoir zéro, et il est mesurable avec n'importe quel
modèle — même mauvais. C'est précisément ce que la simulation ne pouvait pas prouver.

## D'où vient l'architecture

Le transformeur décodeur (self-attention causale, embeddings de position appris, tête de
langage) suit [`karpathy/nanoGPT`](https://github.com/karpathy/nanoGPT) et son ancêtre
[`karpathy/minGPT`](https://github.com/karpathy/minGPT). Le code est écrit ici — court,
lisible, sans dépendance autre que **PyTorch** ([`pytorch/pytorch`](https://github.com/pytorch/pytorch)) —
mais l'idée n'est pas de nous.

Le corpus est le meilleur disponible sur cette machine : **le code de ce dépôt**.

## Comment ça marche, et pourquoi par une API

```
entrainer.py   ->  modele/modele.pt          (poids + alphabet + configuration)
serveur.py     ->  http://127.0.0.1:PORT/v1  (API compatible OpenAI)
jio            ->  JIO_OLLAMA=http://127.0.0.1:PORT   (le harness, inchangé)
```

Le harness **n'est pas modifié** pour ce cas particulier : il sait déjà parler à tout ce qui
expose `/v1/chat/completions` (Ollama, vLLM, OpenRouter). Ce qui est mesuré est donc le
chemin réel qu'un utilisateur emprunte, et non un adaptateur écrit pour la circonstance.

## Reproduire

```sh
cd scripts/modele-local
python entrainer.py --sortie ../../modele/modele.pt     # ~10 min sur 2 cœurs
scripts/modele-local/mesurer.sh 5 3                     # la mesure, avec son rapport
```

Le modèle entraîné **n'est pas versionné** (un binaire de quelques mégaoctets n'a rien à faire
dans l'historique) : ce qui est versionné, c'est la **graine**, la **configuration**, le
**corpus** (le dépôt lui-même) et le **journal d'entraînement** — de quoi refaire exactement
le même modèle et vérifier l'empreinte.

## Les deux défauts trouvés en l'écrivant

Un modèle qu'on entraîne soi-même est aussi un banc d'essai pour nos propres réflexes de
mesure, et il en a révélé deux :

1. **Un masque causal de 4096×4096 partait dans le `state_dict`.** Mesure : un modèle de
   **251 904 paramètres** produisait un fichier de **135 Mo**. La taille d'un fichier doit dire
   le nombre de paramètres de ce qu'il contient ; ici elle disait autre chose. Le masque est
   une constante, pas un poids appris — `persistent=False` le sort de la sauvegarde.
   Après correction : **1,0 Mo**, ce qui est exactement 250 k paramètres en float32.
2. **La table de décodage était inversée.** `{i: c for c, i in enumerate(alphabet)}` construit
   l'inverse de ce qu'il fallait ; le premier appel réel a rendu `KeyError: 84` au lieu d'une
   réponse. Un défaut qu'aucun test unitaire du serveur n'aurait attrapé si l'on n'avait pas
   **appelé** le service pour de vrai : c'est la même leçon que partout dans ce dépôt.
