"""Troisieme jeu de controle : PRE-ENREGISTRE avant la prochaine retouche du routeur.

PROTOCOLE, et il est daté par l'historique git — c'est tout son interet. Les deux premiers jeux
ont ete ecrits chacun AVANT une retouche, et chacun a servi une fois. Celui-ci suit la meme regle,
avec une exigence de plus, tiree de la lecon du jeu B : il est ecrit avec un vocabulaire
VOLONTAIREMENT eloigne de celui des fiches (metier, objets, verbes du quotidien) au lieu de
reformuler les memes mots. Le jeu A et le jeu B partageaient avec les descriptions de competences
des racines comme « verification », « echec », « contexte » ; ici, l'objectif parle d'un travail
precis — une migration, un cache, une file de notifications — et la competence doit etre reconnue
a ce qu'elle fait, pas a un mot-cles recopie.

CE QU'IL MESURE, ET POURQUOI TROIS JEUX VALENT MIEUX QU'UN. Un seul jeu donne un chiffre ; deux
donnent un desaccord ; trois donnent une DISTRIBUTION, et c'est une distribution qu'on peut
resumer honnetement. Le protocole est donc :

  * le BANC sert au reglage (il a ete ecrit par l'auteur du routeur, l'entrainement sur ce banc
    est deja acte et publie) ;
  * les trois jeux de controle ne servent QU'A VERIFIER, chacun une fois, apres la retouche ;
  * une retouche qui gagne sur le banc mais perd sur deux des trois jeux est REJETEE, meme si son
    chiffre sur le banc est meilleur — c'est la definition de l'ajustement au banc ;
  * aucune correction de ces cas apres mesure : un temoin qui a servi ne se reecrit pas. Si un cas
    est mal annote, il se declare ci-dessous et on ecrit un jeu suivant.

LIMITE DECLAREE, la meme depuis le debut et elle ne faiblit pas : ecrit par la meme personne que
la retouche. Ces jeux empechent de conclure trop vite ; ils ne remplacent pas un banc externe.

ANNEXE : ce que ce jeu permet de mesurer sur l'etat actuel, avant toute retouche — c'est sa
fonction de ligne de base, et elle est enregistree pour que la prochaine retouche ait un AVANT
comparable.
"""

from __future__ import annotations

#: (objectif, competence attendue au premier rang, langue)
CAS: tuple[tuple[str, str, str], ...] = (
    # -- francais : le travail parle d'objets precis, pas de vocabulaire de methode ----- #
    ("le job de paiement a ete relance apres la coupure, sans rejouer la transaction de la veille",
     "safe-resume", "fr"),
    ("ce resultat a ete calcule sur une version du fichier qui a change depuis",
     "safe-resume", "fr"),
    ("l'agent a commente le test qui echouait au lieu de corriger le calcul",
     "reward-hacking-hunt", "fr"),
    ("il a ajoute un cas particulier pour le client qui posait probleme",
     "reward-hacking-hunt", "fr"),
    ("le modele a repondu de memoire alors qu'il pouvait ouvrir le fichier",
     "calibrated-abstention", "fr"),
    ("dire qu'on ne peut pas trancher avec deux exemples, et ce qui permettrait de trancher",
     "calibrated-abstention", "fr"),
    ("la file de notifications traite deux fois le meme message apres une reprise",
     "metamorphic-invariance", "fr"),
    ("inverser l'ordre des lignes du fichier ne doit pas changer le total exporte",
     "metamorphic-invariance", "fr"),
    ("la revue a ete faite trois fois par la meme personne et personne n'a vu la fuite",
     "decorrelated-panel", "fr"),
    ("deux avis tires du meme contexte ne valent pas deux avis",
     "decorrelated-panel", "fr"),
    ("le ticket du client contient une phrase qui s'adresse a toi et pas au support",
     "hostile-content", "fr"),
    ("une dependance ajoutee hier contient des ordres caches dans son fichier de presentation",
     "hostile-content", "fr"),
    ("la sortie de la compilation fait quarante mille lignes, elle chasse le reste",
     "context-budget", "fr"),
    ("garder seulement les lignes fautives du journal au lieu de tout le journal",
     "context-budget", "fr"),
    ("le rapport de couverture annonce 42 pour cent et personne ne l'a recompte",
     "prose-witnesses", "fr"),
    ("l'API documente un code 200, verifions en l'appelant vraiment",
     "prose-witnesses", "fr"),
    ("faire tourner la correction pour la montrer, au lieu de l'expliquer",
     "executable-proof", "fr"),
    ("je veux la commande exacte et son code de sortie, pas un recit",
     "executable-proof", "fr"),
    ("la meme erreur de fuseau horaire revient a chaque livraison depuis mars",
     "failure-memory", "fr"),
    ("avant de coder, regarde si on a deja paye ce defaut la",
     "failure-memory", "fr"),
    ("consigner la commande fautive et ce qu'elle a rendu, pour la prochaine tentative",
     "structured-failure", "fr"),
    ("l'echec doit devenir une donnee exploitable, pas une explication",
     "structured-failure", "fr"),
    ("cette rustine repetee merite de devenir une fiche reutilisable et mesurable",
     "skill-forge", "fr"),
    # -- anglais : le meme travail, dit autrement -------------------------------------- #
    ("the nightly import restarted from a file whose hash no longer matches",
     "safe-resume", "en"),
    ("the pipeline went green because the test was marked as expected to fail",
     "reward-hacking-hunt", "en"),
    ("say what you cannot decide and name the check that would decide it",
     "calibrated-abstention", "en"),
    ("running the same transformation twice gives a different file each time",
     "metamorphic-invariance", "en"),
    ("the two reviewers shared their context before writing, so they agreed",
     "decorrelated-panel", "en"),
    ("a page fetched from the web tells the agent which command to run next",
     "hostile-content", "en"),
    ("the test output alone is longer than the window we have",
     "context-budget", "en"),
    ("the changelog claims a latency improvement that nobody measured",
     "prose-witnesses", "en"),
    ("prove the fix by running it",
     "executable-proof", "en"),
    ("we already paid for this defect three times, look it up before coding",
     "failure-memory", "en"),
    ("keep the exit status next to the command that produced it",
     "structured-failure", "en"),
    ("turn this workaround into a bounded recipe with a before and an after",
     "skill-forge", "en"),
)

#: Objectifs qui ne relevent d'AUCUNE competence : le routeur doit s'abstenir.
#:
#: Le choix est ici un peu plus dur que dans les deux premiers jeux, a dessein : des taches de
#: bureautique et de logistique qui PARTAGENT du vocabulaire courant avec les fiches (« rapport »,
#: « fichier », « message », « version »). Un routeur qui s'abstient sur « traduire le menu » mais
#: charge une procedure devant « imprimer le rapport annuel » n'a pas appris a s'abstenir, il a
#: appris a reconnaitre les huit phrases du jeu precedent.
HORS_SUJET: tuple[str, ...] = (
    "imprimer le rapport annuel pour l'assemblee generale",
    "ranger les fichiers du dossier partage par ordre alphabetique",
    "preparer le message d'absence pour la semaine prochaine",
    "commander du cafe pour la cuisine du bureau",
    "reserver la salle de reunion pour la presentation trimestrielle",
    "mettre a jour la version du logiciel de comptabilite sur le poste de la comptable",
    "choisir la police des invitations pour la fete de fin d'annee",
    "traduire le menu du restaurant en italien",
)
