"""Un banc d'objectifs REELS pour mesurer la porte de clarification.

Pourquoi un banc, et pourquoi annote a la main
----------------------------------------------
La porte de clarification prend une decision a chaque mission : travailler, ou demander.
Deux facons de se tromper, et elles coutent toutes les deux, mais pas la meme chose :

  * un FAUX POSITIF — poser des questions sur un objectif clair. L'utilisateur repond deux
    fois, puis arrete de repondre : la porte devient une formalite qu'on ignore, et elle ne
    protege plus rien. C'est le mode d'echec le plus probable a l'usage ;
  * un FAUX NEGATIF — travailler sur un objectif ambigu. Le systeme choisit le perimetre, le
    format et le critere a la place de l'utilisateur, puis livre quelque chose de plausible
    qui repond a une autre question.

Les deux se mesurent, mais pas avec un modele : il faut une verite de reference. Elle est ici
ANNOTEE A LA MAIN — `attendu` (l'objectif est-il actionnable ?) et `manquants` (quels signaux
manquent vraiment ?). C'est un travail humain, court, et c'est le seul moyen honnete de dire
« la porte a 100 % de precision » sans se citer soi-meme.

Les objectifs sont ceux qu'un utilisateur ecrit vraiment : courts, en francais ou en anglais,
parfois ambigus, parfois complets. Un banc d'objectifs bien ecrits ne mesurerait rien.

Ce que ce module mesure
-----------------------
`mesurer()` rend la precision (part des objectifs declares a tort ambigus), le rappel (part
des objectifs ambigus detectes), et — pour chaque objectif — ce que la porte a vu de faux ou
de manque. Les erreurs sont listees, jamais resumees : une moyenne cache exactement le cas
qu'il faut corriger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..clarify import MAX_QUESTIONS, Analyse, analyser

__all__ = ["Objectif", "RapportPorte", "CORPUS", "mesurer", "formater"]


@dataclass(frozen=True)
class Objectif:
    """Un objectif REEL, avec la verite de reference ecrite a la main."""

    texte: str
    #: Verite de reference : cet objectif est-il travaillable tel quel ?
    attendu: bool
    #: Signaux reellement absents (verite de reference), parmi ceux de la porte.
    manquants: frozenset[str] = frozenset()
    note: str = ""


#: Le corpus. `attendu=False` signifie : il FAUT poser une question avant de travailler.
CORPUS: tuple[Objectif, ...] = (
    # -- objectifs actionnables : rien a demander ------------------------------------- #
    Objectif(
        "corriger jio/verify/entropy.py : `_numeric_equal` doit rendre False quand aucun "
        "nombre n'est present, avec un test qui le prouve",
        True, frozenset(), "action + cible (chemin) + critere (test qui le prouve)",
    ),
    Objectif(
        "reparer le bug de jio/recover.py ou l'empreinte rate les dossiers non suivis, la "
        "suite doit rester verte",
        True, frozenset(), "action + cible + critere (« la suite doit rester verte »)",
    ),
    Objectif(
        "ajouter dans tests/test_clarify.py un test qui borne le nombre de questions a 3",
        True, frozenset(), "action + cible (chemin) + critere (le test lui-meme)",
    ),
    Objectif(
        "mesurer le gain de la memoire des echecs sur 20 missions, en points de reussite",
        True, frozenset(), "action + cible (la memoire) + critere (points de reussite)",
    ),
    Objectif(
        "documenter dans README.md la porte de clarification en moins de 30 lignes",
        True, frozenset(), "action + cible + critere chiffre",
    ),
    Objectif(
        "analyser le journal .jio/journal.jsonl et lister les regles non couvertes",
        True, frozenset(), "action + cible (chemin) + critere (liste)",
    ),
    Objectif(
        "add a test to tests/test_start.py proving jio start is idempotent",
        True, frozenset(), "anglais, action + cible + critere",
    ),
    Objectif(
        "fix the failing rule R-003 in jio/spec/witness.py; the suite must stay green",
        True, frozenset(), "anglais, action + cible + critere",
    ),
    Objectif(
        "corrige le calcul de jio/trust/router.py : le budget doit valoir le produit des "
        "tours par les candidats, verifie par un test",
        True, frozenset(), "imperatif francais, action + cible + critere",
    ),
    Objectif(
        "remplacer la constante 600 de jio/spec/witness.py par une borne nommee, sans "
        "changer le comportement (tests verts)",
        True, frozenset(), "action + cible + critere (« tests verts »)",
    ),
    # -- objectifs ambigus : une question au minimum ---------------------------------- #
    #
    # NOTE SUR `manquants`, ecrite apres une mesure : ces annotations listaient le signal dont
    # parlait la note, pas TOUS les signaux absents. Le banc ne pouvait pas le voir, puisqu'il
    # ne verifiait que « la porte voit-elle ce qui manque ? ». Le jour ou il a aussi verifie
    # « croit-elle manquant ce qui est ecrit ? », huit annotations se sont revelees incompletes
    # — et chaque fois la porte avait raison : « les performances », « les tests », « le
    # depot », « la documentation » ne sont pas des cibles (liste `_NOMS_VAGUES`), et « fais »,
    # « make », « why » ne sont pas des verbes d'action. Les completer rend le banc PLUS
    # severe, pas plus complaisant : il compte desormais les signaux dans les deux sens.

    Objectif(
        "ameliore le projet",
        False, frozenset({"cible", "critere", "perimetre"}),
        "souhait : ni cible, ni critere, ni perimetre",
    ),
    Objectif(
        "corrige le bug",
        False, frozenset({"cible", "critere"}),
        "action claire, cible et critere absents",
    ),
    Objectif(
        "optimise les performances",
        False, frozenset({"cible", "critere"}),
        "« optimise » sans chiffre : on ne saura jamais si c'est fini",
    ),
    Objectif(
        "il faudrait ameliorer les tests",
        False, frozenset({"cible", "critere"}),
        "quel critere ? couverture, duree, stabilite — trois travaux differents",
    ),
    Objectif(
        "analyse le depot",
        False, frozenset({"cible", "critere"}),
        "analyser pour repondre a quelle question ?",
    ),
    Objectif(
        "documente tout ca",
        False, frozenset({"cible", "critere"}),
        "« tout ca » ne designe rien de verifiable",
    ),
    Objectif(
        "fais en sorte que ca marche mieux",
        False, frozenset({"action", "cible", "critere", "perimetre"}),
        "ni quoi, ni comment on mesure",
    ),
    Objectif(
        "il y a encore des choses a ameliorer, continue",
        False, frozenset({"critere"}),
        "mandat de boucle sans critere d'arret. La CIBLE n'est pas listee manquante parce qu'un "
        "mandat l'HERITE (« continue » renvoie a la mission en cours) : c'est la doctrine ecrite "
        "dans `jio/clarify.py`, et elle a change cette annotation — qu'on la contredise la-bas "
        "avant de la changer ici",
    ),
    Objectif(
        "refactorise",
        False, frozenset({"cible", "critere"}),
        "refactoriser quoi, et selon quelle propriete a preserver ?",
    ),
    Objectif(
        "make it better",
        False, frozenset({"action", "cible", "critere"}),
        "anglais vague",
    ),
    Objectif(
        "why is it slow?",
        False, frozenset({"action", "cible", "critere"}),
        "question ouverte : quelle partie, et mesuree comment ?",
    ),
    Objectif(
        "verifie que tout va bien",
        False, frozenset({"cible", "critere"}),
        "« tout » n'est pas un perimetre",
    ),
    Objectif(
        "mets a jour la documentation",
        False, frozenset({"cible", "critere"}),
        "documentation de quoi, et a quelle aune de justesse ?",
    ),
    Objectif(
        "ajoute des tests",
        False, frozenset({"cible", "critere"}),
        "des tests de quoi, et qui doivent echouer sur quoi ?",
    ),
    Objectif(
        "trouve et corrige les problemes",
        False, frozenset({"cible", "critere"}),
        "« les problemes » : lesquels, avec quelle preuve ?",
    ),
    Objectif(
        "ameliore la qualite du code",
        False, frozenset({"cible", "critere"}),
        "« qualite » sans critere mesurable",
    ),
    Objectif(
        "fais une revue",
        False, frozenset({"action", "cible", "critere"}),
        "revue de quel artefact, selon quelles regles ?",
    ),
    Objectif(
        "continue",
        False, frozenset({"critere"}),
        "mandat de boucle : sans critere, il n'a pas de fin — et la cible est heritee, comme "
        "pour tout mandat de poursuite",
    ),
    Objectif(
        "corrige ce que tu as casse",
        False, frozenset({"cible", "critere"}),
        "accusation sans cible ni preuve : il faut demander laquelle",
    ),
    # -- objectifs limites : la reponse doit rester STABLE ---------------------------- #
    Objectif(
        "supprimer jio/artifacts/doctrine.py",
        True, frozenset(),
        "action destructrice mais parfaitement claire : la porte ne doit PAS demander quoi",
    ),
    Objectif(
        "ecrire un rapport sur l'etat du depot dans docs/ETAT.md",
        True, frozenset(),
        "cible (chemin) + format (rapport) : actionnable",
    ),
    # -- objectifs du TERRAIN : ceux qu'un utilisateur a REELLEMENT ecrits -------------- #
    #
    # Cette section existe parce que le reste du corpus a ete ecrit par la meme personne que le
    # code : il pouvait donc, sans malhonnetete, ne contenir que des cas que la porte savait
    # traiter. Ceux-ci viennent de vraies missions (les mandats de boucle du depot lui-meme),
    # avec ce qu'il a fallu AJOUTER apres coup pour que le travail devienne decidable.
    Objectif(
        "peut-on ameliorer jio terminator ? si oui continue, explore, fais des recherches, puis "
        "retrouve encore des axes d'amelioration",
        False, frozenset({"critere"}),
        "mandat de boucle REEL (8e mission) : action et cible sont la, la fin ne l'est pas. La "
        "question utile est l'ARRET, pas « quelle action attends-tu »",
    ),
    Objectif(
        "continue avec les axes et ne t'arrete pas avant que absolument tout ne soit parfait",
        False, frozenset({"critere"}),
        "mandat REEL : « parfait » n'est pas un critere, et une poursuite sans borne ne "
        "s'arrete que quand elle casse — c'est la panne qui deciderait de l'arret",
    ),
    Objectif(
        "arrange tous les problemes",
        False, frozenset({"cible", "critere", "perimetre"}),
        "demande REELLE (7e mission), et le verbe n'etait meme pas reconnu : « arrange » dit "
        "l'intention, ni l'objet ni l'arene",
    ),
    Objectif(
        "keep going until the whole thing is solid",
        False, frozenset({"critere"}),
        "mandat anglais REEL : « solid » est un adjectif, pas un seuil — et la porte doit "
        "reconnaitre « keep going » comme un mandat, pas comme une phrase sans verbe. La cible "
        "est HERITEE du mandat, seul l'arret manque",
    ),
    Objectif(
        "continue jusqu'a ce que 3 cycles ne trouvent plus d'axe",
        True, frozenset(),
        "le meme mandat, mais BORNE : « 3 cycles » est un critere d'arret. Un mandat qui dit ou "
        "il s'arrete doit partir au travail, pas se faire interroger",
    ),
    Objectif(
        "corrige le calcul de moyenne dans le rapport hebdo pour qu'il compte les jours feries",
        True, frozenset(),
        "critere de COMPORTEMENT : « pour qu'il compte les jours feries » est observable, donc "
        "verifiable. Ecrit pour payer une mesure — l'elision « qu' » echappait a la porte, qui "
        "demandait le critere a un objectif qui venait de le donner",
    ),
    Objectif(
        "ameliore la lisibilite du README pour que les nouveaux arrivants trouvent l'installation "
        "en moins de 2 minutes",
        True, frozenset(),
        "verbe VAGUE mais cible nommee et critere observable (« en moins de 2 minutes ») : zero "
        "question. Le mot « installation » a fait sortir cette phrase avec l'action « livraison » "
        "— mesure qui a paye la recherche de l'action EN POSITION",
    ),
)


#: Les signaux dont l'absence DECLENCHE une question : ce sont les seuls ou une erreur de
#: lecture se paie comptant. `source` et `format` ne declenchent jamais de question a eux seuls
#: (regle ecrite dans `jio/clarify.py`) : les compter ici reprocherait a la porte un silence
#: qui ne coute rien.
ESSENTIELS = ("action", "cible", "critere")


@dataclass
class RapportPorte:
    """Ce que la porte a fait sur le corpus : precision, rappel, et LES ERREURS."""

    total: int = 0
    vrais_positifs: int = 0     # ambigus correctement signales
    faux_positifs: int = 0      # actionnables qui ont recu des questions
    vrais_negatifs: int = 0     # actionnables correctement laisses tranquilles
    faux_negatifs: int = 0      # ambigus partis sans question
    signaux_oublies: int = 0    # signaux manquants que la porte n'a pas vus
    signaux_en_trop: int = 0    # signaux juges manquants a tort
    erreurs: list[str] = field(default_factory=list)
    max_questions: int = 0

    @property
    def precision(self) -> float:
        """Part des questions posees qui etaient justifiees."""
        posees = self.vrais_positifs + self.faux_positifs
        return self.vrais_positifs / posees if posees else 1.0

    @property
    def rappel(self) -> float:
        """Part des objectifs ambigus effectivement signales."""
        ambigus = self.vrais_positifs + self.faux_negatifs
        return self.vrais_positifs / ambigus if ambigus else 1.0

    @property
    def exact(self) -> bool:
        return not self.erreurs and self.max_questions <= MAX_QUESTIONS

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "precision": self.precision,
            "rappel": self.rappel,
            "vrais_positifs": self.vrais_positifs,
            "faux_positifs": self.faux_positifs,
            "vrais_negatifs": self.vrais_negatifs,
            "faux_negatifs": self.faux_negatifs,
            "signaux_oublies": self.signaux_oublies,
            "signaux_en_trop": self.signaux_en_trop,
            "max_questions": self.max_questions,
            "erreurs": list(self.erreurs),
        }


def _en_trop(analyse: Analyse, item: Objectif) -> list[str]:
    """Signaux que l'annotation dit PORTES par le texte, et que la porte croit absents.

    C'est l'erreur symetrique de `signaux_oublies`, et elle etait invisible : le banc verifiait
    « la porte voit-elle ce qui manque ? » mais jamais « croit-elle manquant ce qui est la ? ».
    Consequence mesuree : sur un mandat de boucle (« … continue »), la porte annoncait l'action
    absente et proposait de demander « quelle action attends-tu ? » — a un utilisateur qui venait
    de la donner. Une question pareille ne coute pas un tour : elle coute la confiance.
    """
    return [
        s.nom for s in analyse.signaux
        if not s.present and s.nom in ESSENTIELS and s.nom not in item.manquants
    ]


def mesurer(corpus: tuple[Objectif, ...] = CORPUS) -> RapportPorte:
    """Passe le corpus dans la porte et compte les erreurs, sans les arrondir.

    Un seul critere decide, des deux cotes : **la porte a-t-elle demande quelque chose ?**
    C'est la seule chose que l'utilisateur ressent, et se servir du booleen `actionnable` comme
    intermediaire produisait une accusation fausse : sur « ameliore la lisibilite du README pour
    que … en moins de 2 minutes », la porte ne pose AUCUNE question (l'objectif est decidable) et
    le banc la comptait quand meme en faux positif, parce que le verbe est vague. Un banc qui
    compte faux ce qui ne coute rien pousse a « corriger » la porte dans le mauvais sens.
    """
    rapport = RapportPorte(total=len(corpus))
    for item in corpus:
        analyse: Analyse = analyser(item.texte)
        rapport.max_questions = max(rapport.max_questions, len(analyse.questions))
        posees = [q.signal for q in analyse.questions]
        # 1. Les questions, des deux cotes : c'est ce que l'utilisateur ressent.
        if item.attendu:
            if posees:
                rapport.faux_positifs += 1
                rapport.erreurs.append(
                    f"FAUX POSITIF : « {item.texte[:60]} » est decidable ({item.note}) "
                    f"et la porte demande quand meme : {', '.join(posees)}"
                )
            else:
                rapport.vrais_negatifs += 1
        else:
            if not posees:
                rapport.faux_negatifs += 1
                rapport.erreurs.append(
                    f"FAUX NEGATIF : « {item.texte[:60]} » est ambigu ({item.note}) "
                    "mais la porte laisse partir la mission sans question"
                )
                continue
            rapport.vrais_positifs += 1
        # 2. La lecture des signaux, dans les DEUX sens : voir ce qui manque, et ne pas croire
        #    manquant ce qui est ecrit.
        en_trop = _en_trop(analyse, item)
        rapport.signaux_en_trop += len(en_trop)
        if en_trop:
            rapport.erreurs.append(
                f"SIGNAL EN TROP : « {item.texte[:60]} » porte pourtant "
                f"{', '.join(en_trop)} — signale(s) manquant(s) a tort ({item.note})"
            )
        if not item.attendu:
            vus = set(posees)
            oublies = (item.manquants - vus) - {"action"}
            if oublies:
                rapport.signaux_oublies += len(oublies)
                rapport.erreurs.append(
                    f"SIGNAL NON VU : « {item.texte[:60]} » manque {', '.join(sorted(oublies))} "
                    f"et la porte ne l'a pas signale ({item.note})"
                )
    return rapport


def formater(rapport: RapportPorte) -> str:
    """Le rapport du banc : les chiffres, puis CHAQUE erreur en clair."""
    lignes = [
        "  BANC D'OBJECTIFS  ·  la porte de clarification se trompe-t-elle ?",
        f"    {rapport.total} objectif(s) reels annote(s) a la main  ·  precision "
        f"{rapport.precision:.0%}  ·  rappel {rapport.rappel:.0%}",
        f"    ambigus signales {rapport.vrais_positifs}  ·  actionnables laisses tranquilles "
        f"{rapport.vrais_negatifs}  ·  faux positifs {rapport.faux_positifs}  ·  faux "
        f"negatifs {rapport.faux_negatifs}",
        f"    questions maximum posees : {rapport.max_questions} (borne {MAX_QUESTIONS})",
        "    signaux lus dans les DEUX sens  ·  manques par la porte (elle ne les verra pas) : "
        f"{rapport.signaux_oublies}  ·  juges absents a tort (elle poserait une question inutile) : "
        f"{rapport.signaux_en_trop}",
        "",
    ]
    if rapport.exact:
        lignes += [
            "    AUCUNE ERREUR : chaque objectif ambigu recoit ses questions, chaque objectif",
            "    decidable part au travail, et jamais plus de trois questions. Les signaux sont",
            "    verifies dans les deux sens : voir ce qui manque, et ne pas croire manquant ce",
            "    qui est ecrit.",
        ]
        return "\n".join(lignes)
    lignes.append(f"    {len(rapport.erreurs)} ERREUR(S) — chacune est un cas a corriger :")
    lignes.append("")
    lignes += [f"      - {erreur}" for erreur in rapport.erreurs]
    return "\n".join(lignes)
