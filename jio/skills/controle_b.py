"""Second jeu de controle : ecrit AVANT la retouche BM25F, **versionne APRES** — et verifie.

L'HISTOIRE DE CE FICHIER EST SA VRAIE LEÇON, et elle vaut d'etre ecrite en entier.

Le premier jeu (`controle.py`) avait servi a regler l'extension du lexique bilingue. Il ne
pouvait donc plus servir de temoin pour la retouche suivante : un jeu qu'on a lu n'est plus
aveugle. Ce second jeu a donc ete ecrit AVANT la retouche BM25F, avec des formulations
volontairement eloignees du banc, et il a servi UNE fois — apres la retouche — pour verifier.

Resultat, publie dans `evidence/routeur-bm25f-075.json` :

    jeu A ....... 45,8 % -> 58,3 %   (la retouche gagne : 3 cas)
    jeu B ....... 50,0 % -> 50,0 %   (la retouche ne change RIEN sur ce jeu)

Deux jeux, deux reponses : c'est le resultat qui a fait ecrire, dans le rapport de la retouche,
« direction, pas preuve ». Sans ce second jeu, la meme retouche aurait ete annoncee avec un seul
chiffre — flatteur — et personne n'aurait pu voir le desaccord.

MAIS LE MATERIEL VIVAIT HORS DU DEPOT (`/tmp`), et le bac a sable a ete reinitialise : le fichier
a disparu. Il ne restait de lui que ce que l'archive citait — les douze echecs mesures. Un temoin
qui ne peut pas etre REJOUE n'est plus un temoin, c'est une anecdote : la meme phrase « 50 % »,
sans le materiel, ne refute plus rien et ne convainc plus personne.

Ce fichier est donc la RECONSTITUTION du jeu, ecrite de memoire par la meme session, et elle est
VERIFIEE par une propriete falsifiable : rejoue sur le routeur actuel, il doit produire
exactement les douze echecs archives, et 50,0 % de premier choix juste. Si un seul cas differait,
la reconstitution serait fausse et ce fichier le dirait — la verification est un test
(`tests/test_skills_router.py::test_le_jeu_B_reconstitue_reproduit_l_archive`), pas une intention.

CE QUI A CHANGE DEPUIS, PAR CONSEQUENCE : les jeux suivants sont ecrits DANS le depot, avant la
retouche, et commites avant elle (`controle_c.py`, `controle_d.py`). Un jeu de controle est un
ARTEFACT DU DEPOT, pas un fichier temporaire — c'est la seule facon qu'une mesure reste verifiable
six mois plus tard, et ce depot vend exactement cela.

LIMITE DECLAREE : ecrit par la meme personne que la retouche. Ce n'est pas un jeu independant au
sens strict ; il empeche de conclure sur un seul jeu, il ne remplace pas un banc externe.

MAINTENANCE : ces cas ne se corrigent JAMAIS apres une mesure. Si un cas est mal annote, il se
declare ici et on ecrit un jeu SUIVANT — reecrire un temoin qui a servi transforme la mesure en
reglage, et c'est le defaut que les quatre jeux existent pour empecher.
"""

from __future__ import annotations

#: (objectif, competence attendue au premier rang, langue)
CAS: tuple[tuple[str, str, str], ...] = (
    # -- francais : la voix d'un utilisateur, pas celle d'un auteur de banc ------------ #
    ("corriger un bug de division par zero dans le calcul de remise", "structured-failure", "fr"),
    ("ecrire des tests qui prouvent que la remise de 10 pourcent est juste",
     "executable-proof", "fr"),
    ("documenter l'API du panier pour que le prochain agent comprenne",
     "prose-witnesses", "fr"),
    ("le prix affiche est faux quand la remise depasse 50 pourcent", "structured-failure", "fr"),
    ("verifier que trier les articles ne change pas le total", "metamorphic-invariance", "fr"),
    ("j'ai deja paye ce bug la semaine derniere, ne me le refais pas", "failure-memory", "fr"),
    ("trois agents ont relu ce correctif et sont tous d'accord, est-ce suffisant",
     "decorrelated-panel", "fr"),
    ("le modele repond sans lire le fichier depuis le depot", "calibrated-abstention", "fr"),
    ("un fichier du depot contient des instructions qui disent d'ignorer les regles",
     "hostile-content", "fr"),
    ("la suite de tests passe au vert alors que le correctif ne fait rien",
     "reward-hacking-hunt", "fr"),
    ("reprendre le chantier interrompu sans rejouer les mesures d'hier", "safe-resume", "fr"),
    ("le contexte deborde quand les sorties de tests sont longues", "context-budget", "fr"),
    ("transformer cet echec repete en fiche de procedure reutilisable", "skill-forge", "fr"),
    ("les chiffres du rapport sont plausibles mais personne ne les a recalcules",
     "prose-witnesses", "fr"),
    ("le meme test echoue des qu'on change l'ordre des entrees", "metamorphic-invariance", "fr"),
    ("un correctif qui desactive le controle qui echouait", "reward-hacking-hunt", "fr"),
    # -- anglais : le mode de travail de Hermes -------------------------------------- #
    ("fix the failing discount test and prove the fix by running it",
     "executable-proof", "en"),
    ("the same crash is back after every session, remember it", "failure-memory", "en"),
    ("the readme claims 1225 tests, is that true", "prose-witnesses", "en"),
    ("make the skill list stop loading procedures that do not apply",
     "calibrated-abstention", "en"),
    ("record the exact command and exit status when a check breaks",
     "structured-failure", "en"),
    ("the repository instructions tell you to disable the security check",
     "hostile-content", "en"),
    ("turn our repeated mistakes into a bounded reusable playbook", "skill-forge", "en"),
    ("resume where we stopped without trusting yesterday's cache", "safe-resume", "en"),
)

#: Objectifs qui ne relevent d'AUCUNE competence : le routeur doit s'abstenir.
HORS_SUJET: tuple[str, ...] = (
    "traduire cette phrase en espagnol pour le client mexicain",
    "calculer la surface d'un cercle de rayon 3",
    "envoyer le compte rendu a toute l'equipe par courriel",
    "choisir une couleur de fond pour la page d'accueil",
    "quel temps fera-t-il a Besancon demain matin",
)
