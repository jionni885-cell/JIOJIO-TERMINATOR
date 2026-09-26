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
        False, frozenset({"critere"}),
        "« optimise » sans chiffre : on ne saura jamais si c'est fini",
    ),
    Objectif(
        "il faudrait ameliorer les tests",
        False, frozenset({"critere"}),
        "quel critere ? couverture, duree, stabilite — trois travaux differents",
    ),
    Objectif(
        "analyse le depot",
        False, frozenset({"critere"}),
        "analyser pour repondre a quelle question ?",
    ),
    Objectif(
        "documente tout ca",
        False, frozenset({"cible", "critere"}),
        "« tout ca » ne designe rien de verifiable",
    ),
    Objectif(
        "fais en sorte que ca marche mieux",
        False, frozenset({"cible", "critere", "perimetre"}),
        "ni quoi, ni comment on mesure",
    ),
    Objectif(
        "il y a encore des choses a ameliorer, continue",
        False, frozenset({"cible", "critere"}),
        "mandat de boucle sans critere d'arret",
    ),
    Objectif(
        "refactorise",
        False, frozenset({"cible", "critere"}),
        "refactoriser quoi, et selon quelle propriete a preserver ?",
    ),
    Objectif(
        "make it better",
        False, frozenset({"cible", "critere"}),
        "anglais vague",
    ),
    Objectif(
        "why is it slow?",
        False, frozenset({"cible", "critere"}),
        "question ouverte : quelle partie, et mesuree comment ?",
    ),
    Objectif(
        "verifie que tout va bien",
        False, frozenset({"cible", "critere"}),
        "« tout » n'est pas un perimetre",
    ),
    Objectif(
        "mets a jour la documentation",
        False, frozenset({"critere"}),
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
        False, frozenset({"cible", "critere"}),
        "revue de quel artefact, selon quelles regles ?",
    ),
    Objectif(
        "continue",
        False, frozenset({"cible", "critere"}),
        "mandat de boucle : sans critere, il n'a pas de fin",
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
)


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


def mesurer(corpus: tuple[Objectif, ...] = CORPUS) -> RapportPorte:
    """Passe le corpus dans la porte et compte les erreurs, sans les arrondir."""
    rapport = RapportPorte(total=len(corpus))
    for item in corpus:
        analyse: Analyse = analyser(item.texte)
        rapport.max_questions = max(rapport.max_questions, len(analyse.questions))
        if item.attendu:
            if analyse.actionnable:
                rapport.vrais_negatifs += 1
            else:
                rapport.faux_positifs += 1
                rapport.erreurs.append(
                    f"FAUX POSITIF : « {item.texte[:60]} » est actionnable "
                    f"({item.note}) mais la porte demande : "
                    + ", ".join(q.signal for q in analyse.questions)
                )
            # Un signal juge manquant a tort est une erreur meme si l'objectif reste clair.
            en_trop = [
                s.nom for s in analyse.signaux
                if not s.present and s.nom in {"action", "cible", "critere"}
            ]
            rapport.signaux_en_trop += len(en_trop)
            if en_trop:
                rapport.erreurs.append(
                    f"SIGNAL EN TROP : « {item.texte[:60]} » a pourtant {item.note} ; "
                    f"signale(s) manquant(s) a tort : {', '.join(en_trop)}"
                )
            continue
        if analyse.actionnable:
            rapport.faux_negatifs += 1
            rapport.erreurs.append(
                f"FAUX NEGATIF : « {item.texte[:60]} » est ambigu ({item.note}) "
                "mais la porte laisse partir la mission sans question"
            )
            continue
        rapport.vrais_positifs += 1
        vus = {q.signal for q in analyse.questions}
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
        f"    questions maximum posees : {rapport.max_questions} (borne {MAX_QUESTIONS})"
        + ("  ·  signaux non vus : " + str(rapport.signaux_oublies)
           if rapport.signaux_oublies else ""),
        "",
    ]
    if rapport.exact:
        lignes += [
            "    AUCUNE ERREUR : chaque objectif ambigu recoit ses questions, chaque objectif",
            "    actionnable part au travail, et jamais plus de trois questions.",
        ]
        return "\n".join(lignes)
    lignes.append(f"    {len(rapport.erreurs)} ERREUR(S) — chacune est un cas a corriger :")
    lignes.append("")
    lignes += [f"      - {erreur}" for erreur in rapport.erreurs]
    return "\n".join(lignes)
