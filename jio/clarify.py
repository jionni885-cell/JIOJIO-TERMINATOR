"""Porte de clarification : les questions ESSENTIELLES avant le travail, pas apres.

Le probleme
-----------
Une IA a qui l'on dit « ameliore le projet » ne pose pas de question : elle part. Elle choisit
un perimetre, un format, un critere de reussite — et livre quelque chose de PLAUSIBLE qui
repond a une autre question que celle posee. Le cout n'est pas le travail : c'est le travail
perdu, et la confiance perdue avec.

L'inverse est aussi un defaut : une IA qui pose quinze questions pour un objectif clair est
insupportable, et on finit par ne plus lui parler.

La reponse
----------
Trois principes, et chacun est verifiable ici :

1. **Une question n'est essentielle que si la reponse change la sortie.** Chaque question
   porte donc `pourquoi` — la consequence EXACTE de ne pas y repondre, en une phrase. Une
   question dont on ne peut pas ecrire cette phrase est une question de confort : elle est
   retiree.

2. **On ne repond pas a une question par du travail supplementaire.** Chaque question porte
   son `defaut` : l'hypothese qui sera prise a defaut de reponse. On ne bloque jamais sans
   dire ce qu'on ferait sinon — et ce defaut est DECLARE en tete de mission, jamais tu.

3. **La detection est EXECUTABLE, pas intuitive.** Six signaux sont cherches dans l'objectif
   (action, cible, critere de succes, source, perimetre, format de sortie). Un objectif qui
   porte une action ET une cible ET un critere est ACTIONNABLE : zero question, on travaille.
   C'est mesurable, donc c'est reglable — et ce module est lui-meme mesure (voir
   `tests/test_clarify.py`).

Ce qu'il n'est pas : un modele de langue. Aucun appel de modele, aucune dependance, aucune
latence. Des expressions regulieres et des ensembles de mots — donc reproductible, testable,
et utilisable avant chaque mission sans cout.

Ce que le module ne fait PAS non plus : il ne decide pas a la place de l'utilisateur. Il pose
au maximum `MAX_QUESTIONS` questions, classees par consequence, et rend la main.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "MAX_QUESTIONS",
    "Signal",
    "Question",
    "Analyse",
    "analyser",
    "formater",
    "resume",
]

#: Au-dela de trois questions, on ne clarifie plus : on interroge. Une seule question mal
#: choisie coute plus qu'une hypothese declaree.
MAX_QUESTIONS = 3

# --------------------------------------------------------------------------- #
# Les six signaux, cherches dans l'objectif
# --------------------------------------------------------------------------- #

#: Verbes d'ACTION. Le verbe donne la nature du travail ; sans lui, l'objectif est un souhait.
_ACTIONS: dict[str, str] = {
    "corriger": "correction",
    "reparer": "correction",
    "fix": "correction",
    "bug": "correction",
    "implementer": "ecriture",
    "ecrire": "ecriture",
    "ajouter": "ecriture",
    "creer": "ecriture",
    "generer": "ecriture",
    "refactoriser": "transformation",
    "refactor": "transformation",
    "renommer": "transformation",
    "migrer": "transformation",
    "supprimer": "transformation",
    "simplifier": "transformation",
    "optimiser": "performance",
    "accelerer": "performance",
    "analyser": "analyse",
    "auditer": "analyse",
    "verifier": "analyse",
    "mesurer": "analyse",
    "comparer": "analyse",
    "expliquer": "explication",
    "documenter": "explication",
    "resumer": "explication",
    "tester": "tests",
    "couvrir": "tests",
    "publier": "livraison",
    "deployer": "livraison",
    "installer": "livraison",
    "cabler": "livraison",
    "brancher": "livraison",
    "ameliorer": "amelioration",
    "optimise": "amelioration",
}

#: Verbes qui, seuls, ne designent RIEN de verifiable. « Ameliore le projet » : ameliorer quoi,
#: et a quelle aune ? Ces objectifs demandent une question de CIBLE, meme si le verbe existe.
_VAGUES = frozenset({"ameliorer", "optimise", "optimiser", "simplifier", "nettoyer", "voir",
                     "regarder", "aider", "continuer"})

#: Mots qui designent une CIBLE nommee : un chemin, un module, un objet precis.
_CIBLES = (
    re.compile(r"`[^`]+`"),
    re.compile(r"\b[\w./-]+\.(py|md|json|yaml|yml|toml|sh|txt|csv)\b"),
    re.compile(r"\b(jio|tests?|docs?|scripts?|harnais|harness|cli|api|moteur|boucle)\b"),
    re.compile(r"\b[a-z_][a-z0-9_]{2,}\(\)"),
    re.compile(r"\b[A-Z][A-Za-z0-9]+[A-Z][A-Za-z0-9]*\b"),
)

#: Mots qui annoncent un CRITERE de succes : on saura si c'est fini, et comment.
_CRITERES = (
    re.compile(r"\b(sans|zero|aucun|aucune)\s+(erreur|regression|echange|warning|echec)"),
    re.compile(r"\b(tous?\s+les\s+tests?|les\s+tests?\s+passent|vert|verts|conforme)\b"),
    re.compile(r"\b(en\s+moins\s+de|sous)\s+\d+"),
    re.compile(r"\b\d+\s*(ms|s|secondes?|minutes?|%|points?|lignes?|octets?|ko|mo)\b"),
    re.compile(r"\b(meme|mêmes|identique|egal|egal a)\b"),
    re.compile(r"\b(pour|afin) que\b"),
    re.compile(r"\b(attendu|verifiable?|prouve|preuve|critere|seuil|borne)\b"),
    re.compile(r"\b(doit|devra|doivent)\b"),
)

#: Mots qui annoncent une SOURCE : d'ou vient ce sur quoi on travaille.
_SOURCES = (
    re.compile(r"\b(depuis|d'apres|a partir de|selon|dans)\s+\S"),
    re.compile(r"https?://\S+"),
    re.compile(r"\b(depot|repo|fichier|journal|log|code|document|donnees|base|corpus)\b"),
    re.compile(r"\b(mon|ma|mes|notre|nos|le|la|les)\s+(projet|code|repo|fichier|document)\b"),
)

#: Mots qui annoncent un PERIMETRE : ce qu'on ne touche pas.
_PERIMETRES = (
    re.compile(r"\b(sans (toucher|modifier|casser|changer))\b"),
    re.compile(r"\b(hors|en dehors)\b"),
    re.compile(r"\b(uniquement|seulement|juste|limite a|limitee? a)\b"),
    re.compile(r"\b(ne pas|n'|jamais|interdit|prohibe)\b"),
    re.compile(r"\b(compatibilite|retrocompatibles?|version|python\s*3\.\d+)\b"),
)

#: Mots qui annoncent un FORMAT de sortie.
_FORMATS = (
    re.compile(r"\b(markdown|md|json|yaml|csv|tableau|diagramme|rapport|resume|patch|diff)\b"),
    re.compile(r"\b(un|une)\s+(rapport|fichier|document|liste|tableau|script|module|test)\b"),
    re.compile(r"\b(en|dans)\s+(francais|anglais|français|english|french)\b"),
)


@dataclass(frozen=True)
class Signal:
    """Ce qu'on a cherche, ce qu'on a trouve, et pourquoi ca compte."""

    nom: str
    present: bool
    indice: str


@dataclass(frozen=True)
class Question:
    """Une question essentielle : la question, sa consequence, et le defaut pris sans reponse."""

    signal: str
    question: str
    pourquoi: str
    defaut: str
    #: Nombre de consequences concretes : sert a classer (la plus lourde d'abord).
    poids: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "question": self.question,
            "pourquoi": self.pourquoi,
            "defaut": self.defaut,
        }


@dataclass
class Analyse:
    """Le verdict de la porte : travaillable, ou N questions avant de commencer."""

    objectif: str
    signaux: tuple[Signal, ...] = ()
    questions: tuple[Question, ...] = ()
    action: str = ""
    #: Vrai quand rien ne manque : l'objectif porte une action, une cible et un critere.
    actionnable: bool = False
    #: Vrai quand on peut avancer malgre les questions (hypotheses DECLAREES).
    avancable: bool = True
    mode: str = "assume"          # assume | strict
    motif: str = ""

    @property
    def manquants(self) -> tuple[str, ...]:
        return tuple(s.nom for s in self.signaux if not s.present)

    @property
    def bloquant(self) -> bool:
        """En mode strict, des questions sans reponse BLOQUENT la mission."""
        return self.mode == "strict" and bool(self.questions)

    def as_dict(self) -> dict[str, object]:
        return {
            "objectif": self.objectif,
            "action": self.action,
            "actionnable": self.actionnable,
            "mode": self.mode,
            "motif": self.motif,
            "signaux": {s.nom: s.present for s in self.signaux},
            "indices": {s.nom: s.indice for s in self.signaux if s.indice},
            "questions": [q.as_dict() for q in self.questions],
            "hypotheses": {q.signal: q.defaut for q in self.questions},
        }


def _mots(texte: str) -> set[str]:
    """Mots normalises (sans accents, en minuscules) pour comparer sans piege d'encodage."""
    plat = (texte or "").lower()
    for accent, simple in (
        ("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ûü", "u"), ("ç", "c"),
    ):
        for lettre in accent:
            plat = plat.replace(lettre, simple)
    return set(re.findall(r"[a-z0-9_]+", plat))


def _racine(forme: str) -> str:
    """Radical utilisable pour reconnaitre les formes conjuguees : `ameliorer` -> `amelior`.

    Un utilisateur ecrit « ameliore le projet », pas « ameliorer le projet ». Reconnaitre le
    seul infinitif faisait manquer l'action la plus courante — mesure faite sur « ameliore le
    projet », qui sortait avec « aucune action reconnue ».
    """
    for suffixe in ("er", "ir", "re", "ar"):
        if forme.endswith(suffixe) and len(forme) - len(suffixe) >= 4:
            return forme[: -len(suffixe)]
    return forme


def _action(texte: str, mots: set[str]) -> tuple[str, str]:
    """Le verbe d'action principal, s'il y en a un. Rend `(action, famille)` + la forme vue.

    La recherche se fait sur le RADICAL : « corriger », « corrige », « corrigez » et
    « correction » designent le meme travail. Sans cela, la porte manquait l'action et posait
    une question d'action sur un objectif qui en portait une — le genre de faux positif qui
    fait perdre confiance dans la porte elle-meme.
    """
    for forme, famille in _ACTIONS.items():
        radical = _racine(forme)
        for mot in mots:
            if mot == forme or mot.startswith(radical):
                return famille, mot
    return "", ""


def _cherche(motifs: tuple[re.Pattern[str], ...], texte: str) -> str:
    """Le premier motif qui mord, rendu tel quel : la preuve, pas une impression."""
    for motif in motifs:
        trouve = motif.search(texte)
        if trouve:
            return trouve.group(0).strip()[:80]
    return ""


def _questions(
    texte: str, action: str, manquants: tuple[str, ...], *, max_questions: int
) -> tuple[Question, ...]:
    """Construit les questions manquantes, classees par consequence, bornees.

    L'ordre est celui du COUT de l'ignorance, pas celui des signaux :

      1. la cible — se tromper d'objet, c'est tout refaire ;
      2. le critere de succes — sans lui, « fini » est une opinion, et la mission ne peut pas
         s'auto-verifier : c'est la seule question qui empeche la boucle de preuve de servir ;
      3. la source — travailler sur autre chose que ce qui est vise, c'est produire du plausible ;
      4. le perimetre — ecrire la ou il ne fallait pas est le seul degat irreversible ;
      5. le format — rejouable, mais ca coute un tour entier ;
      6. l'action — quand elle manque, la cible ET le critere manquent presque toujours ; la
         question d'action se pose alors en dernier recours, avec un choix ferme.
    """
    catalogue: dict[str, Question] = {
        "cible": Question(
            signal="cible",
            question=(
                "Sur QUOI exactement ? (un chemin, un module, un fichier, ou une fonction) "
                "Tu peux repondre en une ligne, ou coller le chemin."
            ),
            pourquoi=(
                "sans cible nommee, je choisis moi-meme l'objet du travail — et si je choisis "
                "le mauvais, tout ce qui suit est a refaire, y compris les preuves."
            ),
            defaut=(
                "je prends le point d'entree le plus probable du depot et je l'ANNONCE avant "
                "de commencer, pour que tu puisses m'arreter."
            ),
            poids=3,
        ),
        "critere": Question(
            signal="critere",
            question=(
                "Comment saura-t-on que c'est FINI et CORRECT ? (un test qui doit passer, un "
                "chiffre a atteindre, un format attendu)"
            ),
            pourquoi=(
                "c'est la seule question qui rend le resultat verifiable : sans critere, je ne "
                "peux pas me prouver que j'ai fini, seulement te demander de me croire."
            ),
            defaut=(
                "j'exige la suite de tests du depot verte et je publie ce qui reste non "
                "verifie, en reserve nommee."
            ),
            poids=3,
        ),
        "source": Question(
            signal="source",
            question=(
                "D'OU vient l'information a exploiter ? (le depot, un fichier precis, un "
                "journal, une URL)"
            ),
            pourquoi=(
                "sans source, je travaille sur ma memoire du sujet au lieu du tien — le "
                "resultat sera plausible et peut-etre faux, ce qui est le pire des deux."
            ),
            defaut="je travaille sur le depot courant, a sa revision actuelle.",
            poids=2,
        ),
        "perimetre": Question(
            signal="perimetre",
            question=(
                "Qu'est-ce qui est INTERDIT de toucher ? (fichiers, dependances, "
                "compatibilite, ce qui ne doit pas casser)"
            ),
            pourquoi=(
                "une modification non demandee est le seul degat irreversible : elle part dans "
                "l'historique, et tu la decouvres apres."
            ),
            defaut=(
                "je ne modifie que ce que la mission exige, je ne supprime rien, et je "
                "n'installe aucune dependance."
            ),
            poids=2,
        ),
        "format": Question(
            signal="format",
            question=(
                "Le resultat, sous quelle forme et dans quelle langue ? (code modifie, "
                "rapport, tableau ; francais ou anglais)"
            ),
            pourquoi=(
                "un bon resultat dans le mauvais format se refait entierement : c'est un tour "
                "complet paye pour une question non posee."
            ),
            defaut="code modifie dans le depot + synthese courte en francais, preuves a l'appui.",
            poids=1,
        ),
        "action": Question(
            signal="action",
            question=(
                "Quelle ACTION attends-tu ? (corriger / ecrire / analyser / mesurer / "
                "expliquer / livrer — choisis-en une)"
            ),
            pourquoi=(
                "« ameliorer » ne dit pas s'il faut modifier du code, produire une mesure, ou "
                "expliquer quelque chose : ce sont trois travaux differents."
            ),
            defaut="j'analyse d'abord, je propose un plan chiffre, et je n'ecris rien avant ton accord.",
            poids=1,
        ),
    }
    ordre = ("cible", "critere", "source", "perimetre", "format", "action")
    questions = [catalogue[nom] for nom in ordre if nom in manquants]
    if action in _VAGUES:
        # Un verbe vague est traite comme une action absente : c'est precise dans le motif.
        questions.sort(key=lambda q: (q.signal != "cible", q.signal != "critere"))
    return tuple(questions[:max_questions])


def analyser(
    objectif: str,
    *,
    contexte: str = "",
    max_questions: int = MAX_QUESTIONS,
    mode: str = "assume",
) -> Analyse:
    """Analyse un objectif et rend ce qui manque POUR DECIDER — au plus `max_questions`.

    `contexte` (le contenu d'un README ou d'un AGENTS.md) complete ce que l'objectif ne dit
    pas du MONDE : d'ou vient l'information (`source`) et ce qui est interdit (`perimetre`).
    Il ne fournit jamais l'action, la cible ni le critere : ceux-la appartiennent a la
    demande, et les deduire du projet reviendrait a choisir a la place de l'utilisateur.
    """
    brut = (objectif or "").strip()
    if mode not in {"assume", "strict"}:
        raise ValueError(f"mode inconnu : {mode!r} (attendu : assume ou strict)")
    if not brut:
        question = Question(
            signal="objectif",
            question="Quel est l'objectif, en une phrase ?",
            pourquoi="il n'y a rien a executer : je ne peux pas inventer une mission.",
            defaut="aucun — je m'arrete et j'attends l'objectif.",
            poids=3,
        )
        return Analyse(
            objectif="", questions=(question,), actionnable=False, avancable=False,
            mode=mode, motif="objectif vide : rien a analyser",
        )

    texte = brut + "\n" + (contexte or "")
    mots = _mots(brut)
    action, indice_action = _action(brut, mots)
    if action in _VAGUES:
        action = f"vague:{action}"

    # Qui fournit quoi, et pourquoi cette repartition n'est pas un detail :
    #
    #   * la DEMANDE dit ce qu'on fait, sur QUOI, et comment on saura que c'est fini
    #     (action, cible, critere) — c'est la part non delegable : demander « rends ca
    #     mieux » et laisser le projet decider de la cible, c'est choisir a la place de
    #     l'utilisateur ;
    #   * le CONTEXTE du projet dit sur quoi on est autorise a travailler (source) et ce
    #     qui est interdit (perimetre) — des faits du monde, pas des intentions.
    #
    # Une version precedente laissait le contexte fournir la CIBLE : n'importe quel README
    # citant un chemin faisait alors disparaitre la question « sur quoi ? », et la porte se
    # taisait precisement dans le cas ou elle sert.
    signaux = (
        Signal("action", bool(action), indice_action),
        Signal("cible", bool(_cherche(_CIBLES, brut)), _cherche(_CIBLES, brut)),
        Signal("critere", bool(_cherche(_CRITERES, brut)), _cherche(_CRITERES, brut)),
        Signal("source", bool(_cherche(_SOURCES, texte)), _cherche(_SOURCES, brut)),
        Signal("perimetre", bool(_cherche(_PERIMETRES, texte)), _cherche(_PERIMETRES, brut)),
        Signal("format", bool(_cherche(_FORMATS, brut)), _cherche(_FORMATS, brut)),
    )
    presents = {s.nom: s.present for s in signaux}
    # Le trio qui rend un objectif TRAVAILLABLE : une action, une cible, un critere. Les
    # trois autres amenent du confort ou une securite, pas la possibilite de commencer.
    noyau = ("action", "cible", "critere")
    actionnable = all(presents[nom] for nom in noyau) and not action.startswith("vague:")
    manquants = tuple(s.nom for s in signaux if not s.present)
    questions = [] if actionnable else _questions(brut, action, manquants, max_questions=max_questions)

    if actionnable:
        motif = (
            "objectif actionnable : une action, une cible nommee et un critere de reussite "
            "sont presents. Aucune question n'est utile — commencer."
        )
    elif not questions:
        motif = "objectif actionnable : rien d'essentiel ne manque."
    else:
        motif = (
            f"{len(questions)} question(s) essentielle(s) : chacune change la sortie, et "
            "chaque defaut pris sans reponse sera DECLARE avant de commencer."
        )

    return Analyse(
        objectif=brut,
        signaux=signaux,
        questions=tuple(questions),
        action=action or "(aucune action reconnue)",
        actionnable=actionnable,
        avancable=True,
        mode=mode,
        motif=motif,
    )


def _puce(signal: Signal) -> str:
    return f"{'oui' if signal.present else 'NON':<3} {signal.nom:<10} {signal.indice[:70]}"


def _enroule(texte: str, *, largeur: int, debut: str = "", suite: str = "") -> list[str]:
    """Enroule un texte long en lignes indentees plutot que de le TRONQUER.

    Mesure a l'origine : la premiere version coupait a 100 caracteres. Les questions
    perdaient leur fin — « je ne peux pas me prouver que j'ai fini, seulement te demander de
    me croire » devenait « ...seulement te demander de me cr ». Une question tronquee n'est
    plus une question : c'est une phrase qui fait douter de l'outil.
    """
    import textwrap

    return textwrap.wrap(
        texte, width=max(20, largeur - len(suite)), initial_indent=debut,
        subsequent_indent=suite or debut, break_long_words=False, break_on_hyphens=False,
    ) or [debut.rstrip()]


def formater(analyse: Analyse, *, largeur: int = 100) -> str:
    """Le texte a MONTRER a l'utilisateur — c'est la sortie de `jio clarify`."""
    lignes = [
        "  PORTE DE CLARIFICATION  ·  avant de travailler, ce qui manque pour decider",
        f"    objectif : {analyse.objectif[:80] or '(vide)'}",
        f"    action reconnue : {analyse.action}",
        "",
        "    SIGNAUX (cherches dans l'objectif, pas devines)",
    ]
    lignes += [f"      {_puce(s)}" for s in analyse.signaux]
    lignes.append("")
    if not analyse.questions:
        lignes += [
            "    AUCUNE QUESTION : l'objectif porte une action, une cible et un critere.",
            "    Travailler, prouver, et rendre les preuves. Les questions de confort se",
            "    posent APRES, si quelque chose reste indetermine.",
        ]
        return "\n".join(ligne[:largeur] for ligne in lignes)

    lignes += [
        f"    {len(analyse.questions)} QUESTION(S) ESSENTIELLE(S) — la reponse change la sortie",
        "",
    ]
    for i, question in enumerate(analyse.questions, 1):
        prefixe = f"    {i}. "
        lignes += _enroule(question.question, largeur=largeur - 8, debut=prefixe,
                           suite=" " * len(prefixe))
        lignes += _enroule(question.pourquoi, largeur=largeur - 8,
                           debut="       pourquoi : ", suite="         ")
        lignes += _enroule("defaut sans reponse : " + question.defaut, largeur=largeur - 8,
                           debut="       ", suite="         ")
        lignes.append("")
    lignes += [
        "    Si tu reponds : relance la mission avec ta reponse. Si tu ne reponds pas, les",
        "    defauts ci-dessus sont PRIS et ANNONCES en tete de mission — jamais caches.",
    ]
    return "\n".join(ligne[:largeur] for ligne in lignes)


def resume(analyse: Analyse) -> str:
    """Une ligne pour les rapports : ce qui a ete suppose, et ce qui bloquait."""
    if analyse.actionnable:
        return "objectif actionnable : 0 question"
    if not analyse.questions:
        return "objectif actionnable"
    signaux = ", ".join(q.signal for q in analyse.questions)
    return (
        f"{len(analyse.questions)} question(s) essentielle(s) ({signaux}) ; "
        f"mode {analyse.mode} : "
        + ("mission BLOQUEE tant qu'elles n'ont pas de reponse" if analyse.bloquant
           else "hypotheses DECLAREES et mission poursuivie")
    )
