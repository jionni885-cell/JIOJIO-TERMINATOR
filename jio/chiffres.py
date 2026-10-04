"""Les chiffres de la documentation : mesures, ecarts, et REPARATION.

Le README a annonce « 187 tests verts » alors que la suite en comptait 520. Personne ne
recalcule un compteur en lisant une page — et c'est exactement le genre d'affirmation qui
detruit la confiance dans tout le reste du document.

Le controle existait deja (`tests/test_chiffres_documentes.py`). Il a mordu trois fois, et
trois fois la reaction a ete la meme : ouvrir le README a la main et retaper un nombre. Un
controle **qui punit sans reparer** finit par etre desactive — ou, pire, par etre suivi d'un
`--no-verify`. Celui-ci dit desormais quoi corriger *et* sait le corriger :

    jio chiffres               # que disent la documentation et la realite ?
    jio chiffres --appliquer   # ecrire les valeurs mesurees, avec sauvegarde

Trois regles, heritees du reste du projet :

  * **une seule mesure** — le nombre de tests vient d'un vrai `pytest --collect-only`, le
    nombre de competences et d'agents des definitions qui les generent. Aucun chiffre
    n'est saisi a la main, ici comme dans le document ;
  * **un ecart se nomme** — il porte son fichier, sa ligne, l'ancien et le nouveau texte,
    parce qu'un diagnostic sans localisation oblige a refaire le travail de l'outil ;
  * **une ecriture se verifie** — apres reecriture, le controle est relance ; s'il reste un
    ecart, le fichier est restaure et la commande echoue. Une reparation qui rend le
    document faux est pire que pas de reparation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .artifacts.definitions import AGENTS, SKILLS

__all__ = ["Chiffre", "Ecart", "CHIFFRES", "mesurer", "ecarts", "reparer"]


#: Une zone de texte volontairement hors controle, entre ces deux marqueurs. Elle sert a
#: ce qu'un document puisse RACONTER une erreur passee (« il annoncait 187 tests pour 520 »)
#: sans que le controle prenne cette phrase pour une affirmation du jour. Sans echappatoire,
#: un controle finit par interdire de documenter ses propres defauts.
#: Les marqueurs sont des PREFIXES : la raison de l'exemption s'ecrit apres, sur la meme
#: ligne, et le rapport la reprend. Une exemption sans raison ecrite est presque toujours
#: une exemption qu'on ne saura plus justifier six mois plus tard.
OUVRE = "<!-- chiffres:hors-controle"
FERME = "<!-- /chiffres:hors-controle"


def zones_hors_controle(texte: str) -> tuple[set[int], list[str]]:
    """Rend les numeros de ligne hors controle, et POURQUOI elles le sont.

    La logique vit desormais dans `jio/verify/hors_controle.py` : le besoin a depasse les
    chiffres (les commandes citees, les calculs d'une prose, les exemples de sortie d'outil),
    et trois implementations auraient fini par ne plus s'accorder sur ce qui est exempte. Ici,
    on garde le nom historique : `ecarts` et `reparer` l'appellent, et la compatibilite des
    marqueurs ecrits dans les documents existants est assuree par le module generique.
    """
    from .verify.hors_controle import zones

    return zones(texte)


@dataclass(frozen=True)
class Chiffre:
    """Une grandeur verifiable, ecrite dans le document sous une forme reperable.

    Le motif porte **exactement un** groupe de capture : le nombre. C'est lui qui est
    remplace, jamais le reste de la phrase — une reparation ne doit pas reecrire du texte
    qu'elle n'a pas mesure.
    """

    nom: str
    motif: str
    description: str
    #: Vrai quand le motif est volontairement ANCRE a gauche (« les N competences »). Sans
    #: ancre, la taille d'un panel ecrite dans un tableau (« | 2 agents | ») serait prise
    #: pour une annonce de la bibliotheque d'agents : un faux positif dans un controle de
    #: documentation, c'est-a-dire un bug du controle lui-meme.
    ancre: bool = True
    #: Motif qui doit AUSSI apparaitre sur la ligne pour que le nombre soit celui qu'on croit.
    #: Une liste d'exceptions (« pas si c'est suivi de jamais vus ») est une course sans fin :
    #: chaque nouvelle phrase parlant d'un autre nombre demande une exception de plus, et
    #: l'oubli ne se voit pas — il produit exactement ce que ce module doit empecher, un
    #: chiffre JUSTE reecrit en chiffre faux. Un contexte POSITIF retourne le probleme :
    #: un nombre n'est surveille que dans la phrase qui parle de sa grandeur, et une phrase
    #: qu'on n'a pas prevue est simplement laissee tranquille.
    contexte: str = ""

    def annonce(self, texte: str) -> bool:
        """Le document annonce-t-il ce chiffre, sous la forme surveillee ?

        Question differente de « le chiffre est-il juste », et elle manquait : `ecarts()` rend
        une ABSENCE comme un ecart (c'est voulu — sinon un controle devient vert parce qu'il ne
        trouve plus rien a verifier). Mais ce raisonnement vaut pour les documents de CE depot,
        qui se sont engages a annoncer ces grandeurs. Applique au README d'un projet TIERS, il
        reprochait a ce projet de ne pas annoncer les huit chiffres de JIO et faisait echouer
        son portail — mesure sur un projet etranger, avec un README qui dit seulement
        « python -m pytest lance les tests ». Un controle doit savoir si son sujet PARTICIPE
        avant de le declarer en faute.
        """
        hors_controle, _ = zones_hors_controle(texte)
        motif = re.compile(self.motif)
        contexte = re.compile(self.contexte) if self.contexte else None
        for indice, ligne in enumerate(texte.splitlines(), start=1):
            if indice in hors_controle:
                continue
            if contexte and not contexte.search(ligne):
                continue
            if motif.search(ligne):
                return True
        return False


CHIFFRES: tuple[Chiffre, ...] = (
    Chiffre(
        nom="tests",
        motif=r"(\d+) tests? verts?",
        description="la suite complete, comptee par pytest",
    ),
    Chiffre(
        nom="competences",
        motif=r"[Ll]es (\d+) compétences",
        description="la bibliotheque de competences (jio/artifacts/definitions.py)",
    ),
    Chiffre(
        nom="agents",
        motif=r"[Ll]es (\d+) agents",
        description="les agents generes (jio/artifacts/definitions.py)",
    ),
    # Le banc d'objectifs est entre dans le README comme un argument (« 0 faux positif, 0 faux
    # negatif »), avec son nombre. Ce nombre etait le seul chiffre du README que RIEN ne
    # mesurait : il a donc pu passer de 38 a 41 sans que le controle des nombres bronche —
    # exactement le defaut que ce module existe pour supprimer. Trois objectifs y sont entres
    # le jour ou la porte a appris a lire « fusionner » et « sans casser les tests » ; la
    # phrase du README, elle, annoncait toujours 38.
    Chiffre(
        nom="objectifs",
        # Les exceptions sont des CONTEXTES ou le nombre parle d'autre chose que du banc de la
        # porte. « jamais vus » manquait : `--appliquer` a reecrit « 48 objectifs jamais vus »
        # (les deux jeux de controle du routeur) en « 41 objectifs jamais vus » (la taille du
        # banc de clarification) — un chiffre JUSTE transforme en chiffre faux par l'outil cense
        # les proteger. Un motif large se paie toujours quelque part : ici, il faut nommer
        # chaque contexte qui parle d'un autre nombre.
        motif=r"(\d+) objectifs(?! de routage| de contr| du jeu de contr| d'un projet| hors sujet"
              r"| pertinents| jamais vus| du banc| d'essai)",
        # La phrase qui parle du banc de la porte : c'est la SEULE ou ce nombre a un sens.
        # « 24 objectifs jamais vus », « 24 objectifs, ecrit avant la retouche » parlent du
        # routeur de competences et ne doivent pas etre touches.
        contexte=r"faux positif|faux n[ée]gatif|--mesure|objectifs r[ée]els",
        description="le banc d'objectifs de la porte de clarification (jio/bench/objectifs.py)",
    ),
    # Le routeur de competences publie lui aussi deux nombres dans le README : la taille de son
    # banc et son taux de premier choix juste. Ce sont exactement le genre de chiffres qui
    # pourrissent en silence — un banc qu'on enrichit sans mettre a jour la phrase, un seuil
    # qu'on ajuste sans recalculer le taux. Les deux sont donc MESURES, pas recopies.
    Chiffre(
        nom="objectifs_routage",
        motif=r"(\d+) objectifs de routage",
        description="le banc annote du routeur de competences (jio/skills/banc.py)",
    ),
    # Le JEU DE CONTROLE du meme routeur. Sa taille entre dans la documentation au moment ou
    # l'ecart banc/controle devient le resultat principal — c'est-a-dire au moment exact ou ce
    # nombre peut pourrir : enrichir le jeu de controle sans relire la phrase qui l'annonce
    # ferait disparaitre la mesure en silence. Il est donc VERIFIE, comme les autres.
    Chiffre(
        nom="objectifs_controle",
        motif=r"(\d+) objectifs (?:de |du jeu de )contr[oô]le",
        description="le jeu de controle du routeur, ecrit avant la derniere retouche des fiches",
    ),
    # Le MEME dispositif pour la porte de clarification : son banc cite les chemins de ce
    # depot, donc un second jeu (d'un projet etranger) mesure ce que le banc ne peut pas. Sa
    # taille est un chiffre annonce — elle est donc verifiee comme les autres, sinon la phrase
    # qui dit « 22 objectifs » survivrait a un jeu devenu 30.
    Chiffre(
        nom="objectifs_controle_clarify",
        motif=r"(\d+) objectifs d'un projet",
        description="le jeu de controle de la porte de clarification (un projet etranger)",
    ),
    # La TAILLE des jeux de controle, reunie : elle est publiee dans le README comme un
    # argument (« 113 cas jamais vus »), donc elle est mesuree comme les autres. Le mot choisi
    # est « cas » et non « objectifs » : c'est ce qui la distingue des huit autres nombres
    # surveilles, et un motif qui les melangerait reecrirait les uns avec la valeur des autres.
    Chiffre(
        nom="cas_controle",
        motif=r"(\d+) cas jamais vus",
        description="les quatre jeux de controle du routeur de competences (jio/skills/controle*.py)",
    ),
    # Le motif est insensible a la casse parce que la phrase vit en milieu de paragraphe
    # (« Premier choix juste dans 77 % des cas ») : un chiffre juste mais non surveille a cause
    # d'une majuscule serait exactement le defaut que ce module supprime.
    # La TAILLE de la table de vecteurs, dernier chiffre entre : la phrase du README qui la
    # publie (« 11 000 radicaux ») engage la ressource livree, donc elle se surveille comme les
    # autres. Le mot « radicaux » et non « mots » : la table est indexee par RADICAL, et un motif
    # plus large attraperait n'importe quel compte de mots du document.
        Chiffre(
        nom="entreprise",
        motif=r"entreprise de (\d+) agents",
        description="les postes de l'entreprise de verification (jio/entreprise.py)",
    ),
Chiffre(
        nom="vecteurs",
        motif=r"(\d+) radicaux",
        description="la table de vecteurs embarquee (jio/skills/vecteurs/)",
    ),
    Chiffre(
        nom="premier_choix",
        motif=r"[Pp]remier choix juste dans (\d+) %",
        description="la part d'objectifs du banc dont la premiere competence chargee est la bonne",
    ),
)


@dataclass
class Ecart:
    """Une affirmation du document qui ne correspond plus a la realite.

    Deux natures, et les confondre rendait la reparation impossible :

      * `ligne > 0` — une affirmation FAUSSE, localisee, donc **reparable** ;
      * `ligne == 0` — le chiffre n'apparait plus sous la forme surveillee. C'est un
        **signalement**, pas une faute : la reparation ne peut pas inventer la phrase ou
        ce chiffre devrait vivre. Exiger zero ecart de ce genre apres une correction
        revenait a refuser toutes les corrections.
    """

    nom: str
    ligne: int
    ancien: str
    nouveau: str
    contexte: str

    @property
    def reparable(self) -> bool:
        return self.ligne > 0

    def __str__(self) -> str:  # pragma: no cover - confort d'affichage
        return f"ligne {self.ligne} : {self.ancien} -> {self.nouveau}  ({self.contexte})"


def mesurer(racine: Path | str) -> dict[str, int]:
    """Les valeurs REELLES. Chaque mesure est faite, jamais supposee.

    Le comptage des tests lance un `pytest --collect-only` dans un sous-processus : aucun
    test n'y est execute, donc pas de recursion, et le nombre est celui de pytest lui-meme
    plutot qu'une estimation de ce module.
    """
    racine = Path(racine)
    # `objectifs` : import LOCAL, comme partout ailleurs dans ce depot. Le banc d'objectifs
    # importe la porte de clarification, qui importe ce qu'elle veut de verifier : un import
    # en tete de module ferait dependre le comptage des chiffres de toute la chaine.
    from .bench.objectifs import CORPUS
    # `skills` : import LOCAL pour la meme raison. Le routeur lit les definitions des
    # competences et rien d'autre ; le faire remonter en tete de module coupleraient les
    # chiffres a l'index, qui depend lui-meme des artefacts.
    from .skills.banc import BANC, mesurer as mesurer_le_routage
    from .skills.controle import JEUX
    from .bench.controle_clarify import CAS as CAS_CLARIFY
    from .skills.controle import CAS

    return {
        "tests": _compter_tests(racine),
        "competences": len(SKILLS),
        "agents": len(AGENTS),
        "objectifs": len(CORPUS),
        "objectifs_routage": len(BANC),
        "premier_choix": round(mesurer_le_routage().precision1 * 100),
        "objectifs_controle": len(CAS),
        # Les quatre jeux REUNIS : un seul chiffre a surveiller pour une phrase qui parle des
        # quatre. Les tailles jeu par jeu ne sont pas surveillees separement — le README les
        # publie, mais une phrase par jeu ferait huit motifs de plus pour un gain nul.
        "cas_controle": sum(len(jeu.cas) for jeu in JEUX),
        "objectifs_controle_clarify": len(CAS_CLARIFY),
        "vecteurs": _taille_table_vecteurs(),
        # Les postes de l'entreprise : une constante du code, mais mesuree — un roster
        # qui rapetit sans que le README bouge doit etre un ecart, pas un silence.
        "entreprise": _compter_postes(),
    }


def _compter_postes() -> int:
    """Les postes de l'entreprise de verification (jio/entreprise.py)."""
    from .entreprise import POSTES

    return len(POSTES)


def _taille_table_vecteurs() -> int:
    """Le nombre de radicaux de la table livree, ou 0 si elle est absente.

    Zero et non une exception : `jio chiffres` doit pouvoir DIRE qu'il n'y a plus de table
    (et le README sera alors signale en ecart) plutot que de tomber.
    """
    from .skills.vecteurs import table_du_depot

    table = table_du_depot()
    return len(table.mots) if table else 0


def _compter_tests(racine: Path) -> int:
    """Deux formes de sortie, et il faut les deux.

    `pytest -q --collect-only` affiche un TOTAL (« N tests collected ») sur certaines
    versions, et un compte PAR FICHIER (`tests/test_x.py: 8`) sur d'autres. Le premier jet
    ne lisait que la premiere forme et echouait ici — un test qui ne sait pas lire sa
    propre mesure n'en est pas une.
    """
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=racine, capture_output=True, text=True, timeout=600,
    )
    texte = resultat.stdout

    for ligne in reversed(texte.splitlines()):
        correspondance = re.search(r"(\d+) tests? collected", ligne)
        if correspondance:
            return int(correspondance.group(1))

    par_fichier = re.findall(r"^\S+\.py: (\d+)$", texte, re.MULTILINE)
    if par_fichier:
        return sum(int(x) for x in par_fichier)

    raise RuntimeError(
        "impossible de lire le nombre de tests : ni un total, ni un compte par fichier "
        f"dans la sortie de pytest.\n{texte[-500:]}"
    )


def ecarts(texte: str, mesures: dict[str, int]) -> list[Ecart]:
    """Toutes les affirmations perimees du document, avec leur ligne.

    Un motif qui n'apparait NULLE PART est un ecart a part entiere : soit le document a
    oublie de dire le chiffre, soit il l'ecrit autrement et le controle ne le regarde plus.
    Les deux cas meritent un avertissement — sinon un controle peut devenir vert parce
    qu'il ne trouve plus rien a verifier.
    """
    trouves: list[Ecart] = []
    hors_controle, _ = zones_hors_controle(texte)
    lignes = texte.splitlines()
    for chiffre in CHIFFRES:
        if chiffre.nom not in mesures:
            # Un appelant a le droit de ne mesurer QU'UNE PARTIE des grandeurs : c'est ce que
            # font les tests de la reparation, qui travaillent sur un document de trois lignes.
            # Exiger la mesure complete levait un KeyError sur un appel parfaitement legitime.
            #
            # Mais ce saut doit rester MESURE, sinon il devient le silence qu'un controle
            # existe pour empecher. La couverture de `mesurer()` est donc verrouillee par
            # `test_mesurer_couvre_TOUS_les_chiffres_surveilles` : un chiffre surveille qui
            # n'est pas mesure pour de vrai fait echouer la suite.
            continue
        motif = re.compile(chiffre.motif)
        contexte = re.compile(chiffre.contexte) if chiffre.contexte else None
        vu_quelque_part = False
        for indice, ligne in enumerate(lignes, start=1):
            if indice in hors_controle:
                continue
            if contexte and not contexte.search(ligne):
                continue
            for correspondance in motif.finditer(ligne):
                vu_quelque_part = True
                valeur = int(correspondance.group(1))
                attendue = mesures[chiffre.nom]
                if valeur != attendue:
                    trouves.append(Ecart(
                        nom=chiffre.nom,
                        ligne=indice,
                        ancien=correspondance.group(0),
                        nouveau=correspondance.group(0).replace(
                            correspondance.group(1), str(attendue), 1
                        ),
                        contexte=chiffre.description,
                    ))
        if not vu_quelque_part:
            trouves.append(Ecart(
                nom=chiffre.nom,
                ligne=0,
                ancien="(aucune mention)",
                nouveau=f"les {mesures[chiffre.nom]} {chiffre.nom}"
                if chiffre.nom != "tests" else f"{mesures[chiffre.nom]} tests verts",
                contexte=(
                    f"{chiffre.description} : ce chiffre n'apparait plus sous la forme "
                    "surveillee. Le remettre (ou retirer ce controle) — un controle qui ne "
                    "trouve plus rien a verifier devient vert sans rien prouver."
                ),
            ))
    return trouves


def reparer(
    chemin: Path | str, mesures: dict[str, int], *, ecrire: bool = False
) -> tuple[int, list[Ecart], str]:
    """Ecrit les valeurs mesurees a la place des valeurs perimees.

    Rend `(code, ecarts_restants, message)`. Sans `ecrire`, c'est une simulation : le
    fichier n'est pas touche, seul le plan est calcule.

    La securite tient en trois points :
      1. **sauvegarde** `<fichier>.avant-jio` avant toute ecriture (meme convention que le
         garde d'ecriture des artefacts) ;
      2. **aucune ecriture partielle** : si le nombre de remplacements ne correspond pas au
         nombre d'ecarts annonces, on renonce et on le dit — on n'ecrit pas « a peu pres » ;
      3. **relecture** : le controle est relance sur le texte produit ; s'il reste un ecart,
         le fichier d'origine est restaure et la commande echoue.
    """
    chemin = Path(chemin)
    if not chemin.is_file():
        return 1, [], f"fichier introuvable : {chemin}"

    original = chemin.read_text(encoding="utf-8")
    trouves = ecarts(original, mesures)
    reparables = [ecart for ecart in trouves if ecart.reparable]

    # LA QUESTION SE POSE AVANT LE VERDICT : ce document PARTICIPE-t-il au controle ? S'il
    # n'annonce aucun chiffre surveille, tout ce que `ecarts` rend pour lui est une ABSENCE —
    # et une absence n'est un defaut que pour un document qui s'est engage a annoncer. Mesure
    # faite sur un projet ETRANGER apres `jio start` : `jio chiffres` y sortait en 1 et
    # reprochait au README du projet les huit chiffres de jio, alors que `jio coherence`,
    # corrige pour la meme raison, disait « hors de portee ». Deux commandes qui mesurent la
    # meme chose ne peuvent pas rendre deux verdicts opposes — celle qu'on mettrait dans un
    # pre-commit serait celle qui crie a tort.
    if trouves and not reparables and not any(chiffre.annonce(original) for chiffre in CHIFFRES):
        return 0, trouves, (
            f"hors de portee : {chemin.name} n'annonce aucun chiffre surveille — rien a "
            "confronter. Les grandeurs mesurees sont affichees ci-dessus ; pour que le controle "
            "s'applique, ecrivez-en une sous la forme surveillee."
        )
    if not reparables:
        if not trouves:
            return 0, [], f"aucun ecart : {chemin.name} dit vrai."
        return 1, trouves, (
            f"rien a corriger dans {chemin.name} : les valeurs annoncees sont justes, mais "
            f"{len(trouves)} chiffre(s) n'apparaisse(nt) plus sous la forme surveillee — "
            "a ecrire, ou a retirer du controle. Un controle qui ne trouve plus rien a "
            "verifier devient vert sans rien prouver."
        )

    if not ecrire:
        return 1, trouves, (
            f"{len(trouves)} ecart(s) dans {chemin.name} — relancez avec `--appliquer` "
            "pour ecrire les valeurs mesurees."
        )

    lignes = original.splitlines(keepends=True)
    hors_controle, raisons = zones_hors_controle(original)
    remplacements = 0
    # Chaque reecriture est NOMMEE dans le rapport (ligne, avant -> apres). Un compte global ne
    # permet pas de distinguer une correction juste d'un chiffre juste transforme en faux : ce
    # defaut est arrive, et il n'a ete vu qu'en relisant le texte a la main.
    corrections: list[str] = []
    for chiffre in CHIFFRES:
        if chiffre.nom not in mesures:
            # Meme regle que dans `ecarts` : ce qu'on ne mesure pas, on ne le reecrit pas.
            # Les deux fonctions SAUTENT la meme chose, sinon la reparation ecrirait la ou le
            # controle ne regarde pas — exactement le trou que le test suivant interdit.
            continue
        motif = re.compile(chiffre.motif)
        contexte = re.compile(chiffre.contexte) if chiffre.contexte else None
        attendue = mesures[chiffre.nom]
        for indice, ligne in enumerate(lignes):
            if (indice + 1) in hors_controle:
                continue
            if contexte and not contexte.search(ligne):
                continue
            if not motif.search(ligne):
                continue

            def _corriger(correspondance: re.Match[str], attendue: int = attendue) -> str:
                # Ne toucher QUE ce qui est faux. La premiere version remplacait aussi les
                # mentions deja justes (« les 11 competences » -> « les 11 competences ») :
                # le compte ne tombait plus juste, et une reparation qui reecrit du texte
                # deja vrai finit par abimer des phrases qu'elle n'a pas mesurees.
                if correspondance.group(1) == str(attendue):
                    return correspondance.group(0)
                return correspondance.group(0).replace(
                    correspondance.group(1), str(attendue), 1
                )

            nouvelle, _ = motif.subn(_corriger, ligne)
            if nouvelle != ligne:
                avant = [m.group(0) for m in motif.finditer(ligne)]
                apres = [m.group(0) for m in motif.finditer(nouvelle)]
                for a, b in zip(avant, apres):
                    if a != b:
                        remplacements += 1
                        corrections.append(f"ligne {indice + 1} : {a} -> {b}")
                lignes[indice] = nouvelle

    attendus = sum(1 for ecart in trouves if ecart.reparable)
    if remplacements != attendus:
        return 1, trouves, (
            f"renonce a ecrire : {remplacements} remplacement(s) calcule(s) pour "
            f"{attendus} ecart(s) localise(s). Une reparation qui ne comprend pas ce "
            "qu'elle corrige doit s'arreter."
        )

    produit = "".join(lignes)
    restants = [ecart for ecart in ecarts(produit, mesures) if ecart.reparable]
    if restants:
        return 1, restants, (
            "renonce a ecrire : le texte corrige porte encore "
            f"{len(restants)} ecart(s). Le fichier n'a pas ete modifie."
        )
    # Les signalements survivent a la correction : ils ne se reparent pas, ils se lisent.
    signalements = [ecart for ecart in ecarts(produit, mesures) if not ecart.reparable]

    sauvegarde = chemin.with_name(chemin.name + ".avant-jio")
    sauvegarde.write_text(original, encoding="utf-8")
    chemin.write_text(produit, encoding="utf-8")

    # Relecture depuis le DISQUE : ce qui compte est ce qui est ecrit, pas ce qu'on croit
    # avoir ecrit.
    relu = chemin.read_text(encoding="utf-8")
    if [ecart for ecart in ecarts(relu, mesures) if ecart.reparable]:
        chemin.write_text(original, encoding="utf-8")
        return 1, [], (
            "la relecture du fichier ecrit contredit la correction : restaure a l'identique."
        )

    message = (
        f"{remplacements} chiffre(s) corrige(s) dans {chemin.name} · "
        f"sauvegarde : {sauvegarde.name}"
    )
    if corrections:
        montres = corrections[:8]
        message += "\n    " + "\n    ".join(montres)
        if len(corrections) > len(montres):
            message += f"\n    ... et {len(corrections) - len(montres)} autre(s)"
    if raisons:
        message += f" · {len(raisons)} zone(s) hors controle, declaree(s) : " + " | ".join(raisons)
    if signalements:
        message += (
            f" · {len(signalements)} chiffre(s) reste(nt) sans mention surveillee "
            "(a ecrire, ou a retirer du controle) — le fichier a bien ete ECRIT, c'est le "
            "document qui reste incomplet"
        )
    # LE CODE DE SORTIE DIT CE QUE VAUT LE DOCUMENT, PAS CE QUE LA REPARATION A FAIT.
    # Mesure a l'origine : un chiffre surveille qui n'apparait PLUS nulle part faisait sortir
    # `jio chiffres` en 0 — « tout va bien » — alors que `jio coherence` traite exactement le
    # meme constat comme une incoherence et sort en 1. Deux commandes qui mesurent la meme
    # chose ne peuvent pas rendre deux verdicts opposes : celle qu'on met dans un pre-commit
    # serait celle qui se tait.
    return (1 if signalements else 0), signalements, message
