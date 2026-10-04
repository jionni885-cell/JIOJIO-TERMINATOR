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
#:
#: LIMITE DECLAREE : la recherche par radical laisse un NOM mordre (« l'installation » croise
#: « installer »). Le departage par position corrige le cas ou un vrai verbe existe ailleurs dans
#: la phrase ; quand il n'y en a pas, la famille lue reste une LECTURE ANNONCEE — c'est-a-dire une
#: hypothese, jamais une preuve. Retirer ces formes couterait une question de plus sur des
#: objectifs decidables : le compromis est assume, ici, et pas decouvert par l'utilisateur.
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
    # « fusionner » manquait, et le trou etait visible en une commande. DEUX defauts pour un
    # seul mot absent, mesures tous les deux :
    #   * « fusionne les deux modules ... la suite doit rester verte » sortait avec « aucune
    #     action reconnue » ET une question d'action — sur un objectif qui nomme son action ;
    #   * « fusionner X et Y sans casser les tests » etait lu comme une action « tests » : le
    #     verbe INCONNU laissait la place a un mot plus loin dans la phrase, et la porte
    #     annoncait une action que l'utilisateur n'avait pas ecrite. Pire qu'une action
    #     manquante : une lecture fausse presentee comme une lecture.
    "fusionner": "transformation",
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
    # « arrange tous les problemes » : la famille est la bonne (amelioration), donc la porte le
    # range dans les verbes VAGUES — mais sans cette entree, elle affichait « aucune action
    # reconnue » sur une phrase qui en porte une. Ecrit apres l'avoir vu dans une vraie mission.
    "arranger": "amelioration",
}

#: Verbes d'ACTION en anglais, formes flechies ECRITES explicitement.
#:
#: Pourquoi une seconde table plutot que des mots de plus dans `_ACTIONS` : la recherche
#: francaise travaille par RADICAL (« amelior » reconnait « ameliore »), ce qui convient a une
#: langue aux formes regulieres — mais en anglais, le radical fait mordre « additional » sur
#: « add » et « tested » sur « test ». Ici on cherche donc des MOTS ENTIERS, avec leurs
#: flexions nommees une par une. Un radical anglais trop court est un piege, pas un raccourci.
#:
#: Cette table existe parce que le depot est bilingue : les prompts de ses agents sont en
#: anglais, et une porte qui ne comprend qu'une langue se tairait sur la moitie des missions.
_ACTIONS_EN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(fix|fixes|fixed|fixing|repair|repairs|repaired|debug|debugs|debugged)\b"),
     "correction"),
    (re.compile(r"\b(add|adds|added|adding|write|writes|writing|created|create|creates|creating|"
                r"implement|implements|implemented|implementing|generate|generates|generated|"
                r"generating)\b"), "ecriture"),
    (re.compile(r"\b(rename|renames|renamed|migrate|migrates|migrated|simplify|simplifies|"
                r"simplified|delete|deletes|deleted|remove|removes|removed|refactor|refactors|"
                r"refactored|merge|merges|merged)\b"), "transformation"),
    (re.compile(r"\b(optimize|optimizes|optimized|optimise|optimised|speed\s+up|accelerate|"
                r"accelerates|accelerated|reduce|reduces|reduced|reducing)\b"), "performance"),
    (re.compile(r"\b(analyze|analyzes|analyzed|analyse|analyses|analysed|audit|audits|audited|"
                r"verify|verifies|verified|measure|measures|measured|compare|compares|compared|"
                r"review|reviews|reviewed|scan|scans|scanned)\b"), "analyse"),
    (re.compile(r"\b(explain|explains|explained|document|documents|documented|summarize|"
                r"summarizes|summarized|describe|describes|described)\b"), "explication"),
    (re.compile(r"\b(test|tests|tested|testing|cover|covers|covered|covering)\b"), "tests"),
    (re.compile(r"\b(publish|publishes|published|deploy|deploys|deployed|install|installs|"
                r"installed|wire\s+up|wires\s+up|wired\s+up)\b"), "livraison"),
    (re.compile(r"\b(improve|improves|improved|improving|enhance|enhances|enhanced|"
                r"clean\s+up|cleans\s+up|arrange|arranges|arranged)\b"), "amelioration"),
)

#: Verbes qui, seuls, ne designent RIEN de verifiable. « Ameliore le projet » : ameliorer quoi,
#: et a quelle aune ? Ces objectifs demandent une question de CIBLE, meme si le verbe existe.
_VAGUES = frozenset({"ameliorer", "optimise", "optimiser", "simplifier", "nettoyer", "voir",
                     "regarder", "aider", "arranger",
                     # Anglais : les formes de la ligne « amelioration » de `_ACTIONS_EN`.
                     "improve", "improves", "improved", "improving", "enhance", "enhances",
                     "enhanced", "clean", "cleans", "arrange", "arranges", "arranged"})

#: Mots qui designent une CIBLE nommee : un chemin, un module, un objet precis.
_CIBLES = (
    re.compile(r"`[^`]+`"),
    re.compile(r"\b[\w./-]+\.(py|md|json|yaml|yml|toml|sh|txt|csv)\b"),
    # Noms qui IDENTIFIENT un objet du projet. `tests`, `docs` et `scripts` en sont
    # volontairement ABSENTS : « ajoute des tests » n'a pas de cible, et les y laisser faisait
    # passer l'objectif le plus vague du corpus pour une mission precise (mesure faite par
    # `jio/bench/objectifs.py`, qui l'a compte en FAUX NEGATIF).
    re.compile(r"\b(jio|harnais|harness|cli|api|moteur|boucle|banc|panel|journal)\b"),
    re.compile(r"\b[a-z_][a-z0-9_]{2,}\(\)"),
    re.compile(r"\b[A-Z][A-Za-z0-9]+[A-Z][A-Za-z0-9]*\b"),
)

#: Determiniant + nom : « la memoire des echecs », « le calcul de la moyenne ». C'est une
#: cible quand le nom designe une CHOSE, et pas un collectif vague.
_DETERMINEE = re.compile(
    r"\b(?:le|la|les|l'|mon|ma|mes|notre|nos|un|une|des|du|de la)\s+"
    r"([a-z][a-z0-9_-]{3,})"
)

#: Noms qui ne designent RIEN de verifiable : « corriger le bug », « ameliorer la qualite ».
#: Sans cette liste, la regle ci-dessus transformerait le moindre article en cible — et la
#: porte se tairait sur les objectifs les plus ambigus, exactement ceux qu'elle doit arreter.
#: Mesure a l'origine : `tests/test_clarify.py` et le banc d'objectifs ont montre que
#: « corrige le bug » et « ajoute des tests » passaient pour des objectifs cibles.
_NOMS_VAGUES = frozenset({
    "bug", "bugs", "erreur", "erreurs", "probleme", "problemes", "chose", "choses", "truc",
    "trucs", "ca", "cela", "projet", "depot", "repo", "code", "fichier", "fichiers",
    "documentation", "docs", "qualite", "revue", "test", "tests", "performance",
    "performances", "rapidite", "vitesse", "tout", "tous", "toutes", "ensemble", "partie",
    "parties", "aspect", "aspects", "point", "points", "zone", "zones", "endroit", "endroits",
    "thing", "things", "stuff", "issue", "issues", "quality", "review", "everything",
})


def _cible_nommee(texte: str) -> str:
    """Une cible par son NOM (« la memoire des echecs »), hors collectifs vagues.

    Rend le fragment reconnu, ou la chaine vide. C'est une detection de FORME, declaree comme
    telle : elle se trompe si un nom de chose est dans `_NOMS_VAGUES`, et cette liste est
    courte et lisible a dessein.
    """
    for trouve in _DETERMINEE.finditer(texte.lower()):
        nom = trouve.group(1)
        if nom not in _NOMS_VAGUES:
            return trouve.group(0)
    return ""


#: Mots qui annoncent un CRITERE de succes : on saura si c'est fini, et comment.
_CRITERES = (
    re.compile(r"\b(sans|zero|aucun|aucune)\s+(erreur|regression|echange|warning|echec)"),
    re.compile(r"\b(tous?\s+les\s+tests?|les\s+tests?\s+passent|vert|verts|conforme)\b"),
    re.compile(r"\b(en\s+moins\s+de|sous)\s+\d+"),
    re.compile(r"\b\d+\s*(ms|s|secondes?|minutes?|%|points?|lignes?|octets?|ko|mo)\b"),
    # Une borne de BOUCLE est un critere : « jusqu'a ce que 3 cycles ne trouvent plus d'axe » dit
    # exactement ou la poursuite s'arrete. Mesure a l'origine : elle sortait avec la question
    # « jusqu'ou dois-je continuer ? » — a une phrase qui venait de repondre.
    re.compile(r"\b\d+\s*(cycles?|tours?|passes?|iterations?|etapes?|missions?)\b"),
    re.compile(r"\b(meme|mêmes|identique|egal|egal a)\b"),
    re.compile(r"\b(pour|afin) que\b"),
    # « corrige le calcul de moyenne pour qu'il compte les jours feries » : le critere est le
    # COMPORTEMENT attendu, et c'est le meilleur critere qui existe (il est observable). Il
    # echappait a la porte a cause d'une seule lettre — l'elision « qu' » du francais, que le
    # motif « (pour|afin) que » ne couvrait pas. Mesure : l'objectif sortait avec la question
    # « comment saura-t-on que c'est fini ? » alors qu'il venait de le dire.
    re.compile(r"\b(pour|afin)\s+qu['\u2019]"),
    # « sans casser les tests », « sans rien casser », « sans casser l'existant » : en francais,
    # c'est le critere le PLUS ecrit, et il n'etait reconnu qu'PAR ACCIDENT. Quand la phrase
    # contenait « de tests » (« sans casser la suite de tests »), le motif des UNITES
    # (« en points de reussite », « de tests ») le prenait pour une unite — et l'objectif etait
    # juge borne par un motif ecrit pour autre chose. Les six autres formulations mesuraient le
    # defaut : « corrige X sans casser les tests » et « fix X without breaking the tests »
    # sortaient tous les deux avec la question « comment saura-t-on que c'est FINI ? », a des
    # objectifs qui venaient de repondre.
    re.compile(r"\bsans\s+(?:rien\s+)?cass\w*"),
    re.compile(r"\bwithout\s+breaking\b"),
    re.compile(r"\b(attendu|verifiable?|prouve|preuve|critere|seuil|borne)\b"),
    re.compile(r"\b(doit|devra|doivent)\b"),
    # « en points de reussite », « en missions », « en appels » : l'unite annoncee EST le
    # critere. Mesure a l'origine : « mesurer le gain ... en points de reussite » etait juge
    # sans critere, donc la porte demandait « comment saura-t-on ? » a un objectif qui venait
    # de le dire.
    re.compile(r"\b(?:en|de|par)\s+(?:points?|pour ?cent|%|missions?|tours?|appels?|regles?|"
               r"tests?|lignes?|secondes?|minutes?|millisecondes?)\b"),
    # Le LIVRABLE enonce fait office de critere : « et lister les regles non couvertes »
    # dit ce qui doit exister a la fin.
    re.compile(r"\b(lister|produire|rendre|fournir|sortir|ecrire|rapporter)\b.*\b(regles?|"
               r"liste|tableau|rapport|resume|fichiers?|resultats?)\b"),
    # Anglais : « proving X is idempotent », « the suite must stay green », « within 20 ms ».
    # Mesure a l'origine : deux objectifs anglais parfaitement bornes sortaient avec la
    # question « comment saura-t-on que c'est fini ? » — la porte ne connaissait que le
    # francais, et l'utilisateur ecrit dans les deux langues.
    re.compile(r"\b(proving|proves|proven|must\s+(stay|remain|pass|be)|should\s+(stay|remain|"
               r"pass|be)|so\s+that|stay\s+green|passing|green|within\s+\d+)\b"),
    # -- l'anglais, mesure sur le JEU DE CONTROLE (objectifs d'un autre projet) ------------- #
    #
    # Le meme raisonnement que ci-dessus, applique a la seconde langue : la porte connaissait
    # trois tournures anglaises et manquait toutes les autres. Mesure : sur 4 objectifs anglais
    # parfaitement bornes d'un projet ETRANGER, **4 recevaient la question « comment
    # saura-t-on que c'est FINI ? »** — soit 50 % d'exactitude en anglais contre 100 % en
    # francais. A l'usage, c'est le defaut le plus couteux : une question inutile A CHAQUE
    # objectif, et l'utilisateur apprend a ignorer la porte.
    #
    # Bornes quantitatives : « below 200 MB », « in under 60 lines », « at least 90 % ».
    re.compile(r"\b(below|under|above|over|at\s+most|at\s+least|no\s+more\s+than)\s+\d+"),
    # Un TEST nomme est un critere verificable : « cover it in tests/test_limits.py »,
    # « test it in `tests/test_deploy.py` ». Le francais avait l'equivalent (« avec un test
    # dans tests/… »), l'anglais ne l'avait pas.
    re.compile(r"\b(cover(?:ed|ing|s)?|test(?:ed|ing|s)?|check(?:ed|ing|s)?)\s+(?:it\s+)?"
               r"(?:in|by|with)\s+`?[\w./-]*tests?/"),
    # Un invariant explicite : « keeping `docker compose up` working », « keep the tests green ».
    re.compile(r"\bkeep(?:ing|s)?\s+[\w`./-]+\s+(working|green|passing|intact|unchanged)\b"),
)

#: Actions dont le RESULTAT est directement observable sur la cible : supprimer X (X a
#: disparu), renommer X en Y (Y existe), creer X dans un chemin donne (X existe). Le critere
#: est alors IMPLIQUE par l'action et la cible, et demander « comment saura-t-on que c'est
#: fini ? » serait une question de confort — le genre qui apprend a ignorer la porte.
#:
#: La liste est VOLONTAIREMENT courte : « corriger », « optimiser » ou « ameliorer » n'y sont
#: pas, parce qu'un fichier qui existe encore ne dit pas s'il est CORRECT.
#: Les verbes anglais sont ceux du FRANCAIS traduits, famille par famille : la regle est la
#: meme, elle n'etait simplement ecrite qu'en une langue. Mesure sur le jeu de controle :
#: « Write `docs/install.md` … » et « Add a `--dry-run` flag … » sortaient avec la question du
#: critere alors que l'action ET la cible nommee suffisaient — exactement comme « ecris » et
#: « ajoute » en francais, qui, eux, etaient reconnus.
_CRITERE_IMPLIQUE = {
    "supprimer": r"\b(supprimer|supprime|effacer|efface|retirer|retire|enlever|enleve|"
                 r"remove|removes|removed|delete|deletes|deleted|drop|drops|dropped)\b",
    "renommer": r"\b(renommer|renomme|deplacer|deplace|rename|renames|renamed|move|moves|"
                r"moved)\b",
    "creer": r"\b(ecrire|ecris|creer|cree|generer|genere|ajouter|ajoute|write|writes|written|"
             r"create|creates|created|generate|generates|generated|add|adds|added)\b",
}


def _critere_implique(texte: str, cible: str) -> str:
    """Le critere est-il IMPLIQUE par l'action et la cible nommee ? Rend la raison, ou vide."""
    if not cible:
        return ""
    for famille, motif in _CRITERE_IMPLIQUE.items():
        if re.search(motif, texte.lower()):
            # Il faut une cible NOMMEE (un chemin, un identifiant) : sans elle, « ajoute des
            # tests » ne dit toujours pas ce qui doit exister a la fin.
            return f"critere implique par l'action ({famille}) et la cible « {cible} »"
    return ""


#: Un mandat de POURSUITE : l'utilisateur ne redecrit pas la mission, il dit de CONTINUER.
#:
#: Trois raisons de le traiter a part, chacune mesuree sur un objectif REEL :
#:
#:   * sans cette reconnaissance, « continue avec les axes » sortait avec la question
#:     « quelle ACTION attends-tu ? (corriger / ecrire / analyser…) » — a un utilisateur qui
#:     venait de dire quoi faire. C'est le faux positif le plus couteux qui existe : il apprend
#:     a ignorer la porte ;
#:   * la question utile d'un mandat n'est pas « comment saura-t-on que c'est fini » mais
#:     « jusqu'ou continuer » : une boucle sans critere d'arret ne s'arrete que quand elle
#:     casse, et c'est alors la panne qui decide ;
#:   * un mandat HERITE son action du tour precedent : la chercher dans la phrase est une
#:     erreur de lecture, pas une exigence de precision.
#:
#: Le francais et l'anglais sont couverts : les prompts de ce depot sont anglais, les rapports
#: et les mandats recus sont souvent francais.
_POURSUITES = re.compile(
    r"\b(?:continue|continuez|continuer|poursuis|poursuivez|poursuivre|poursuite|"
    r"reprends|reprenez|reprendre|vas[- ]?y|"
    r"ne\s+t['\u2019]?arretes?\s+pas|ne\s+vous\s+arretez\s+pas|"
    r"keep\s+going|carry\s+on|go\s+on|keep\s+at\s+it|don['\u2019]?t\s+stop)\b"
)


def _plat(texte: str) -> str:
    """Le texte en minuscules et SANS ACCENTS : sert a chercher des formes conjuguees.

    « ne t'arrete pas » s'ecrit aussi « ne t'arrête pas » : chercher la forme accentuee ferait
    echouer la reconnaissance sur une lettre — et une porte qui echoue sur une lettre n'inspire
    pas confiance sur le reste.
    """
    plat = (texte or "").lower()
    for accents, simple in (
        ("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ûü", "u"), ("ç", "c"),
    ):
        for lettre in accents:
            plat = plat.replace(lettre, simple)
    return plat


def _poursuite(texte: str) -> str:
    """La forme de poursuite reconnue (« continue », « don't stop »), ou la chaine vide."""
    trouve = _POURSUITES.search(_plat(texte))
    return trouve.group(0).strip() if trouve else ""


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
    #: Obligatoire, et non « par defaut 1 » : toutes les constructions le donnent, et une
    #: valeur par defaut que personne n'utilise est une ligne que `jio mutants` signalait a
    #: juste titre comme non prouvee — elle ne pouvait pas changer le comportement.
    poids: int

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
    return set(re.findall(r"[a-z0-9_]+", _plat(texte)))


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


def _vague(forme: str) -> bool:
    """Le verbe reconnu designe-t-il, SEUL, quelque chose de verifiable ?

    Compare des FORMES (« ameliore » contre la liste de verbes vagues), par RADICAL, et non des
    familles : `_action` rend une famille (« amelioration ») alors que `_VAGUES` contient des
    verbes. La comparaison precedente ne pouvait donc jamais mordre, et la porte affichait
    « amelioration » — jamais « vague:amelioration » — sur les objectifs que sa propre doctrine
    decrit comme des souhaits. Une regle qui ne peut pas se declencher n'est pas une securite :
    c'est une ligne de plus a relire.
    """
    if not forme:
        return False
    return any(forme == vague or forme.startswith(_racine(vague)) for vague in _VAGUES)


def _action(texte: str, mots: set[str]) -> tuple[str, str]:
    """L'ACTION PRINCIPALE : le premier verbe, en position, pas le premier du dictionnaire.

    Deux regles, chacune payee par une mesure :

      * la recherche se fait sur le RADICAL — « corriger », « corrige », « corrigez » et
        « correction » designent le meme travail. Sans cela, la porte manquait l'action et
        posait une question d'action sur un objectif qui en portait une ;
      * le verbe retenu est celui qui apparaît le PLUS TOT dans la phrase, et non le premier de
        `_ACTIONS` qui mord. Mesure a l'origine : « ameliore la lisibilite du README pour que les
        nouveaux arrivants trouvent l'installation en moins de 2 minutes » sortait avec l'action
        « livraison » — le mot « installation » croisait le radical de « installer » AVANT que
        le dictionnaire n'arrive a « ameliorer ». La porte annoncait donc une action que
        l'utilisateur n'avait pas ecrite, ce qui est pire qu'une action manquante : c'est une
        lecture fausse, presentee comme une lecture.
      * a position egale, la forme EXACTE passe avant la forme approchee, puis l'ordre du
        dictionnaire. Et `mots` est parcouru TRIE : un ensemble n'a pas d'ordre, donc sans ce
        tri la forme reconnue dependait du hachage de la session, et la porte n'etait plus
        reproductible.
    """
    plat = _plat(texte)
    anglais = _action_en(plat)
    meilleur: tuple[int, int, int, str, str] | None = None
    for ordre, (forme, famille) in enumerate(_ACTIONS.items()):
        radical = _racine(forme)
        for mot in sorted(mots):
            if mot == forme:
                exact = 0
            elif mot.startswith(radical):
                exact = 1
            else:
                continue
            position = plat.find(mot)
            if position < 0:
                position = len(plat)
            cle = (position, exact, ordre, famille, mot)
            if meilleur is None or cle[:3] < meilleur[:3]:
                meilleur = cle
    if meilleur is None:
        return ("", "") if anglais is None else (anglais[1], anglais[2])
    # Les deux lectures sont comparees EN POSITION : le premier verbe de la phrase gagne, quelle
    # que soit la langue. Sans cette comparaison, une phrase mixte (« corrige le bug, then add a
    # test ») serait decidee par l'ordre des tables, pas par la phrase.
    if anglais is not None and anglais[0] < meilleur[0]:
        return anglais[1], anglais[2]
    return meilleur[3], meilleur[4]


def _action_en(plat: str) -> tuple[int, str, str] | None:
    """Le premier verbe d'action ANGLAIS de la phrase, en position. Rend `(position, famille, mot)`.

    Deux passes valent mieux qu'une table unique : la table francaise cherche des radicaux (juste
    pour le francais), la table anglaise des mots entiers (obligatoire en anglais). Les deux
    candidats sont ensuite departages par leur POSITION dans la phrase.
    """
    meilleur: tuple[int, str, str] | None = None
    for motif, famille in _ACTIONS_EN:
        trouve = motif.search(plat)
        if trouve is not None and (meilleur is None or trouve.start() < meilleur[0]):
            meilleur = (trouve.start(), famille, trouve.group(0))
    return meilleur


def _cherche(motifs: tuple[re.Pattern[str], ...], texte: str) -> str:
    """Le premier motif qui mord, rendu tel quel : la preuve, pas une impression."""
    for motif in motifs:
        trouve = motif.search(texte)
        if trouve:
            return trouve.group(0).strip()[:80]
    return ""


def _question_de_critere(poursuite: str = "") -> Question:
    """La question de critere — SPECIALISEE quand l'objectif est un mandat de poursuite.

    « Continue » et « comment saura-t-on que c'est fini ? » ne parlent pas du meme probleme. Un
    mandat de boucle est deja en cours : ce qui manque n'est pas la definition de « fini », c'est
    un ARRET. Un objectif borne, lui, a besoin de savoir ce qui doit passer pour etre cru.

    Le defaut du mandat est celui que la mission 8 a reellement negocie avec son utilisateur : un
    cycle complet (recherche, changement, tests, audit, mesures) PUBLIE avant de reprendre — un
    seul cycle, verifiable, plutot qu'une promesse d'avancer indefiniment.
    """
    if poursuite:
        return Question(
            signal="critere",
            question=(
                "Jusqu'ou dois-je continuer ? (un nombre de cycles, un seuil a atteindre, ou "
                "« tant que tu trouves des axes »)"
            ),
            pourquoi=(
                "une poursuite n'a pas de fin en elle-meme : sans critere d'arret, je continue "
                "jusqu'a ce que quelque chose casse — et c'est la panne qui decide de l'arret, "
                "pas toi."
            ),
            defaut=(
                "je fais UN cycle complet, je le publie avec ses preuves et ses mesures, puis "
                "je reprends — et je m'arrete quand un cycle entier ne trouve plus ni "
                "amelioration ni innovation."
            ),
            poids=3,
        )
    return Question(
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
    )


def _questions(
    texte: str,
    action: str,
    manquants: tuple[str, ...],
    *,
    max_questions: int,
    poursuite: str = "",
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
        "critere": _question_de_critere(poursuite),
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
    # Ce qui est ESSENTIEL, et ce qui ne l'est pas. Trois regles, chacune payee par une
    # mesure prise sur le banc d'objectifs (`jio/bench/objectifs.py`) :
    #
    #   * `cible` et `critere` sont essentiels : sans eux, le systeme choisit a la place de
    #     l'utilisateur, et personne ne peut dire si le travail est fini ;
    #   * `source` et `format` ne sont JAMAIS essentiels a eux seuls. Six objectifs reels
    #     parfaitement travaillables les ont fait poser en vain, soit 6 faux positifs sur 31 —
    #     et un faux positif apprend a ignorer la porte ;
    #   * `perimetre` n'est demande que si la cible ET le critere manquent : c'est alors une
    #     demande entierement floue (« ameliore le projet »), et le seul degat irreversible
    #     possible merite sa question. Sur un objectif cible et borne, elle est du confort.
    essentielles = ["cible", "critere"]
    if "cible" in manquants and "critere" in manquants:
        essentielles.append("perimetre")
    if "action" in manquants:
        essentielles.append("action")
    questions = [catalogue[nom] for nom in essentielles if nom in manquants]
    # L'ordre « cible puis critere » n'est PAS obtenu par un tri : il vient de l'ordre du
    # catalogue et des POIDS (cible et critere valent 3, perimetre 2, action 1), et le tri
    # ci-dessous est STABLE. Une ligne de tri (« si le verbe est vague, mettre cible et critere
    # d'abord ») a existe ici : elle comparait une FAMILLE a une liste de VERBES, donc elle ne
    # pouvait pas se declencher — et meme declenchee, les poids produisaient deja le meme ordre.
    # Deux raisons de la retirer, et la seconde suffisait.
    # Le departage se fait par POIDS : la question dont l'ignorance coute le plus passe
    # devant. Sans ce tri, `poids` etait une valeur decorative — et une valeur decorative
    # finit par etre fausse sans que personne ne le voie.
    questions.sort(key=lambda q: -q.poids)
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
    poursuite = _poursuite(brut)
    action, indice_action = _action(brut, mots)
    if poursuite:
        # Un mandat HERITE son action du tour precedent : chercher le verbe dans la phrase est
        # une erreur de lecture. Il prime donc sur un verbe vague eventuel (« continue
        # d'ameliorer » n'est pas plus clair qu'un mandat : c'est le mandat qui commande).
        action, indice_action = "poursuite", poursuite
    elif _vague(indice_action):
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
    cible = _cherche(_CIBLES, brut) or _cible_nommee(brut)
    critere = _cherche(_CRITERES, brut)
    # Le critere IMPLIQUE se deduit de la cible ECRITE : une cible heritee ne dit rien de ce qui
    # doit exister a la fin, et s'en servir ferait croire a un critere que personne n'a formule.
    implique = _critere_implique(brut, cible) if not critere else ""
    # Un mandat de poursuite HERITE sa cible : « continue » renvoie a la mission en cours. La
    # marquer presente n'est pas une commodite, c'est une lecture — et elle est ECRITE, pour qu'on
    # puisse la contester. Sans elle, la porte demandait « sur quoi exactement ? » a un utilisateur
    # qui venait de dire « continue » : la question la plus inutile de tout le catalogue.
    cible_du_mandat = cible or (
        f"heritee du mandat : « {poursuite} » renvoie a la mission en cours" if poursuite else ""
    )
    signaux = (
        Signal("action", bool(action), indice_action),
        Signal("cible", bool(cible_du_mandat), cible_du_mandat),
        Signal("critere", bool(critere or implique), critere or implique),
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
    questions = (
        []
        if actionnable
        else _questions(
            brut, action, manquants, max_questions=max_questions, poursuite=poursuite
        )
    )

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
