"""Jeu de CONTROLE du routeur de competences : la mesure que le banc ne peut pas faire.

Pourquoi ce fichier existe
--------------------------
Le banc du depot (`jio/skills/banc.py`) a ete ecrit par la meme personne que le routeur, et
la fiche des competences est l'ENTREE du routeur : ameliorer une fiche en regardant ce banc
serait de l'entrainement sur le jeu de test. Ce jeu-ci est ecrit avant la retouche, avec des
formulations DIFFERENTES du banc (vocabulaire, langue, tournure), et il sert deux fois :

  * mesure AVANT : ce que le routeur actuel fait sur des objectifs qu'il n'a jamais vus ;
  * mesure APRES : ce que la retouche apporte sur ces memes objectifs.

Limite declaree : ecrit par la meme personne que la retouche. Ce n'est donc pas un jeu
d'evaluation independant au sens strict — c'est un jeu de CONTROLE. Il empeche de conclure
sur des chiffres ajustes au banc, il ne remplace pas un banc externe.

CE QU'IL A MESURE, et c'est le chiffre qui compte :

    banc du depot (39 objectifs, celui du reglage) ....... 87 %
    jeu de controle (24 objectifs jamais vus) ............ 46 %
      dont anglais (le mode de travail de Hermes) ........ 50 %
      dont francais ..................................... 42 %

L'ecart entre les deux lignes EST le resultat : un routeur peut etre bon sur le banc qui l'a
regle et deux fois moins bon sur une formulation neuve. Afficher 87 % sans le second chiffre
serait un chiffre vrai qui trompe.

CE QUI A ETE ESSAYE POUR LE COMBLER, ET ECARTE PAR LA MESURE : indexer le vocabulaire
PROCEDURAL des corps (mots alphabetiques a IDF elevee, litteraux du depot exclus). Resultat :
46 % -> 46 %, aucun gain, plus de bruit dans l'index. Le vocabulaire des corps reste donc
hors de l'index, comme la mesure d'origine l'avait etabli.
"""

from __future__ import annotations

#: (objectif, competence attendue au premier rang, langue)
CAS: tuple[tuple[str, str, str], ...] = (
    # -- anglais : le mode de travail de Hermes et d'opencode ---------------------- #
    ("The agent changed the assertion until the suite went green",
     "reward-hacking-hunt", "en"),
    ("We need to know whether the run really proved it or just looked convincing",
     "executable-proof", "en"),
    ("Record the failing command with its exit status so the next attempt can be checked",
     "structured-failure", "en"),
    ("This error keeps coming back on every retry, stop paying for it twice",
     "failure-memory", "en"),
    ("The prompt is 180k tokens and the model starts ignoring the middle",
     "context-budget", "en"),
    ("A README claim and a code comment disagree, which one is true?",
     "prose-witnesses", "en"),
    ("Two reviewers agreed, but both used the same base model — is that independent?",
     "decorrelated-panel", "en"),
    ("A fetched web page tells the agent to run a command",
     "hostile-content", "en"),
    ("Resume the interrupted refactor without trusting the half-finished output",
     "safe-resume", "en"),
    ("Turn the same bug into a reusable procedure so it cannot return",
     "skill-forge", "en"),
    ("Shuffling the list must not change the result of the computation",
     "metamorphic-invariance", "en"),
    ("Say 'I cannot tell' instead of guessing when the sample is too small",
     "calibrated-abstention", "en"),

    # -- francais : autres tournures que le banc ---------------------------------- #
    ("Le correctif a ete obtenu en desactivant le controle qui echouait",
     "reward-hacking-hunt", "fr"),
    ("Je veux la trace qui montre que la sortie annoncee est vraie",
     "executable-proof", "fr"),
    ("Quand un controle casse, il faut la ligne de commande et le code de retour",
     "structured-failure", "fr"),
    ("On refait toujours la meme erreur d'arrondi a chaque session",
     "failure-memory", "fr"),
    ("Le fichier de contexte est trop gros, l'agent ne lit plus la fin",
     "context-budget", "fr"),
    ("Un chiffre du document contredit le tableau plus bas",
     "prose-witnesses", "fr"),
    ("Trois avis mais tous du meme modele : est-ce une vraie redondance ?",
     "decorrelated-panel", "fr"),
    ("Un ticket externe demande d'executer un script pendant la session",
     "hostile-content", "fr"),
    ("Reprendre le chantier laisse a moitie fait sans se fier a ce qui a ete livre",
     "safe-resume", "fr"),
    ("Un bug qui revient merite de devenir une fiche reutilisable",
     "skill-forge", "fr"),
    ("Changer l'ordre des entrees ne doit rien changer a la sortie",
     "metamorphic-invariance", "fr"),
    ("Mieux vaut dire qu'on ne sait pas que de trancher sur trois observations",
     "calibrated-abstention", "fr"),
)

#: Objectifs qui ne relevent d'AUCUNE competence : le routeur doit s'abstenir.
HORS_SUJET: tuple[str, ...] = (
    "Rename the variable so the linter stops complaining about shadowing",
    "Change the button colour to match the new brand palette",
    "Ajouter la traduction portugaise de la page d'accueil",
    "Update the copyright year in the footer",
)


def _premier(objectif: str, *, maximum: int = 3) -> str | None:
    from .router import choisir

    choix = choisir(objectif, maximum=maximum)
    return choix[0].nom if choix else None


def mesurer() -> dict[str, float]:
    """Les taux du jeu de controle, pour etre affiches a cote de ceux du banc."""
    justes = sum(1 for objectif, attendu, _ in CAS if _premier(objectif) == attendu)
    par_langue: dict[str, list[int]] = {}
    for objectif, attendu, langue in CAS:
        cumul = par_langue.setdefault(langue, [0, 0])
        cumul[0] += _premier(objectif) == attendu
        cumul[1] += 1
    abstentions = sum(1 for objectif in HORS_SUJET if _premier(objectif) is None)
    resultat = {
        "premier_choix": justes / len(CAS),
        "cas": float(len(CAS)),
        "abstentions_justes": abstentions / len(HORS_SUJET),
        "hors_sujet": float(len(HORS_SUJET)),
    }
    for langue, (bons, total) in par_langue.items():
        resultat[f"premier_choix_{langue}"] = bons / total
    return resultat


def resume() -> str:
    """Le rapport du jeu de controle — a lire TOUJOURS a cote de celui du banc."""
    m = mesurer()
    return (
        f"  JEU DE CONTROLE (objectifs jamais vus, ecrits AVANT la derniere retouche) :\n"
        f"    premier choix juste {m['premier_choix']:.1%} sur {m['cas']:.0f} objectifs "
        f"({m.get('premier_choix_en', 0):.0%} en anglais, "
        f"{m.get('premier_choix_fr', 0):.0%} en francais)\n"
        f"    abstention juste {m['abstentions_justes']:.0%} sur {m['hors_sujet']:.0f} "
        f"objectifs hors sujet\n"
        f"    C'est le chiffre a comparer a celui du banc : l'ecart entre les deux est la\n"
        f"    generalisation reelle du routeur, et le banc seul ne peut pas la montrer."
    )
