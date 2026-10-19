# Doctrine d'infaillibilité visée

## Le but

JIO vise **zéro erreur acceptée comme correcte et livrée sans avertissement**. Ce n'est pas une promesse mathématique qu'un logiciel complexe ne peut pas soutenir : une spécification peut omettre un cas, un oracle peut être faux, deux vérificateurs peuvent partager le même angle mort, et l'environnement d'exécution peut différer de la production.

## Règles opérationnelles

1. Une sortie sans preuve n'est pas une réussite.
2. Une vérification échouée, incomplète, tronquée ou non fiable ne peut pas produire un verdict de réussite.
3. Un désaccord, une réserve, une intégrité compromise ou un témoin absent doit rester visible ; si l'information est insuffisante, s'abstenir. Dans le panel, un vote `ABSTAIN` ou `ERROR` est un veto à la certification : une indisponibilité de vérification n'est pas une opinion minoritaire que la majorité peut neutraliser.
4. Les tests doivent tenter de réfuter l'artefact (cas négatifs, mutations, adversaires) et pas seulement confirmer qu'il passe quelques exemples.
5. Toute garantie statistique doit annoncer ses hypothèses, sa calibration, son périmètre et son incertitude. Une probabilité calibrée n'est pas une certitude.
6. Une livraison « propre » ne signifie que « les contrôles spécifiés ont passé dans cet environnement » ; elle ne prouve pas l'absence de défauts inconnus.

## Politique zéro-réserve

`jio run --zero-reserve` est la voie la plus prudente actuellement disponible : le panel doit être unanime pour atteindre le consensus. En cas de désaccord, le moteur poursuit ses tours jusqu'à la limite configurée (`--rounds`) ; s'il ne résout pas le désaccord ou si une réserve subsiste, la CLI transforme `DELIVERED_WITH_RESERVATION` en abstention, inscrit cette décision dans le journal et rend le code de sortie correspondant à l'abstention. Un résultat déjà abstenu ou livré sans réserve n'est pas réécrit. L'unanimité n'est pas une preuve absolue : les agents peuvent partager une erreur, d'où l'obligation de preuves exécutables indépendantes.

Cette option bloque les incertitudes **déjà détectées par JIO** ; elle n'élimine pas les défauts que ses oracles ne savent pas détecter. Elle peut donc produire beaucoup plus d'abstentions. Pour réduire également les erreurs inconnues, il faut améliorer indépendamment les spécifications, les oracles, la couverture, les contrôles d'exécution et les évaluations adversariales.

## Mesure requise

Le critère de progrès n'est pas « plus de tâches déclarées terminées ». Mesurer sur des tâches définies et appariées :

- erreurs livrées sans réserve (objectif : zéro observée, sans prétendre que cela prouve un zéro universel) ;
- faux succès des vérificateurs et défauts de leurs propres oracles ;
- taux d'abstention et tâches correctes refusées ;
- coût, latence et taux de réussite par difficulté ;
- tests mutants survivants, attaques d'injection et incidents de sandbox.

Chaque changement de politique doit conserver ces métriques et être testé contre les cas où l'ancien comportement livrait à tort.
