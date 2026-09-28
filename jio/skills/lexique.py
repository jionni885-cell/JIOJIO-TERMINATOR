"""Le pont bilingue du routeur de competences — et sa limite, ecrite noir sur blanc.

POURQUOI IL EXISTE. Le depot est bilingue par construction : les descriptions des competences
sont en francais, leurs corps et leurs noms sont en anglais, et l'utilisateur ecrit dans les deux
langues. Mesure faite sur le banc annote : cinq objectifs sur dix-neuf ne contenaient AUCUN mot
present dans l'index — non parce qu'aucune competence ne s'appliquait, mais parce que « the same
failure keeps coming back » ne partage pas un seul mot avec « memoire des echecs ». Le routeur
n'avait pas tort : il ne comprenait pas la question.

CE QUE CE N'EST PAS. Ce n'est pas un modele de langue, ni une traduction. C'est une table de
classes d'equivalence sur le vocabulaire du DOMAINE — la meme technique que `_ACTIONS_EN` dans la
porte de clarification, qui existe pour la meme raison et a paye la meme erreur avant nous. Un
mot d'une classe rappelle tous les autres, avec un poids plus faible que le mot ecrit, parce que
« test » et « preuve » ne sont pas interchangeables : ils sont seulement voisins.

SA LIMITE, ET ELLE EST REELLE. Le lexique a ete ecrit en regardant les echecs du banc. Sa
generalite n'est donc PAS mesuree : ce qui est mesure est son effet sur ce banc-la. Trois
proprietes le bornent tout de meme, et un test les verifie :

  * il ne contient que du vocabulaire de domaine, jamais une phrase entiere ni un objectif : une
    entree qui ressemblerait a une question serait un tour de passe-passe sur le banc ;
  * aucune classe ne melange deux competences REPUTATIONNELLEMENT confondues (mutation et
    memoire, par exemple) : un pont trop large ne route plus, il brouille ;
  * il reste petit et lisible en entier — un lexique qu'on ne peut pas relire est un lexique
    qu'on ne peut pas corriger.
"""

from __future__ import annotations

__all__ = ["CLASSES", "PONT", "concept", "concepts", "expansion", "poids"]


#: Le poids d'un mot VOISIN, par rapport au mot reellement ecrit.
#:
#: MESURE, et le plateau compte plus que le point : 0,0 (pas de pont) donne 61 % de premier choix
#: juste, 0,2 en donne 87 %, et la valeur reste entre 81 et 87 % jusqu'a 0,6. Autrement dit, la
#: valeur exacte n'est PAS un equilibre sur le fil — tout le plateau fonctionne, et 0,2 est le
#: bord bas de ce plateau. Un reglage qui ne tient qu'a une valeur serait un reglage sur le banc
#: plutot que sur le probleme.
POIDS_VOISIN = 0.2


#: Les classes d'equivalence du domaine. Un mot d'une classe rappelle les autres.
CLASSES: tuple[tuple[str, ...], ...] = (
    # -- preuve et execution ------------------------------------------------- #
    ("test", "tests", "testing", "check", "checks", "checked", "assert", "assertion",
     "preuve", "proof", "prove", "proving", "witness", "temoin", "temoin", "verification",
     "verifie", "verifier", "verify", "oracle", "oracles", "execution", "execute",
     "executable", "fail-closed", "green", "vert", "verts"),
    # -- invariance et mutation --------------------------------------------- #
    ("invariant", "invariants", "invariance", "metamorphic", "metamorphique", "mutation",
     "mutant", "mutants", "idempotent", "idempotence", "idempotency", "property", "propriete",
     "proprietes", "transformation", "transform", "tri", "sort", "sorted", "twice", "deux"),
    # -- recompense detournee ----------------------------------------------- #
    ("cheat", "cheating", "triche", "tricher", "trick", "hacking", "hack", "reward",
     "recompense", "game", "gaming", "shortcut", "raccourci", "exploit", "exploits",
     "contourne", "contournement", "detourne", "detournement"),
    # -- memoire des echecs -------------------------------------------------- #
    ("memory", "memoire", "failure", "failures", "fail", "fails", "failed", "echec", "echecs",
     "recall", "rappel", "rappeler", "souvenir", "souvenirs", "regression", "recidive",
     "revient", "revenir", "repetition", "repete", "again", "encore"),
    # -- contexte ------------------------------------------------------------ #
    ("context", "contexte", "prompt", "prompts", "token", "tokens", "jeton", "jetons",
     "window", "fenetre", "compaction", "compacter", "budget", "truncation", "troncature",
     "resume", "summary", "sature", "saturated", "length", "longueur", "forgets", "perd"),
    # -- securite ------------------------------------------------------------ #
    ("security", "securite", "injection", "hostile", "malicious", "malveillant", "untrusted",
     "provenance", "poison", "poisoned", "attack", "attaque", "adversaire", "adversarial",
     "dangerous", "dangereux", "ignore", "instructions"),
    # -- consensus ----------------------------------------------------------- #
    ("consensus", "agreement", "accord", "vote", "votes", "reviewer", "reviewers", "critique",
     "critiques", "panel", "decorrelation", "decorrele", "decorrelee", "echo", "quorum",
     "agree", "desaccord", "identical", "identiques", "same", "meme"),
    # -- documents et prose -------------------------------------------------- #
    ("document", "documents", "report", "rapport", "readme", "prose", "claim", "claims",
     "affirmation", "affirmations", "chiffre", "chiffres", "number", "numbers", "nombre",
     "nombres", "texte", "text", "markdown", "citation", "cite"),
    # -- reprise et cache ---------------------------------------------------- #
    ("resume", "reprise", "reprendre", "rollback", "cache", "checkpoint", "interruption",
     "interrupted", "interrompu", "restart", "redemarrage", "retry", "rejouer", "rejoue",
     "invalidate", "invalide", "stale", "perime"),
    # -- messages d'echec ---------------------------------------------------- #
    ("error", "errors", "erreur", "erreurs", "message", "messages", "stderr", "stdout",
     "exit", "code", "traceback", "stacktrace", "diagnostic", "feedback", "remontee",
     "recoit", "sans", "savoir", "quel", "quelle"),
    # -- abstention et calibration ------------------------------------------- #
    ("abstain", "abstention", "abstenir", "abstient", "calibration", "calibre", "calibree",
     "calibrated", "confidence", "confiance", "seuil", "threshold", "risk", "risque",
     "uncertainty", "incertitude", "sous", "au-dessus", "fake", "faux", "fausse"),
    # -- competences et evolution -------------------------------------------- #
    ("skill", "skills", "competence", "competences", "forge", "forging", "fabriquer",
     "creation", "creer", "self-improvement", "auto-amelioration", "metacognition",
     "metacognitive", "bibliotheque", "library", "enrichir", "enrichit"),
    # -- audit et revue (vocabulaire manquant, vu dans les echecs) ----------- #
    ("audit", "audite", "auditer", "auditeur", "auditrice", "revue", "relecture", "inspection",
     "review", "inspect", "controle", "controler", "supervise", "supervision"),
    # -- defaut et panne : un echec EST un defaut, dans les deux langues -------- #
    ("bug", "bugs", "bogue", "defaut", "defauts", "panne", "pannes", "fault", "faulty",
     "defect", "broken", "casse", "crashed", "crash", "plante", "plantage"),
    # -- agents et depot ----------------------------------------------------- #
    ("agent", "agents", "ia", "ai", "modele", "model", "models", "modele", "llm"),
    ("depot", "repository", "repo", "fichier", "fichiers", "file", "files", "code",
     "source", "module", "modules"),
)


def _index() -> dict[str, frozenset[str]]:
    """Mot normalise -> ses voisins. Normalise comme le routeur : sans accents, minuscules."""
    from .router import _sans_accent

    table: dict[str, frozenset[str]] = {}
    for classe in CLASSES:
        mots = frozenset(_sans_accent(m).lower() for m in classe)
        for mot in mots:
            # Un mot present dans DEUX classes garde l'union des deux : les classes se recouvrent
            # volontairement (« tri » est une transformation ET un test d'invariance), et
            # trancher serait inventer une distinction qui n'existe pas.
            table[mot] = table.get(mot, frozenset()) | (mots - {mot})
    return table


#: Le pont, construit une fois.
PONT: dict[str, frozenset[str]] = _index()


def _classes() -> dict[str, int]:
    """Mot -> numero de sa classe, la premiere qui le declare (les classes se recouvrent)."""
    table: dict[str, int] = {}
    from .router import _sans_accent

    for i, classe in enumerate(CLASSES):
        for mot in classe:
            table.setdefault(_sans_accent(mot).lower(), i)
    return table


#: Mot -> classe, construit une fois.
CONCEPT: dict[str, int] = _classes()


def expansion(texte: str) -> dict[str, float]:
    """Les termes d'un objectif, mots ecrits en 1,0 et leurs voisins en `POIDS_VOISIN`.

    Un voisin qui est AUSSI ecrit garde le poids du mot ecrit : la classe ne doit jamais
    affaiblir ce que l'utilisateur a dit.
    """
    from .router import jetons

    mots = jetons(texte)
    ecrits = frozenset(mots)
    poids: dict[str, float] = {}
    for mot in mots:
        poids[mot] = 1.0
        for voisin in PONT.get(mot, ()):
            if voisin in ecrits:
                continue
            poids[voisin] = max(poids.get(voisin, 0.0), POIDS_VOISIN)
    return poids


def poids(mot: str) -> float:
    """Le poids d'un mot comme entree de lexique, ou 0 s'il n'en fait pas partie."""
    return POIDS_VOISIN if mot in PONT else 0.0


def concept(mot: str) -> str:
    """L'IDENTITE d'un concept : la classe du lexique, ou le RADICAL du mot.

    C'est ici qu'un defaut a ete mesure, et il valait la peine d'etre ecrit. La premiere version
    donnait a chaque forme ECRITE son propre concept : « outil » et « outils » en comptaient
    donc DEUX, ainsi que « convert » et « convertir ». Deux objectifs hors sujet — « Ajouter une
    icone dans la barre d'outils » et « Convertir les images PNG en JPEG » — passaient ainsi le
    seuil d'evidence, et le routeur chargeait une competence pour une tache de plomberie.

    L'identite est donc le radical : deux formes du meme mot designent UN concept. Le repli sur
    le radical n'est pas un detail d'implementation, c'est la difference entre « cette phrase
    parle du domaine » et « cette phrase contient deux fois le meme mot ».
    """
    from .router import stem

    if mot in PONT:
        return f"classe:{CONCEPT.get(mot, mot)}"
    return f"mot:{stem(mot)}"


def concepts(texte: str) -> frozenset[str]:
    """Les concepts de DOMAINE qu'un objectif met en jeu — mots de contenu, sans doublon."""
    from .router import jetons

    return frozenset(concept(mot) for mot in jetons(texte))
