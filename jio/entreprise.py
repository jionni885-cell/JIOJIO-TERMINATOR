"""L'entreprise : des postes d'agents specialises, des missions reelles, du parallele.

POURQUOI CE MODULE EXISTE
-------------------------
Le constat qui l'a demande : les verifications du depot etaient completes mais
SEQUENTIELLES — la suite entiere (~5 min), puis `jio coherence`, puis `jio chiffres`,
puis `jio claims`, puis les regimes d'ablation. Chaque cycle passait plus de temps a
ATTENDRE qu'a LIRE. Or ces verifications sont independantes les unes des autres : ce sont
des missions, et des missions independantes se distribuent.

Ce que « entreprise » veut dire ICI, sans embellissement :

  * **52 postes d'agents**, chacun avec une specialite et un mandat ecrit — c'est le
    ROSTER, la structure de l'entreprise. Un poste est un titre de competence, pas un
    processus qui tourne en permanence ;
  * **des ouvriers reels** : les missions sont executees par des processus separees
    (`multiprocessing`, contexte `fork`), en parallele. Le nombre d'ouvriers est borne par
    la MACHINE — 2 coeurs ici, donc 4 ouvriers — et le rapport DECLARE cette borne au lieu
    de laisser croire a 52 processus ;
  * **des missions qui verifient VRAI** : chaque mission lance un controle existant
    (un fichier de tests, un controle de coherence, un chiffre, une affirmation, un regime
    d'ablation). Aucun agent n'OPINE : il EXECUTE, et le rapport porte la preuve (code de
    sortie, duree, extrait). Ou un agent ne peut pas mesurer (pas d'interpreteur, pas
    d'outil), il le dit hors de portee au lieu de rendre un faux vert ;
  * **la traçabilite** : chaque mission est portee par UN agent nomme. Un probleme n'est
    jamais « il y a un echec quelque part » — il a un responsable, une duree et un extrait.

Ce que ce module ne fait pas : inventer des avis de modele. La ou une OPINION est
necessaire, le depot a deja ses panels deterministes (`jio audit`), declares comme tels.
L'entreprise, elle, ne fabrique que du constat execute.
"""

from __future__ import annotations

import multiprocessing
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "POSTES", "Mission", "RapportMission", "RapportEntreprise",
    "cataloguer", "affecter", "executer_mission", "mener", "formater",
]


# --------------------------------------------------------------------------- #
# Le roster : 52 postes, une specialite et un mandat chacun
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Poste:
    """Un poste dans l'entreprise : un nom, une specialite, un mandat ecrit."""

    nom: str
    specialite: str
    mandat: str


def _roster() -> tuple[Poste, ...]:
    """Les 52 postes. Ecrits a la main : un roster genere serait un roster que personne
    n'a lu, et un mandat que personne n'a lu n'est pas un mandat."""
    postes: list[Poste] = []
    tests = (
        ("anti-erreur", "la suite qui verrouille le noyau fail-closed"),
        ("moteur", "la boucle, ses tours, ses abstentions"),
        ("preuve", "prover, temoins, spec, sandboxes"),
        ("panel", "red-team, consensus, votes, personas"),
        ("routeur", "selection de competences, classement, vecteurs"),
        ("artefacts", "emission, installation, desinstallation propre"),
        ("clarify", "la porte de questions essentielles"),
        ("banc", "les bancs : taches, objectifs, apparie"),
        ("cli", "codes de sortie, parser, fumee, couleurs"),
        ("memoire", "memoire des echecs, bibliotheque, apprentissage"),
        ("integrite", "journal, replay, exploits, oscillation"),
        ("integrations", "depots tiers, hooks, MCP, providers reels"),
    )
    for nom, mandat in tests:
        for i in range(1, 5):  # 12 specialites x 4 = 48 postes de test
            postes.append(Poste(nom=f"test-{nom}-{i}", specialite="tests",
                                mandat=f"execute un fichier de la suite ({mandat})"))
    postes += [
        Poste("audit-artefacts", "coherence", "controle : les artefacts font ce qu'ils disent"),
        Poste("audit-nombres", "coherence", "controle : chaque chiffre publie est mesure"),
        Poste("audit-documents", "coherence", "controle : les documents ne citent pas dans le vide"),
        Poste("audit-commandes", "coherence", "controle : les commandes citees existent"),
        Poste("audit-competences", "coherence", "controle : les competences tiennent leur budget"),
        Poste("audit-environnement", "coherence", "controle : les variables lues sont documentees"),
        Poste("audit-sources", "coherence", "controle : pas de lint ni d'import mort dans jio/"),
        Poste("audit-journal", "coherence", "controle : le journal de bord tient ses promesses"),
        Poste("audit-plan", "coherence", "controle : aucun plan autonome oublie en cours"),
        Poste("mesurier", "mesure", "les chiffres officiels, mesures jamais supposes"),
        Poste("mesurier-adjoint", "mesure", "relecture des ecarts chiffres <-> documents"),
        Poste("verificateur-affirmations", "affirmations", "jio claims sur le README"),
        Poste("verificateur-preuves", "affirmations", "jio claims sur les preuves archivees"),
        Poste("linteur", "lint", "ruff F sur le paquet : pas d'import mort, pas de variable morte"),
        Poste("logueur-ablation", "ablation", "l'instrument d'activite parle sur le regime par defaut"),
        Poste("logueur-regimes", "ablation", "l'instrument parle aussi sans oracle"),
        Poste("logueur-partielle", "ablation", "le differentiel s'exerce sur la tache a spec partielle"),
        Poste("simmistre", "fumee", "la CLI s'instancie : --help, sous-commandes, liste des leviers"),
    ]
    return tuple(postes)


POSTES: tuple[Poste, ...] = _roster()

assert len(POSTES) >= 52, f"le roster a perdu des postes : {len(POSTES)} < 52"
assert len({p.nom for p in POSTES}) == len(POSTES), "deux postes portent le meme nom"


# --------------------------------------------------------------------------- #
# Les missions : ce que l'entreprise sait verifier, tire du depot lui-meme
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mission:
    """Une unite de verification : independante, executable, a resultat binaire.

    `type` choisit l'executeur : `pytest` (un fichier de la suite), `controle` (un des
    neuf controles de coherence, par nom de fonction), `commande` (une sous-commande jio
    dont le code de sortie fait foi), `ruff`, `ablation` (l'instrument d'activite doit
    parler). `payload` est l'argument de l'executeur.
    """

    id: str
    type: str
    payload: str
    specialite: str
    resume: str


def cataloguer(racine: Path | str = ".") -> list[Mission]:
    """Tire le catalogue du depot LUI-MEME : les fichiers de tests qui existent, les
    controles qui existent, les documents qui existent. Un fichier ajoute entre dans
    l'entreprise sans toucher ce module ; un fichier supprime n'y laisse pas de mission
    fantome."""
    racine = Path(racine)
    missions: list[Mission] = []

    dossiers_tests = racine / "tests"
    if dossiers_tests.is_dir():
        for chemin in sorted(dossiers_tests.glob("test_*.py")):
            missions.append(Mission(
                id=f"tests/{chemin.name}", type="pytest", payload=chemin.name,
                specialite="tests", resume=f"la suite {chemin.name} au vert",
            ))

    from .verify.coherence import CONTROLES

    for fonction in CONTROLES:
        missions.append(Mission(
            id=f"coherence/{fonction.__name__}", type="controle", payload=fonction.__name__,
            specialite="coherence", resume=f"controle de coherence : {fonction.__name__}",
        ))

    missions.append(Mission(
        id="mesure/chiffres", type="commande", payload="chiffres",
        specialite="mesure", resume="les chiffres officiels sont mesures et dit vrais",
    ))
    if (racine / "README.md").is_file():
        missions.append(Mission(
            id="affirmations/README", type="commande",
            payload="claims README.md", specialite="affirmations",
            resume="les affirmations verifiables du README tiennent",
        ))
    preuves = sorted((racine / "evidence").glob("*.md")) if (racine / "evidence").is_dir() else []
    for chemin in preuves:
        missions.append(Mission(
            id=f"affirmations/{chemin.name}", type="commande",
            payload=f"claims evidence/{chemin.name}", specialite="affirmations",
            resume=f"les affirmations de {chemin.name} tiennent",
        ))

    missions.append(Mission(
        id="lint/jio", type="ruff", payload="jio", specialite="lint",
        resume="aucun import mort ni variable morte dans le paquet",
    ))
    missions.append(Mission(
        id="ablation/instrument", type="ablation",
        payload="--missions 2 --levers preuve,routeur,porte",
        specialite="ablation", resume="l'instrument d'activite parle (colonne + phrases)",
    ))
    missions.append(Mission(
        id="ablation/partielle", type="ablation",
        payload="--missions 2 --taches mean_partial --skill 0.7 --levers differentiel",
        specialite="ablation", resume="le differentiel s'exerce sur la spec partielle",
    ))
    missions.append(Mission(
        id="fumee/cli", type="commande", payload="--help", specialite="fumee",
        resume="la CLI s'instancie et rend son aide",
    ))
    # L'adjoint du mesurier : un controle DISTINCT du premier — tous les chiffres mesures
    # sont des entiers positifs (une table de vecteurs a zero, un compteur negatif, c'est
    # une ressource perdue que l'ecart README ne montrerait pas forcement).
    missions.append(Mission(
        id="mesure/entiers", type="entiers", payload="", specialite="mesure",
        resume="tous les chiffres mesures sont des entiers positifs",
    ))
    # Le troisieme logeur : le regime sans oracle, ou temoins doit parler.
    missions.append(Mission(
        id="ablation/sans-oracle", type="ablation",
        payload="--sans-oracle --fidelite 0.6 --missions 2 --levers temoins",
        specialite="ablation", resume="en sans-oracle, le levier temoins parle",
    ))
    return missions


# --------------------------------------------------------------------------- #
# L'affectation : qui fait quoi
# --------------------------------------------------------------------------- #


#: Les reparations MECANIQUES : mission -> commande qui la repare, sans rien inventer.
#: C'est la frontiere que le depot refuse de franchir ailleurs : reparer ce qui est
#: mecanique (un compteur perime, un artefact stale), jamais ce qui demanderait une
#: decision (un document faux, une competence dangereuse). Une mission absente de cette
#: table n'est jamais reparee — elle est remontee, et c'est a un humain de trancher.
REPARATIONS: dict[str, list[str]] = {
    # Les chiffres documents sont perimes : `--appliquer` ecrit les valeurs mesurees.
    "mesure/chiffres": ["chiffres", "--appliquer"],
    # Un artefact ne fait plus ce qu'il dit : la reparation mecanique de coherence.
    "coherence/_controle_artefacts": ["coherence", "--reparer"],
}


def affecter(missions: list[Mission]) -> dict[str, str]:
    """Distribue les missions aux postes, par specialite, a la ronde.

    Un poste peut prendre plusieurs missions (il y a plus de missions que de postes par
    specialite) ; un poste sans mission de sa specialite reste au vestiaire et le rapport
    le dit — pas de mobilisation de facade.
    """
    par_specialite: dict[str, list[str]] = {}
    for poste in POSTES:
        par_specialite.setdefault(poste.specialite, []).append(poste.nom)
    affectation: dict[str, str] = {}
    curseurs: dict[str, int] = {}
    for mission in missions:
        poste = par_specialite.get(mission.specialite)
        if not poste:  # sans poste attitre, l'ouvrier generique prend la mission
            poste = ["simmistre"]
        i = curseurs.get(mission.specialite, 0)
        affectation[mission.id] = poste[i % len(poste)]
        curseurs[mission.specialite] = i + 1
    return affectation


# --------------------------------------------------------------------------- #
# L'execution : un ouvrier, une mission, une preuve
# --------------------------------------------------------------------------- #


@dataclass
class RapportMission:
    """Le compte-rendu d'une mission : statut, agent, duree, et l'extrait qui prouve."""

    mission: str
    type: str
    agent: str
    ok: bool
    duree_s: float
    resume: str
    portee: bool = True
    details: tuple[str, ...] = field(default_factory=tuple)


def _lancer(commande: list[str], racine: Path, timeout: int = 900) -> tuple[int, str, str]:
    """Lance une commande dans le depot et rend (code, stdout, stderr) SEPARES.

    La separation n'est pas du confort : plusieurs outils du depot ecrivent leur rapport
    lisible par une machine sur stdout et leur progression sur stderr — les melanger rend
    le rapport illisible pour la machine, defaut constate des le premier tour de garde
    (les deux missions d'ablation rendaient « JSON illisible » a cause de la barre de
    progression). Aucune exception ne remonte : une commande qui explose est un constat,
    pas un plantage d'entreprise."""
    try:
        resultat = subprocess.run(
            commande, cwd=racine, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "outil introuvable"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout {timeout}s"
    return resultat.returncode, resultat.stdout or "", resultat.stderr or ""


def _extrait(*textes: str, lignes_max: int = 6) -> str:
    """Les dernieres lignes non vides de plusieurs flux — pour un constat lisible."""
    tout = "\n".join(textes)
    lignes = [l for l in tout.splitlines() if l.strip()]
    return "\n".join(lignes[-lignes_max:]) if lignes else "(aucune sortie)"


def executer_mission(mission: Mission, racine: Path | str = ".") -> RapportMission:
    """Execute une mission et rend son compte-rendu. Fonction de niveau module (donc
    picklable) : c'est elle que les ouvriers executent dans leur processus."""
    racine = Path(racine)
    debut = time.monotonic()
    ok, portee, resume, details = True, True, "", ()

    if mission.type == "pytest":
        code, sortie, erreurs = _lancer(
            [sys.executable, "-m", "pytest", f"tests/{mission.payload}", "-q",
             "-p", "no:randomly"],
            racine,
        )
        ok = code == 0
        resume = f"pytest {mission.payload} -> code {code}"
        details = (_extrait(sortie, erreurs),)
        if code == 127:
            portee, resume = False, "pytest introuvable ici"

    elif mission.type == "controle":
        from .verify.coherence import CONTROLES

        fonction = next((f for f in CONTROLES if f.__name__ == mission.payload), None)
        if fonction is None:
            ok, portee, resume = False, False, f"controle inconnu : {mission.payload}"
        else:
            constat = fonction(racine)
            ok = constat.ok or not constat.portee
            resume = f"{constat.controle} : {constat.resume}"
            details = constat.details[:4]
            portee = constat.portee

    elif mission.type == "commande":
        code, sortie, erreurs = _lancer(
            [sys.executable, "-m", "jio", *shlex.split(mission.payload)], racine,
        )
        ok = code == 0
        resume = f"jio {mission.payload} -> code {code}"
        details = (_extrait(sortie, erreurs),)

    elif mission.type == "ruff":
        code, sortie, erreurs = _lancer(
            [sys.executable, "-m", "ruff", "--isolated", "check", "--select", "F",
             mission.payload],
            racine,
        )
        if code == 127:
            ok, portee, resume = True, False, "ruff absent : hors de portee ici"
        else:
            ok = code == 0
            resume = f"ruff {mission.payload} -> code {code}"
            details = (_extrait(sortie, erreurs),)

    elif mission.type == "ablation":
        code, sortie, erreurs = _lancer(
            [sys.executable, "-m", "jio", "ablation", *shlex.split(mission.payload),
             "--json"],
            racine, timeout=1200,
        )
        if code not in (0, 1):
            ok, resume, details = False, f"jio ablation -> code {code}", (_extrait(sortie, erreurs),)
        else:
            # L'instrument doit PARLER : au moins un levier avec un verdict d'activite.
            # On lit le flux MACHINE seul (stdout) : la progression va sur stderr.
            import json as _json

            try:
                rapport = _json.loads(sortie[sortie.index("{"):])
                phrases = [
                    l for l in rapport["leviers"]
                    if l["missions_activite_differente"] > 0
                    or l["observations_avec"] != l["observations_sans"]
                ]
                ok = bool(phrases)
                resume = (
                    f"l'instrument a parle sur {len(phrases)}/{len(rapport['leviers'])} "
                    "levier(s)"
                )
            except (ValueError, KeyError):
                ok = False
                resume = "rapport JSON illisible : l'instrument est peut-etre debranche"
                details = (_extrait(sortie, erreurs)[:400],)
    elif mission.type == "entiers":
        from .chiffres import mesurer  # noqa: PLC0415

        mesures = mesurer(racine)
        nuls = {cle: valeur for cle, valeur in mesures.items() if valeur <= 0}
        ok = not nuls
        resume = (
            "tous les chiffres sont des entiers positifs"
            if ok
            else f"chiffre(s) nul(s) ou negatif(s) : {nuls}"
        )
        details = (str(mesures),)
    else:
        ok, portee, resume = False, False, f"type de mission inconnu : {mission.type}"

    return RapportMission(
        mission=mission.id, type=mission.type, agent="", ok=ok, duree_s=time.monotonic() - debut,
        resume=resume, portee=portee, details=details,
    )


def _ouvrier(tache: tuple[Mission, str, str]) -> RapportMission:
    """Le travail d'un ouvrier : executer la mission, signer le compte-rendu."""
    mission, agent, racine = tache
    rapport = executer_mission(mission, racine)
    rapport.agent = agent
    return rapport


# --------------------------------------------------------------------------- #
# La direction : distribuer, attendre, juger
# --------------------------------------------------------------------------- #


@dataclass
class RapportEntreprise:
    """Le verdict de l'entreprise : combien de missions, qui, combien de temps, quels
    problemes — et le parallele declare, mesure, jamais gonfle.

    `repares` : les problemes MECANIQUES trouves puis repares par l'agent responsable,
    et re-verifies au vert. Un probleme repare n'est pas un probleme escamote : il est
    nomme deux fois (trouve, puis repare) — sinon une entreprise qui repare tout en
    silence finirait par cacher ce qu'elle repare mal.
    """

    missions: list[RapportMission] = field(default_factory=list)
    postes_total: int = 0
    postes_mobilises: int = 0
    ouvriers: int = 0
    temps_cumule_s: float = 0.0
    temps_reel_s: float = 0.0
    repares: list[tuple[str, str]] = field(default_factory=list)  # (mission, agent)

    @property
    def problemes(self) -> list[RapportMission]:
        """Une mission hors de portee n'est pas un probleme : elle est listee a part."""
        return [m for m in self.missions if m.portee and not m.ok]

    @property
    def hors_portee(self) -> list[RapportMission]:
        return [m for m in self.missions if not m.portee]

    @property
    def code(self) -> int:
        return 0 if not self.problemes else 1

    def as_dict(self) -> dict[str, object]:
        return {
            "postes_total": self.postes_total,
            "postes_mobilises": self.postes_mobilises,
            "ouvriers": self.ouvriers,
            "temps_cumule_s": round(self.temps_cumule_s, 2),
            "temps_reel_s": round(self.temps_reel_s, 2),
            "parallele": round(
                self.temps_cumule_s / self.temps_reel_s, 2
            ) if self.temps_reel_s else 0.0,
            "problem": [m.mission for m in self.problemes],
            "repares": [list(r) for r in self.repares],
            "hors_portee": [m.mission for m in self.hors_portee],
            "missions": [
                {"mission": m.mission, "agent": m.agent, "ok": m.ok, "portee": m.portee,
                 "duree_s": round(m.duree_s, 2), "resume": m.resume}
                for m in self.missions
            ],
        }


def mener(
    racine: Path | str = ".",
    missions: list[Mission] | None = None,
    ouvriers: int | None = None,
) -> RapportEntreprise:
    """Distribue les missions aux postes et les execute EN PARALLELE.

    `ouvriers` borne le parallelisme ; par defaut, deux fois le nombre de coeurs, plafonne
    a 6 — au-dela, sur une machine a 2 coeurs, on paierait du changement de contexte sans
    gagner du temps. La borne est DECLAREE dans le rapport : 52 postes, 4 ouvriers, ce sont
    deux chiffres differents qui disent deux choses differentes.
    """
    missions = missions if missions is not None else cataloguer(racine)
    affectation = affecter(missions)
    if ouvriers is None:
        ouvriers = max(2, min(6, (os.cpu_count() or 2) * 2))
    taches = [(m, affectation[m.id], str(racine)) for m in missions]
    debut = time.monotonic()
    context = multiprocessing.get_context("fork")
    if len(taches) <= 1 or ouvriers <= 1:
        resultats = [_ouvrier(t) for t in taches]
    else:
        with context.Pool(processes=ouvriers) as pool:
            resultats = pool.map(_ouvrier, taches, chunksize=1)

    # La BOUCLE DE REPARATION, fermee et honnete : un probleme dont la reparation est
    # MECANIQUE (table REPARATIONS) est repare par l'agent responsable, puis la mission
    # est REJOUEE une fois. Repare au vert -> il quitte la liste des problemes et entre
    # dans `repares` (trouve, puis repare — jamais escamote). Toujours rouge -> il reste
    # un probleme, avec la reparation tentee pour mémoire. Ce qui n'est pas mecanique
    # n'est JAMAIS touche : une decision humaine ne se devine pas.
    repares: list[tuple[str, str]] = []
    par_id = {m.id: m for m in missions}
    for probleme in [r for r in resultats if r.portee and not r.ok]:
        commande = REPARATIONS.get(probleme.mission)
        if not commande or probleme.mission not in par_id:
            continue
        code, _, _ = _lancer([sys.executable, "-m", "jio", *commande], racine)
        seconde = executer_mission(par_id[probleme.mission], racine)
        seconde.agent = probleme.agent
        if seconde.ok:
            repares.append((probleme.mission, probleme.agent))
            resultats[resultats.index(probleme)] = seconde
        else:
            seconde.resume = f"reparation tentee ({' '.join(commande)}), toujours en echec : " + seconde.resume
            resultats[resultats.index(probleme)] = seconde

    rapport = RapportEntreprise(
        missions=resultats, postes_total=len(POSTES), ouvriers=ouvriers,
        temps_cumule_s=sum(m.duree_s for m in resultats),
        temps_reel_s=time.monotonic() - debut, repares=repares,
    )
    rapport.postes_mobilises = len({m.agent for m in resultats if m.agent})
    return rapport


def formater(rapport: RapportEntreprise, *, largeur: int = 96) -> str:
    """Le rapport d'entreprise, en francais, lisible par un humain presse."""
    lignes: list[str] = []
    ok_n = sum(1 for m in rapport.missions if m.portee and m.ok)
    hp_n = len(rapport.hors_portee)
    pb_n = len(rapport.problemes)
    parallele = (
        rapport.temps_cumule_s / rapport.temps_reel_s if rapport.temps_reel_s else 0.0
    )
    lignes.append(
        f"  ENTREPRISE JIO  ·  {rapport.postes_total} postes  ·  "
        f"{len(rapport.missions)} mission(s)  ·  {rapport.ouvriers} ouvrier(s) en parallele"
    )
    lignes.append(
        f"    temps cumule {rapport.temps_cumule_s:.0f}s  ·  temps reel "
        f"{rapport.temps_reel_s:.0f}s  ·  gain mesure x{parallele:.1f}"
    )
    lignes.append(
        f"    postes mobilises : {rapport.postes_mobilises}/{rapport.postes_total} "
        "(les autres sont la pour la montee en charge, pas pour la pose)"
    )
    lignes.append("")
    if rapport.repares:
        lignes.append(f"  REPARES ({len(rapport.repares)}) — trouves, repares mecaniquement, re-verifies :")
        for mission, agent in rapport.repares:
            lignes.append(f"    [ok] {mission}  ·  {agent}")
        lignes.append("")
    if pb_n:
        lignes.append(f"  PROBLEMES ({pb_n}) — chaque probleme a un responsable :")
        for m in rapport.problemes:
            lignes.append(f"    [KO] {m.mission}  ·  {m.agent}  ·  {m.duree_s:.1f}s")
            lignes.append(f"         {m.resume}")
            for d in m.details[:2]:
                for ligne in str(d).splitlines()[:3]:
                    lignes.append(f"         | {ligne[:largeur]}")
    else:
        lignes.append(f"  PROBLEMES : AUCUN  ·  {ok_n} mission(s) au vert, {hp_n} hors de portee")
    if hp_n:
        for m in rapport.hors_portee:
            lignes.append(f"    [--] {m.mission}  ·  {m.resume}")
    lignes.append("")
    verdict = (
        "AUCUN PROBLEME"
        if not pb_n
        else f"{pb_n} PROBLEME(S) — a reparer avant tout"
    )
    lignes.append(f"  VERDICT : {verdict}")
    return "\n".join(lignes)
