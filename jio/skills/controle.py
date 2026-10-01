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
    jeu de controle (24 objectifs jamais vus) ............ 58 %
      dont anglais (le mode de travail de Hermes) ........ 58 %
      dont francais ..................................... 58 %

L'ecart entre les deux lignes EST le resultat : un routeur peut etre bon sur le banc qui l'a
regle et nettement moins bon sur une formulation neuve. Afficher 87 % sans le second chiffre
serait un chiffre vrai qui trompe.

HISTORIQUE DE CET ECART, parce qu'il dit quelle retouche a servi :

    46 %  etat livre avant la retouche BM25F (33 % a l'ecriture du jeu)
    58 %  apres : le CORPS des competences est entre dans l'index comme SECOND champ pondere
          (voir `router.POIDS_CORPS`), au lieu d'en etre exclu ou d'y etre verse brut.

CE QUI A ETE ESSAYE POUR LE COMBLER, ET ECARTE PAR LA MESURE :
  * indexer le vocabulaire PROCEDURAL filtre des corps (mots alphabetiques a IDF elevee,
    litteraux du depot exclus) : 46 % -> 46 %, aucun gain, plus de bruit ;
  * verser le corps entier dans le MEME index que le tiers 0 : le classement se degradait, les
    exemples des corps citant le vocabulaire du depot ;
  * ponderer les deux champs separement (BM25F) : c'est la seule variante qui a gagne, et
    l'abstention n'a pas bouge d'un cas — le vocabulaire du domaine ne regarde que le tiers 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from .controle_b import CAS as CAS_B
from .controle_b import HORS_SUJET as HORS_B
from .controle_c import CAS as CAS_C
from .controle_c import HORS_SUJET as HORS_C
from .controle_d import CAS as CAS_D
from .controle_d import HORS_SUJET as HORS_D

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

#: Les trois jeux, dans l'ordre ou ils ont ete ecrits. Chacun a servi UNE fois : celui-ci a
#: mesure une retouche, celui-la la suivante. Un jeu qui a servi ne sert plus de temoin — il
#: devient un cas de reference, et c'est la raison d'etre des deux suivants.
#:
#: Le nom porte sa fonction : `A` est le jeu d'origine, `B` a ete ecrit avant la retouche BM25F,
#: `C` avant la retouche suivante. Les trois ensemble donnent une DISTRIBUTION, qu'on resume
#: honnetement (`resume_tous`), au lieu du chiffre unique d'un seul jeu.
#: (rempli plus bas, une fois la dataclass `JeuControle` definie)


#: Objectifs qui ne relevent d'AUCUNE competence : le routeur doit s'abstenir.
HORS_SUJET: tuple[str, ...] = (
    "Rename the variable so the linter stops complaining about shadowing",
    "Change the button colour to match the new brand palette",
    "Ajouter la traduction portugaise de la page d'accueil",
    "Update the copyright year in the footer",
)


@dataclass(frozen=True)
class JeuControle:
    """Un jeu de controle : ses cas, ses hors sujet, et la retouche devant laquelle il a ete ecrit.

    `ecrit_avant` n'est pas une decoration : c'est ce qui distingue un temoin d'un jeu de reglage.
    Un jeu ecrit APRES la retouche mesure l'auteur, pas le routeur.
    """

    nom: str
    cas: tuple[tuple[str, str, str], ...]
    hors_sujet: tuple[str, ...]
    ecrit_avant: str
    #: Ce que ce jeu a mesure la derniere fois qu'il a servi. Un jeu deja lu ne redevient pas
    #: aveugle : le garder ici evite de faire semblant, et dit au lecteur ce qu'il regarde.
    derniere_mesure: float = 0.0


def _taux(cas: tuple[tuple[str, str, str], ...]) -> tuple[int, int]:
    """(premiers choix justes, cas) pour un jeu — la brique de tout le reste."""
    justes = sum(1 for objectif, attendu, _ in cas if _premier(objectif) == attendu)
    return justes, len(cas)


def mesurer_jeu(jeu: JeuControle) -> dict[str, float]:
    """Les taux d'UN jeu : premier choix juste, par langue, et abstentions justes."""
    justes, total = _taux(jeu.cas)
    par_langue: dict[str, list[int]] = {}
    for objectif, attendu, langue in jeu.cas:
        cumul = par_langue.setdefault(langue, [0, 0])
        cumul[0] += _premier(objectif) == attendu
        cumul[1] += 1
    abstentions = sum(1 for objectif in jeu.hors_sujet if _premier(objectif) is None)
    resultat: dict[str, float] = {
        "premier_choix": justes / total if total else 0.0,
        "cas": float(total),
        "abstentions_justes": abstentions / len(jeu.hors_sujet) if jeu.hors_sujet else 0.0,
        "hors_sujet": float(len(jeu.hors_sujet)),
    }
    for langue, (bons, nombre) in par_langue.items():
        resultat[f"premier_choix_{langue}"] = bons / nombre
    return resultat


def mesurer_tous() -> dict[str, float]:
    """Les trois jeux REUNIS, et jeu par jeu.

    Agreger compte : un seul jeu de 24 cas a un intervalle de confiance de +/-20 points, et c'est
    ce qui a fait dire « direction, pas preuve » a la derniere retouche. Separes, les jeux disent
    en plus si une retouche a aide PARTOUT ou seulement la ou son auteur regardait — un chiffre
    global cache exactement ce desaccord-la.
    """
    reunis: dict[str, float] = {}
    justes = total = 0
    abstentions = hors = 0
    for jeu in JEUX:
        m = mesurer_jeu(jeu)
        reunis[f"{jeu.nom}:premier_choix"] = m["premier_choix"]
        reunis[f"{jeu.nom}:cas"] = m["cas"]
        reunis[f"{jeu.nom}:abstentions_justes"] = m["abstentions_justes"]
        justes += round(m["premier_choix"] * m["cas"])
        total += int(m["cas"])
        abstentions += round(m["abstentions_justes"] * m["hors_sujet"])
        hors += int(m["hors_sujet"])
    reunis["premier_choix"] = justes / total if total else 0.0
    reunis["cas"] = float(total)
    reunis["abstentions_justes"] = abstentions / hors if hors else 0.0
    reunis["hors_sujet"] = float(hors)
    return reunis


def qualite_de_la_liste() -> dict[str, float]:
    """Quand la porte se ferme, ce qu'elle rend vaut-il mieux que le hasard ?

    La question du routeur ne s'arrete pas a « charger ou non » : quand il ne charge rien, il
    REND quelque chose, et ce quelque chose est mesurable. Sur les objectifs du domaine qu'il
    refuse, le premier de la liste classee est le bon dans une part des cas tres superieure au
    hasard (12 competences = 1 sur 12) : c'est ce chiffre qui justifie d'afficher la liste au
    lieu du vide — et c'est aussi lui qui fixe la confiance a lui accorder.

    Ce chiffre inclut le jeu D, dont seuls les TAUX GLOBAUX ont ete regardes : le detail de son
    classement n'a jamais ete ouvert a la main, ce qui est la propriete annoncee par ce jeu.
    """
    from .router import catalogue_du_depot, proches

    justes = total = 0
    for jeu in JEUX:
        for texte, attendu, _ in jeu.cas:
            if _premier(texte) is not None:
                continue                      # servi : la question ne se pose pas
            total += 1
            liste = proches(texte, maximum=3)
            if liste and liste[0].nom == attendu:
                justes += 1
    hasard = 1.0 / max(1, len(catalogue_du_depot().documents))
    return {
        "justes": float(justes),
        "cas": float(total),
        "taux": (justes / total) if total else 0.0,
        "hasard": hasard,
        "facteur": ((justes / total) / hasard) if total and hasard else 0.0,
    }


def resume_tous() -> str:
    """Le tableau des trois jeux, puis la ligne agregee. Ce qu'un rapport doit montrer."""
    lignes = []
    for jeu in JEUX:
        m = mesurer_jeu(jeu)
        lignes.append(
            f"    {jeu.nom}  {m['premier_choix']:>6.1%} sur {int(m['cas']):>3} cas "
            f"({m.get('premier_choix_en', 0):.0%} en anglais, {m.get('premier_choix_fr', 0):.0%} "
            f"en francais) · abstention juste {m['abstentions_justes']:.0%} sur "
            f"{int(m['hors_sujet'])} hors sujet   ecrit avant : {jeu.ecrit_avant}"
        )
    t = mesurer_tous()
    lignes.append(
        f"    {'TOTAL':>3} {t['premier_choix']:>5.1%} sur {int(t['cas'])} cas jamais vus · "
        f"abstention juste {t['abstentions_justes']:.0%} sur {int(t['hors_sujet'])} hors sujet"
    )
    q = qualite_de_la_liste()
    lignes.append(
        f"    QUAND LA PORTE SE FERME : la premiere de la liste classee est la bonne "
        f"{q['justes']:.0f}/{q['cas']:.0f} fois ({q['taux']:.0%}), contre {q['hasard']:.0%} "
        f"au hasard — la liste vaut donc {q['facteur']:.1f} fois le hasard, et c'est ce qui "
        f"est rendu a la place du vide"
    )
    return "\n".join(lignes)


JEUX = (
    JeuControle(nom="A", cas=CAS, hors_sujet=HORS_SUJET,
                ecrit_avant="la retouche du lexique bilingue", derniere_mesure=0.583),
    JeuControle(nom="B", cas=CAS_B, hors_sujet=HORS_B,
                ecrit_avant="la retouche BM25F (le corps entre dans l'index)",
                derniere_mesure=0.500),
    JeuControle(nom="C", cas=CAS_C, hors_sujet=HORS_C,
                ecrit_avant="la retouche A VENIR (pre-enregistre ; detail relu pour les "
                            "annotations, jamais regle dessus)",
                derniere_mesure=0.0),
    # D est le seul dont le DETAIL n'a pas ete regarde avant la retouche : c'est lui qui permet
    # de dire, si le resultat est bon, que le gain n'a pas ete obtenu en pensant a ses cas.
    JeuControle(nom="D", cas=CAS_D, hors_sujet=HORS_D,
                ecrit_avant="la retouche A VENIR (pre-enregistre, detail AVEUGLE)",
                derniere_mesure=0.0),
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
