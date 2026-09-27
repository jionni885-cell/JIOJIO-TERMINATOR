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
`controler()` rend un verdict et une liste de constats, chacun avec sa preuve. Neuf controles,
tous executables, aucun avis :

  1. `artefacts`     — les artefacts generes sont-ils ceux que la doctrine produit ?
                       (comparaison a l'ecriture : une derive se voit immediatement)
  2. `nombres`       — les chiffres annonces dans les documents sont-ils ceux mesures ?
  3. `documents`     — les faits verifiables des documents (calculs, blocs, chemins) tiennent-ils ?
  4. `commandes`     — chaque `jio <commande>` cite existe-t-il dans le parseur REEL ?
  5. `competences`   — les competences ecrites EN VERTU de la doctrine, et celles ecrites HORS de
                       la doctrine (un tap externe passe par la meme aune : le contenu lu par un
                       agent est le contenu lu par un agent)
  6. `environnement` — toute variable lue par le code est-elle documentee, et inversement ?
  7. `sources`       — le paquet passe-t-il ses propres portes (lint, imports) ?
  8. `journal`       — la chaine du journal tient-elle ? Un maillon casse est la seule trace d'une
                       reecriture : il se CONSTATE, il ne se repare pas
  9. `plan`          — un plan autonome laisse-t-il des etapes NON TENTEES (travail en suspens) ?

Ces listes sont recopiees a trois endroits qui parlent A UN AGENT (la description de l'outil MCP,
la doctrine, ce docstring) : elles derivent — c'est mesure, deux fois — donc un test les compare
desormais a `CONTROLES`, qui est la source. Un texte lu par un modele qui sous-estime la porte
est pire qu'un texte absent : l'agent conclut qu'il a tout verifie.

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
    """Un controle, son verdict, et la preuve de ce verdict.

    `portee` distingue deux choses qu'un booleen confondait : un controle qui a MESURE et
    trouve le depot coherent, et un controle qui n'AVAIT RIEN A MESURER ici. Le second etait
    rendu « ok » — donc un depot tiers obtenait un faux vert silencieux sur des controles qui
    ne s'appliquaient pas a lui. Le portail affiche maintenant `[--]` avec la raison, et
    `as_dict` les liste a part : hors de portee n'est ni un succes ni un echec.
    """

    controle: str
    ok: bool
    resume: str
    details: tuple[str, ...] = ()
    portee: bool = True

    @property
    def marque(self) -> str:
        if not self.portee:
            return "--"
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

    @property
    def hors_portee(self) -> tuple[Constat, ...]:
        """Les controles qui n'avaient rien a mesurer ICI : ni succes, ni echec."""
        return tuple(c for c in self.constats if not c.portee)

    def as_dict(self) -> dict[str, object]:
        return {
            "coherent": self.ok,
            "duree_s": self.duree_s,
            "hors_portee": [c.controle for c in self.hors_portee],
            "constats": [
                {"controle": c.controle, "ok": c.ok, "resume": c.resume,
                 "details": list(c.details), "portee": c.portee}
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

    from ..artifacts.write_guard import REGISTRE, _porte_la_marque, lire_registre

    registre = lire_registre(racine) if (racine / REGISTRE).is_file() else {}
    divergents: list[str] = []
    manquants: list[str] = []
    proteges: list[str] = []
    for rel, attendu in sorted(manifest().items()):
        chemin = racine / rel
        if not chemin.is_file():
            manquants.append(rel)
            continue
        sur_disque = chemin.read_text(encoding="utf-8", errors="replace")
        if sur_disque == attendu:
            continue
        # Le fichier diverge. Mais `jio artifacts --write` le REECRIRA-t-il ? Non, si le garde
        # d'ecriture ne le reconnait pas comme sien : sans marque et hors registre, il est
        # PRESERVE, et notre version part a cote en `.jio`. Recommander une commande qui ne peut
        # pas reparer, c'est envoyer l'utilisateur dans une boucle — defaut trouve ici meme, sur
        # `.hermes/skills/README.md` : divergence signalee, puis « PRESERVE : ecrit par vous ».
        if rel not in registre and not _porte_la_marque(sur_disque):
            proteges.append(rel)
        else:
            divergents.append(rel)
    ok = not manquants and not divergents and not proteges
    if ok:
        resume = f"{len(manifest())} artefact(s) generes, tous a jour"
    else:
        resume = f"{len(manquants)} manquant(s), {len(divergents)} divergent(s)"
        if proteges:
            resume += f", {len(proteges)} non ecrasable(s) par jio"
    details = tuple(f"manquant : {m}" for m in manquants[:4])
    details += tuple(f"a regenerer : {d} (`jio artifacts --write`)" for d in divergents[:4])
    details += tuple(
        f"{p} n'est pas marque comme genere par jio : `jio artifacts --write` le PRESERVERA "
        f"(notre version ira en {p}.jio). Comparez les deux, puis supprimez-le si vous voulez "
        "que jio le gere."
        for p in proteges[:3]
    )
    return Constat("artefacts", ok, resume, details)


def _controle_nombres(racine: Path) -> Constat:
    """Les chiffres annonces dans les documents sont-ils ceux mesures MAINTENANT ?"""
    from ..chiffres import ecarts, mesurer

    if not (racine / "tests").is_dir():
        # Sans dossier de tests, il n'y a aucun chiffre a mesurer — et un controle muet rendu
        # « ok » serait un faux vert. Meme regle que les deux autres : dire hors portee.
        return Constat("nombres", True, "hors de portee : aucun dossier tests/ dans cette racine",
                       portee=False)
    try:
        mesures = mesurer(racine)
    except RuntimeError as exc:
        # Ici, des tests EXISTENT mais la mesure echoue : c'est un echec, pas une absence.
        return Constat("nombres", False, f"mesure IMPOSSIBLE alors que des tests existent : {exc}"[:150])
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

    cibles = _documents(racine)
    if not cibles:
        return Constat("documents", True, "hors de portee : aucun document a verifier ici",
                       portee=False)
    refutations: list[str] = []
    verifies = 0
    for chemin in cibles:
        rapport = verifier(chemin.read_text(encoding="utf-8", errors="replace"), racine=racine)
        verifies += len(rapport.verifications)
        for blocage in rapport.bloquantes[:3]:
            refutations.append(f"{chemin.name} : {str(blocage)[:110]}")
    ok = not refutations
    return Constat(
        "documents",
        ok,
        f"{verifies} affirmation(s) verifiee(s) sur {len(cibles)} document(s)"
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
    if vues == 0 and not inconnues and not sans_raison:
        return Constat("commandes", True,
                       "hors de portee : aucune commande `jio ...` citee par un document",
                       portee=False)
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

    # Meme regle que `sources` : ce controle decrit les variables lues par le CODE de JIO.
    # Sur un autre depot, il n'a rien a dire — et se taire serait un faux vert.
    if not (racine / "jio" / "__init__.py").is_file():
        return Constat("environnement", True,
                       "hors de portee : aucun paquet jio/ dans cette racine", portee=False)

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

    paquet = racine / "jio"
    if not (paquet / "__init__.py").is_file():
        # Absence de paquet `jio/` : le controle n'a rien a mesurer. L'annoncer est le seul
        # comportement acceptable — rendre « propre » sur zero fichier est un faux vert, et
        # c'est exactement ce qu'un depot tiers obtenait avant.
        return Constat("sources", True, "hors de portee : aucun paquet jio/ dans cette racine",
                       portee=False)

    fichiers = sorted(p for p in paquet.rglob("*.py") if "__pycache__" not in p.parts)
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


def _controle_competences(racine: Path) -> Constat:
    """Les competences et les agents : ce qu'ils DISENT, et ce qu'ils COUTENT.

    Deux questions, et une seule fonction pour les deux, parce qu'elles se repondent au meme
    endroit — le fichier que l'agent lit avant de travailler :

      * **securite** : une competence est une INSTRUCTION executee avec les droits de l'agent.
        Son contenu doit passer l'audit des motifs dangereux (`audit_skills`), mises en garde
        distinguees des interdits : un texte qui INTERDIT `curl | sh` est une protection, pas
        un risque ;
      * **budget** : au-dela d'environ 5 000 jetons, une competence ne se charge plus en une
        fois ; au-dela de 25 000, la bibliotheque ne tient plus dans la fenetre avec la mission.
        Le cout est rendu en INTERVALLE (3,2 a 4,4 caracteres par jeton) : un seuil depasse
        sans ambiguite n'est pas la meme chose qu'un seuil peut-etre depasse.

    L'audit porte sur les DEFINITIONS qui generent les fichiers, jamais sur les fichiers ecrits :
    auditer la copie laisserait passer exactement le cas qu'on veut attraper — un fichier
    modifie a la main.
    """
    from ..artifacts.audit_skills import analyser_artefacts, artefacts_analyses
    from ..artifacts.budget import SEUILS, mesurer

    dossier = racine / ".hermes" / "skills"
    if not dossier.is_dir():
        return Constat("competences", True,
                       "hors de portee : aucune competence dans cette racine", portee=False)

    fichiers = sorted(p for p in dossier.rglob("*.md") if p.name != "README.md")
    if not fichiers:
        return Constat("competences", True,
                       "hors de portee : le dossier des competences est vide", portee=False)

    mesures = [
        mesurer(str(p.relative_to(racine)), p.read_text(encoding="utf-8", errors="replace"))
        for p in fichiers
    ]
    certains = [m for m in mesures if m.depasse(SEUILS["competence_jetons"])]
    doutes = [m for m in mesures if not m.depasse(SEUILS["competence_jetons"])
              and m.peut_depasser(SEUILS["competence_jetons"])]
    total_min = sum(m.jetons_min for m in mesures)
    total_max = sum(m.jetons_max for m in mesures)
    bibliotheque_trop_grosse = total_min > SEUILS["bibliotheque_jetons"]

    # Deux sources, et il faut les DEUX :
    #   * les DEFINITIONS qui generent les fichiers (l'audit de la doctrine, pour ne pas auditer
    #     une copie modifiee a la main) ;
    #   * les FICHIERS SUR LE DISQUE — parce que c'est ce que l'agent lit vraiment. Une
    #     competence ajoutee par un « tap » externe, recopiee d'un autre projet ou ecrite par un
    #     tiers n'existe dans aucune definition, et c'est exactement le scenario documente
    #     (arXiv 2608.29381) : une competence est une instruction executee avec les droits de
    #     l'agent, donc son contenu est du contenu a auditer comme le reste.
    from ..artifacts.audit_skills import analyser_texte

    risques = analyser_artefacts()
    lus = len(artefacts_analyses())
    for chemin in fichiers:
        nom = str(chemin.relative_to(racine))
        trouve = analyser_texte(
            chemin.read_text(encoding="utf-8", errors="replace"), f"fichier:{nom}"
        )
        risques.extend(trouve)
        lus += 1
    for dossier_agents, motif in ((".opencode/agents", "*.md"), (".claude/agents", "*.md")):
        for chemin in sorted((racine / dossier_agents).glob(motif)):
            nom = str(chemin.relative_to(racine))
            risques.extend(analyser_texte(
                chemin.read_text(encoding="utf-8", errors="replace"), f"fichier:{nom}"
            ))
            lus += 1

    dangereux = [r for r in risques if not r.mise_en_garde]

    ok = not certains and not bibliotheque_trop_grosse and not dangereux
    resume = (
        f"{len(fichiers)} competence(s) auditee(s), {lus} artefact(s) lus, "
        f"~{total_min}-{total_max} jetons au total"
    )
    if not ok:
        resume = f"{len(dangereux)} motif(s) dangereux, {len(certains)} competence(s) hors budget"
    details = tuple(
        f"{r.artefact} ligne {r.ligne} : {r.nature} — {r.extrait[:70]}" for r in dangereux[:4]
    ) + tuple(
        f"{m.chemin} : {m.intervalle()} jetons (seuil {SEUILS['competence_jetons']})"
        for m in certains[:3]
    )
    if doutes:
        details += tuple(
            f"a verifier : {m.chemin} fait {m.intervalle()} jetons pour un seuil de "
            f"{SEUILS['competence_jetons']}" for m in doutes[:2]
        )
    if bibliotheque_trop_grosse:
        details += (
            f"bibliotheque au-dela de {SEUILS['bibliotheque_jetons']} jetons "
            f"({total_min} au minimum) : elle ne tient plus dans la fenetre avec la mission",
        )
    return Constat("competences", ok, resume, details)


def _controle_journal(racine: Path) -> Constat:
    """Le journal est-il INTEGRE ? (chaine de hachage verifiee, pas une simple relecture)

    Un journal est la piece a conviction de ce systeme : il dit ce qui a ete fait, avec quel
    niveau de confiance. Sa valeur tient entierement a une propriete — chaque evenement est
    chaine au precedent par un condensat. Verifier cette chaine prend quelques millisecondes et
    repond a la seule question qui compte : **quelqu'un a-t-il reecrit l'histoire ?**

    Sans journal, le controle est HORS PORTEE : un projet qui n'a jamais lance de mission n'a
    rien a prouver. C'est different d'un journal casse, qui est un echec.
    """
    import os

    chemin = Path(os.environ.get("JIO_JOURNAL", str(racine / ".jio" / "journal.jsonl")))
    if not chemin.is_absolute():
        chemin = racine / chemin
    if not chemin.is_file():
        return Constat("journal", True, "hors de portee : aucun journal dans cette racine",
                       portee=False)

    from ..core.journal import Journal

    journal = Journal.from_jsonl(chemin.read_text(encoding="utf-8"), path=chemin)
    ok, casse = journal.verify_chain()
    resume = journal.summary()
    if ok:
        return Constat(
            "journal", True,
            f"chaine INTEGRE sur {resume['events']} evenement(s) — rien n'a ete reecrit",
        )
    return Constat(
        "journal", False,
        f"chaine CASSEE a l'evenement {casse} : le journal a ete modifie apres coup",
        (f"tete annoncee : {journal.head}",),
    )


#: L'ordre est celui du rapport. `artefacts` d'abord : c'est la derive la plus frequente.
CONTROLES = (
    _controle_artefacts,
    _controle_nombres,
    _controle_documents,
    _controle_commandes,
    _controle_competences,
    _controle_environnement,
    _controle_sources,
    _controle_journal,
    _controle_plan,
)


def controler(racine: Path | str = ".") -> RapportCoherence:
    """Passe LES neuf controles et rend le verdict. Aucun controle n'est optionnel.

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


#: Ce qu'un ordinateur peut reparer SEUL, et ce qu'il ne peut pas.
#:
#: La distinction n'est pas technique, elle est de nature :
#:
#:   * MECANIQUE — la valeur correcte existe deja dans le code (`artefacts`, `nombres`). Il n'y a
#:     aucune decision a prendre : regenerer, reecrire la valeur mesuree ;
#:   * HUMAIN — reparer demanderait d'INVENTER. Un document affirme quelque chose de faux : il
#:     faut savoir ce qui etait vrai. Une competence contient un motif dangereux : il faut juger
#:     l'intention. Une commande citee n'existe pas : il faut choisir entre la creer et la retirer ;
#:   * JAMAIS — le journal. Une chaine cassee est une PREUVE de reecriture. La « reparer », c'est
#:     effacer la seule trace de ce qui s'est passe. On ne lave pas les pieces a conviction.
REPARABLES = {
    "artefacts": (
        "les artefacts sont GENERES : regenerer est mecanique, aucune decision a prendre",
        "jio artifacts --write",
    ),
    "nombres": (
        "les chiffres sont MESURES : reecrire la valeur mesuree est mecanique",
        "jio chiffres --appliquer",
    ),
}

#: Ce qu'il ne faut JAMAIS « reparer », meme quand c'est techniquement possible.
JAMAIS_REPARABLE = {
    "journal": (
        "une chaine cassee est la PREUVE qu'un journal a ete reecrit. La reparer effacerait la "
        "seule trace de ce qui s'est passe : c'est une piece a conviction, pas un fichier"
    ),
}

#: Le reste demande un HUMAIN, et le rapport dit pourquoi — un constat qu'on ne peut pas
#: reparer doit au moins dire quelle decision il attend.
DECISIONS_HUMAINES = {
    "documents": "un document affirme quelque chose de faux : il faut savoir ce qui etait vrai",
    "commandes": "une commande citee n'existe pas : il faut choisir entre la creer et la retirer",
    "competences": "une competence dangereuse est une INTENTION : elle se relit, elle ne se repare pas",
    "environnement": "une variable non documentee est un CHOIX de configuration a assumer",
    "sources": "un constat de lint ou d'import est un defaut de code a comprendre",
    "plan": "des etapes non tentees attendent une decision : reprendre, ou abandonner",
}


def reparer(
    racine: Path | str = ".", *, rapport: RapportCoherence | None = None
) -> tuple[RapportCoherence, list[str], list[str]]:
    """Répare ce qui est MECANIQUE, puis re-passe la porte. Rend `(rapport, faits, restants)`.

    Trois listes, et la troisieme est la plus importante : ce qui a ete repare, ce qui n'a pas pu
    l'etre, et POURQUOI. Une reparation qui reussit en silence laisse croire que tout etait
    mecanique ; une qui echoue en silence laisse croire que tout va bien.

    Le principe : **on ne repare que ce dont la valeur correcte est deja dans le code.** Des qu'il
    faudrait inventer — quel chiffre etait vrai dans un document, ce que voulait dire une
    competence — la decision revient a un humain, et le rapport le dit au lieu de deviner.
    """
    base = Path(racine).expanduser()
    avant = rapport if rapport is not None else controler(base)
    faits: list[str] = []
    restants: list[str] = []

    for constat in avant.incoherents:
        if constat.controle in JAMAIS_REPARABLE:
            restants.append(f"{constat.controle} : NE PAS REPARER — {JAMAIS_REPARABLE[constat.controle]}")
            continue
        if constat.controle in REPARABLES:
            raison, commande = REPARABLES[constat.controle]
            if constat.controle == "artefacts":
                from ..artifacts import manifest
                from ..artifacts.write_guard import ecrire_manifest

                decisions = ecrire_manifest(base, manifest())
                ecrits = [d for d in decisions if d.action not in {"inchange", "preserve"}]
                proteges = [d for d in decisions if d.action == "preserve"]
                faits.append(f"artefacts : {len(ecrits)} fichier(s) regenere(s) — {raison}")
                for protege in proteges:
                    restants.append(
                        f"artefacts : {protege.chemin} PRESERVE (pas marque comme genere par "
                        "jio) — comparer avec le .jio a cote, puis decider"
                    )
            elif constat.controle == "nombres":
                # On reutilise la fonction de `jio chiffres --appliquer` : une seconde
                # implementation de la meme reecriture finirait par diverger de la premiere, et
                # c'est exactement ce que ce depot s'interdit (« un seul ecrivain, une seule
                # doctrine »). Elle ecrit, relit, et restaure si un ecart subsiste.
                from ..chiffres import ecarts as ecarts_chiffres, mesurer, reparer as reparer_chiffres

                mesures = mesurer(base)
                for nom in DOCUMENTS_CHIFFRES:
                    chemin = base / nom
                    if not chemin.is_file():
                        continue
                    absents = [
                        e for e in ecarts_chiffres(
                            chemin.read_text(encoding="utf-8", errors="replace"), mesures
                        )
                        if e.ligne == 0
                    ]
                    code, restants_ici, message = reparer_chiffres(chemin, mesures, ecrire=True)
                    if code == 0 and not restants_ici:
                        faits.append(f"nombres : {nom} — {raison}")
                    else:
                        restants.append(f"nombres : {nom} — {message[:90]}")
                    # Deux cas differents, et les confondre ferait perdre le second : une valeur
                    # PERIMEE se reecrit (mecanique), un chiffre qui n'apparait NULLE PART demande
                    # de decider s'il faut l'ecrire dans le document ou retirer le controle.
                    for absent in absents:
                        restants.append(
                            f"nombres : {nom} n'annonce nulle part « {absent.nouveau} » — "
                            "l'ecrire dans le document, ou retirer ce controle"
                        )
            continue
        motif = DECISIONS_HUMAINES.get(constat.controle, "ce constat demande une decision")
        restants.append(f"{constat.controle} : {motif} — {constat.resume[:80]}")

    apres = controler(base) if faits else avant
    return apres, faits, restants


def formater(rapport: RapportCoherence, *, largeur: int = 100) -> str:
    """Le rapport : un verdict d'abord, les preuves ensuite, les details a la fin."""
    verdict = (
        "COHERENT : tout ce que ce depot affirme est encore vrai"
        if rapport.ok
        else f"INCOHERENT : {len(rapport.incoherents)} controle(s) en echec"
    )
    hors = len(rapport.hors_portee)
    lignes = [
        "  COHERENCE D'ENSEMBLE  ·  ce que ce depot affirme est-il encore vrai ?",
        f"    {len(rapport.constats)} controle(s) en {rapport.duree_s:.1f}s  ·  VERDICT : {verdict}",
    ]
    if hors:
        lignes.append(
            f"    ({hors} controle(s) HORS PORTEE ici : ils ne s'appliquent pas a cette racine, "
            "donc ils ne comptent ni comme succes ni comme echec)"
        )
    lignes.append("")
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
