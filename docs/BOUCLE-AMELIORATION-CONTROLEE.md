# Boucle d'amélioration contrôlée de JIO

## Réflexion obligatoire et agents de revue adaptés à chaque demande

Chaque `Engine.run()` construit un plan de réflexion **avant toute génération** à partir du
mandat formulé par l'utilisateur, des règles compilées et du contexte de la tâche. Le plan est
append-only dans le journal (`task_reflection`) et conserve le hash de l'objectif, les domaines
détectés, les indicateurs de risque et les rôles recrutés, sans recopier l'objectif en clair.

Trois rôles transversaux sont toujours créés : interprète du brief, relecteur adversarial et
auditeur de preuves. Les spécialistes **ne viennent pas d'un roster** : JIO les forge à partir
des groupes de critères et des mots distinctifs de la demande (par exemple, un brief de vidéo
peut produire `specialist_video_motion_design`). Les signaux de santé, de droit, de sécurité ou
d'autres enjeux sensibles forgent en plus un mandat de revue du risque correspondant. Les
critiques LLM reçoivent des rubriques distinctes et une preuve attendue; les noms de rôle et les
empreintes de leurs consignes sont consignés, sans recopier les prompts dans le journal.

La sélection est une heuristique déclarée, bornée à six rôles : elle ne prouve ni que le domaine
est correctement classé, ni que les modèles sont indépendants. Plusieurs rôles servis par le même
fournisseur peuvent partager un angle mort. Les contrôles exécutables, la provenance des modèles,
les désaccords et l'abstention restent nécessaires. En simulation, les rôles restent simulés et
ne doivent pas être présentés comme des LLM réels.

## Ce que cette boucle garantit — et ce qu'elle ne peut pas garantir

Aucune campagne finie ne permet d'affirmer « sans l'ombre d'un doute » que JIO donnera toujours les meilleures réponses ou qu'il n'a plus aucun problème. Les tâches futures, les changements de modèle, les oracles incomplets et les nouveaux environnements laissent toujours une incertitude résiduelle.

Le but opérationnel est donc plus strict et plus honnête : **ne jamais activer automatiquement un changement parce qu'il semble meilleur**. Il doit démontrer un gain sur des tâches jamais utilisées pour le régler, à modèle et budget égaux, sans accroître les erreurs silencieuses, les abstentions ou les violations de sécurité. Une amélioration admissible passe en revue/staging, puis peut être activée avec retour arrière.

## Cycle proposé

1. **Observer** : journaliser les erreurs silencieuses, les tests échoués, les réserves, abstentions, coûts et temps. Garder la provenance et la version du modèle/outils.
2. **Classer** : regrouper les échecs par cause, distinguer défaut de modèle, oracle, spécification, outil, contexte et environnement. Ne pas transformer un seul incident en règle générale.
3. **Proposer** : produire un changement candidat isolé (prompt, skill, vérificateur, routage, mémoire ou code) avec hypothèse falsifiable et justification.
4. **Vérifier d'abord** : tests unitaires, sécurité, mutation testing, cohérence et non-régression. Un contrôle absent ou en erreur est bloquant.
5. **Comparer à budget égal** : baseline et candidat évalués sur les mêmes tâches et graines, avec le même modèle, outils, budget et version de banc.
6. **Garder le holdout intact** : séparer strictement apprentissage et holdout; ne jamais régler le candidat à partir des résultats holdout. Utiliser de nouvelles tâches privées/rotatives pour les campagnes suivantes.
7. **Décider prudemment** : JIO fournit `PROMOTE_ELIGIBLE`, `REJECT` ou `INDETERMINATE`. Le premier signifie seulement « admissible à une revue/staging ». Jamais d'activation automatique.
8. **Stager et surveiller** : déployer à faible portée, mesurer les mêmes métriques, comparer à la baseline, rollback si une erreur silencieuse ou un incident sécurité apparaît.
9. **Réviser** : intégrer les incidents confirmés à la mémoire et aux tests de régression, avec provenance et garde exécutable; expirer ou retirer les souvenirs nuisibles. Les échecs sans remède observé restent en quarantaine dans `FailureMemory`; seul un succès ultérieur qui résout l'échec active le souvenir pour les prompts.

## Forge d'agents adaptatifs

`jio improve` lance les portes disponibles (Ruff complet et `jio coherence`, plus pytest par défaut; `--scan` ajoute le scan strict) puis **crée automatiquement un mandat d'agent par groupe de constats observés**. Le roster n'est pas un nombre fixe d'agents : si Ruff trouve des constats dans plusieurs domaines, des agents spécialisés sont générés pour ces groupes; si aucun constat n'est détecté, aucun agent fictif n'est créé. `--max-agents` borne les mandats et regroupe les constats excédentaires sans les perdre.

```sh
jio improve --root . --scan --timeout 60
# les fiches sont déposées dans .jio/improve/round-N/agents/
# après les corrections, relancer jio improve : un nouvel audit ouvre le tour suivant
```

Chaque fiche porte les constats comme données non fiables, le périmètre, les critères de preuve et les vérifications exigées. Une génération de fiche ne compte ni comme correction, ni comme vote IA, ni comme avis indépendant; le rapport contient son empreinte SHA-256 et `certifies_perfection: false`. Un code de sortie non nul signifie qu'il reste des mandats à examiner, pas que le correctif a été appliqué.

**Limite explicite de cette première version :** la forge adapte le nombre et le mandat des agents aux constats; elle ne prétend pas instancier 50 modèles distincts. Les fiches attendent qu'un agent IA réellement connecté les exécute. Elle ne modifie pas elle-même le code et ne collecte pas encore les votes unanimes d'un jury ni l'approbation du responsable. Le processus est relançable et chaque audit est borné; il n'y a pas de boucle infinie en arrière-plan.

## Comparateur expérimental disponible

`jio evolve compare --baseline baseline.json --candidate candidate.json` compare des rapports JSON appariés. La quarantaine des souvenirs s'inspire aussi des résultats de VaG : l'article observe que des skills erronés peuvent contaminer les skills distillés plus tard et recommande une admission avant activation, plutôt qu'un nettoyage seulement a posteriori ([Shang et al., 2026](https://arxiv.org/abs/2608.05810)). Ce résultat motive un garde conservateur; il ne prouve pas que la même ampleur d'effet existe dans JIO. Contrat minimal :

```json
{
  "schema_version": 1,
  "variant": "candidate-v2",
  "dataset_id": "holdout-rotatif-2026-10",
  "split": "holdout",
  "model": "provider/model/version",
  "budget": {"rounds": 5, "tokens": 12000},
  "task_set_hash": "sha256:...",
  "trials": [
    {"task_id": "task-17", "seed": 42, "outcome": "success", "safety_violation": false}
  ],
  "frozen_replays": [
    {
      "replicate_id": "baseline-rescore-1",
      "variant": "baseline-v1",
      "schema_version": 1,
      "dataset_id": "holdout-rotatif-2026-10",
      "split": "holdout",
      "model": "provider/model/version",
      "budget": {"rounds": 5, "tokens": 12000},
      "task_set_hash": "sha256:...",
      "trials": [
        {"task_id": "task-17", "seed": 4201, "outcome": "success"}
      ]
    }
  ]
}
```

`frozen_replays` doit contenir au moins trois répétitions de la baseline et couvre les mêmes `task_id`; les graines de tous les replay sont distinctes des graines principales et entre elles. Le même champ peut être omis des rapports candidate.

`outcome` vaut `success` (réponse correcte acceptée), `silent_error` (réponse incorrecte acceptée) ou `abstain`. Chaque variante doit contenir exactement les mêmes paires tâche/graine et métadonnées de modèle, de budget, de dataset et de split. Le gain est évalué par le test exact apparié de McNemar, pas par deux pourcentages indépendants.

La baseline doit aussi fournir au moins trois `frozen_replays` : ré-exécutions de la version baseline inchangée sur les mêmes tâches, avec graines distinctes et non réutilisées. Le candidat n'est éligible que si son gain dépasse le plus grand écart vu dans ces rescoring sans évolution. Cela évite d'attribuer au patch une variation qui survient même sans changement de version. Ce contrôle est inspiré du protocole d'attribution de TEB, qui constate des variations de score au re-scoring d'un agent gelé et recommande des bandes de bruit par graine ([Li et al., 2026](https://arxiv.org/abs/2610.15055)).

La promotion en staging est refusée si le candidat ajoute une violation de sécurité, augmente les erreurs silencieuses, augmente les abstentions, n'a pas de gain net significatif sur les réussites correctes, ou reste dans le bruit de rescoring. Un résultat non significatif reste `INDETERMINATE`, pas « égalité prouvée ».

**Limite du format :** `dataset_id`, `split=holdout`, le hash et les replays sont fournis par l'appelant. Le comparateur contrôle la cohérence interne des rapports, mais ne peut pas prouver que le holdout est resté secret, que le baseline est inchangé ou qu'un résultat est honnête. Il faut un banc indépendant, versionné, des oracles audités et une revue de la provenance.

## Ce qui n'est pas encore automatisé

Cette première brique est un **garde de décision**, pas une auto-modification autonome : elle ne génère pas elle-même des correctifs, n'exécute pas encore le benchmark externe, ne crée pas de déploiement canari et ne fait aucun merge/rollback. Ces actions exigent un runner isolé, des tâches privées/rotatives et une approbation/revue traçable. L'auto-édition du système de production sans ces protections pourrait rendre JIO moins fiable en prétendant l'améliorer.

La boucle `jio learn --cycles N` mesure déjà l'effet multi-cycle de la mémoire simulée; elle ne prouve pas que le modèle réel est devenu meilleur. Le comparateur `jio evolve compare` est le premier garde-fou de promotion pour des mesures réelles appariées.
