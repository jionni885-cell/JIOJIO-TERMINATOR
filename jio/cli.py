"""Interface en ligne de commande `jio`.

Commandes :
    jio doctor            etat du systeme et des fournisseurs detectes
    jio tasks             liste le banc d'essai
    jio bench             mesure le gain du harness (S0 -> S3)
    jio run "<objectif>"  execute une mission complete
    jio audit <fichier>   audite un artefact
    jio trace <journal>   rejoue un journal et verifie sa chaine de hashes
    jio version

Sortie : synthese + preuves par defaut ; details via `jio trace`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from .core.env import bool_env, float_env, int_env, str_env
from .verify.claims import RapportProse
from typing import Sequence

from dataclasses import replace as _replace

from . import __version__
from .audit.consensus import ConsensusEngine
from .audit.integrity import IntegrityMonitor
from .bench.tasks import TASKS, TASKS_BY_ID, Task, build_bank
from .bench.temoins import TraducteurSimule
from .core.journal import Journal
from .core.types import Mission, MissionReport, MissionStatus
from .gate.conformal import ConformalGate
from .loop.engine import Engine, EngineConfig, WorkItem
from .providers.registry import detect_clis
from .providers.simulated import Persona, SimulatedProvider, make_panel
from .spec.compiler import SpecCompiler
from .verify.executable import ExecutableProver, Sandbox

BANNER = r"""
     ██╗██╗ ██████╗      ████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ████████╗ ██████╗ ██████╗
     ██║██║██╔═══██╗     ╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
     ██║██║██║   ██║        ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║   ██║   ██║   ██║██████╔╝
██   ██║██║██║   ██║        ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║   ██║   ██║   ██║██╔══██╗
╚█████╔╝██║╚██████╔╝        ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║   ██║   ╚██████╔╝██║  ██║
 ╚════╝ ╚═╝ ╚═════╝         ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
"""

ICONS = {
    MissionStatus.DELIVERED: "OK",
    MissionStatus.DELIVERED_WITH_RESERVATION: "!!",
    MissionStatus.ABSTAINED: "··",
    MissionStatus.FAILED: "XX",
}

COLORS = {
    "ok": "\033[32m",
    "warn": "\033[33m",
    "bad": "\033[31m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _c(text: str, key: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    return f"{COLORS.get(key, '')}{text}{COLORS['reset']}"


# --------------------------------------------------------------------------- #
# Construction du systeme
# --------------------------------------------------------------------------- #


def _consensus(min_panel: int) -> ConsensusEngine:
    """Agregateur de votes. Le seuil est explicite : il change ce qui est atteignable."""
    return ConsensusEngine(min_panel=int(min_panel))


def _engine_config(max_rounds: int, famille: str = "code", seed: int = 0) -> EngineConfig:
    """Reglages du moteur : les defauts viennent de l'environnement, les flags priment.

    Chaque variable ci-dessous correspond a un parametre REEL de `EngineConfig`.
    Une variable documentee sans parametre derriere est du poids mort : c'est
    pourquoi `.env.example` a ete aligne sur ce que le code lit vraiment, et
    pourquoi un test verifie cette coherence.
    """
    return EngineConfig(
        max_rounds=max_rounds,
        time_budget_s=float_env("JIO_TIME_BUDGET", 600.0),
        candidates_per_round=int_env("JIO_CANDIDATES", 3),
        mutation_gate=bool_env("JIO_MUTATION_GATE", True),
        self_check=bool_env("JIO_SELF_CHECK", True),
        differential=bool_env("JIO_DIFFERENTIAL", True),
        temoins=bool_env("JIO_WITNESS", True),
        famille=famille,
        # La graine de la mission entre dans celle de chaque generation : sans
        # elle, des graines differentes produisaient les MEMES candidats, et les
        # `runs` du banc repetaient un seul tirage (voir EngineConfig.seed).
        seed=seed,
    )


def _simulated_engine(
    task: Task | None,
    *,
    skill: float = 0.35,
    panel_size: int = 5,
    correlated: bool = False,
    seed: int = 0,
    journal_path: Path | None = None,
    max_rounds: int = 5,
    alpha: float = 0.05,
    min_panel: int = 3,
    temoins: bool = True,
    traducteur: object | None = None,
    traduire_les_regles: bool = False,
    famille: str = "code",
    banque: object | None = None,
    racine: Path | None = None,
    fournisseur: object | None = None,
    fournisseurs: object | None = None,
) -> Engine:
    """Assemble un moteur utilisant la simulation deterministe (aucune cle requise).

    `fournisseur` : la vraie source des reponses, quand l'utilisateur a demande son
    propre modele (`jio bench --provider cli:opencode`). Seuls les GENERATEURS et le
    PANEL changent : la verification reste la meme, reelle, et c'est la seule facon
    de repondre a la question posee — « mon modele, avec le harness, vaut-il mieux
    que mon modele seul ? ».
    """
    from .audit.panel import DEFAULT_PERSONAS, AuditPanel

    # `banque` : une banque de DOCUMENTS (famille prose). Le simulateur est deja
    # generique — cle de tache vers (reponse, distracteurs) — donc une mission de
    # prose se mesure avec le meme fournisseur, sans code dedie.
    bank = banque if banque is not None else build_bank()
    if famille == "prose":
        from .verify.prose_prover import ProseProver

        prover: object = ProseProver(racine=racine)
    else:
        prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    personas = list(DEFAULT_PERSONAS)[:panel_size]
    # Un ou PLUSIEURS modeles : plusieurs donnent un panel reellement decorrele, ce qui est
    # la seule facon pour le consensus de valoir quelque chose.
    reels = [getattr(f, "provider", None) for f in (fournisseurs or [])]
    reels = [r for r in reels if r is not None]
    if not reels and fournisseur is not None:
        unique = getattr(fournisseur, "provider", None)
        reels = [unique] if unique is not None else []
    reel = reels[0] if reels else None
    if reels:
        # Le panel doit garder plusieurs critiques pour rester decorrele : le meme CLI est
        # appele plusieurs fois, avec des personas differentes. Un panel d'une seule voix
        # ne serait pas un panel — et c'est la decorrelation qui fait sa valeur.
        # Le panel cycle sur les modeles fournis : `AuditPanel.llm` prend un fournisseur
        # par critique, donc deux modeles suffisent a casser l'echo.
        panel = AuditPanel.llm(list(reels) * len(personas), personas)
        fournisseurs = list(reels)
    else:
        fournisseurs = make_panel(
            [p.name for p in personas], skill, bank, correlated=correlated
        )
        panel = AuditPanel.simulated(personas, seed=seed)
    generateurs = fournisseurs or [
        SimulatedProvider(
            name=f"gen::{p.name}", model="sim-1",
            persona=Persona(name=f"gen-{p.name}", skill=skill), bank=bank,
        )
        for p in personas[:3]
    ]
    return Engine(
        generators=generateurs,
        journal=Journal(path=journal_path, racine=racine or Path.cwd()),
        panel=panel,
        prover=prover,
        gate=ConformalGate(alpha=alpha),
        monitor=IntegrityMonitor(),
        spec_compiler=SpecCompiler(
            provider=traducteur or reel or _traducteur_simule(traduire_les_regles)
        ),
        consensus=_consensus(min_panel),
        config=_replace(
            _engine_config(max_rounds, famille, seed),
            # `temoins=False` par defaut en prose : il n'y a pas de regle de code a
            # traduire en test.
            temoins=temoins and famille == "code",
        ),
    )


def _traducteur_simule(actif: bool):
    """Un traducteur de regles simule, quand la simulation doit prouver sans oracle.

    Hypothese DECLAREE : traduire une regle deja enumeree est plus facile que
    resoudre la mission, donc le modele simule le fait fidelement. C'est la borne
    HAUTE mesuree par le banc (`jio bench`, bras S4) ; les bornes basses y sont
    mesurees aussi, et le systeme y survit sans jamais livrer d'erreur non declaree.
    """
    if not actif:
        return None
    from .bench.temoins import TraducteurSimule

    return TraducteurSimule(taches=TASKS, fidelite=1.0)


def _real_engine(
    *, journal_path: Path | None = None, max_rounds: int = 5, min_panel: int = 3,
    famille: str = "code", racine: Path | None = None, fournisseur: object | None = None,
    fournisseurs: object | None = None,
) -> Engine:
    """Assemble un moteur adosse aux CLI/API reellement disponibles.

    `fournisseur` : quand l'utilisateur a NOMME son modele (`--provider cli:opencode`),
    on l'utilise lui, et pas « tout ce qui a ete detecte ». La difference compte : un
    poste peut avoir plusieurs CLI installes, et le panel mesurait alors un melange dont
    personne ne peut dire ce qu'il vaut. Nommer son modele, c'est mesurer LE SIEN.
    """
    from .audit.panel import DEFAULT_PERSONAS, AuditPanel
    from .providers.registry import from_env

    nommes = [getattr(f, "provider", None) for f in (fournisseurs or [])]
    nommes = [n for n in nommes if n is not None]
    if not nommes and fournisseur is not None:
        unique = getattr(fournisseur, "provider", None)
        if unique is not None:
            # Un seul modele nomme : on l'instancie plusieurs fois, le panel a besoin de
            # plusieurs critiques (la decorrelation dira ensuite si c'est un echo).
            instances = max(1, int(getattr(fournisseur, "instances", 1)))
            nommes = [unique] * instances
    providers = nommes or list(from_env())
    if not providers:
        raise SystemExit(
            "Aucun fournisseur detecte.\n"
            "Installe un CLI (opencode, hermes, claude, codex, gemini) ou definis\n"
            "une variable d'environnement d'API (OPENROUTER_API_KEY, OPENAI_API_KEY...).\n"
            "Sans cle, utilises : jio bench"
        )
    gens = providers[:3]
    if famille == "prose":
        from .verify.prose_prover import ProseProver

        prover: object = ProseProver(racine=racine or Path.cwd())
    else:
        prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    return Engine(
        generators=gens,
        journal=Journal(path=journal_path, racine=racine or Path.cwd()),
        panel=AuditPanel.llm(providers, list(DEFAULT_PERSONAS)),
        prover=prover,
        gate=ConformalGate(alpha=float_env("JIO_ALPHA", 0.05)),
        monitor=IntegrityMonitor(),
        spec_compiler=SpecCompiler(provider=gens[0]),
        consensus=_consensus(min_panel),
        config=_engine_config(max_rounds, famille),
    )


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #


def render_report(report: MissionReport, *, verbose: bool = False, color: bool = True) -> str:
    """Synthese + preuves, en francais. Details via `jio trace`."""
    icon = ICONS.get(report.status, "??")
    key = {
        MissionStatus.DELIVERED: "ok",
        MissionStatus.DELIVERED_WITH_RESERVATION: "warn",
    }.get(report.status, "bad")

    lines: list[str] = []
    lines.append("")
    lines.append(_c(f"  [{icon}] {report.status.value.upper()}", key, color))
    lines.append(_c(f"  objectif    {report.objective[:100]}", "dim", color))
    lines.append(
        f"  preuves     {report.passed}/{report.total_checks} regles satisfaites"
        f"  |  {report.rounds} tour(s)  |  {report.duration_s:.1f}s"
    )
    lines.append(
        f"  consensus   {len(report.votes)} vote(s)"
        f"  |  integrite {'propre' if report.integrity.clean else 'COMPROMISE'}"
        f"  |  journal {report.journal_digest[:12]}"
    )

    if report.spec and report.spec.under_specified:
        lines.append("")
        lines.append(_c("  NON SPECIFIE (declare, jamais suppose) :", "warn", color))
        for gap in report.spec.under_specified:
            lines.append(f"    - {gap}")

    if report.witnesses:
        lines.append("")
        lines.append(_c("  PREUVES", "bold", color))
        for w in report.witnesses:
            mark = _c("ok", "ok", color) if w.ok else _c("KO", "bad", color)
            lines.append(f"    [{mark}] {w.rule_id:<8} {w.command[:58]}")

    blocking = [f for f in report.findings if f.blocking]
    if blocking:
        lines.append("")
        lines.append(_c("  ALERTES BLOQUANTES", "bold", color))
        for f in blocking[:6]:
            lines.append(f"    - {f.agent}: {f.message[:110]}")

    # Un desaccord entre candidats n'est pas une alerte bloquante — il porte souvent
    # sur un comportement non specifie — mais il doit etre VISIBLE : livrer l'un des
    # deux sans le dire etait exactement le trou que cette section comble. Le constat
    # nomme l'entree et les valeurs obtenues, donc il est exploitable tel quel.
    desaccords = [f for f in report.findings if f.agent == "divergence"]
    if desaccords:
        lines.append("")
        lines.append(_c("  DESACCORDS ENTRE CANDIDATS (non bloquant, non tranche)", "warn", color))
        for f in desaccords[:3]:
            lines.append(f"    - {f.message[:150]}")
            if f.evidence:
                for extrait in f.evidence.split(" ; ")[:3]:
                    lines.append(f"        {extrait[:150]}")

    if report.blames:
        lines.append("")
        lines.append(_c("  ATTRIBUTION (premier pas fautif)", "bold", color))
        for b in report.blames[:4]:
            tag = " (tentative de reparation)" if b.is_repair_attempt else ""
            lines.append(f"    - {b.agent} @ etape {b.step}: {b.message[:90]}{tag}")

    if not report.integrity.clean:
        lines.append("")
        lines.append(_c("  EXPLOITS DETECTES", "bad", color))
        for e in report.integrity.exploits[:5]:
            lines.append(f"    - {e.kind.value} @ etape {e.step}: {e.detail[:100]}")

    if report.abstention_reason:
        lines.append("")
        # Un motif tronque est un motif inutilisable : la partie actionnable
        # (« ajouter un modele distinct, calibrer, ... ») arrivait coupee.
        lines.append(_c(f"  MOTIF : {report.abstention_reason[:600]}", "warn", color))

    if verbose and report.subject:
        lines.append("")
        lines.append(_c("  LIVRABLE", "bold", color))
        for line in report.subject.splitlines()[:60]:
            lines.append(f"    {line}")

    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Commandes
# --------------------------------------------------------------------------- #


def cmd_doctor(args: argparse.Namespace) -> int:
    print(BANNER)
    print(f"  version {__version__}  ·  python {sys.version.split()[0]}")
    print()
    print("  Fournisseurs detectes :")
    clis = detect_clis()
    if clis:
        for c in clis:
            print(f"    - {c.name}  ({c.binary})")
    else:
        print("    aucun CLI externe trouve (opencode, hermes, claude, codex, gemini, aider)")

    import os

    keys = [
        k for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                    "DEEPSEEK_API_KEY", "JIO_OPENAI_BASE")
        if os.environ.get(k)
    ]
    print(f"    cles API presentes : {', '.join(keys) if keys else 'aucune'}")
    print()
    print("  Mode disponible :")
    print("    - simulation deterministe  (aucune cle requise)  -> `jio bench`")
    if clis or keys:
        print("    - mode reel                -> `jio run \"<objectif>\"`")
    print()
    print(f"  Banc d'essai : {len(TASKS)} taches verifiables avec oracles caches")
    # Ce que la configuration coute AVANT la premiere question. Un fichier de contexte
    # trop long est survole : il occupe la fenetre sans rien apporter.
    try:
        from .artifacts.budget import SEUILS, mesurer
        from .artifacts.emit import manifest

        # On mesure ce que l'OUTIL LIT, pas la source qui le produit : la doctrine
        # inclut des commentaires de maintenance qui ne sont pas emis. Mesurer la source
        # annoncait « TROP LONG » pour des fichiers de 133 lignes (mesure faite).
        contexte = {
            chemin: texte for chemin, texte in manifest().items()
            if chemin in {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/jio.mdc",
                          ".github/copilot-instructions.md"}
        }
        mesures = sorted((mesurer(c, x) for c, x in contexte.items()),
                         key=lambda m: -m.lignes)
        if mesures:
            pire = mesures[0]
            etat = ("dans le budget" if pire.lignes <= SEUILS["contexte_lignes"]
                    else "TROP LONG ; a raccourcir")
            print(f"  Fichier de contexte le plus long : {pire.chemin} — "
                  f"{pire.lignes} ligne(s), {pire.intervalle()} jetons — {etat}")
            print(f"    (seuil {SEUILS['contexte_lignes']} lignes ; detail : "
                  "`jio artifacts --budget`)")
    except Exception:  # un diagnostic qui plante ne diagnostique rien
        pass
    print()

    # ---------------------------------------------------------------- #
    # Coherence de l'etat local.
    #
    # Incident reel, vecu par ce projet : l'environnement d'execution a restaure
    # `.git` a son etat INITIAL entre deux sessions. Le travail etait intact sur le
    # disque, mais le depot ne suivait plus rien (`git status` affichait tout le code
    # comme « non suivi », `git log` revenait au commit initial). Rien ne le
    # signalait : un `git commit` ulterieur aurait produit un historique absurde, et
    # toute la tracabilite — la promesse centrale de JIO — etait perdue.
    #
    # Un outil dont l'etat peut reculer SANS LE DIRE n'est pas un outil de confiance.
    # On le dit, avec la commande exacte pour reparer.
    # ---------------------------------------------------------------- #
    suspect = _depot_suspect()
    if suspect is not None:
        commits, non_suivis = suspect
        print("  /!\\ DEPOT SUSPECT : l'historique local a peut-etre ete reinitialise.")
        print(f"      {commits} commit(s) local(aux) pour {non_suivis} fichier(s) NON SUIVIS.")
        print("      Le travail est sur le disque, mais git ne le suit plus : un commit")
        print("      maintenant fabriquerait un historique absurde.")
        print("      Reparation SANS perte, en UNE commande :")
        print("        jio recover")
        print("      Elle restaure l'historique distant, indexe le travail retrouve, et ne")
        print("      touche a aucun fichier du disque (ni --hard, ni checkout, ni clean).")
        print("      Detail de ce qui sera fait, sans rien faire :  jio recover --dry-run")
        print()

    etat = _git_state()
    print("  Etat du depot :")
    if etat is None:
        print("    pas un depot git (ou git absent) — tracabilite NON disponible")
    else:
        branche, avance, recul, distant, distant_existe = etat
        if not distant:
            # « 0 en retard » quand on n'a AUCUN distant a comparer serait un
            # mensonge par omission : c'est exactement le silence qui a fait passer
            # inapercu le retour en arriere du depot. On dit ce qu'on ne peut pas
            # savoir — et on ne se trompe pas sur la CAUSE, ce qui etait le cas :
            # un depot avec `origin` configure mais sans reference locale affichait
            # « aucun depot origin », en envoyant l'utilisateur verifier une chose
            # qui n'etait pas en cause.
            print(f"    branche {branche}  ·  AUCUN DISTANT COMPARABLE"
                  f"  ({'distant present' if distant_existe else 'aucun distant configure'})")
            if distant_existe:
                print(f"        `origin` est configure, mais la branche {branche} n'a pas de")
                print("        reference locale : impossible de dire si ce travail est")
                print(f"        sauvegarde. Rendre la comparaison possible :  git fetch origin {branche}")
            else:
                print("        Aucun depot distant configure : ce travail n'existe QUE ici.")
                print("        Verifier avec `git remote -v` (et pousser si besoin).")
        else:
            print(f"    branche {branche}  ·  {avance} commit(s) en avance  ·  {recul} en retard")
        if distant and recul and not avance:
            print()
            print(f"    /!\\ Le depot local est EN RETARD de {recul} commit(s) sur origin.")
            print("        Reparation sure (aucun travail perdu) :  scripts/sync.sh")
        elif distant and recul and avance:
            print()
            print(f"    /!\\ Les historiques ont DIVERGE ({avance} local, {recul} distant).")
            print("        Ne rien forcer a l'aveugle : comparer, puis fusionner ou choisir.")
        elif distant and avance:
            print("        travail local non pousse (normal en session ; pousser pour le garder)")
    print()
    return 0


def _git_state() -> tuple[str, int, int, bool, bool] | None:
    """`(branche, en avance, en retard, distant_connu, distant_existe)`.

    Les deux derniers champs ne sont PAS la meme question, et les confondre a produit
    un diagnostic faux :
      * `distant_existe`  : un depot distant est configure (`origin`) ;
      * `distant_connu`   : une reference COMPARABLE existe localement.

    Constate en usage reel : un depot avec `origin` configure mais sans reference
    locale de la branche affichait « aucun depot `origin` : impossible de dire si ce
    travail est sauvegarde ailleurs ». C'est le diagnostic du silence : il envoie
    l'utilisateur verifier `git remote -v` alors que le distant est la, et que la
    seule chose qui manque est un `git fetch`.
    

    Que des lectures : on ne modifie JAMAIS le depot depuis `doctor`. Un diagnostic
    qui agit est un diagnostic qu'on n'ose plus lancer.
    """
    import subprocess

    def _distant_configure(sonde) -> bool:
        """`origin` (ou un autre distant) est-il configure ?

        Question DIFFERENTE de « peut-on comparer » : un depot peut avoir un distant
        et aucune reference locale. Les confondre a produit un diagnostic faux.
        """
        for nom in ("origin", "upstream"):
            code, _ = sonde("remote", "get-url", nom)
            if code == 0:
                return True
        return False

    def git(*argv: str) -> tuple[int, str]:
        try:
            # On interroge le depot du DOSSIER COURANT : c'est la que l'utilisateur
            # travaille. Un `jio doctor` lance depuis son projet doit parler de son
            # projet ; fixer le chemin sur l'installation de JIO repondait toujours
            # l'etat de JIO, quel que soit l'endroit d'ou on appelait.
            proc = subprocess.run(
                ["git", *argv], capture_output=True, text=True, timeout=10,
            )
        except Exception:
            return 1, ""
        return proc.returncode, proc.stdout.strip()

    code, branche = git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0 or not branche:
        return None
    # La reference de suivi peut manquer (`git fetch origin <branche>` ne cree pas
    # forcement `origin/<branche>`). On essaie l'amont configure, puis la convention.
    for candidat in ("@{upstream}", f"origin/{branche}"):
        code, ref = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", candidat)
        if code == 0 and ref:
            break
        code, ref = git("rev-parse", "--verify", "--quiet", candidat)
        if code == 0 and ref:
            ref = candidat
            break
    else:
        # Aucune reference comparable : on le DIT — en distinguant « pas de distant »
        # de « distant present, reference absente ».
        return branche, 0, 0, False, _distant_configure(git)
    code, comptes = git("rev-list", "--left-right", "--count", f"{ref}...HEAD")
    if code != 0 or not comptes:
        return branche, 0, 0, False, True
    try:
        retard, avance = (int(x) for x in comptes.split()[:2])
    except Exception:
        return branche, 0, 0, False, True
    return branche, avance, retard, True, True


def _depot_suspect() -> tuple[int, int] | None:
    """`(commit(s) locaux, fichiers non suivis)` quand le depot a l'air reinitialise.

    Incident reel, vecu DEUX fois par ce projet : l'environnement d'execution restaure
    `.git` a son etat initial entre deux sessions. Le travail est intact sur le disque,
    mais le depot ne suit plus rien : `git log` revient au commit initial et tout le code
    apparait comme « non suivi ».

    Les avertissements existants de `doctor` parlaient du DISTANT (en retard, reference
    absente) : ils supposent tous que le local suit quelque chose et qu'on peut comparer.
    Or dans cet incident, la comparaison est impossible — la reference distante vient
    d'etre effacee avec le reste. Il fallait un signal qui ne depende d'AUCUN reseau :
    un depot qui contient beaucoup de fichiers de projet et presque aucun commit est
    l'empreinte exacte de cet accident.

    On ne modifie rien, jamais : `doctor` observe, et donne la commande de reparation.
    """
    import subprocess

    def git(*argv: str) -> tuple[int, str]:
        try:
            proc = subprocess.run(["git", *argv], capture_output=True, text=True, timeout=10)
        except Exception:
            return 1, ""
        return proc.returncode, proc.stdout.strip()

    code, _ = git("rev-parse", "--is-inside-work-tree")
    if code != 0:
        return None
    code, commits = git("rev-list", "--count", "HEAD")
    if code != 0 or not commits.isdigit():
        return None
    # `--untracked-files=all` : sans lui, git regroupe un dossier non suivi en UNE ligne
    # (`?? jio/`). Un projet organise en dossiers n'afficherait que 2 ou 3 entrees, et
    # l'accident — celui pour lequel ce controle existe — passerait inapercu.
    code, statut = git("status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return None
    non_suivis = sum(1 for ligne in statut.splitlines() if ligne.startswith("??"))

    # Seuils volontairement larges : on veut rater le moins possible de vrais accidents,
    # et un depot neuf de l'utilisateur (1 commit, 3 fichiers) ne doit pas declencher.
    if int(commits) <= 3 and non_suivis >= 20:
        return int(commits), non_suivis
    return None


def cmd_recover(args: argparse.Namespace) -> int:
    """`jio recover` : restaurer l'historique d'un depot reinitialise, sans perdre un octet.

    Complete la boucle de `jio doctor` : le diagnostic DIT ce qui s'est passe, `recover`
    le REPARE. Sans elle, le seul chemin documente etait `scripts/sync.sh` — qui refuse de
    travailler quand `git status` n'est pas vide, c'est-a-dire exactement dans cet accident.
    """
    from .recover import recuperer

    print(BANNER)
    racine = Path(getattr(args, "root", ".") or ".").expanduser()
    resultat = recuperer(
        racine,
        remote=getattr(args, "remote", "origin") or "origin",
        branche=getattr(args, "branch", "") or "",
        dry_run=bool(getattr(args, "dry_run", False)),
    )

    print(f"  RECUPERATION  ·  {racine.resolve()}")
    print()
    if resultat.branche:
        print(f"    branche : {resultat.branche}")
    if resultat.distant:
        print(f"    distant : {resultat.distant[:12]}")
    for operation in resultat.operations:
        print(f"    $ {operation}")
    print()
    print(f"    {resultat.motif}")
    if resultat.fait:
        print()
        print(f"    contenu de l'arbre : {resultat.avant[:12]} (avant) == "
              f"{resultat.apres[:12]} (apres)  ->  "
              f"{'INTACT' if resultat.contenu_intact else 'MODIFIE'}")
        if resultat.etiquette:
            print(f"    etiquette posee sur l'etat precedent : {resultat.etiquette}")
        print(f"    etat local : {resultat.fichiers_modifies} modification(s), "
              f"{resultat.fichiers_non_suivis} fichier(s) non suivi(s)")
        if resultat.preuves_perimees:
            nombre = resultat.preuves_perimees
            if nombre == 1:
                phrase = ("1 preuve enregistree porte le sceau d'un AUTRE etat du monde "
                          f"(sur {resultat.preuves_total} au total).")
            else:
                phrase = (f"{nombre} preuves enregistrees portent le sceau d'un AUTRE etat "
                          f"du monde (sur {resultat.preuves_total} au total).")
            print()
            print(f"    {phrase}")
            print("    Elles restent valides pour ce qu'elles decrivent, pas pour l'etat")
            print("    actuel : `jio trace` les montre, groupees par monde.")
        print()
        print("    Aucune commande n'a touche aux fichiers du disque (ni `--hard`, ni")
        print("    `checkout`, ni `clean`). Verifiez avec `git status`, puis commitez.")
    print()
    # 0 = « plan etabli » (ou repare). 1 = rien n'a pu etre etabli : a examiner.
    # Une simulation reussie est une inspection reussie, donc 0 : sans cela, un
    # script confondrait « voici ce que je ferais » avec « j'ai echoue ».
    return 0 if (resultat.fait or resultat.simulation) else 1


def cmd_chiffres(args: argparse.Namespace) -> int:
    """`jio chiffres` : les chiffres de la documentation sont-ils encore vrais ?

    Le controle existait deja, en test. Il a mordu trois fois et trois fois la reparation
    s'est faite a la main : un controle qui punit sans reparer finit par etre contourne.
    Ici, le meme controle, avec la reparation a cote (`--appliquer`).
    """
    from .chiffres import mesurer, reparer

    print(BANNER)
    racine = Path(getattr(args, "root", ".") or ".").expanduser()
    cibles = [Path(c) for c in (getattr(args, "fichiers", None) or ["README.md"])]
    mesures = mesurer(racine)
    print("  CHIFFRES  ·  mesures reelles")
    print()
    for nom in sorted(mesures):
        print(f"    {nom:12s} : {mesures[nom]:5d}")
    print()

    code = 0
    for cible in cibles:
        chemin = cible if cible.is_absolute() else racine / cible
        resultat, trouves, message = reparer(
            chemin, mesures, ecrire=bool(getattr(args, "appliquer", False))
        )
        for ecart in trouves:
            marque = "ECART" if ecart.reparable else "SIGNAL"
            print(f"    {marque}  {chemin.name} ligne {ecart.ligne} : {ecart.ancien}"
                  f"  ->  {ecart.nouveau}")
        print(f"    {message}")
        print()
        code = max(code, resultat)
    return code


def cmd_tasks(args: argparse.Namespace) -> int:
    print()
    print("  BANC D'ESSAI")
    print()
    for t in TASKS:
        print(f"    {t.id:<16} [{t.difficulty:<7}] {len(t.rules)} regles"
              f"  |  {len(t.distractors)} distracteurs")
        print(f"      {t.objective[:96]}")
    print()
    return 0


def _bench_prose(args: argparse.Namespace) -> int:
    """Le banc de PROSE : des documents, pas des programmes.

    Meme exigence que le banc de code, et le meme chiffre qui doit rester a zero :
    les documents FAUX presentes comme prouves. La difference est dans ce qu'on
    mesure — ici, le harness ne peut pas executer le livrable, il ne peut que
    verifier ses affirmations.
    """
    from .bench.prose import PROSE_TASKS, mesurer_prose

    print(BANNER)
    print(f"  Mesure du harness sur des DOCUMENTS  ·  competence simulee {args.skill:.2f}"
          f"  ·  {args.runs} tirage(s)  ·  {len(PROSE_TASKS)} tache(s)")
    print("  Aucune cle API requise : les documents sont simules, la VERIFICATION est reelle.")
    print()
    print("    bras                                   justes       IC95   comparaison")
    print("    -------------------------------------- -------  ----------  --------------------")
    total = {"essais": 0, "silencieux": 0, "sous_reserve": 0, "abstentions": 0}
    for skill in sorted({0.0, 0.35, float(args.skill)}):
        mesure = mesurer_prose(skill=skill, runs=args.runs, max_rounds=args.rounds,
                               racine=Path.cwd())
        bas, haut = mesure.intervalle()
        resume = mesure.resume(f"competence {skill:.2f}")
        # L'IC95 est insere au bon endroit dans une ligne deja longue : on ne reformate
        # pas `resume()` (il sert au journal), on ajoute la colonne ici.
        avant, _, apres = resume.partition("%")
        print(f"{avant}%  [{bas:.0%} ; {haut:.0%}]{apres}")
        total["essais"] += mesure.essais
        total["silencieux"] += mesure.erreurs_silencieuses
        total["sous_reserve"] += mesure.sous_reserve
        total["abstentions"] += mesure.abstentions
    print()
    print(f"  {total['essais']} essai(s) au total")
    print(f"  ERREURS LIVREES SANS RIEN DIRE : {total['silencieux']}"
          "  <- le seul chiffre qui doit rester a zero")
    print(f"  livres avec une reserve NOMMEE (chemin introuvable, "
          f"confiance sous le seuil) : {total['sous_reserve']}")
    print(f"  abstentions (rien de verifiable, ou preuve impossible) : {total['abstentions']}")
    print()
    print("  LIMITES, en toute honnete :")
    print("    - un document peut etre FAUX sans qu'aucune de ses affirmations ne le soit :")
    print("      la verification porte sur ce qui est calculable, pas sur le sens.")
    print("    - competence 0.00 : tous les tirages sont des distracteurs. Le systeme")
    print("      livre alors SOUS RESERVE, ou s'abstient — jamais en presentant un faux")
    print("      calcul comme prouve.")
    print("    - les documents sont SIMULES : ce chiffre mesure l'architecture.")
    print()
    return 0 if total["silencieux"] == 0 else 1


def cmd_bench(args: argparse.Namespace) -> int:
    """Mesure le gain reel du harness sur le MEME modele, fige.

    S0  un seul appel, sans verification        (modele brut)
    S1  best-of-N, sans verification            (echantillonnage seul)
    S2  best-of-N + preuve executable + reprise (verification)
    S3  moteur complet                          (JIO)

    C'est la mesure que personne ne publie : le harness, a poids constants.
    """
    if getattr(args, "prose", False):
        return _bench_prose(args)

    from .bench.provider_spec import resoudre as resoudre_modele
    from .core.errors import ProviderError

    try:
        modele = resoudre_modele(getattr(args, "provider", "simule") or "simule")
    except ProviderError as exc:
        # On s'arrete. Mesurer un modele simulé en annoncant le modele de l'utilisateur
        # serait le pire resultat possible : un rapport credible et faux.
        print(f"  {exc}", file=sys.stderr)
        return 2

    skill = args.skill
    runs = args.runs
    seeds = list(range(runs))

    print(BANNER)
    if modele.genre == "simule":
        print(f"  Mesure du harness  ·  competence simulee {skill:.2f}  ·  {runs} tirage(s)  ·"
              f"  {len(TASKS)} taches")
        print("  Aucune cle API requise : les reponses sont simulees, la VERIFICATION est reelle.")
    else:
        print(f"  Mesure du harness  ·  modele : {modele.spec}  ·  {runs} tirage(s)  ·"
              f"  {len(TASKS)} taches")
        print(f"  {modele.note}")
    print()

    results: dict[str, list[float]] = {
        "S0": [], "S1": [], "S1b": [], "S2": [], "S3": [], "S4": [], "S4b": [], "S4c": [],
    }
    calls: dict[str, list[int]] = {k: [] for k in results}
    integrity_hits = 0
    abstentions_sans_oracle = 0
    contrefacons = 0
    rejets_faux = 0
    erreurs_silencieuses = 0
    justes: list[tuple[str, bool]] = []
    started = time.monotonic()

    # `build_bank()` ne depend d'aucune graine ni d'aucune tache : le construire une
    # fois au lieu de `len(seeds) * len(TASKS)` fois ne change aucun resultat et evite
    # de refaire le meme travail a chaque tirage du banc.
    bank = build_bank()
    # Les trois generateurs du banc etaient TOUJOURS simules, meme quand l'utilisateur
    # branche son propre modele : les bras S0/S1/S1b mesuraient alors la simulation, et
    # le rapport avait l'air de parler de son modele. Corrige ici.
    generateurs_reels = (
        [] if modele.provider is None
        else [modele.provider] * max(3, modele.instances)
    )
    for seed in seeds:
        for task in TASKS:
            generators = generateurs_reels or [
                SimulatedProvider(
                    name=f"gen{i}", model="sim-1",
                    persona=Persona(name=f"gen{i}", skill=skill), bank=bank,
                )
                for i in range(3)
            ]

            # --- S0 : un appel, aucune verification ------------------------
            c = generators[0].complete([_msg(task.objective)], seed=seed)
            code = _code(c.text, task.entrypoint)
            results["S0"].append(1.0 if _check(code, task) else 0.0)
            calls["S0"].append(1)

            # --- S1 : best-of-3, sans verification -------------------------
            cands = [
                _code(generators[i % 3].complete([_msg(task.objective)], seed=seed + i).text,
                      task.entrypoint)
                for i in range(3)
            ]
            results["S1"].append(1.0 if any(_check(x, task) for x in cands) else 0.0)
            calls["S1"].append(3)

            # --- S2/S3 : moteur complet ------------------------------------
            engine = _simulated_engine(
                task, skill=skill, seed=seed, max_rounds=args.rounds, fournisseur=modele
            )
            report = engine.run(
                Mission(objective=task.objective, id=f"{task.id}-{seed}", max_rounds=args.rounds),
                WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                         checks=task.checks, spec=task.spec()),
            )
            n_calls = int(report.usage.get("calls", 0)) or 1
            ok = _check(report.subject, task)
            results["S2"].append(1.0 if ok else 0.0)
            calls["S2"].append(n_calls)

            # --- S1b : meme budget d'appels, AUCUNE verification -----------
            # C'est le controle scientifique : le gain vient-il de la
            # verification, ou simplement d'avoir droit a plus d'essais ?
            # On tire n_calls candidats et on les evalue tous sans feedback.
            blind = [
                _code(
                    generators[i % 3].complete(
                        [_msg(task.objective)], seed=seed * 97 + i
                    ).text,
                    task.entrypoint,
                )
                for i in range(n_calls)
            ]
            results["S1b"].append(1.0 if any(_check(x, task) for x in blind) else 0.0)
            calls["S1b"].append(n_calls)

            # S3 = S2 + accepte seulement si le systeme le declare livre.
            delivered = report.status in (
                MissionStatus.DELIVERED, MissionStatus.DELIVERED_WITH_RESERVATION
            )
            results["S3"].append(1.0 if (ok and delivered) else 0.0)
            calls["S3"].append(n_calls)
            if not report.integrity.clean:
                integrity_hits += 1
            # --- S4 : AUCUN ORACLE — les regles traduites en temoins -------- #
            # C'est l'etat d'une MISSION REELLE : personne ne fournit de test. Sans
            # traduction, le moteur ne peut rien prouver et s'abstient. Avec
            # traduction, chaque regle devient une assertion executable, et le moteur
            # choisit sur preuve au lieu de parier. Meme budget que le controle :
            # 3 candidats + 1 appel de traduction, soit exactement un best-of-4.
            #
            # Trois fidelites : la borne haute (le modele lit les regles), la borne
            # basse (il les lit a l'envers), et le milieu. Le simulateur DECLARE ce
            # qu'il simule : voir jio/bench/temoins.py.
            for cle, fidelite in (
                (("S4", 1.0), ("S4c", 0.5), ("S4b", 0.0))
                if modele.genre == "simule" else ()
            ):
                traducteur = TraducteurSimule(taches=TASKS, fidelite=fidelite)
                moteur = _simulated_engine(
                    task, skill=skill, seed=seed, max_rounds=args.rounds,
                    temoins=True, traducteur=traducteur,
                )
                rapport = moteur.run(
                    Mission(objective=task.objective, id=f"{task.id}-{seed}-{cle}",
                            max_rounds=args.rounds),
                    WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                             spec=task.spec()),
                )
                contrefacons += len(traducteur.contrefaites)
                justes.append((cle, _check(rapport.subject, task)))
                candidat_juste = any(
                    e.payload.get("sim_correct") for e in moteur.journal.events()
                    if getattr(e, "kind", "") == "candidate"
                )
                if rapport.status is MissionStatus.ABSTAINED:
                    abstentions_sans_oracle += 1
                elif not justes[-1][1] and candidat_juste:
                    # Une implementation CORRECTE etait disponible et le moteur a
                    # livre autre chose : c'est le cout reel d'un traducteur
                    # imparfait, et le seul nombre qui puisse condamner l'axe.
                    rejets_faux += 1
                if not justes[-1][1] and rapport.status is MissionStatus.DELIVERED:
                    # Le pire des cas, celui qui doit rester a ZERO : une erreur
                    # livree SANS reserve, c'est-a-dire sans que rien ne le dise.
                    erreurs_silencieuses += 1
                results[cle].append(1.0 if justes[-1][1] else 0.0)
                calls[cle].append(int(rapport.usage.get("calls", 0)) or 1)

            if os.environ.get("JIO_DEBUG_BENCH") and ok and not delivered:
                print(
                    f"    [debug] {task.id} seed={seed} statut={report.status.value} "
                    f"ok={ok} preuves={report.passed}/{report.total_checks} "
                    f"exploits={[e.kind.value for e in report.integrity.exploits]} "
                    f"motif={report.abstention_reason[:120]}"
                )

    elapsed = time.monotonic() - started
    print("  RESULTATS")
    print()
    labels = {
        "S0": "modele brut (1 appel)",
        "S1": "echantillonnage seul (best-of-3)",
        "S1b": "CONTROLE : autant d'appels, 0 verification",
        "S2": "verification executable + reprise",
        "S3": "JIO complet (livraison auditee)",
        "S4": "AUCUN ORACLE : regles traduites en temoins",
        "S4c": "AUCUN ORACLE : traducteur a 50 % de fidelite",
        "S4b": "AUCUN ORACLE : traducteur FAUX (lue a l'envers)",
    }
    base = _mean(results["S0"])
    print(f"    {'config':<40} {'reussite':>9} {'IC95':>15} {'appels':>7} {'vs S0':>7}")
    print(f"    {'-' * 40} {'-' * 9} {'-' * 15} {'-' * 7} {'-' * 7}")
    for key in ("S0", "S1", "S1b", "S2", "S3", "S4", "S4c", "S4b"):
        if not results[key]:
            # Un bras sans donnee s'afficherait « 0,0 % [0 % ; 0 %] » : un chiffre
            # invente. On l'annonce, et on continue.
            print(f"    {labels[key]:<40} {'non mesure':>9}")
            continue
        rate = _mean(results[key])
        budget = _mean(calls[key])
        bas, haut = _wilson(results[key])
        # Un rapport de ratio sur une base NULLE n'a pas de sens : « 1000000000.00x »
        # etait affiche quand le modele brut ne reussissait rien. On ecrit `n/a`, qui est
        # la verite, au lieu d'un nombre a douze chiffres qui n'en est pas une.
        ratio = f"{rate / base:>5.2f}x" if base > 1e-9 else "   n/a"
        print(f"    {labels[key]:<40} {rate:>8.1%} "
              f"{f'[{bas:.0%} ; {haut:.0%}]':>15} {budget:>7.1f} {ratio}")
    print()
    print("    Lire l'IC95 avant de conclure : un ecart dont l'intervalle contient zero")
    print("    est INDETERMINE a ce nombre d'essais, pas demontre. `--runs` elargit n.")
    print()
    print()

    # --- la seule comparaison qui compte : a budget d'appels EGAL ---------- #
    s1b, s2 = _mean(results["S1b"]), _mean(results["S2"])
    delta, (bas_d, haut_d), tranche = _ecart(results["S1b"], results["S2"])
    print("  ISOLATION DE L'EFFET")
    print("    echantillonnage seul vs verification, MEME nombre d'appels du modele :")
    print(f"      sans verification {s1b:>7.1%}   avec verification {s2:>7.1%}   "
          f"ecart {delta:+.1f} points  IC95 [{bas_d:+.1f} ; {haut_d:+.1f}]")
    if tranche and delta > 0:
        print("      -> l'intervalle EXCLUT zero : le gain vient de la VERIFICATION, pas")
        print("         du nombre d'essais.")
    elif delta > 0:
        print("      -> ecart POSITIF mais l'intervalle CONTIENT zero : INDETERMINE a ce")
        print("         nombre d'essais. Augmenter --runs avant de conclure quoi que ce soit.")
        # Un constat « indéterminé » sans budget de mesure laisse l'utilisateur sans
        # prise. On calcule le nombre d'essais qu'il faudrait POUR CETTE TAILLE D'EFFET :
        # c'est la difference entre « je ne sais pas » et « voici ce qu'il faudrait ».
        from .bench.incertitude import essais_necessaires

        besoin = essais_necessaires(s1b, s2)
        taches = max(1, len(results["S0"]) // max(1, args.runs))
        if besoin > 0:
            print(f"         Pour demontrer un ecart de {delta:+.1f} points : environ "
                  f"{besoin} essai(s) par bras,")
            print(f"         soit `--runs {math.ceil(besoin / taches)}` sur ce jeu de "
                  f"{taches} tache(s).")
    else:
        print("      -> sur ce jeu de taches, l'echantillonnage suffisait : resultat honnete.")
    print()
    gain, (bas_g, haut_g), tranche_g = _ecart(results["S0"], results["S3"])
    print(f"    gain total du harness : {gain:+.1f} points  IC95 [{bas_g:+.1f} ; {haut_g:+.1f}]"
          "  (cible mesuree dans la litterature : +15 a +54)")
    print(f"    {'significatif' if tranche_g else 'INDETERMINE a cet echantillon'}"
          f" — {len(results['S0'])} essai(s) par bras.")
    print()
    if modele.genre != "simule":
        print("  LES BRAS SANS ORACLE NE SONT PAS MESURES AVEC UN VRAI MODELE")
        print("    S4/S4b/S4c reposent sur un TRADUCTEUR simule (fidelite fixee a 100, 50")
        print("    ou 0 %) : avec votre modele, ce serait votre modele qui traduirait, et")
        print("    le chiffre annonce ne correspondrait plus a rien. Il n'est donc pas")
        print("    affiche. `jio bench` sans `--provider` mesure cet axe.")
        print()
        print(f"    erreurs livrees SANS reserve : {erreurs_silencieuses}"
              "  <- le seul chiffre qui doit rester a zero")
        print(f"    duree : {elapsed:.1f}s")
        print()
        return 0

    print("  QUAND LA MISSION NE FOURNIT AUCUN ORACLE — le cas de toute mission reelle")
    print("    sans oracle, le moteur ne peut RIEN prouver : il s'abstient, et il le dit.")
    print("    avec les regles traduites en temoins, une seule echelle : fidelite du traducteur")
    print(f"      fidelite 100 %  -> {_mean(results['S4']):>6.1%} de livraisons justes"
          f"   ({_mean(calls['S4']):.1f} appels, autant qu'un best-of-4)")
    print(f"      fidelite  50 %  -> {_mean(results['S4c']):>6.1%} de livraisons justes"
          f"   ({_mean(calls['S4c']):.1f} appels)")
    print(f"      fidelite   0 %  -> {_mean(results['S4b']):>6.1%} de livraisons justes"
          f"   ({contrefacons} regle(s) contrefaite(s) au total)")
    print(f"    issues des bras sans oracle : {abstentions_sans_oracle} abstention(s),"
          f" {rejets_faux} rejet(s) d'un candidat CORRECT")
    print(f"    ERREURS LIVREES SANS RESERVE : {erreurs_silencieuses}  <- le seul chiffre qui doit rester a zero")
    print("    -> la traduction est le chainon qui rend la preuve POSSIBLE hors banc, et")
    print("       elle marche quand le traducteur est juste. Quand il se trompe, le systeme")
    print("       s'abstient ou livre AVEC reserve : il ne presente jamais un artefact faux")
    print("       comme prouve. Un temoin que TOUS les candidats echouent est declare NON")
    print("       PROUVE : il ne peut ni accuser ni innocenter.")
    print(f"    exploites d'integrite detectes : {integrity_hits}")
    print(f"    duree : {elapsed:.1f}s")
    print()
    print("  LIMITES, en toute honnete :")
    print("    - les reponses sont SIMULEES : ce chiffre mesure l'architecture, pas un modele reel.")
    print("    - la litterature mesure le harness sur des modeles reels : +15 a +54 points.")
    print("    - la verification n'aide que si la tache EST verifiable. Ailleurs : abstention.")
    print("    - aucun harness ne cree de connaissance absente du modele.")
    print()
    return 0


def _attach_learning(engine, state_dir: Path, *, disable: bool = False) -> None:
    """Active la memoire des echecs et le routeur de confiance sur un moteur.

    Sans cet appel, ces deux modules existent mais ne sont JAMAIS charges par une
    mission : l'auto-amelioration annoncee ne tournait pas. Un composant qui ne
    s'execute pas n'existe pas — constate en mesurant les modules reellement
    importes pendant une mission.
    """
    if disable:
        return
    from .learn import FailureMemory
    from .spec.library import BibliothequeTemoins
    from .trust import TrustRouter

    state_dir.mkdir(parents=True, exist_ok=True)
    engine.memory = FailureMemory(
        path=Path(str_env("JIO_MEMORY", str(state_dir / "failures.jsonl")))
    )
    # Bibliotheque de temoins : une traduction DEJA VALIDEE par une livraison prouvee
    # n'est pas repayee la fois suivante. Sans cet appel, la bibliotheque existerait
    # sans jamais servir — « un composant qui ne s'execute pas n'existe pas », la
    # lecon qui avait deja oblige a cabler la memoire des echecs.
    engine.bibliotheque = BibliothequeTemoins(
        path=Path(str_env("JIO_WITNESS_LIB", str(state_dir / "temoins.jsonl")))
    )
    engine.router = TrustRouter(
        path=Path(str_env("JIO_TRUST", str(state_dir / "trust.json"))),
        cost_weight=float_env("JIO_COST_WEIGHT", 0.35),
    )


def _racine_du_document(chemin: Path) -> Path:
    """Racine ou chercher les chemins cites par un document.

    Un document cite `jio/loop/engine.py` : ce chemin est ecrit RELATIVEMENT A LA
    RACINE DU DEPOT, jamais relativement au dossier du document. Prendre le dossier du
    document transformait chaque citation juste en « chemin introuvable » — du bruit,
    et le bruit fait desactiver un outil aussi surement qu'une fausse accusation.
    Faute de depot, on retombe sur le dossier du document : c'est la seule reference
    dont on dispose alors, et elle est exacte.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, cwd=chemin.parent,
            check=False,  # un dossier hors depot n'est pas une erreur
        )
    except Exception:
        proc = None
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip())
    return chemin.parent


def _rapport_du_document(
    chemin: Path, racine: Path | None
) -> tuple[RapportProse, Path]:
    """Verifie un document et rend `(rapport, racine_utilisee)`, sans RIEN afficher.

    Deux appelants, une seule verification : le rapport detaille de `jio claims`, et la
    ligne compacte du hook pre-commit. Deux implementations auraient fini par diverger sur
    le seul point qui compte — quand dire « refute ».
    """
    from .verify.claims import verifier

    texte = chemin.read_text(encoding="utf-8", errors="replace")
    ou = racine if racine is not None else _racine_du_document(chemin)
    return verifier(texte, racine=ou), ou


def _rapport_prose(chemin: Path, racine: Path | None, *, titre: str) -> int:
    """Imprime le rapport de prose et rend le CODE DE SORTIE. Implementation unique.

    Trois codes, et la distinction est le sujet :
      0  conforme sur ce qui est verifiable ;
      1  au moins une affirmation REFUTEE ;
      3  RIEN a verifier — ni succes, ni echec.

    Le 3 existe parce que confondre « document muet » et « document fautif » obligeait
    a choisir entre deux mauvaises reponses : soit un document sans matiere passait
    pour un quitus, soit il etait signale comme un defaut. Aucune des deux n'est vraie.
    

    `jio claims` et `jio audit <document>` appellent cette fonction : deux entrees,
    une seule doctrine. Deux implementations auraient fini par diverger sur le seul
    point qui compte — quand dire « refute ».
    """
    rapport, ou = _rapport_du_document(chemin, racine)

    print()
    print(f"  {titre} · {chemin}")
    print(f"  racine des chemins cites : {ou}")
    print()
    if not rapport.verifications:
        print("    aucune affirmation verifiable trouvee. Ce n'est PAS un quitus : un")
        print("    document sans calcul, sans code et sans chemin cite n'offre rien a")
        print("    prouver — et jio ne pretend pas juger le reste.")
        print("    Code de sortie 3 : « rien a verifier » n'est NI un succes, NI un")
        print("    echec. Un appelant peut donc distinguer les deux, au lieu de")
        print("    confondre un document muet avec un document fautif (code 1).")
        print()
        return 3
    for verification in rapport.verifications:
        marque = "ok " if verification.ok else ("KO " if verification.bloquant else "!  ")
        print(f"    [{marque}] {verification.message}")
    if rapport.ignorees or rapport.non_evaluees:
        print()
        if rapport.ignorees:
            print(f"    [!!] LIMITE DE VOLUME : {rapport.ignorees} affirmation(s) au-dela "
                  "de la limite declaree n'ont PAS ete verifiees. Ce rapport est "
                  "PARTIEL — il ne dit rien de ces affirmations-la.")
        if rapport.non_evaluees:
            print(f"    [!!] {rapport.non_evaluees} calcul(s) trop long(s) pour etre "
                  "evalue(s) : NI verifies, ni accuses. Evaluer une partie des termes "
                  "et la comparer au total inventerait un refus.")
    print()
    print(f"  BILAN : {rapport.resume()}")
    if not rapport.conforme:
        print("    VERDICT : NON CONFORME — une affirmation refutee est un fait, pas")
        print("    une opinion. Corriger le texte, ou retirer l'affirmation.")
        print()
        return 1
    print("    VERDICT : conforme sur ce qui est verifiable (le reste est declare")
    print("    non verifie, jamais suppose vrai).")
    print()
    return 0


def cmd_claims(args: argparse.Namespace) -> int:
    """Verifie les affirmations VERIFIABLES d'un document : calculs, code, chemins.

    Les missions generalistes — analyse, rapport, note de recherche — n'ont pas
    d'oracle executable, donc JIO s'abstenait. Un texte contient pourtant des
    affirmations qui sont vraies ou fausses sans interpretation : un calcul annonce,
    un bloc presente comme Python, un chemin cite. C'est exactement la que se logent
    les hallucinations, et on peut les PROUVER plutot que les relire.
    """
    racine = Path(args.racine) if getattr(args, "racine", "") else None
    fichiers = [Path(f) for f in args.fichier]
    hook = bool(getattr(args, "hook", False))

    # Mode hook : pre-commit lance la commande avec TOUS les fichiers modifies d'un coup.
    # Il faut donc que « rien a verifier » (code 3) ne fasse pas echouer un commit, alors
    # que le meme code 3 reste distinct d'un succes en usage direct. Le contrat du hook est
    # etroit et explicite : echouer UNIQUEMENT sur une affirmation refutee.
    if hook:
        print()
        print("  HOOK PRE-COMMIT  ·  faits verifiables des documents modifies")
        print()
        refutes = 0
        for chemin in fichiers:
            if not chemin.exists():
                continue
            rapport, _ = _rapport_du_document(chemin, racine)
            if not rapport.verifications:
                # « 0 verifiee(s) » se lirait comme un succes a zero faute. C'est le
                # contraire : le document n'offre RIEN a prouver. Le tiret le dit.
                print(f"    [--] {chemin.name} : rien a verifier (ni succes, ni echec)")
                continue
            if rapport.refutees:
                refutes += 1
                print(f"    [KO] {chemin.name} : {rapport.refutees} affirmation(s) refutee(s)")
                for verification in rapport.bloquantes[:4]:
                    print(f"         · {verification.message[:130]}")
            else:
                detail = f"{rapport.verifiees} verifiee(s)"
                if rapport.signalees:
                    detail += f", {rapport.signalees} signalee(s) non concluante(s)"
                print(f"    [ok] {chemin.name} : {detail}")
        print()
        if refutes:
            print(f"  {refutes} document(s) refute(s) : corriger, ou retirer l'affirmation.")
            print("  (`jio claims <fichier>` pour le detail complet.)")
            print()
            return 1
        print("  Aucun fait refute. Le hook ne bloque QUE sur une refutation : un document")
        print("  sans matiere prouvable n'est ni un succes ni un echec.")
        print()
        return 0

    if not fichiers:
        print("  aucun fichier indique", file=sys.stderr)
        return 2
    for chemin in fichiers:
        if not chemin.exists():
            print(f"  fichier introuvable : {chemin}", file=sys.stderr)
            return 2
    if len(fichiers) == 1:
        return _rapport_prose(fichiers[0], racine, titre="AFFIRMATIONS VERIFIABLES")

    # Plusieurs fichiers : le pire code l'emporte, dans l'ordre de gravite 1 > 3 > 0.
    # Un document refute ne doit pas etre noye par un document muet.
    codes: list[int] = []
    for chemin in fichiers:
        codes.append(_rapport_prose(chemin, racine, titre=f"AFFIRMATIONS VERIFIABLES · {chemin}"))
    if 1 in codes:
        return 1
    return 3 if 3 in codes else 0


def cmd_providers(args: argparse.Namespace) -> int:
    """Liste les fournisseurs detectes, et — avec `--prove` — les sonde pour de vrai.

    « Un CLI installe » et « un CLI avec qui jio peut prouver quelque chose » sont
    deux choses differentes. La sonde repond aux deux, avant la premiere mission :
    vivacite, format, et surtout la capacite a TRADUIRE les regles en temoins
    executables — sans laquelle la preuve reste impossible hors banc d'essai.
    """
    from .providers.registry import from_env

    print()
    print("  FOURNISSEURS DETECTES")
    print()
    providers = list(from_env())
    if not providers:
        print("    aucun. Installez un CLI (opencode, hermes, claude, codex, gemini, aider)")
        print("    ou definissez une variable d'environnement d'API. Sans cela :")
        print("      jio bench                     (mesure du harness, sans cle)")
        print("      jio run ... --simulate --task sum_even --no-oracle")
        print()
        return 0

    for provider in providers:
        print(f"    {provider.name:<14} modele {getattr(provider, 'model', '?')}")
    print()

    if not getattr(args, "prove", False):
        print("  Pour PROUVER qu'ils repondent vraiment — et qu'ils savent traduire les")
        print("  regles en temoins executables — relancez avec :  jio providers --prove")
        print()
        return 0

    from .providers.probe import sonder

    print("  SONDES REELLES (une requete minimale, puis le prompt de traduction)")
    print()
    vivants = 0
    capables = 0
    for provider in providers:
        sonde = sonder(provider)
        if sonde.vivant:
            vivants += 1
        if sonde.traduit:
            capables += 1
        marque = "ok " if sonde.traduit else ("vivant" if sonde.vivant else "ko")
        print(f"    [{marque:^6}] {sonde.resume()}")
        if sonde.temoignage is not None:
            for regle, test in list(sonde.temoignage.tests.items())[:2]:
                print(f"             {regle} -> {test[:110]}")
            for regle, raison in list(sonde.temoignage.aveux.items())[:2]:
                print(f"             {regle} -> AVEU : {raison[:100]}")
            for regle, motif in list(sonde.temoignage.refuses.items())[:2]:
                print(f"             {regle} -> REFUSE par les garde-fous : {motif[:100]}")
        if sonde.erreur:
            print(f"             erreur : {sonde.erreur[:200]}")
    print()
    print(f"  BILAN : {vivants}/{len(providers)} repondent, "
          f"{capables}/{len(providers)} savent traduire les regles en temoins.")
    if capables:
        print("    -> jio peut PROUVER sans oracle avec ceux-la : les regles de la")
        print("       mission deviennent des tests executables, et un temoin que tous")
        print("       les candidats echouent ne condamne personne.")
    else:
        print("    -> sans traduction des regles, la preuve reste impossible hors banc")
        print("       d'essai : jio s'abstiendra (c'est la sortie honnete). Fournissez des")
        print("       oracles (--task) ou des exemples `>>>` dans le code a livrer.")
    print()
    return 0 if vivants else 1


def cmd_run(args: argparse.Namespace) -> int:
    journal_path = Path(args.journal) if args.journal else None
    prose = bool(getattr(args, "prose", False))
    # En prose, la tache du banc n'est pas une tache de code : `--task` designe un
    # DOCUMENT de reference (voir `jio/bench/prose.py`).
    tache_prose = None
    if prose:
        from .bench.prose import PROSE_BY_ID, PROSE_TASKS

        if getattr(args, "task", ""):
            tache_prose = PROSE_BY_ID.get(args.task)
            if tache_prose is None:
                print(f"  tache de prose inconnue : {args.task}", file=sys.stderr)
                print("  disponibles : " + ", ".join(t.id for t in PROSE_TASKS),
                      file=sys.stderr)
                return 2
        elif args.simulate:
            tache_prose = PROSE_TASKS[0]
    task = TASKS_BY_ID.get(args.task) if getattr(args, "task", "") and not prose else None

    if prose and args.simulate and tache_prose is None:  # pragma: no cover - garde
        print("  mode prose simule : aucune tache de document disponible.", file=sys.stderr)
        return 2
    if not getattr(args, "objective", "") and not task and not args.simulate:
        # Sans tache du banc et sans simulation, il n'y a rien a faire : on le dit
        # au lieu de partir avec un objectif vide et d'abstenir pour une mauvaise
        # raison.
        print("  objectif requis : jio run \"<objectif>\"", file=sys.stderr)
        print("  en simulation, une tache du banc le fournit : jio run --simulate "
              "--task sum_even", file=sys.stderr)
        return 2

    if args.simulate and not task and not prose:
        print(
            "  Mode simulation : aucun CLI ni cle d'API requis. La generation a besoin\n"
            "  d'une tache du banc pour que le modele SIMULE ait du code a rendre :\n"
            "    jio run \"<objectif>\" --simulate --task sum_even\n"
            "    jio run \"<objectif>\" --simulate --task sum_even --no-oracle\n"
            "  Taches disponibles : " + ", ".join(t.id for t in TASKS) + "\n"
            "  Sans --task, la simulation ne peut rien generer : elle le dit au lieu\n"
            "  d'inventer une reponse.\n"
        )
        return 2

    # Meme syntaxe que le banc : `--provider cli:opencode`, `openai:<modele>`, `simule`.
    # Un modele nomme et indisponible ARRETE la mission, ici comme ailleurs.
    modele_liste: list[object] = []
    specs = list(getattr(args, "provider", []) or [])
    if specs:
        from .bench.provider_spec import resoudre_liste
        from .core.errors import ProviderError

        try:
            modele_liste = list(resoudre_liste(specs))
        except ProviderError as exc:
            print(f"  {exc}", file=sys.stderr)
            return 2
        if all(f.genre == "simule" for f in modele_liste):
            # `--provider simule` sans `--simulate` n'aurait aucun sens : la simulation
            # a besoin d'une tache du banc pour generer quelque chose, et c'est
            # `--simulate` qui le dit. On refuse au lieu d'inventer.
            print("  `--provider simule` a besoin de `--simulate` (et d'une `--task`).",
                  file=sys.stderr)
            return 2
        args.simulate = False

    if prose and args.simulate:
        from .bench.prose import prose_bank

        engine = _simulated_engine(
            None, seed=0, journal_path=journal_path, max_rounds=args.rounds,
            alpha=args.alpha, min_panel=args.min_panel,
            famille="prose", banque=prose_bank(tache_prose), racine=Path.cwd(),
        )
    elif prose:
        engine = _real_engine(
            journal_path=journal_path, max_rounds=args.rounds,
            min_panel=args.min_panel, famille="prose", racine=Path.cwd(),
            fournisseurs=modele_liste,
        )
    elif args.simulate:
        engine = _simulated_engine(
            task, seed=0, journal_path=journal_path, max_rounds=args.rounds,
            alpha=args.alpha, min_panel=args.min_panel,
            # --no-oracle : la mission ne fournit AUCUN test, comme une mission
            # reelle. Le modele simule traduit les regles en temoins, et la preuve
            # doit tenir toute seule.
            traduire_les_regles=bool(getattr(args, "no_oracle", False)),
        )
    else:
        engine = _real_engine(
            journal_path=journal_path, max_rounds=args.rounds, min_panel=args.min_panel,
            fournisseurs=modele_liste,
        )
    _attach_learning(engine, Path(args.state), disable=args.no_learn)

    if tache_prose is not None:
        objective = args.objective or tache_prose.objective
    else:
        objective = task.objective if task else args.objective

    # La specification d'une mission de prose n'est PAS derivee d'un modele : la
    # regle de couverture (au moins une affirmation verifiable, aucune refutee) est
    # vraie par construction du verificateur. La confier a un modele reviendrait a
    # lui demander d'autoriser sa propre existence.
    spec_statique = None
    if prose:
        from .verify.prose_prover import spec_prose

        spec_statique = spec_prose(objective)

    mission = Mission(objective=objective, max_rounds=args.rounds, alpha=args.alpha)
    work = WorkItem(
        objective=objective,
        entrypoint=(task.entrypoint if task else args.entrypoint or ""),
        checks=(dict(task.checks) if task and not getattr(args, "no_oracle", False) else {}),
        spec=(task.spec() if task else spec_statique),
    )
    report = engine.run(mission, work)
    # Les avertissements du journal sont affiches APRES l'execution : c'est
    # l'ecriture qui revele l'etat du fichier (reprise d'une chaine, mise en
    # quarantaine d'un journal falsifie). Les annoncer avant l'ecriture serait
    # annoncer un fait qui n'a pas encore eu lieu.
    for notice in getattr(engine.journal, "notices", []):
        print(f"  [journal] {notice}", file=sys.stderr)
    # La memoire des temoins peut avoir ete mise en quarantaine (chaine cassee) :
    # perdre une memoire sans le dire serait exactement le silence que ce projet
    # refuse. On le dit, sur la sortie d'erreur, sans bloquer la mission.
    for notice in getattr(engine.bibliotheque, "notices", []) or []:
        print(f"  [temoins] {notice}", file=sys.stderr)
    print(render_report(report, verbose=args.verbose))
    if args.json:
        Path(args.json).write_text(report.to_json(), encoding="utf-8")
        print(f"  rapport JSON ecrit dans {args.json}")
    return 0 if report.status is MissionStatus.DELIVERED else 1


def cmd_audit(args: argparse.Namespace) -> int:
    from .core.errors import FailClosed
    from .verify.autocheck import derive

    path = Path(args.file)
    if not path.exists():
        print(f"  fichier introuvable : {path}", file=sys.stderr)
        return 2
    source = path.read_text(encoding="utf-8", errors="replace")

    # Une seule porte, deux familles de temoins. Sur un document, auditer comme du
    # code rendait « la source ne compile pas » : vrai, et inutile — l'utilisateur
    # n'apprend rien. Un document est juge par ses propres temoins de prose.
    from .verify.claims import est_un_document

    if not getattr(args, "task", "") and est_un_document(path, source):
        racine = Path(args.racine) if getattr(args, "racine", "") else None
        return _rapport_prose(path, racine, titre="AUDIT (prose)")

    task = TASKS_BY_ID.get(args.task) if args.task else None
    origin = ""
    notes: tuple[str, ...] = ()
    preamble = ""
    if task:
        spec = task.spec()
        checks = dict(task.checks)
        entrypoint = task.entrypoint
        origin = f"oracles caches du banc ({task.id})"
    else:
        derived = derive(source, entrypoint=args.entrypoint, path=path)
        spec = derived.spec
        checks = derived.checks
        entrypoint = derived.entrypoint
        preamble = derived.preamble
        notes = derived.notes
        origin = f"regles derivees de l'artefact (entree : {entrypoint or 'aucune'})"
        if not derived.verifiable:
            print()
            print(f"  AUDIT  {path}")
            print("  0 regle executable -> RIEN N'A ETE PROUVE.")
            print()
            for lim in spec.under_specified:
                print(f"    [limite] {lim}")
            print()
            print("  VERDICT : INDETERMINE — declarer un succes ici serait un mensonge.")
            print()
            return 2

    prover = ExecutableProver(sandbox=Sandbox(timeout=20), journal=Journal())
    try:
        res = prover.prove(
            source, spec, hidden_checks=checks, entrypoint=entrypoint, preamble=preamble
        )
    except FailClosed as exc:
        print()
        print(f"  AUDIT  {path}")
        print(f"  {exc}")
        print()
        print("  VERDICT : INDETERMINE (fail-closed : aucune preuve disponible).")
        print()
        return 2

    reservations = res.reservations
    total = len(res.witnesses)
    ok = total - len(res.failures)
    print()
    print(f"  AUDIT  {path}")
    print(f"  {ok}/{total} regles satisfaites   ·   source des regles : {origin}")

    if reservations and not res.hard_failures:
        print("  (les regles en RESERVE ne comptent pas comme des preuves de defaut)")
    print()
    for w in res.witnesses:
        detail = ""
        if not w.ok:
            lines = [x.strip() for x in (w.stderr or "").splitlines() if x.strip()]
            detail = lines[-1][:90] if lines else f"code de sortie {w.exit_code}"
        mark = "ok" if w.ok else ("??" if w.rule_id in res.advisory_ids else "KO")
        print(f"    [{mark}] {w.rule_id:<7} {detail}".rstrip())
    print()
    if reservations:
        print("  RESERVES (suspect, non prouve) :")
        for w in reservations:
            print(f"    - {w.rule_id} : {(w.stderr or '').strip().splitlines()[-1][:100]}")
        print()
    if spec.under_specified:
        print("  LIMITES DECLAREES (ce qui n'a PAS ete prouve) :")
        for lim in spec.under_specified:
            print(f"    - {lim}")
        print()
    for note in notes:
        print(f"    note : {note}")
    if notes:
        print()
    if not res.passed:
        print("  VERDICT : NON CONFORME — livrer en l'etat serait une erreur silencieuse.")
        print()
        return 1
    print("  VERDICT : CONFORME sur les regles verifiables (et seulement sur celles-la).")
    print()
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """`jio sync` : propager tout le cerveau anti-erreur dans l'ecosysteme, en une fois.

    Les documents promettaient `jio sync` a trois endroits, et la commande n'existait pas :
    `jio claims docs/ROADMAP.md` l'a refute. C'est exactement ce que la verification des
    commandes citees sert a attraper.

    Elle fait ce que la promesse dit, et rien de plus :
      * elle ecrit tous les artefacts natifs (les dialectes de contexte, les agents
        opencode, les competences Hermes) sous la racine visee ;
      * elle branche le serveur MCP pour chaque outil, sans jamais modifier une
        configuration existante ;
      * elle n'ecrase jamais un fichier qui n'est pas de nous.

    Elle ne touche PAS a git : `scripts/sync.sh` fait cela, avec ses propres garde-fous.
    Deux roles, deux commandes — celle-ci propage, l'autre synchronise le DEPOT.
    """
    from .artifacts import TARGETS, manifest
    from .artifacts.wiring import DIALECTES, brancher
    from .artifacts.write_guard import ecrire_manifest

    racine = Path(args.root).expanduser()
    print(BANNER)
    print(f"  PROPAGATION  ·  racine : {racine.resolve()}")
    print()

    if args.dry_run:
        for rel in sorted(manifest()):
            print(f"    [simulation] {rel}")
        print()
        # `jio sync` n'a pas de `--write` : il ecrit. Lui conseiller un drapeau inexistant
        # envoyait l'utilisateur dans un `unrecognized arguments` — le meme defaut que
        # `jio claims` traque maintenant dans les documents.
        print("    mode simulation : rien n'a ete ecrit. Relancez SANS --dry-run.")
        print()
        return 0

    print(f"    artefacts natifs ({len(TARGETS)} cibles)")
    # Le registre `.jio/generated.json` remplace toute heuristique : il porte l'empreinte
    # de ce que NOUS avons ecrit, ce qui permet de savoir si quelqu'un y a touche depuis.
    decisions = ecrire_manifest(racine, manifest())
    for decision in sorted(decisions, key=lambda d: d.chemin):
        if decision.action == "inchange":
            continue
        marque = {"preserve": "PRESERVE", "remplace": "mis a jour"}.get(
            decision.action, decision.action
        )
        print(f"      {marque:11} {decision.chemin} — {decision.detail}")
    ecrits = sum(1 for d in decisions if d.ecrit)
    preserves = [d for d in decisions if d.action == "preserve"]
    print(f"    => {ecrits} ecrit(s), {len(decisions) - ecrits - len(preserves)} deja a jour, "
          f"{len(preserves)} preserve(s)")

    print()
    print("    serveur MCP")
    dialectes = [d for d in DIALECTES if not args.mcp or d[0] == args.mcp]
    for nom, _fichier, description in dialectes:
        # `brancher` ecrit le fichier s'il est ABSENT et rend le fragment sinon : la
        # configuration de l'utilisateur n'est jamais reecrite.
        _ecrit, message = brancher(racine, nom)
        premiere = message.splitlines()[0] if message else ""
        print(f"      {nom:<12} {description:<40} {premiere}")
    print()
    print("    Pour synchroniser le DEPOT (et non les artefacts) : scripts/sync.sh")
    print("    Aucun fichier ne portant pas la marque de jio n'a ete touche.")
    print()
    return 1 if preserves else 0


def _brancher_mcp(args: argparse.Namespace) -> int:
    """`jio artifacts --mcp <dialecte>` : brancher le serveur MCP, sans rien ecraser."""
    from .artifacts.wiring import DIALECTES, brancher

    print(BANNER)
    if args.mcp == "liste":
        print("  DIALECTES MCP  ·  brancher le serveur JIO dans votre outil")
        print()
        for nom, fichier, description in DIALECTES:
            cible = fichier or "(fragment a coller)"
            print(f"    {nom:<12} {description:<44} {cible}")
        print()
        print("    `jio artifacts --mcp <dialecte>` ecrit le fichier s'il n'existe PAS, et")
        print("    affiche le fragment sinon. Ce depot ne modifie jamais votre configuration.")
        print()
        if args.dry_run:
            from .artifacts.wiring import fragments

            for nom, texte in fragments().items():
                print(f"  --- {nom} ---")
                print(texte)
        return 0

    # `--root` permet de viser une configuration GLOBALE (~/.config/opencode,
    # ~/.cursor) et pas seulement la racine du projet.
    destination = Path(getattr(args, "root", ".") or ".").expanduser()
    ecrit, message = brancher(destination, args.mcp)
    print(f"  BRANCHEMENT MCP  ·  {args.mcp}  ·  {destination}")
    print()
    for ligne in message.splitlines():
        print(f"    {ligne}")
    print()
    if ecrit:
        print("    Le serveur expose jio_prove, jio_audit, jio_contract, jio_claims et")
        print("    jio_skills. Verifier avec `jio mcp --list`.")
    return 0


def _budget_contexte(args: argparse.Namespace) -> int:
    """`jio artifacts --budget` : ce que la configuration coute en contexte, mesure.

    Un fichier de contexte trop long est SURVOLE, pas lu — il coute du contexte sans rien
    apporter. Un test vert ne le dit pas a l'utilisateur ; ce rapport, si.
    """
    from .artifacts.budget import SEUILS, mesurer_depuis, resume, verdict
    from .artifacts.emit import manifest

    print(BANNER)
    print("  BUDGET DE CONTEXTE  ·  ce que vos outils chargent, et ce qu'ils ignorent")
    print()

    tous = manifest()
    # Ce qui est charge au DEMARRAGE : fichiers de contexte et fragments de cablage.
    # Les agents et les competences se chargent a la demande (revelation progressive) :
    # les confondre ferait croire a un cout qui n'existe pas.
    demarrage = {
        chemin: texte for chemin, texte in tous.items()
        if chemin in {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/jio.mdc",
                      ".github/copilot-instructions.md"}
    }
    skills = {c: x for c, x in tous.items() if "/skills/" in c and c.endswith("SKILL.md")}
    agents = {c: x for c, x in tous.items() if c.startswith(".opencode/agents/")
              and c.endswith(".md") and not c.endswith("README.md")}

    # Un outil donne ne charge QU'UN fichier de contexte : Claude lit CLAUDE.md, Cursor
    # lit .cursor/rules/jio.mdc, Copilot lit .github/copilot-instructions.md, etc. Les
    # additionner produirait un total qu'AUCUNE session ne paie — c'est exactement le genre
    # de chiffre faux qu'un rapport sur le contexte ne peut pas se permettre. On mesure le
    # fichier le plus lourd et le plus leger, et on dit ce que paie une session reelle.
    demarrage_mesures = mesurer_depuis(Path.cwd(), demarrage)
    for lignes in resume(
        demarrage_mesures,
        "CHARGE AU DEMARRAGE — un outil n'en lit qu'UN (celui de son dialecte)",
        total=False,
    ):
        print(lignes)
    if demarrage_mesures:
        plus_leger = min(m.jetons for m in demarrage_mesures)
        plus_lourd = max(m.jetons for m in demarrage_mesures)
        print()
        print(f"    Cote d'une session REELLE : ~{plus_leger} a {plus_lourd} jetons selon "
              "l'outil, pas la somme.")
    print()
    for lignes in resume(mesurer_depuis(Path.cwd(), skills), "DISPONIBLE A LA DEMANDE — competences"):
        print(lignes)
    print()
    for lignes in resume(mesurer_depuis(Path.cwd(), agents), "DISPONIBLE A LA DEMANDE — agents"):
        print(lignes)
    print()

    tous_mesures = mesurer_depuis(Path.cwd(), tous)
    for ligne in verdict(
        tous_mesures,
        est_competence=lambda chemin: "/skills/" in chemin and chemin.endswith("SKILL.md"),
    ):
        print(ligne)
    print()

    total_skills = sum(m.jetons for m in mesurer_depuis(Path.cwd(), skills))
    print(f"    Bibliotheque de competences : ~{total_skills} jetons "
          f"(seuil {SEUILS['bibliotheque_jetons']})")
    print("    Contexte injecte au demarrage : un seul fichier par outil (voir ci-dessus)")
    print()
    print("    Lecture : les jetons sont un INTERVALLE (3,2 a 4,4 caracteres par jeton "
          "selon")
    print("    la langue et le code) — un tokenizer reel est une dependance, et la mesure")
    print("    varie d'un modele a l'autre. Ce qu'on peut dire, on le dit ; le reste est")
    print("    declare comme incertain.")
    print()
    return 0


def cmd_artifacts(args: argparse.Namespace) -> int:
    """Emet les artefacts natifs. `--mcp` route vers le branchement du serveur MCP."""
    if getattr(args, "budget", False):
        return _budget_contexte(args)
    if getattr(args, "mcp", None):
        return _brancher_mcp(args)
    from .artifacts import TARGETS, manifest

    targets = tuple(args.target) if args.target else TARGETS
    try:
        files = manifest(targets)
    except ValueError as exc:
        print(f"  {exc}", file=sys.stderr)
        return 2

    print()
    print(f"  ARTEFACTS NATIFS  ·  {len(files)} fichier(s)  ·  cibles : {', '.join(targets)}")
    print()
    for rel in sorted(files):
        print(f"    {rel}")
    print()

    if not args.write:
        print("  mode simulation : rien n'a ete ecrit. Ajoutez --write pour creer les fichiers.")
        print()
        return 0

    root = Path(args.root)
    # On n'ecrase pas un fichier qui n'est PAS de nous (voir write_guard) : `AGENTS.md`
    # est precisement le fichier ou un projet met ses conventions, editees a la main.
    from .artifacts.write_guard import ecrire_manifest

    decisions = ecrire_manifest(root, files)
    ecrits = [d for d in decisions if d.ecrit]
    preserves = [d for d in decisions if d.action == "preserve"]
    a_jour = [d for d in decisions if d.action == "inchange"]
    detail = f", {len(a_jour)} deja a jour" if a_jour else ""
    print(f"  {len(ecrits)} fichier(s) ecrit(s){detail} sous {root.resolve()}")
    for decision in preserves:
        print(f"    PRESERVE : {decision.chemin} — {decision.detail}")
    avertis = [d for d in decisions if d.action == "remplace" and "modifiee" in d.detail]
    for decision in avertis:
        print(f"    ATTENTION : {decision.chemin} — {decision.detail}")
    print()
    if preserves:
        # Un fichier NON ecrit n'est pas un succes : un appelant qui enchaine doit pouvoir
        # s'en apercevoir (meme regle que le hook `jio claims`).
        print("  Des fichiers ont ete PRESERVES : ils ne portent pas la marque de jio, donc")
        print("  ils sont a vous. Leur version jio est ecrite a cote (suffixe .jio).")
        print()
    print("  Une seule doctrine, tous les dialectes : pour modifier le contenu,")
    print("  editez jio/artifacts/doctrine.py ou definitions.py, jamais les fichiers generes.")
    print()
    return 1 if preserves else 0


def cmd_trust(args: argparse.Namespace) -> int:
    from .trust import TrustRouter, task_class

    router = TrustRouter(path=Path(args.state))
    print()
    print(f"  ROUTEUR DE CONFIANCE  ·  etat : {args.state}")
    if args.objective:
        klass = task_class(args.objective)
        arm = router.choose(args.objective)
        print(f"  objectif : {args.objective}")
        print(f"  classe   : {klass}")
        print()
        print(f"  bras recommande : {arm.name}")
        print(f"    candidats/tour {arm.candidates}  ·  tours {arm.rounds}"
              f"  ·  panel {arm.panel_size}  ·  alpha {arm.alpha}  ·  cout {arm.cost}")
        print(f"    budget d'appels maximum : {arm.budget_calls}")
        print()
    print(router.report())
    print()
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    from .learn import FailureMemory

    memory = FailureMemory(path=Path(args.state))
    print()
    print(f"  MEMOIRE DES ECHECS  ·  {args.state}")
    print()
    if args.add:
        try:
            rec = memory.record(
                objective=args.objective or "",
                symptom=args.symptom or "",
                root_cause=args.cause or "",
                wrong_fix=args.wrong_fix or "",
                correct_fix=args.fix or "",
                guard=args.guard or "",
            )
        except ValueError as exc:
            print(f"  REFUS : {exc}", file=sys.stderr)
            print()
            return 2
        print(f"  enregistre : {rec.fingerprint} (evenement {rec.seq})")
        print()
        return 0
    if args.recall:
        found = memory.recall(args.recall)
        print(f"  rappel pour : {args.recall}")
        print()
        if not found:
            print("    aucun souvenir pertinent.")
            print("    Une memoire vide est un etat legitime : le systeme n'invente pas")
            print("    de mises en garde qu'il n'a pas payees.")
            print()
            return 0
        for rec in found:
            print(rec.as_block())
            print()
        return 0
    print(memory.report())
    print()
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    from .learn.experiment import run_abc

    print()
    print(f"  AUTO-AMELIORATION  ·  competence simulee {args.skill}  ·  {args.runs} tirage(s) "
          f"par tache  ·  {args.rounds} tours")
    print("  Memoire vive sur disque (usage reel) ; memes graines dans les trois bras.")
    print()
    res = run_abc(skill=args.skill, runs=args.runs, rounds=args.rounds)

    print(f"    {'tache':<16} {'A froid':>8} {'B temoin':>9} {'C chaud':>8}   effet isole")
    print(f"    {'-' * 16} {'-' * 8} {'-' * 9} {'-' * 8}   {'-' * 11}")
    for tid, (cold, control, warm) in sorted(res.per_task.items()):
        delta = warm - control
        mark = "  <-- gain" if delta > 0 else ("  <-- PERTE" if delta < 0 else "")
        print(f"    {tid:<16} {cold:>8} {control:>9} {warm:>8}"
              f"   {delta:>+11d}{mark}")
    print()
    print(f"    A  froid  (sans memoire)             {res.cold_success}/{res.total}"
          f"  ({res.cold_rate:.1%})")
    print(f"    B  temoin (memoire, effet desactive) {res.control_success}/{res.total}"
          f"  ({res.control_rate:.1%})")
    print(f"    C  chaud  (memoire, effet actif)     {res.warm_success}/{res.total}"
          f"  ({res.warm_rate:.1%})")
    print()
    print("  ISOLATION DE L'EFFET")
    ecart_ab, (bas_ab, haut_ab), tranche_ab = res.intervalle(res.cold_success, res.control_success)
    ecart_bc, (bas_bc, haut_bc), tranche_bc = res.intervalle(res.control_success, res.warm_success)
    print(f"    A -> B  artefact de loterie de graine : {res.lottery_artifact * 100:+.1f} points"
          f"  IC95 [{bas_ab:+.1f} ; {haut_ab:+.1f}]")
    print("            (le prompt change, la probabilite non : attendu ~0)")
    print(f"    B -> C  gain ATTRIBUABLE a la memoire : {res.isolated_gain * 100:+.1f} points"
          f"  IC95 [{bas_bc:+.1f} ; {haut_bc:+.1f}]")
    print("            (prompts identiques, seule la probabilite differe : causalement propre)")
    # Un ecart sans intervalle se lit comme un resultat. Ici, avec un `total` de quelques
    # dizaines d'essais, l'immense majorite des ecarts sont INDETERMINES — et c'est une
    # information sur le banc, pas sur la memoire.
    if not tranche_bc:
        besoin = res.budget_de_mesure()
        print("    -> l'intervalle du gain attribuable CONTIENT zero : INDETERMINE a cet")
        print(f"       echantillon ({res.total} essai(s) par bras).")
        if besoin:
            print(f"       Pour demontrer {res.isolated_gain * 100:+.1f} points : environ "
                  f"{besoin} essai(s) par bras.")
        else:
            print("       Aucun nombre d'essais ne demontrera un effet nul.")
    else:
        print("    -> l'intervalle du gain attribuable EXCLUT zero : effet demontre.")
    if tranche_ab:
        print("    ATTENTION : l'artefact de loterie est lui aussi significatif — le banc")
        print("    est trop petit pour attribuer l'effet a la memoire plutot qu'a la graine.")
    print()
    print(f"    echecs memorises : {res.recorded}   ·   missions ou un souvenir a ete rappele : "
          f"{res.missions_with_recall}")
    print()
    quantum = 100.0 / res.total if res.total else 0.0
    print(f"  RESOLUTION : un quantum = 1 mission = {quantum:.1f} points.")
    print(f"    Toute difference inferieure a {quantum:.1f} points n'est pas mesurable ici ;")
    print("    c'est la raison pour laquelle le temoin A -> B est affiche : il montre le")
    print("    plancher de bruit reel, pas un bruit suppose.")
    print()
    if res.isolated_gain <= 0.0:
        print("  DIAGNOSTIC : gain attribuable NON MESURABLE dans ce regime.")
        print("    Ce n'est pas un echec de la mesure, c'est une conclusion sur l'architecture.")
        print("    La reprise est deja assuree par deux mecanismes qui ne dependent pas de")
        print("    la memoire : la LARGEUR DE TIRAGE (best-of-N) et la VERIFICATION, qui")
        print("    SELECTIONNE le bon candidat parmi ceux produits. Quand ces deux-la")
        print("    suffisent, la memoire n'a rien a ajouter : son effet est un gain")
        print("    relatif par tentative, noye dans le nombre de tentatives.")
        print("    Ou la memoire devrait payer : la ou la verification NE VOIT PAS")
        print("    l'erreur (affirmations non verifiables, choix de conception,"
              " plausibilite).")
        print("    Ce banc ne peut pas representer ce regime : il est bati sur des oracles")
        print("    executables. L'affirmer sans le mesurer serait exactement ce que ce")
        print("    projet refuse.")
    else:
        print(f"  RESULTAT : gain attribuable de {res.isolated_gain * 100:+.1f} points, a")
        print("    tirages identiques entre B et C. C'est un effet reel de la mecanique.")
    print()
    print("  CE QUE CE CHIFFRE EST, ET CE QU'IL N'EST PAS")
    print("    - c'est la mesure de la MECANIQUE : memoriser, rappeler, injecter.")
    print("    - ce n'est PAS une mesure de modele reel : le modele est simule.")
    print("    - l'effet d'avertissement est une MODELISATION explicite : un gain")
    print("      RELATIF de 15 % par tentative (base 50-60 % + 5 a 10 points dans la")
    print("      litterature du retour d'echec = 10 a 20 % relatifs).")
    print("    - le gain est MULTIPLICATIF et non additif, a dessein : un harness")
    print("      amplifie la competence, il n'en cree pas. A competence nulle, aucun")
    print("      avertissement ne sauve le modele — l'invariant est encode dans le")
    print("      simulateur, et un test le verrouille.")
    print()
    return 0


def _classify_failure(stderr: str, exit_code: int) -> str:
    """Un echec de verification est-il un defaut de l'artefact ou une limite d'environnement ?

    Constate sur un vrai projet (`humanize`) : `_version.py` est GENERE a
    l'installation (setuptools-scm) et absent du depot. Les regles echouaient
    alors avec `ModuleNotFoundError`, et l'audit declarait 7 problemes dans un
    projet parfaitement correct.

    Un echec du a l'environnement n'est NI un defaut, NI une reserve : c'est
    l'aveu que la verification n'a pas pu avoir lieu. Les distinguer, c'est la
    difference entre un outil qu'on peut brancher sur du vrai code et un outil
    qui noie l'utilisateur sous de fausses alertes.
    """
    text = stderr or ""
    if "ModuleNotFoundError" in text or "ImportError" in text:
        return "environment"
    # Un SyntaxError atteignant ce point ne peut PAS venir de l'artefact : derive()
    # l'a deja analyse avec succes. Il vient donc forcement d'un module importe —
    # typiquement un fichier casse dont notre fichier depend. L'accuser produirait
    # une CASCADE de faux positifs : un seul fichier fautif ferait declarer
    # coupables tous ses dependants. Constate sur un vrai projet.
    if "SyntaxError" in text or "IndentationError" in text:
        return "environment"
    if exit_code == 127:  # binaire absent
        return "environment"
    # Construit en scannant des bibliotheques reelles (rich, click, attrs) : une
    # classe dont la construction CONSULTE l'environnement — argumentaire de ligne
    # de commande, saisie clavier — echoue en bac a sable ferme. `EOFError` (stdin
    # ferme), `SystemExit` (argparse sans arguments) et `KeyboardInterrupt` ne disent
    # rien sur la correction du code : c'est notre facon de mesurer qui est en cause.
    if any(marque in text for marque in ("EOFError", "SystemExit", "KeyboardInterrupt")):
        return "environment"
    if "[RESERVE]" in text:
        return "reserve"
    # Un fichier ABSENT, designe par un chemin absolu hors du projet : la regle
    # cherche une donnee de demonstration qui n'est pas la (`/tmp/evidence/...`,
    # corpus de test non regenere). Le code du projet n'y est pour rien — et l'accuser
    # ferait passer un fichier de test parfaitement sain pour un defaut.
    if "FileNotFoundError" in text or "No such file or directory" in text:
        return "environment"
    return "defect"


#: Dossiers qu'un balayage de projet ne doit JAMAIS traverser par defaut.
#:
#: Mesure du probleme : `jio scan .` sur ce depot balayait 1363 fichiers Python,
#: dont l'environnement virtuel, et produisait 736 « problemes » — des faux positifs
#: sur du code tiers, plus 285 secondes d'attente. Une liste de defauts qu'on ne peut
#: pas lire ne vaut rien : elle est ignorée en entier, y compris ses vrais defauts.
#:
#: Ces dossiers ne contiennent pas le code du projet : ils contiennent des copies de
#: dependances, des caches et des artefacts de construction. Le nom du dossier est
#: compare SOUS la racine balayee, jamais au-dessus : on peut donc auditer un paquet
#: installe en le nommant directement.
DOSSIERS_IGNORES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", ".tox", ".nox", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".pytype",
    "node_modules", "site-packages", "dist-packages", "build", "dist",
    ".eggs", ".idea", ".vscode", "vendor", "third_party", ".direnv",
})


#: Marqueur par lequel un fichier DECLARE contenir une faute VOLONTAIRE.
#:
#: Sans lui, le corpus de preuves de ce depot (`evidence/**/fautifs/`,
#: `evidence/claims/rapport_fautif.md`) etait signale comme 16 defauts du projet :
#: un balayage qui crie sur ses propres fixtures est un balayage qu'on ignore.
#: Le fichier lui-meme dit ce qu'il est — a la maniere des directives de silence des
#: linters, mais VERIFIABLE : le marqueur est compte et affiche, jamais applique en
#: silence.
MARQUEUR_CORPUS = "jio:corpus-fautif"


def _corpus_volontaire(texte: str) -> bool:
    """Vrai si le fichier se declare porteur d'une faute volontaire (3 premieres lignes)."""
    return any(MARQUEUR_CORPUS in ligne for ligne in texte.splitlines()[:3])


def _est_ignore(chemin: Path, racine: Path) -> bool:
    """Vrai si le chemin traverse un dossier a ignorer, SOUS la racine donnee."""
    try:
        relatif = chemin.relative_to(racine)
    except ValueError:
        return False
    for partie in relatif.parts[:-1]:
        if partie in DOSSIERS_IGNORES or partie.endswith(".egg-info"):
            return True
    return False


def cmd_scan(args: argparse.Namespace) -> int:
    """Audite un projet entier et n'affiche QUE ce qui ne va pas.

    C'est l'utilite premiere : pointer le systeme sur du vrai code et obtenir une
    liste courte de defauts reels, chacun avec sa preuve. Un rapport qui recopie
    « tout va bien » pour 200 fichiers n'aide personne.
    """
    from .verify.autocheck import derive
    from .verify.executable import ExecutableProver, Sandbox

    root = Path(args.path)
    if not root.exists():
        print(f"  chemin introuvable : {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
    if args.exclude_tests:
        files = [f for f in files
                 if not (f.name.startswith("test_") or f.name == "conftest.py"
                         or "/tests/" in str(f) or "/test/" in str(f))]

    # On IGNORE les dossiers qui ne contiennent pas le code du projet (mesure :
    # sans ce filtre, `jio scan .` sur ce depot lisait 1363 fichiers — l'environnement
    # virtuel — et rendait 736 faux positifs en 285 secondes). Ce qui est ignore est
    # DIT plus bas : un balayage qui se tairait sur ce qu'il n'a pas regarde serait
    # exactement le silence que ce projet refuse.
    ignores: list[str] = []
    if root.is_dir() and not getattr(args, "tout", False):
        gardes = [f for f in files if not _est_ignore(f, root)]
        if len(gardes) != len(files):
            sous = {p.parts[len(root.parts)] for p in files
                    if _est_ignore(p, root) and len(p.parts) > len(root.parts)}
            ignores = sorted(sous)
        files = gardes

    # --- les DOCUMENTS du projet, juges par leurs propres temoins ------------ #
    # Un depot contient du code ET de la prose : un README qui cite un fichier
    # inexistant ou annonce un calcul faux est un defaut du depot, exactement comme
    # une fonction qui ne compile pas. Les traiter dans le MEME balayage evite au
    # passage d'oublier une moitie du projet.
    documents = (
        sorted(
            d for suffixe in (".md", ".markdown", ".rst")
            for d in root.rglob(f"*{suffixe}")
            if not getattr(args, "tout", False) and not _est_ignore(d, root)
        )
        if root.is_dir() else []
    )

    prover = ExecutableProver(sandbox=Sandbox(timeout=args.timeout))
    problems: list[tuple[Path, str, str]] = []    # fichier, regle, preuve
    environment: list[tuple[Path, str, str]] = []  # verification impossible : pas un defaut
    reserves: list[tuple[Path, str, str]] = []
    partial: dict[Path, list[str]] = {}
    unverifiable: list[Path] = []
    with_rules = 0
    checked = 0

    corpus_volontaire: list[Path] = []

    for path in files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(source) > 500_000:
            continue
        if _corpus_volontaire(source):
            # Le fichier DIT qu'il est faux a dessein : on le compte et on l'annonce,
            # on ne le juge pas.
            corpus_volontaire.append(path)
            continue
        try:
            derived = derive(source, path=path)
        except Exception as exc:                    # un fichier hostile ne casse pas le scan
            problems.append((path, "SCAN", f"analyse impossible : {exc}"[:120]))
            continue
        if not derived.verifiable:
            # Un fichier qui ne compile pas n'est PAS « non verifiable » : c'est un
            # defaut, et le plus grave qui soit puisqu'il empeche tout le reste.
            broken = next((u for u in derived.spec.under_specified
                           if "ne compile pas" in u), "")
            if broken:
                problems.append((path, "SYNTAXE", broken[:160]))
            else:
                unverifiable.append(path)
            continue
        with_rules += 1
        try:
            res = prover.prove(
                source, derived.spec, hidden_checks=derived.checks,
                entrypoint=derived.entrypoint, preamble=derived.preamble,
            )
        except Exception as exc:
            problems.append((path, "SCAN", f"preuve impossible : {exc}"[:120]))
            continue
        checked += len(res.witnesses)
        for w in res.hard_failures:
            detail = [x.strip() for x in (w.stderr or "").splitlines() if x.strip()]
            message = (detail[-1] if detail else f"exit {w.exit_code}")[:160]
            verdict = _classify_failure(w.stderr, w.exit_code)
            if verdict == "environment":
                # Ce n'est pas un defaut du projet : c'est notre environnement qui
                # est incomplet (dependance generee, paquet non installe), ou notre
                # facon de mesurer qui est inadequate (classe interactive).
                environment.append((path, w.rule_id, message))
            elif verdict == "reserve":
                # La regle n'a pas pu conclure sur du code qui n'est pas fautif :
                # exemples qui supposent un contexte (fixture de test), exemples
                # d'illustration sans sortie attendue. On le SIGNALE, on ne condamne
                # pas.
                reserves.append((path, w.rule_id, message.replace("[RESERVE]", "").strip()[:120]))
            else:
                problems.append((path, w.rule_id, message))
        for w in res.reservations:
            lines = [x.strip() for x in (w.stderr or w.stdout or "").splitlines() if x.strip()]
            reserves.append((path, w.rule_id, (lines[-1] if lines else "non tranche")[:120]))
        # Une limite declaree n'est pas un defaut : c'est la liste de ce que ces
        # regles-la ne savent pas juger (parametres non annotes, fonctions hors
        # audit, hasard hors des fonctions auditees). La taire serait presenter un
        # audit partiel comme un audit complet.
        limits = [u for u in derived.spec.under_specified
                  if "ne compile pas" not in u]
        if limits:
            partial.setdefault(path, []).extend(limits)

    # --- documents : seuls les REFUS sont des defauts ------------------------ #
    # Un calcul CITE, un chemin introuvable : signales, jamais accuses. Seule une
    # affirmation refutee entre dans `problems`, et elle porte sa preuve.
    from .verify.claims import verifier as verifier_la_prose

    for document in documents:
        try:
            texte = document.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(texte) > 500_000:
            continue
        if _corpus_volontaire(texte):
            corpus_volontaire.append(document)
            continue
        rapport = verifier_la_prose(texte, racine=root if root.is_dir() else root.parent)
        if not rapport.verifications:
            unverifiable.append(document)
            continue
        with_rules += 1
        checked += rapport.verifiees + rapport.refutees
        for verification in rapport.bloquantes:
            problems.append((document, verification.affirmation.genre.value.upper(),
                             verification.message[:200]))
        for verification in rapport.verifications:
            if not verification.ok and not verification.bloquant:
                reserves.append((document, verification.affirmation.genre.value.upper(),
                                 verification.message[:120]))

    # --- coherence des imports internes (aucune execution, deterministe) ----- #
    import_problems: list[tuple[Path, str, str]] = []
    if args.check_imports and len(files) > 1:
        from .verify.imports import check_project

        scan_root = root if root.is_dir() else root.parent
        try:
            for prob in check_project(files, scan_root):
                import_problems.append((prob.path, "IMPORT", prob.message))

        except Exception as exc:  # une analyse qui echoue ne doit pas tuer le scan
            import_problems.append((root, "IMPORT", f"analyse impossible : {exc}"[:120]))
    problems.extend(import_problems)

    # --- analyseurs standards du metier ------------------------------------- #
    # Regle de travail : quand quelqu'un a deja resolu le probleme proprement, on
    # utilise sa solution. Ruff/Flake8/Pyflakes sont l'etat de l'art pour reperer
    # les erreurs reelles en Python ; les reecrire serait du gaspillage. Chaque
    # constat nomme son outil : c'est une preuve verifiable, pas une affirmation.
    linter_note = ""
    linter_tool = ""
    if args.check_linters and files:
        from .verify.linters import analyse as linter_analyse

        report = linter_analyse(
            files, root=root if root.is_dir() else root.parent,
            timeout=max(args.timeout * 10, 120),
            prefer=str_env("JIO_LINTERS", "auto"),
        )
        linter_tool, linter_note = report.tool, report.note
        broken = {path for path, rule, _ in problems if rule == "SYNTAXE"}
        for finding in report.findings:
            target = finding.path if (root / finding.path).exists() else root.parent / finding.path
            if finding.path in broken or target in broken:
                continue  # deja signale comme incompilable : pas de doublon
            problems.append((target if target.exists() else finding.path,
                             finding.rule, finding.label[:160]))
        if report.truncated:
            linter_note = (linter_note + " " if linter_note else "") + (
                f"{report.truncated} constat(s) au-dela du plafond d'affichage"
            )

    print()
    print(f"  SCAN  {root}  ·  {len(files)} fichier(s) Python  ·  "
          f"{len(documents)} document(s)  ·  {checked} verification(s)")
    if ignores:
        print(f"  dossiers ignores : {', '.join(ignores)}"
              "   (--tout pour les inclure)")
    if corpus_volontaire:
        print(f"  corpus de fautes VOLONTAIRES : {len(corpus_volontaire)} fichier(s) "
              f"exclu(s) sur leur propre declaration ({MARQUEUR_CORPUS})")
    print()
    if problems:
        print(f"  {len(problems)} PROBLEME(S) — avec la preuve :")
        print()
        by_file: dict[Path, list[tuple[str, str]]] = {}
        for path, rule, detail in problems:
            by_file.setdefault(path, []).append((rule, detail))
        for path in sorted(by_file, key=lambda p: (-len(by_file[p]), str(p))):
            print(f"    {path}")
            for rule, detail in by_file[path]:
                print(f"        [{rule}] {detail}")
        print()
    else:
        print("  Aucun probleme sur les regles verifiables.")
        print()

    if environment:
        print(f"  {len(environment)} FICHIER(S) NON TESTABLE(S) ICI — ce n'est PAS un defaut :")
        for path, rule, detail in environment[:6]:
            print(f"    {path.name} [{rule}] {detail[:100]}")
        if len(environment) > 6:
            print(f"    ... et {len(environment) - 6} autre(s)")
        print("    cause : l'environnement est incomplet (dependance generee, paquet non")
        print("    installe). Installer le projet puis relancer donnerait un vrai verdict.")
        print()

    if reserves:
        print(f"  {len(reserves)} RESERVE(S) (suspect, non prouve — jamais un verdict) :")
        for path, rule, why in reserves[:10]:
            print(f"    {path.name} [{rule}] {why}")
        if len(reserves) > 10:
            print(f"    ... et {len(reserves) - 10} autre(s)")
        print("    une reserve n'est pas une accusation : c'est ce que ces regles-la ne")
        print("    savent pas trancher. Elle ne fait jamais echouer le scan.")
        print()

    if partial:
        if args.verbose:
            print(f"  {len(partial)} FICHIER(S) A AUDIT PARTIEL — ce qui reste NON verifie :")
            for path in list(partial)[:8]:
                print(f"    {path.name}")
                for limit in partial[path][:5]:
                    print(f"        · {limit[:150]}")
            if len(partial) > 8:
                print(f"    ... et {len(partial) - 8} autre(s) — jio scan -v pour tout voir")
        else:
            worst = sorted(partial.items(), key=lambda kv: -len(kv[1]))[:3]
            print(f"  {len(partial)} fichier(s) a audit PARTIEL (limites declarees) :")
            for path, limits in worst:
                print(f"    {path.name} : {limits[0][:110]}")
            print("    relancer avec -v pour la liste complete. Un audit partiel n'est pas")
            print("    un audit complet : ces limites sont declarees, jamais presumees.")
        print()

    if unverifiable and args.verbose:
        print(f"  {len(unverifiable)} fichier(s) sans regle executable :")
        for path in unverifiable[:20]:
            print(f"    {path}")
        print()

    remembered = 0
    if problems and not args.no_learn:
        from .learn import FailureMemory

        memory = FailureMemory(path=Path(args.state) / "failures.jsonl")
        for path, rule, detail in problems:
            try:
                memory.record(
                    objective=f"corriger {path.name}",
                    symptom=f"[{rule}] {detail}",
                    root_cause=f"defaut detecte par le scan dans {path}",
                    correct_fix="non encore applique",
                    guard=f"jio scan {root} : la regle {rule} de {path.name}",
                    mission_id=f"scan:{path.name}",
                )
                remembered += 1
            except Exception:  # une memoire defaillante ne casse pas le scan
                break

    if linter_tool:
        print(f"    analyseurs standards : {linter_tool} (regles de vrais bugs, sans style)")
    elif linter_note:
        print(f"    analyseurs standards : {linter_note}")
    print(f"    {with_rules} fichier(s) verifiable(s) · {len(unverifiable)} sans regle"
          f" · {len(environment)} non testable(s) ici · {len(reserves)} reserve(s)"
          f" · {len(partial)} a audit partiel")
    if remembered:
        print(f"    {remembered} probleme(s) memorise(s) : la prochaine execution saura quoi")
        print(f"    eviter, et pourquoi. Consulter : jio memory --state {args.state}")
    print("    Lecture du resultat : code 0 = rien trouve ; code 1 = au moins un defaut")
    print("    reel avec sa preuve. Un fichier sans regle executable n'est PAS un")
    print("    fichier correct : c'est un fichier que ces regles-la ne savent pas juger.")

    # --- mode strict : une porte de CI n'a pas les memes exigences qu'un humain ----- #
    # `.pre-commit-hooks.yaml` annoncait `jio-scan-strict` comme « echoue aussi si le
    # projet est incoherent a l'import » — avec exactement la MEME commande que le hook
    # normal. Une promesse sans implementation est un artefact qui ment sur lui-meme, et
    # c'est precisement ce que ce projet traque ailleurs. Le mode existe maintenant, et il
    # couvre ce qui etait deja affiche sans jamais faire echouer : les RESERVES (une regle
    # n'a pas su trancher) et les fichiers NON TESTABLES (import incoherent, analyse
    # impossible). Le mode normal les montre ; le mode strict refuse de les laisser passer.
    if getattr(args, "strict", False):
        print()
        print("  MODE STRICT — les reserves et les fichiers non testables font echouer.")
        bloquants = len(reserves) + len(environment)
        if bloquants == 0:
            print("    -> 0 reserve, 0 non testable : la porte est franchie.")
        else:
            print(f"    -> {len(reserves)} reserve(s) et {len(environment)} fichier(s) non "
                  "testable(s) : a instruire.")
            print("       Une reserve n'est pas une accusation, mais elle n'est pas un quitus")
            print("       non plus : en CI, elle doit etre levee ou declaree.")
        print()
        return 1 if (problems or reserves or environment) else 0
    print()
    return 1 if problems else 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import TOOLS, main as mcp_main

    if getattr(args, "prove", None) is not None:
        from .artifacts.wiring import _COMMANDE, prouver_branchement

        print(BANNER)
        print("  PREUVE DU BRANCHEMENT MCP  ·  le serveur est demarre et interroge")
        print()
        # Une commande passee en argument est decoupee naivement : c'est un diagnostic
        # local, pas une execution de contenu non fiable.
        commande = tuple(args.prove.split()) if args.prove else _COMMANDE
        print(prouver_branchement(commande))
        print()
        print("  Une configuration correcte qui ne branche RIEN est le defaut que cette")
        print("  sonde existe pour attraper : `python3` peut exister sans `jio`.")
        print()
        return 0

    if args.list:
        print()
        print("  SERVEUR MCP JIO  ·  transport stdio, JSON-RPC 2.0, zero dependance")
        print()
        for tool in TOOLS:
            print(f"    {tool['name']:<14} {tool['description'][:80]}")
        print()
        print("  Configuration : `jio artifacts --mcp <dialecte>` pour opencode, Hermes,")
        print("  Codex, Claude Code ou Cursor ; `jio artifacts --target mcp --write` pour")
        print("  `.mcp.json` (dialecte de Claude Code, lu aussi par Cursor).")
        print("  Preuve du cablage : `jio mcp --prove`. Securite : chemins confines a JIO_ROOT.")
        print()
        return 0
    return mcp_main()


def cmd_trace(args: argparse.Namespace) -> int:
    """Rejoue et verifie un journal — meme sans indiquer lequel.

    `jio trace` sans argument echouait : il fallait connaitre le chemin exact du
    journal pour savoir ce qui s'etait passe. Exiger de connaitre la reponse pour
    poser la question est une mauvaise interface. On cherche donc le journal, du
    plus recent au plus ancien, et on dit clairement quoi faire s'il n'y en a pas.
    """
    path = Path(args.journal) if args.journal else Path(
        str_env("JIO_JOURNAL", ".jio/journal.jsonl")
    )
    if not path.exists():
        candidates = sorted(
            (p for p in Path(".jio").rglob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            path = candidates[0]
        else:
            print()
            print("  Aucun journal pour l'instant : rien n'a encore ete execute.")
            print("  Un journal se cree a la premiere mission :")
            print("      jio run \"corriger la somme des pairs\" --task sum_even --simulate")
            print("  Chaque evenement est chaine par hachage : rejouer ne peut pas")
            print("  mentir, et `jio trace` verifie cette chaine.")
            print()
            return 0
    journal = Journal.from_jsonl(path.read_text(encoding="utf-8"))
    ok, bad = journal.verify_chain()
    summary = journal.summary()

    print()
    print(f"  JOURNAL  {path}")
    print(f"  {summary['events']} evenements  ·  chaine {'INTEGRE' if ok else f'CASSEE @ {bad}'}")
    print(f"  tete : {journal.head}")
    print()
    for ev in journal:
        if args.kind and ev.kind != args.kind:
            continue
        # Le sceau est deja lu juste au-dessus, sous une forme lisible : le repeter ici
        # noierait l'evenement lui-meme sous 130 caracteres de hachage.
        corps = {cle: valeur for cle, valeur in ev.payload.items() if cle != "monde"}
        payload = json.dumps(corps, ensure_ascii=False, default=str) if corps else "{}"
        print(f"    {ev.seq:>4}  {ev.kind:<14} {ev.trust.value:<9} {payload[:110]}")
    print()

    # Le journal prouve que rien n'a ete altere. Il ne prouve pas que le monde n'a pas
    # change : c'est le role du sceau porte par chaque evenement.
    mondes = journal.mondes()
    courant = journal._sceau_du_moment()  # noqa: SLF001 - meme mesure, meme module
    print(f"  MONDE : {len(mondes)} etat(s) distinct(s) dans ce journal")
    for entree in mondes:
        marque = "  (etat actuel)" if entree["sceau"] == courant["sceau"] else ""
        revision = f"  revision {entree['revision'][:9]}" if entree["revision"] else ""
        print(f"    sceau {entree['sceau'][:12] or '(absent)'}{revision}"
              f"  ·  {len(entree['evenements'])} evenement(s){marque}")
    if len(mondes) > 1:
        print()
        print("    ATTENTION : le monde a change PENDANT cette mission. Une conclusion peut")
        print("    s'appuyer sur des observations faites sur deux etats differents — il faut")
        print("    la relire avant de l'utiliser comme preuve.")
    elif mondes and courant["sceau"] and mondes[0]["sceau"] != courant["sceau"]:
        print()
        print("    Ces preuves portent sur un etat ANTERIEUR du depot : le contenu a change")
        print("    depuis. Elles restent valides pour ce qu'elles decrivent, pas pour l'etat")
        print("    actuel. Pour comparer a coup sur : `jio doctor` puis `jio recover`.")
    print()

    report = IntegrityMonitor().audit(journal)
    print(f"  INTEGRITE : {'propre' if report.clean else 'ANOMALIES'}")
    for e in report.exploits:
        print(f"    - {e.kind.value} @ {e.step}: {e.detail[:100]}")
    print()
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# Aides de banc
# --------------------------------------------------------------------------- #


def _msg(objective: str):
    from .providers.base import Message

    return Message("user", f"OBJECTIVE:\n{objective}\n\nReturn the implementation.")


def _code(text: str, entrypoint: str) -> str:
    from .loop.engine import _extract_code

    return _extract_code(text, entrypoint)


def _check(source: str, task: Task) -> bool:
    """Oracle cache : execute le code du candidat contre les tests de la tache."""
    if not source.strip():
        return False
    sandbox = Sandbox(timeout=15)
    program = source + "\n\n" + "\n".join(task.checks[k] for k in task.checks)
    return sandbox.run_python(program, tag="oracle").ok


def _wilson(echantillon: Sequence[float]) -> tuple[float, float]:
    """Intervalle de confiance a 95 % d'un taux observe (voir `jio.bench.incertitude`)."""
    from .bench.incertitude import intervalle_wilson

    succes = sum(1 for valeur in echantillon if valeur >= 1.0)
    return intervalle_wilson(succes, len(echantillon))


def _ecart(
    gauche: Sequence[float], droite: Sequence[float]
) -> tuple[float, tuple[float, float], bool]:
    """Ecart en points, son intervalle, et s'il exclut zero (donc s'il est significatif)."""
    from .bench.incertitude import ecart_a_la_une

    return ecart_a_la_une(gauche, droite)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# --------------------------------------------------------------------------- #
# Entree
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jio",
        description="JIOJIO-TERMINATOR — noyau anti-erreur pour agents d'IA.",
    )
    p.add_argument("--version", action="version", version=f"jio {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("doctor", help="etat du systeme").set_defaults(func=cmd_doctor)
    sub.add_parser("tasks", help="liste le banc d'essai").set_defaults(func=cmd_tasks)
    p_rec = sub.add_parser(
        "recover", help="restaure l'historique d'un depot reinitialise, sans rien detruire"
    )
    p_rec.add_argument("--root", default=".", help="racine du depot (defaut : dossier courant)")
    p_rec.add_argument("--remote", default="origin", help="depot distant (defaut : origin)")
    p_rec.add_argument("--branch", default="", help="branche a recuperer (defaut : la courante)")
    p_rec.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="montrer ce qui serait fait, sans rien faire",
    )
    p_rec.set_defaults(func=cmd_recover)

    p_chiffres = sub.add_parser(
        "chiffres",
        help="verifier (et reparer) les chiffres annonces dans la documentation",
    )
    p_chiffres.add_argument("fichiers", nargs="*", help="fichiers a verifier (defaut : README.md)")
    p_chiffres.add_argument("--root", default=".", help="racine (defaut : dossier courant)")
    p_chiffres.add_argument(
        "--appliquer", action="store_true",
        help="ecrire les valeurs mesurees (une sauvegarde .avant-jio est creee)",
    )
    p_chiffres.set_defaults(func=cmd_chiffres)

    p_sync = sub.add_parser(
        "sync", help="propage le cerveau anti-erreur : artefacts natifs + MCP"
    )
    p_sync.add_argument(
        "--root", default=".", help="racine a equiper (defaut : dossier courant)"
    )
    p_sync.add_argument(
        "--mcp", default=None, help="ne brancher qu'un seul outil (defaut : tous)"
    )
    p_sync.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="montrer ce qui serait ecrit, sans rien ecrire",
    )
    p_sync.set_defaults(func=cmd_sync)

    sub.add_parser("version", help="version").set_defaults(
        func=lambda a: (print(f"jio {__version__}") or 0)
    )

    b = sub.add_parser("bench", help="mesure le gain du harness (S0 -> S3)")
    b.add_argument("--skill", type=float, default=0.35, help="competence du modele simule")
    b.add_argument("--runs", type=int, default=5, help="nombre de tirages par tache")
    b.add_argument(
        "--provider", default="simule",
        help=(
            "QUEL modele mesure. `simule` (defaut, sans cle), `cli:opencode`, `cli:hermes`, "
            "`cli:claude`, `cli:codex`, `cli:gemini`, `cli:<autre>` (avec "
            "JIO_CLI_<AUTRE>_ARGV), ou `openai:<modele>`. Un modele demande et "
            "indisponible ARRETE la mesure : aucun repli silencieux."
        ),
    )
    b.add_argument("--rounds", type=int, default=int_env("JIO_MAX_ROUNDS", 4),
                   help="tours de boucle maximum")
    b.add_argument("--prose", action="store_true",
                   help="mesure le harness sur des DOCUMENTS (rapports) au lieu de code")
    b.set_defaults(func=cmd_bench)

    cl = sub.add_parser(
        "claims", help="verifie les affirmations d'un document (calculs, code, chemins)")
    cl.add_argument(
        "fichier", nargs="+",
        help="document(s) a verifier (.md, .rst, .txt, ...) — pre-commit en passe plusieurs",
    )
    cl.add_argument("--racine", default="", help="racine des chemins cites")
    cl.add_argument(
        "--hook",
        action="store_true",
        help=(
            "mode pre-commit : n'echoue QUE sur une affirmation refutee. "
            "« rien a verifier » ne bloque pas un commit."
        ),
    )
    cl.set_defaults(func=cmd_claims)
    cl.epilog = ("codes de sortie : 0 conforme · 1 affirmation refutee · "
                 "3 rien a verifier (ni succes, ni echec)")

    prov = sub.add_parser(
        "providers", help="liste les fournisseurs, et les SONDE avec --prove")
    prov.add_argument(
        "--prove", action="store_true",
        help="envoie une requete reelle a chaque fournisseur et mesure sa capacite a "
             "traduire les regles en temoins executables (sans quoi la preuve est "
             "impossible hors banc d'essai)",
    )
    prov.set_defaults(func=cmd_providers)

    r = sub.add_parser("run", help="execute une mission complete")
    # `objective` devient FACULTATIF : en simulation (`--simulate`), une tache du
    # banc fournit l'objectif, et exiger une repetition inutile faisait echouer des
    # commandes que la documentation proposait elle-meme. Le refus reste explicite,
    # plus bas, quand rien ne peut fournir l'objectif.
    r.add_argument("objective", nargs="?", default="", help="objectif de la mission")
    r.add_argument("--prose", action="store_true",
                   help="mission de DOCUMENT : la preuve porte sur les affirmations "
                        "verifiables du texte (calculs, blocs de code, chemins cites)")
    r.add_argument("--entrypoint", default="", help="nom de la fonction attendue")
    r.add_argument("--simulate", action="store_true",
                   help="modele simule deterministe : aucune cle API requise")
    r.add_argument("--task", default="", help="id de tache du banc (oracles + specification)")
    r.add_argument(
        "--provider", action="append", default=[],
        help=(
            "QUEL modele travaille : `cli:opencode`, `cli:hermes`, `cli:<autre>` (avec "
            "JIO_CLI_<AUTRE>_ARGV) ou `openai:<modele>`. REPETABLE : nommer DEUX modeles "
            "differents donne un panel reellement decorrele, donc un consensus qui vaut "
            "quelque chose. Par defaut, tous ceux qui sont detectes. Un modele nomme et "
            "indisponible ARRETE la mission."
        ),
    )
    r.add_argument("--state", default=str_env("JIO_STATE", ".jio"),
                   help="dossier d'etat (memoire + routeur)")
    r.add_argument("--min-panel", dest="min_panel", type=int,
                   default=int_env("JIO_MIN_PANEL", 3),
                   help="taille minimale du panel pour conclure (defaut 3 : n >= 3f+1). "
                        "En dessous, aucune livraison complete n'est possible — le "
                        "systeme le dit au lieu de bruler des appels.")
    r.add_argument("--no-learn", dest="no_learn", action="store_true",
                   help="desactiver memoire et routeur pour cette execution")
    r.add_argument("--rounds", type=int, default=int_env("JIO_MAX_ROUNDS", 5))
    r.add_argument("--alpha", type=float, default=float_env("JIO_ALPHA", 0.05),
                   help="risque d'erreur accepte")
    r.add_argument("--journal", default=str_env("JIO_JOURNAL", ".jio/journal.jsonl"))
    r.add_argument("--json", default="", help="ecrit le rapport JSON a ce chemin")
    r.add_argument(
        "--no-oracle", dest="no_oracle", action="store_true",
        help="retirer les tests fournis par la mission et PROUVER a partir des seules "
             "regles, traduites en temoins executables — exactement ce qu'une mission "
             "reelle impose. Un temoin ecrit par un modele ne peut jamais, a lui seul, "
             "faire rejeter un candidat ; une regle non prouvee interdit la mention "
             "« livre sans reserve ».",
    )
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("audit", help="audite un artefact contre une specification")
    a.add_argument("--racine", default="",
                   help="document : racine ou chercher les chemins cites")
    a.add_argument("file")
    a.add_argument("--task", default="", help="id de tache du banc pour les oracles")
    a.add_argument("--entrypoint", default="", help="fonction a auditer (sinon la premiere)")
    a.set_defaults(func=cmd_audit)

    sc = sub.add_parser("scan", help="audite un projet entier et n'affiche que les problemes")
    sc.add_argument(
        "--strict",
        action="store_true",
        help="echoue aussi sur les RESERVES et les fichiers non testables (mode CI)",
    )
    sc.add_argument("--tout", action="store_true",
                    help="balayer AUSSI les dossiers habituellement ignores "
                         "(environnements virtuels, caches, dependances)")
    sc.add_argument("path", help="fichier ou repertoire")
    sc.add_argument("--exclude-tests", action="store_true",
                    help="ignorer test_*.py, conftest.py et les dossiers tests/")
    sc.add_argument("--timeout", type=int, default=int_env("JIO_SCAN_TIMEOUT", 20),
                    help="timeout par verification (s)")
    sc.add_argument("-v", "--verbose", action="store_true",
                    help="lister aussi les fichiers non verifiables")
    sc.add_argument("--no-imports", dest="check_imports", action="store_false",
                    help="ne pas verifier la coherence des imports internes")
    sc.add_argument("--no-linters", dest="check_linters", action="store_false",
                    help="ne pas utiliser les analyseurs standards (ruff/flake8/pyflakes)")
    sc.add_argument("--state", default=str_env("JIO_STATE", ".jio"),
                    help="dossier d'etat (memoire des echecs)")
    sc.add_argument("--no-learn", dest="no_learn", action="store_true",
                    help="ne rien memoriser")
    sc.set_defaults(func=cmd_scan, check_imports=True, check_linters=True)

    t = sub.add_parser("trace", help="rejoue et verifie un journal")
    t.add_argument("journal", nargs="?", default="",
                   help="chemin du journal (defaut : le plus recent trouve)")
    t.add_argument("--kind", default="", help="filtre par type d'evenement")
    t.set_defaults(func=cmd_trace)

    ar = sub.add_parser("artifacts", help="genere les artefacts natifs de tous les outils")
    ar.add_argument("--root", default=".", help="repertoire de destination")
    ar.add_argument(
        "--target",
        action="append",
        default=[],
        help=(
            "cible : opencode, hermes, claude, agents, gemini, cursor, copilot, mcp, "
            "opencode-mcp, hermes-mcp"
        ),
    )
    ar.add_argument("--write", action="store_true", help="ecrit reellement les fichiers")
    # Ce que la configuration COUTE, en jetons de contexte. Un fichier trop long est
    # survole par le modele : il occupe la fenetre sans rien apporter.
    ar.add_argument(
        "--budget",
        action="store_true",
        help="mesure le cout en contexte des artefacts (demarrage vs a la demande)",
    )
    # Le CABLAGE du serveur MCP, distinct de son emission : `.mcp.json` est le dialecte de
    # Claude Code, opencode lit `opencode.json`, Hermes lit `~/.hermes/config.yaml`. Sans
    # cette option, les outils JIO existaient et restaient injoignables depuis deux des
    # trois outils nommes par l'utilisateur.
    ar.add_argument(
        "--mcp",
        metavar="DIALECTE",
        help=(
            "branche le serveur MCP : opencode, hermes, codex, claude-code, cursor, "
            "ou `liste` pour tout afficher"
        ),
    )
    ar.add_argument(
        "--dry-run",
        action="store_true",
        help="avec --mcp liste : affiche aussi le contenu des fragments",
    )
    ar.set_defaults(func=cmd_artifacts)

    mc = sub.add_parser("mcp", help="serveur MCP (stdio) ou liste des outils")
    mc.add_argument("--list", action="store_true", help="affiche les outils exposes")
    # Prouver le BRANCHEMENT, pas le serveur : la commande ecrite dans une configuration
    # peut exister et ne rien trouver (interpreteur sans `jio`). On lui parle vraiment.
    mc.add_argument(
        "--prove",
        nargs="?",
        const="",
        metavar="COMMANDE",
        help="demarre le serveur MCP et compte les outils qu'il sert (preuve du cablage)",
    )
    mc.set_defaults(func=cmd_mcp)

    tr = sub.add_parser("trust", help="routeur de confiance : combien de verification depenser")
    tr.add_argument("objective", nargs="?", default="", help="objectif a router")
    tr.add_argument("--state", default=".jio/trust.json", help="etat persistant")
    tr.set_defaults(func=cmd_trust)

    me = sub.add_parser("memory", help="memoire des echecs (rappel, ajout, integrite)")
    me.add_argument("--state", default=".jio/failures.jsonl", help="journal de memoire")
    me.add_argument("--recall", default="", help="objectif pour rappeler les souvenirs")
    me.add_argument("--add", action="store_true", help="enregistre un echec")
    me.add_argument("--objective", default="", help="objectif concerne")
    me.add_argument("--symptom", default="", help="ce qui a ete observe")
    me.add_argument("--cause", default="", help="cause reelle")
    me.add_argument("--wrong-fix", default="", help="piste tentee sans succes")
    me.add_argument("--fix", default="", help="correctif retenu")
    me.add_argument("--guard", default="", help="controle qui echoue si l'erreur revient (obligatoire)")
    me.set_defaults(func=cmd_memory)

    le = sub.add_parser("learn", help="mesure le gain de l'auto-amelioration (A/B)")
    le.add_argument("--skill", type=float, default=0.20, help="competence du modele simule")
    le.add_argument("--runs", type=int, default=3, help="tirages par tache et par phase")
    le.add_argument("--rounds", type=int, default=int_env("JIO_MAX_ROUNDS", 4),
                    help="tours de boucle maximum")
    le.set_defaults(func=cmd_learn)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        print(BANNER)
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
