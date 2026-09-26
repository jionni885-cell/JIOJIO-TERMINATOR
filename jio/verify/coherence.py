"""La coherence d'ensemble : « tout ce que ce depot affirme est-il encore vrai ? »

Le probleme, et il n'est pas theorique
--------------------------------------
Ce projet sait verifier un artefact (`jio run`), un document (`jio claims`), un chiffre
(`jio chiffres`), un fichier (`jio scan`). Il ne savait pas repondre a la seule question qui
compte avant de dire « c'est fini » : **est-ce que l'ENSEMBLE tient encore ?**

Ces incoherences-la sont arrivees, toutes les trois, pendant une seule session de travail :

  * un document annoncait `755 tests verts` alors que la suite en comptait 848 ;
  * un artefact genere citait `jio verify`, une commande qui n'existe pas — et c'est la fiche
    que l'IA lit en PREMIER ;
  * un fichier de contexte depassait 150 lignes, la limite au-dela de laquelle il est survole.

Aucune n'etait un bug du code. Toutes etaient des **mensonges par retard** : une affirmation
vraie un jour, devenue fausse, personne ne l'ayant relue. C'est exactement la classe d'erreur
que ce depot traque ailleurs, et il ne la traquait pas chez lui.

La reponse : un portail, pas un rapport
---------------------------------------
`controler()` rend un verdict et une liste de constats, chacun avec sa preuve. Sept controles,
tous executables, aucun avis :

  1. `artefacts`     — les artefacts generes sont-ils ceux que la doctrine produit ?
                       (comparaison a l'ecriture : une derive se voit immediatement)
  2. `nombres`       — les chiffres annonces dans les documents sont-ils ceux mesures ?
  3. `documents`     — les faits verifiables des documents (calculs, blocs, chemins) tiennent-ils ?
  4. `commandes`     — chaque `jio <commande>` cite existe-t-il dans le parseur REEL ?
  5. `environnement` — toute variable lue par le code est-elle documentee, et inversement ?
  6. `sources`       — le paquet passe-t-il ses propres portes (lint, imports) ?
  7. `plan`          — un plan autonome laisse-t-il des etapes NON TENTEES (travail en suspens) ?

`code` vaut 0 seulement si TOUT est coherent. C'est un portail : un appelant automatise (une IA
qui veut declarer « fini ») peut s'y fier sans lire le texte, et le texte lui dit pourquoi.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Constat", "RapportCoherence", "controler", "formater", "CONTROLES"]

#: Les documents dont on verifie les faits verifiables. Volontairement COURTE : chaque document
#: ajoute du temps de verification, et un portail lent n'est pas lance.
DOCUMENTS = ("README.md",)

#: Documents dont les chiffres sont suivis. Un chiffre non suivi est un chiffre qui derive.
DOCUMENTS_CHIFFRES = ("README.md",)


@dataclass(frozen=True)
class Constat:
    """Un controle, son verdict, et la preuve de ce verdict."""

    controle: str
    ok: bool
    resume: str
    details: tuple[str, ...] = ()

    @property
    def marque(self) -> str:
        return "ok" if self.ok else "KO"


@dataclass
class RapportCoherence:
    """Le verdict d'ensemble : coherent, ou non — et jamais « probablement »."""

    constats: list[Constat] = field(default_factory=list)
    duree_s: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.constats) and all(c.ok for c in self.constats)

    @property
    def code(self) -> int:
        return 0 if self.ok else 1

    @property
    def incoherents(self) -> tuple[Constat, ...]:
        return tuple(c for c in self.constats if not c.ok)

    def as_dict(self) -> dict[str, object]:
        return {
            "coherent": self.ok,
            "duree_s": self.duree_s,
            "constats": [
                {"controle": c.controle, "ok": c.ok, "resume": c.resume, "details": list(c.details)}
                for c in self.constats
            ],
        }


def _sous_commandes() -> set[str]:
    """Les sous-commandes du parseur REEL, jamais une liste recopiee a la main."""
    from ..cli import build_parser

    noms: set[str] = set()
    for action in build_parser()._actions:  # noqa: SLF001 - c'est le parseur qu'on interroge
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            noms = set(action.choices)
    return noms


def _documents(racine: Path) -> list[Path]:
    """Les documents a verifier : ceux qui existent, un point c'est tout."""
    trouves: list[Path] = []
    for nom in DOCUMENTS:
        chemin = racine / nom
        if chemin.is_file():
            trouves.append(chemin)
    dossier = racine / "docs"
    if dossier.is_dir():
        trouves += sorted(dossier.glob("*.md"))
    return trouves


def _controle_artefacts(racine: Path) -> Constat:
    """Les artefacts sur le disque sont-ils exactement ce que la doctrine produit ?

    On REGENERE en memoire et on compare. C'est la seule facon de voir une derive : un fichier
    a la main apres une modification de la doctrine reste coherent avec lui-meme, et faux.
    """
    from ..artifacts import manifest

    divergents: list[str] = []
    manquants: list[str] = []
    for rel, attendu in sorted(manifest().items()):
        chemin = racine / rel
        if not chemin.is_file():
            manquants.append(rel)
        elif chemin.read_text(encoding="utf-8", errors="replace") != attendu:
            divergents.append(rel)
    ok = not manquants and not divergents
    resume = (
        f"{len(manifest())} artefact(s) generes, tous a jour"
        if ok
        else f"{len(manquants)} manquant(s), {len(divergents)} divergent(s)"
    )
    details = tuple(f"manquant : {m}" for m in manquants[:4])
    details += tuple(f"a regenerer : {d} (`jio artifacts --write`)" for d in divergents[:4])
    return Constat("artefacts", ok, resume, details)


def _controle_nombres(racine: Path) -> Constat:
    """Les chiffres annonces dans les documents sont-ils ceux mesures MAINTENANT ?"""
    from ..chiffres import ecarts, mesurer

    mesures = mesurer(racine)
    tous: list[str] = []
    for nom in DOCUMENTS_CHIFFRES:
        chemin = racine / nom
        if not chemin.is_file():
            continue
        for ecart in ecarts(chemin.read_text(encoding="utf-8"), mesures):
            tous.append(f"{chemin.name} ligne {ecart.ligne} : {ecart.ancien} -> {ecart.nouveau}")
    ok = not tous
    return Constat(
        "nombres",
        ok,
        f"{len(mesures)} chiffre(s) mesure(s)"
        + ("" if ok else f", {len(tous)} ecart(s) — `jio chiffres --appliquer`"),
        tuple(tous[:6]),
    )


def _controle_documents(racine: Path) -> Constat:
    """Les faits verifiables des documents tiennent-ils ? (calculs, blocs Python, chemins)"""
    from .claims import verifier

    refutations: list[str] = []
    verifies = 0
    for chemin in _documents(racine):
        rapport = verifier(chemin.read_text(encoding="utf-8", errors="replace"), racine=racine)
        verifies += len(rapport.verifications)
        for blocage in rapport.bloquantes[:3]:
            refutations.append(f"{chemin.name} : {str(blocage)[:110]}")
    ok = not refutations
    return Constat(
        "documents",
        ok,
        f"{verifies} affirmation(s) verifiee(s) sur {len(_documents(racine))} document(s)"
        + ("" if ok else f", {len(refutations)} refutee(s)"),
        tuple(refutations[:6]),
    )


def _controle_commandes(racine: Path) -> Constat:
    """Chaque `jio <commande>` citee dans un document ou un artefact existe-t-il VRAIMENT ?"""
    connues = _sous_commandes()
    inconnues: list[str] = []
    vues = 0
    cibles = [*_documents(racine)]
    for nom in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        chemin = racine / nom
        if chemin.is_file():
            cibles.append(chemin)
    from .hors_controle import masquer, raisons_manquantes, zones

    # Un exemple de SORTIE d'outil n'affirme rien : le README cite `jio scna` parce que c'est
    # le message reel que `jio` rend sur une sous-commande inconnue (montrer l'erreur fait
    # partie du mode d'emploi). Ces cas-la sont nommes ici, et il n'y en a que trois.
    examples = ("connait pas cette commande", "jio scna", "git clone")
    exemptions: list[str] = []
    sans_raison: list[str] = []
    # Deux formes comptent, et la SECONDE est la plus importante : une commande entre
    # backticks (`jio run`) et une commande EN DEBUT DE LIGNE dans un bloc de code — c'est
    # celle-la que l'IA lit et execute. Ne regarder que les backticks laissait passer la
    # fiche d'integration entiere. Le `[a-z]` qui suit est exige : il evite d'attraper
    # « jio 0.1.0 » ou un chemin, qui ne sont pas des sous-commandes.
    motif = re.compile(r"(?:`|^[ \t]*|\$ )jio ([a-z][a-z0-9-]*)", re.MULTILINE)
    for chemin in cibles:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        for ligne in texte.splitlines():
            if any(ex in ligne for ex in examples):
                texte = texte.replace(ligne, "")
        # Les zones declarees HORS CONTROLE : elles sortent du champ, et on le DIT. Une
        # exemption silencieuse serait un trou dans la porte ; une exemption sans raison est
        # refusee, parce qu'elle serait indefendable six mois plus tard.
        for numero in raisons_manquantes(texte):
            sans_raison.append(
                f"{chemin.name} ligne {numero} : zone hors controle SANS RAISON ecrite"
            )
        for raison in zones(texte)[1]:
            exemptions.append(f"{chemin.name} : {raison}")
        texte = masquer(texte)
        for citee in sorted(set(motif.findall(texte))):
            vues += 1
            if citee not in connues:
                inconnues.append(f"{chemin.name} cite `jio {citee}` (inexistante)")
    ok = not inconnues and not sans_raison
    if ok:
        resume = f"{vues} commande(s) citee(s), toutes existantes"
    elif sans_raison:
        resume = f"{len(sans_raison)} zone(s) hors controle SANS RAISON"
        if inconnues:
            resume += f", {len(inconnues)} commande(s) inexistante(s)"
    else:
        resume = f"{len(inconnues)} commande(s) citee(s) INEXISTANTE(S)"
    if exemptions:
        resume += f" · {len(exemptions)} zone(s) declaree(s) hors controle"
    return Constat(
        "commandes",
        ok,
        resume,
        tuple(inconnues[:4])
        + tuple(sans_raison[:2])
        + tuple(f"hors controle (declare) : {e[:70]}" for e in exemptions[:3]),
    )


def _controle_environnement(racine: Path) -> Constat:
    """Toute variable lue par le code est-elle documentee dans `.env.example` ?

    Le controle existait en test (`tests/test_env_wiring.py`) et il a deja refuse un commit.
    Il est ici pour que le PORTAIL le dise aussi : une variable non documentee est un reglage
    que l'utilisateur ne peut pas trouver, et une variable documentee mais jamais lue est une
    promesse en l'air.
    """
    import tests.test_env_wiring as wiring  # noqa: PLC0415 - module de test, import paresseux

    documentees = wiring._documented()                                            # noqa: SLF001
    brutes = wiring._read_by_code()                                               # noqa: SLF001
    # On reutilise les MEMES exclusions que le test, mot pour mot. Recopier la regle a moitie
    # ferait accuser des variables legitimes : une famille (`JIO_BIN_<NOM>`) est lue par
    # prefixe, une variable etrangere ou exportee n'appartient pas a ce fichier.
    familles = {n for n in brutes if n.endswith("_")}
    lues = {
        n for n in brutes - documentees
        if not n.endswith("_")
        and not wiring._dans_une_famille(n)                                       # noqa: SLF001
        and n not in wiring._FOREIGN                                              # noqa: SLF001
        and n not in wiring._EXPORTED_BY_JIO                                       # noqa: SLF001
    }
    mortes = sorted(
        n for n in documentees - brutes
        if not any(n.startswith(prefix) for prefix in familles)
    )
    invisibles = sorted(lues)
    ok = not mortes and not invisibles
    return Constat(
        "environnement",
        ok,
        f"{len(documentees & brutes)} variable(s) lue(s) et documentee(s)"
        if ok
        else f"{len(mortes)} documentee(s) sans lecteur, {len(invisibles)} lue(s) sans document",
        tuple(f"documentee mais jamais lue : {m} (`.env.example`)" for m in mortes[:4])
        + tuple(f"lue mais non documentee : {i} (`.env.example`)" for i in invisibles[:4]),
    )


def _controle_sources(racine: Path) -> Constat:
    """Le paquet `jio/` passe-t-il ses propres portes (lint, imports, syntaxe) ?"""
    from .imports import check_project
    from .linters import analyse

    fichiers = sorted(p for p in (racine / "jio").rglob("*.py") if "__pycache__" not in p.parts)
    rapport = analyse(fichiers, root=racine)
    problemes = list(rapport.findings)
    limites: list[str] = []
    imports = list(check_project(fichiers, racine / "jio", limites=limites))
    ok = not problemes and not imports
    return Constat(
        "sources",
        ok,
        f"paquet jio/ : {len(fichiers)} fichier(s), {len(problemes)} constat(s) de lint, "
        f"{len(imports)} d'import" + (f", {len(limites)} non conclu(s)" if limites else ""),
        tuple(str(p)[:130] for p in problemes[:4])
        + tuple(str(i)[:130] for i in imports[:4])
        + tuple(f"non conclu : {n[:110]}" for n in limites[:2]),
    )


def _controle_plan(racine: Path) -> Constat:
    """Un plan autonome est-il reste EN SUSPENS (etapes non tentees, ou plan bloque) ?

    Un plan bloque dont personne ne parle est un travail a moitie fait presente comme termine.
    C'est le troisieme mensonge par retard de la liste : l'etat existe sur le disque, et
    personne ne le lit.
    """
    import json

    chemin = racine / ".jio" / "plan.json"
    if not chemin.is_file():
        return Constat("plan", True, "aucun plan autonome en cours")
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Constat("plan", False, "etat de plan ILLISIBLE (`.jio/plan.json`)")
    etat = str(donnees.get("etat", ""))
    non_tentees = [e for e in donnees.get("etapes", []) if e.get("etat") == "non_tentee"]
    if etat in {"bloque", "budget"} or non_tentees:
        return Constat(
            "plan",
            False,
            f"plan en suspens : etat {etat}, {len(non_tentees)} etape(s) NON TENTEE(S)",
            tuple(f"non tentee : {str(e.get('objectif'))[:100]}" for e in non_tentees[:4]),
        )
    return Constat(
        "plan", True,
        f"plan {etat} : {donnees.get('prouvees', 0)}/{donnees.get('total', 0)} etape(s) prouvee(s)",
    )


#: L'ordre est celui du rapport. `artefacts` d'abord : c'est la derive la plus frequente.
CONTROLES = (
    _controle_artefacts,
    _controle_nombres,
    _controle_documents,
    _controle_commandes,
    _controle_environnement,
    _controle_sources,
    _controle_plan,
)


def controler(racine: Path | str = ".") -> RapportCoherence:
    """Passe LES sept controles et rend le verdict. Aucun controle n'est optionnel.

    Un controle qui plante n'est pas « ignore » : il devient un constat en echec avec son
    exception. Un portail qui saute silencieusement l'etape qui echoue est un portail ouvert.
    """
    import time

    depart = time.monotonic()
    base = Path(racine).expanduser()
    rapport = RapportCoherence()
    for controle in CONTROLES:
        try:
            rapport.constats.append(controle(base))
        except Exception as exc:  # fail-closed : l'echec est un constat, pas un silence
            rapport.constats.append(
                Constat(controle.__name__.removeprefix("_controle_"), False,
                        f"le controle a leve : {exc}")
            )
    rapport.duree_s = time.monotonic() - depart
    return rapport


def formater(rapport: RapportCoherence, *, largeur: int = 100) -> str:
    """Le rapport : un verdict d'abord, les preuves ensuite, les details a la fin."""
    verdict = (
        "COHERENT : tout ce que ce depot affirme est encore vrai"
        if rapport.ok
        else f"INCOHERENT : {len(rapport.incoherents)} controle(s) en echec"
    )
    lignes = [
        "  COHERENCE D'ENSEMBLE  ·  ce que ce depot affirme est-il encore vrai ?",
        f"    {len(rapport.constats)} controle(s) en {rapport.duree_s:.1f}s  ·  VERDICT : {verdict}",
        "",
    ]
    for constat in rapport.constats:
        lignes.append(f"    [{constat.marque:<2}] {constat.controle:<13} {constat.resume[:72]}")
        for detail in constat.details:
            lignes.append(f"         - {detail[:90]}")
    if not rapport.ok:
        lignes += [
            "",
            "    Ce rapport ne dit pas seulement qu'il y a un probleme : il dit LEQUEL, et",
            "    chaque constat porte sa preuve. Corriger, puis relancer.",
        ]
    return "\n".join(ligne[:largeur] for ligne in lignes)
