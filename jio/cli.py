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

from typing import Any, Mapping, Sequence

from .core.env import bool_env, float_env, int_env, str_env
from .verify.claims import RapportProse

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
from .clarify import MAX_QUESTIONS

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


def couleur_activee(flux: object | None = None) -> bool:
    """Faut-il ecrire des sequences ANSI dans `flux` ?

    DEFAUT MESURE ET CORRIGE. `render_report` peignait sa sortie par defaut, sans regarder OU
    elle allait : `jio run > rapport.txt` ecrivait donc sept sequences d'echappement dans un
    fichier, et un journal de CI les affichait en clair. Une couleur est une commodite de
    TERMINAL ; ailleurs, c'est du bruit qui pollue les fichiers, casse les comparaisons de
    texte et se retrouve colle dans un ticket.

    Trois regles, dans cet ordre — les deux premieres sont des CONVENTIONS, pas des inventions :

      * `NO_COLOR`, present et non vide (https://no-color.org) : plus une seule sequence.
        C'est le standard que les outils respectent, et un test l'exige ici ;
      * `JIO_NO_COLOR`, notre nom a nous, pour couper les couleurs sans toucher a `NO_COLOR`
        du reste de la machine ;
      * `TERM=dumb` : le terminal annonce qu'il ne sait rien afficher ;
      * sinon, la sortie doit etre un TERMINAL. Un tube ou un fichier n'en est pas un.

    L'ordre compte : une variable d'environnement explicite gagne toujours sur la deduction.
    """
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("JIO_NO_COLOR", "").strip():
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    cible = flux if flux is not None else sys.stdout
    try:
        return bool(cible.isatty())
    except (AttributeError, ValueError):
        # Un flux sans `isatty`, ou ferme : on ne peint pas.
        return False


def _c(text: str, key: str, enabled: bool | None = None) -> str:
    """Colore `text` — par defaut seulement si la sortie est un terminal (voir `couleur_activee`)."""
    if enabled is None:
        enabled = couleur_activee()
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
    competences: bool = True,
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
        skills=_injecteur_de_competences(competences),
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


def _injecteur_de_competences(actif: bool):
    """Le routeur de procedures, ou `None` quand l'utilisateur l'a desactive.

    Rend un objet exposant `bloc(objectif)` — l'interface lue par `Engine._prompt`. On importe
    le module ICI et pas en tete de fichier : `jio/skills` lit les definitions des competences,
    et faire dependre l'analyseur de toute la chaine d'artefacts rendrait `jio --help` plus
    fragile qu'il ne doit l'etre.
    """
    if not actif:
        return None
    from .skills.injection import bloc as bloc_de_competences

    class _Injecteur:
        """Une seule methode, l'interface exacte du moteur : rien de plus a comprendre."""

        @staticmethod
        def bloc(objectif: str):
            return bloc_de_competences(objectif)

    return _Injecteur()


def _real_engine(
    *, journal_path: Path | None = None, max_rounds: int = 5, min_panel: int = 3,
    famille: str = "code", racine: Path | None = None, fournisseur: object | None = None,
    fournisseurs: object | None = None, competences: bool = True,
) -> Engine:
    """Assemble un moteur adosse aux CLI/API reellement disponibles.

    `fournisseur` : quand l'utilisateur a NOMME son modele (`--provider cli:opencode`),
    on l'utilise lui, et pas « tout ce qui a ete detecte ». La difference compte : un
    poste peut avoir plusieurs CLI installes, et le panel mesurait alors un melange dont
    personne ne peut dire ce qu'il vaut. Nommer son modele, c'est mesurer LE SIEN.
    """
    from .audit.panel import DEFAULT_PERSONAS, AuditPanel
    from .core.codes import INDETERMINE
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
        # INDETERMINE, PAS 0. Ce chemin s'annoncait « Aucun fournisseur detecte » et sortait en
        # 0 (voir `codes.sortir`) : un agent qui enchaine lit un 0 comme « c'est fait, et
        # prouve ». Or rien n'a ete fait, et ce qui manque a un nom — un fournisseur.
        for message in (
            "Aucun fournisseur detecte.",
            "Installez un CLI (opencode, hermes, claude, codex, gemini, aider) ou definissez",
            "une variable d'environnement d'API (OPENROUTER_API_KEY, OPENAI_API_KEY...).",
            "",
            "Sans cle, deux chemins existent DEJA, et ils ne demandent rien :",
            "  jio bench                                  mesure du harness sur son banc",
            "  jio run \"<objectif>\" --simulate --task sum_even --no-oracle",
            "                                             mission reelle du banc, sans modele",
        ):
            print(f"  {message}" if message else "", file=sys.stderr)
        raise SystemExit(INDETERMINE)
    gens = providers[:3]
    if famille == "prose":
        from .verify.prose_prover import ProseProver

        prover: object = ProseProver(racine=racine or Path.cwd())
    else:
        prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    return Engine(
        generators=gens,
        skills=_injecteur_de_competences(competences),
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


def render_report(
    report: MissionReport, *, verbose: bool = False, color: bool | None = None
) -> str:
    """Synthese + preuves, en francais. Details via `jio trace`.

    `color=None` (le defaut) interroge `couleur_activee()` : la couleur suit la SORTIE reelle
    au lieu d'etre supposee. Les appelants qui veulent forcer l'un ou l'autre passent `True` ou
    `False`, ce que font les tests — et c'est la seule facon d'ecrire un test de couleur qui ne
    depend pas du terminal qui l'execute.
    """
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
    # Sans `--root`, `doctor` ne savait diagnostiquer que le depot COURANT : toutes les
    # autres commandes (`recover`, `scan`, `claims`, `sync`...) acceptent `--root`, et un
    # script qui enchaine « diagnostic puis reparation » sur plusieurs depots devait
    # changer de dossier entre les deux. Une option manquante n'est pas un detail :
    # `jio doctor --root <chemin>` sortait en 2, en refusant l'argument.
    racine = getattr(args, "root", ".") or "."
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
    suspect = _depot_suspect(racine)
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

    etat = _git_state(racine)
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


def _git_state(racine: str = ".") -> tuple[str, int, int, bool, bool] | None:
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
            # `--root` permet de viser un AUTRE depot sans changer de dossier : c'est ce
            # qui rend possible un script « diagnostic puis reparation » sur plusieurs
            # depots, `doctor` et `recover` acceptant alors le meme argument.
            proc = subprocess.run(
                ["git", *argv], capture_output=True, text=True, timeout=10, cwd=racine,
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


def _depot_suspect(racine: str = ".") -> tuple[int, int] | None:
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
            proc = subprocess.run(
                ["git", *argv], capture_output=True, text=True, timeout=10, cwd=racine
            )
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


class _Progression:
    """Dit OU EN EST une mesure longue, sur la sortie d'erreur, pendant qu'elle tourne.

    Pourquoi ce n'est pas du confort : `jio bench` dure quatre minutes et demie sur une machine
    a deux coeurs, `jio ablation` davantage. Sans une ligne reguliere, la commande est
    INDISTINGUABLE d'une commande bloquee — et la seule reaction possible est de l'interrompre,
    c'est-a-dire de ne jamais obtenir la mesure. Un outil qui cache son progres cache aussi son
    echec : les deux se ressemblent.

    Trois choix, chacun pour une raison :

      * sur la SORTIE D'ERREUR, jamais sur la sortie standard : le rapport reste une sortie
        propre, redirigeable et comparable entre deux executions ;
      * immediatement vide (flush), sinon la ligne arrive avec le rapport — c'est-a-dire trop
        tard ;
      * une ligne par unite, avec l'avancement, le libelle et le TEMPS ECOULE : c'est le temps
        ecoule qui permet de decider s'il faut attendre ou interrompre.
    """

    def __init__(self, total: int, *, quoi: str, flux: Any = None) -> None:
        self.total = max(1, total)
        self.fait = 0
        self.quoi = quoi
        self.debut = time.monotonic()
        self.flux = flux if flux is not None else sys.stderr

    def __call__(self, libelle: str = "") -> None:
        self.fait += 1
        ecoule = time.monotonic() - self.debut
        reste = (ecoule / self.fait) * (self.total - self.fait) if self.fait else 0.0
        suite = f"  ·  reste ~{_duree(reste)}" if 0 < self.fait < self.total else ""
        print(
            f"  [{self.fait:>3}/{self.total}] {self.quoi}"
            + (f" · {libelle}" if libelle else "")
            + f"  ·  {_duree(ecoule)} ecoulees{suite}",
            file=self.flux, flush=True,
        )


def _duree(secondes: float) -> str:
    """Une duree lisible : `12s`, `4m26s`. Les dixiemes ne servent a rien pour ATTENDRE."""
    total = int(max(0.0, secondes))
    minutes, reste = divmod(total, 60)
    return f"{minutes}m{reste:02d}s" if minutes else f"{reste}s"


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
    # `--taches` : borner le banc. Deux raisons, et la seconde n'est pas cosmetique : un premier
    # tour rapide pour voir si le dispositif tourne, et la possibilite de TESTER le banc lui-meme
    # en quelques secondes. Un banc qu'on ne peut pas lancer en test est un banc dont personne ne
    # verifie le branchement avant qu'il ne serve.
    demandees = int(getattr(args, "taches", 0) or 0)
    taches = TASKS[:demandees] if demandees > 0 else TASKS
    # `--sans-oracle-reel` : le bras « aucune mission reelle ne fournit de test » coute un
    # moteur complet de plus par tirage. Il est ACTIF par defaut parce que c'est le seul
    # bras qui parle d'une mission reelle ; l'ecarter doit rester possible, et visible.
    oracle_reel = not bool(getattr(args, "sans_oracle_reel", False))

    print(BANNER)
    if modele.genre == "simule":
        print(f"  Mesure du harness  ·  competence simulee {skill:.2f}  ·  {runs} tirage(s)  ·"
              f"  {len(taches)} taches")
        print("  Aucune cle API requise : les reponses sont simulees, la VERIFICATION est reelle.")
    else:
        print(f"  Mesure du harness  ·  modele : {modele.spec}  ·  {runs} tirage(s)  ·"
              f"  {len(taches)} taches")
        print(f"  {modele.note}")
    print()

    results: dict[str, list[float]] = {
        "S0": [], "S1": [], "S1b": [], "S2": [], "S3": [], "S4": [], "S4b": [], "S4c": [],
        "S4r": [], "S4rc": [],
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
    avancer = _Progression(len(seeds) * len(taches), quoi=f"tirage {skill:.2f}")
    for seed in seeds:
        for task in taches:
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

            # --- S4r : AUCUN ORACLE, avec VOTRE modele comme traducteur ---- #
            # C'est le cas de TOUTE mission reelle : personne ne fournit de test. Le banc
            # refusait de mesurer cet axe des qu'un vrai modele etait branche, au motif
            # qu'« alors c'est votre modele qui traduit, et le chiffre ne correspondrait
            # plus a rien ». Le fait est exact, la conclusion ne l'etait pas : le couple
            # (votre modele, le harness) EST la question posee, et la seule chose qui
            # manquait pour rester interpretable etait le CONTROLE apparié — le meme
            # budget d'appels sans aucune verification. Les deux sont mesures ici.
            #
            # Ce bras laisse le moteur appeler le modele pour traduire les regles : c'est
            # `SpecCompiler(provider=reel)` qui le fait, sans rien de special ici. Si le
            # modele ne sait pas traduire, le moteur s'abstient — et l'abstention est un
            # resultat, pas un echec de la mesure.
            if modele.genre != "simule" and oracle_reel:
                moteur_sans_oracle = _simulated_engine(
                    task, skill=skill, seed=seed, max_rounds=args.rounds,
                    temoins=True, fournisseur=modele,
                )
                rapport_sans = moteur_sans_oracle.run(
                    Mission(objective=task.objective, id=f"{task.id}-{seed}-S4r",
                            max_rounds=args.rounds),
                    WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                             spec=task.spec()),
                )
                n_appels = int(rapport_sans.usage.get("calls", 0)) or 1
                juste = _check(rapport_sans.subject, task)
                if rapport_sans.status is MissionStatus.ABSTAINED:
                    abstentions_sans_oracle += 1
                elif not juste and rapport_sans.status is MissionStatus.DELIVERED:
                    # Aucun oracle fourni, et le modele a livre sans reserve un artefact
                    # que le banc sait faux : c'est ici que se mesure le risque, et c'est
                    # le seul chiffre qui doit rester a zero.
                    erreurs_silencieuses += 1

                # CONTROLE apparié : autant de tirages du modele, AUCUNE verification.
                aveugles = [
                    _code(
                        generators[i % 3].complete(
                            [_msg(task.objective)], seed=seed * 131 + i
                        ).text,
                        task.entrypoint,
                    )
                    for i in range(n_appels)
                ]
                results["S4r"].append(1.0 if juste else 0.0)
                calls["S4r"].append(n_appels)
                results["S4rc"].append(1.0 if any(_check(x, task) for x in aveugles) else 0.0)
                calls["S4rc"].append(n_appels)

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
                traducteur = TraducteurSimule(taches=taches, fidelite=fidelite)
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

            # Le point d'avancement est pose ICI, a la fin du tirage : le placer au debut
            # annoncerait un travail qui n'est pas encore fait, et une ligne qui avance sans
            # que rien ne se passe est pire que pas de ligne du tout.
            avancer(f"{task.id} graine {seed}")

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
        "S4r": "AUCUN ORACLE : VOS regles traduites par le modele",
        "S4rc": "CONTROLE sans oracle : meme budget, 0 verification",
    }
    base = _mean(results["S0"])
    print(f"    {'config':<40} {'reussite':>9} {'IC95':>15} {'appels':>7} {'vs S0':>7}")
    print(f"    {'-' * 40} {'-' * 9} {'-' * 15} {'-' * 7} {'-' * 7}")
    for key in ("S0", "S1", "S1b", "S2", "S3", "S4", "S4c", "S4b", "S4r", "S4rc"):
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
        print("  QUAND LA MISSION NE FOURNIT AUCUN ORACLE — le cas de toute mission reelle")
        print("    Ici, vos regles ne sont pas des slogans : le moteur demande a VOTRE")
        print("    modele de les traduire en temoins executables, et ne livre que ce qui")
        print("    passe ces temoins. Le controle juste en dessous a le MEME budget.")
        print()
        if results["S4r"]:
            s4r, s4rc = _mean(results["S4r"]), _mean(results["S4rc"])
            ic4r, ic4rc = _wilson(results["S4r"]), _wilson(results["S4rc"])
            delta_r, (bas_r, haut_r), tranche_r = _ecart(results["S4rc"], results["S4r"])
            cadre_r = f"[{ic4r[0]:.0%} ; {ic4r[1]:.0%}]"
            cadre_rc = f"[{ic4rc[0]:.0%} ; {ic4rc[1]:.0%}]"
            print(f"      {'votre modele + harness (sans oracle)':<40} {s4r:>8.1%} "
                  f"{cadre_r:>15} {_mean(calls['S4r']):>7.1f}")
            print(f"      {'CONTROLE : autant d appels, 0 verification':<40} {s4rc:>8.1%} "
                  f"{cadre_rc:>15} {_mean(calls['S4rc']):>7.1f}")
            print(f"      ecart {delta_r:+.1f} points  IC95 [{bas_r:+.1f} ; {haut_r:+.1f}]"
                  f"  {'-> l intervalle EXCLUT zero' if tranche_r else '-> INDETERMINE ici'}")
            print(f"    issues de ce bras : {abstentions_sans_oracle} abstention(s) — une")
            print("      abstention est une reponse : le moteur dit qu'il ne peut pas prouver.")
        else:
            print("    non mesure (`--sans-oracle-reel`) : le bras existe, il a ete ecarte.")
        print()
        print("    HONNETETE SUR CE BRAS : le traducteur EST votre modele, donc ce chiffre")
        print("    mesure le couple (votre modele, le harness) et pas le harness seul. C'est")
        print("    exactement la question utile, et le controle apparié la rend lisible.")
        print(f"    erreurs livrees SANS reserve : {erreurs_silencieuses}"
              "  <- le seul chiffre qui doit rester a zero")
        print(f"    duree : {elapsed:.1f}s")
        print()
        if getattr(args, "rapport", ""):
            _ecrire_rapport_du_bench(
                args, results, calls, labels, modele, skill, runs, len(taches), args.rounds,
                elapsed, integrite={
                    "exploits d'integrite detectes": integrity_hits,
                    "abstentions sans oracle": abstentions_sans_oracle,
                    "candidats CORRECTS rejetes": rejets_faux,
                    "ERREURS LIVREES SANS RESERVE": erreurs_silencieuses,
                },
            )
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
    if getattr(args, "rapport", ""):
        _ecrire_rapport_du_bench(
            args, results, calls, labels, modele, skill, runs, len(taches), args.rounds, elapsed,
            integrite={
                "exploits d'integrite detectes": integrity_hits,
                "abstentions sans oracle": abstentions_sans_oracle,
                "regles contrefaites par un traducteur faux": contrefacons,
                "candidats CORRECTS rejetes": rejets_faux,
                "ERREURS LIVREES SANS RESERVE": erreurs_silencieuses,
            },
        )
    return 0


def _ecrire_rapport_du_bench(
    args, results, calls, labels, modele, skill, runs, taches, rounds, elapsed, *,
    integrite=None, ecarts=(), hypotheses=(),
) -> None:
    """Ecrit le rapport du duel — la MEME mesure, sous une forme qui se garde.

    Ce helper ne mesure rien : il met en forme ce que `cmd_bench` vient de calculer, par les
    fonctions testees de `jio.bench.incertitude`. Deux implementations d'une mesure feraient
    deux verites possibles.
    """
    from .bench.incertitude import essais_necessaires as _essais
    from .bench.rapport import construire, ecrire

    def _commit_court() -> str:
        """Le commit mesure — un rapport sans lui ne se rattache a aucune version du harness.

        Si git est absent ou le depot non initialise, on ecrit `inconnu` : un identifiant
        invente serait pire qu'une absence declaree.
        """
        import subprocess

        try:
            sortie = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=Path.cwd(),
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return "inconnu"
        return sortie.stdout.strip() if sortie.returncode == 0 else "inconnu"

    ordre = ("S0", "S1", "S1b", "S2", "S3", "S4", "S4c", "S4b", "S4r", "S4rc")

    def _ecart_sur(gauche: str, droite: str, question: str) -> tuple:
        if not results.get(gauche) or not results.get(droite):
            return (gauche, droite, question, None, None, False)
        delta, (bas, haut), tranche = _ecart(results[gauche], results[droite])
        return (gauche, droite, question, delta, (bas, haut), tranche)

    mesures = list(ecarts)
    mesures = [e for e in mesures if e[3] is not None]
    mesures.append(_ecart_sur("S1b", "S2",
                              "budget d'appels EGAL : verification vs echantillonnage"))
    mesures.append(_ecart_sur("S0", "S3", "gain total du harness (modele brut -> JIO)"))
    if results.get("S4rc") and results.get("S4r"):
        mesures.append(_ecart_sur("S4rc", "S4r",
                                  "sans oracle : harness vs meme budget sans verification"))

    if modele.genre == "simule":
        hypotheses = (
            "les reponses du modele sont SIMULEES : ce rapport mesure l'ARCHITECTURE du "
            "harness, pas un modele reel. Le meme rapport avec `--provider cli:<votre outil>` "
            "mesure votre modele.",
        )

    rapport = construire(
        resultats=results, appels=calls, libelles=labels, ordre=ordre, modele=modele,
        skill=skill, runs=runs, taches=taches, rounds=rounds, duree_s=elapsed,
        commit=_commit_court(), integrite=integrite, hypotheses=hypotheses,
        ecarts=[m for m in mesures if isinstance(m, tuple) and len(m) == 6],
    )
    md, js = ecrire(rapport, args.rapport)
    print(f"  RAPPORT ECRIT : {md}")
    print(f"    JSON a cote  : {js}")
    bases = [e for e in mesures if isinstance(e, tuple) and e[3] is None]
    for gauche, droite, question, *_ in bases:
        print(f"    non mesurable ici (bras sans donnees) : {question}")
    besoin = _essais(_mean(results["S1b"]), _mean(results["S2"])) \
        if results.get("S1b") and results.get("S2") else 0
    if besoin > 0:
        par_tache = max(1, len(results["S0"]) // max(1, runs))
        print(f"    pour trancher l'ecart de verification : ~{besoin} essai(s) par bras, "
              f"soit --runs {math.ceil(besoin / par_tache)} sur ce jeu de {par_tache} tache(s)")
    print()


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

    # --- Porte de clarification --------------------------------------------- #
    # Elle passe AVANT tout appel de modele : une mission ambigue coute tous ses tours et
    # livre quelque chose de plausible repondant a une autre question. En mode strict elle
    # ARRETE la mission et rend les questions (code 3) ; sinon elle DECLARE les hypotheses
    # qu'elle prend. Dans les deux cas, rien n'est tu.
    # Quand une tache du banc existe, c'est SON objectif qui est execute (`mission.objective`
    # plus bas) : c'est donc lui qu'il faut analyser. Analyser l'objectif tape a la main
    # poserait des questions sans objet, la specification etant deja dans la tache — un faux
    # positif de la porte, exactement ce qui lui ferait perdre toute autorite.
    if tache_prose is not None:
        objectif_pour_la_porte = tache_prose.objective
    elif task is not None:
        objectif_pour_la_porte = task.objective
    else:
        objectif_pour_la_porte = args.objective
    from .clarify import analyser as _analyser, formater as _formater_clarify

    analyse = _analyser(
        objectif_pour_la_porte,
        contexte=(Path("README.md").read_text(encoding="utf-8", errors="replace")[:50_000]
                  if Path("README.md").is_file() else ""),
        mode="strict" if getattr(args, "strict", False) else "assume",
    )
    if analyse.bloquant:
        print(_formater_clarify(analyse))
        print()
        print("  MISSION ARRETEE (--strict) : reponds aux questions ci-dessus, puis relance.")
        print("  Sans reponse, les defauts proposes sont ce que je ferais — dis-le si c'est bon.")
        return 3
    if analyse.questions and getattr(args, "strict", False) is False:
        print("  HYPOTHESES DECLAREES (l'objectif laissait ces points ouverts) :")
        for question in analyse.questions:
            print(f"    - {question.signal} : {question.defaut}")
        print("  Reponds a une seule d'entre elles pour que je l'enleve de cette liste.")
        print()

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
            competences=not getattr(args, "sans_competences", False),
        )
    elif prose:
        engine = _real_engine(
            journal_path=journal_path, max_rounds=args.rounds,
            min_panel=args.min_panel, famille="prose", racine=Path.cwd(),
            fournisseurs=modele_liste,
            competences=not getattr(args, "sans_competences", False),
        )
    elif args.simulate:
        engine = _simulated_engine(
            task, seed=0, journal_path=journal_path, max_rounds=args.rounds,
            alpha=args.alpha, min_panel=args.min_panel,
            # --no-oracle : la mission ne fournit AUCUN test, comme une mission
            # reelle. Le modele simule traduit les regles en temoins, et la preuve
            # doit tenir toute seule.
            traduire_les_regles=bool(getattr(args, "no_oracle", False)),
            competences=not getattr(args, "sans_competences", False),
        )
    else:
        engine = _real_engine(
            journal_path=journal_path, max_rounds=args.rounds, min_panel=args.min_panel,
            fournisseurs=modele_liste,
            competences=not getattr(args, "sans_competences", False),
        )
    _attach_learning(engine, Path(args.state), disable=args.no_learn)

    if tache_prose is not None:
        objective = args.objective or tache_prose.objective
    else:
        # Le MANDAT de l'utilisateur prime pour l'objectif de la MISSION ; l'enonce de tache
        # reste l'objectif de TRAVAIL (`work.objective`, ci-dessous), qui porte l'entrypoint,
        # les verifications et les oracles.
        #
        # Ce n'est pas cosmetique. Quand `--task` ecrasait le mandat, le routeur de procedures
        # voyait « Ecrire une fonction sum_even(nums)... » et s'abstenait legitimement : cet
        # enonce ne dit rien du DOMAINE. Le mandat, lui, dit tout — c'est la question posee.
        # Un seul mot change de place, et les procedures du depot arrivent au bon moment.
        objective = args.objective or (task.objective if task else "")

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
        objective=(task.objective if task else objective),
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
    # Le code de sortie vient de la TABLE, pas d'une condition ecrite ici : une abstention
    # (rien n'a pu etre prouve) n'est pas une reserve a lever, et l'appelant doit pouvoir les
    # distinguer pour savoir s'il corrige ou s'il fournit. Voir `jio/core/codes.py`.
    from .core.codes import ACTION, code_de_mission

    code = code_de_mission(report.status)
    if code:
        print(f"  -> code {code} : {ACTION[code]}")
    return code


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
    from .artifacts.budget import SEUILS, mesurer_depuis, resume, sur_disque, verdict
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
    # Meme regle pour ce qui se charge a la demande : c'est le fichier du disque qui sera lu.
    etat_skills = sur_disque(Path.cwd(), skills)
    skills = etat_skills.fichiers
    etat_agents = sur_disque(Path.cwd(), agents)
    agents = etat_agents.fichiers

    # Un outil donne ne charge QU'UN fichier de contexte : Claude lit CLAUDE.md, Cursor
    # lit .cursor/rules/jio.mdc, Copilot lit .github/copilot-instructions.md, etc. Les
    # additionner produirait un total qu'AUCUNE session ne paie — c'est exactement le genre
    # de chiffre faux qu'un rapport sur le contexte ne peut pas se permettre. On mesure le
    # fichier le plus lourd et le plus leger, et on dit ce que paie une session reelle.
    # On mesure le fichier du DISQUE, pas le texte que jio regenererait : c'est le premier que
    # l'outil charge. `sur_disque` rend aussi ce qui diverge et ce qui n'existe pas encore, et
    # les deux sont DITS plus bas — un chiffre qui porte sur un autre fichier que le sien est
    # un chiffre faux, meme s'il est exact.
    etat = sur_disque(Path.cwd(), demarrage)
    demarrage = etat.fichiers
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

    # Le VERDICT porte sur les memes fichiers que l'affichage : ceux du disque. Le calculer sur
    # le manifeste disait « aucun fichier ne depasse » d'un `.cursor/rules/jio.mdc` edite a la
    # main qui en faisait 152 lignes — vu ici meme, en verifiant la correction.
    tous_mesures = mesurer_depuis(
        Path.cwd(), {**tous, **demarrage, **skills, **agents}
    )
    for ligne in verdict(
        tous_mesures,
        est_competence=lambda chemin: "/skills/" in chemin and chemin.endswith("SKILL.md"),
    ):
        print(ligne)
    print()

    # La bibliotheque est annoncee en JETONS **et** en CARACTERES, avec l'intervalle. Ce n'est
    # pas un exces de zele : 24 416 caracteres ressemblent a 98 % d'un seuil de 25 000, alors
    # que la bibliotheque pese 5 500 a 7 600 jetons — un quart du seuil. Confondre les deux
    # unites fait conclure a une saturation qui n'existe pas, et retient d'ajouter une
    # competence utile. Les unites sont donc nommees dans la ligne.
    mesures_skills = mesurer_depuis(Path.cwd(), skills)
    total_skills = sum(m.jetons for m in mesures_skills)
    bas = sum(m.jetons_min for m in mesures_skills)
    haut = sum(m.jetons_max for m in mesures_skills)
    caracteres = sum(len(texte) for texte in skills.values())
    print(f"    Bibliotheque de competences : ~{total_skills} jetons "
          f"({bas} a {haut} selon la langue) · {caracteres} caracteres "
          f"· seuil {SEUILS['bibliotheque_jetons']} jetons")
    # Un seuil qu'on approche sans le voir est un seuil qu'on depasse par surprise. La marge
    # est donc dite dans les deux sens : « encore X de disponible » ou « il reste X ».
    palier = int(0.8 * SEUILS["bibliotheque_jetons"])
    if bas < palier:
        print(f"      marge : {palier - bas} jetons avant 80 % du seuil, sur la borne BASSE")
    else:
        print("      ATTENTION : la bibliotheque approche le seuil — chaque competence ajoutee "
              "coute, et le routeur existe pour que vous n'ayez PAS a tout charger.")
    print("    Contexte injecte au demarrage : un seul fichier par outil (voir ci-dessus)")
    print()
    print("    Lecture : les jetons sont un INTERVALLE (3,2 a 4,4 caracteres par jeton "
          "selon")
    print("    la langue et le code) — un tokenizer reel est une dependance, et la mesure")
    print("    varie d'un modele a l'autre. Ce qu'on peut dire, on le dit ; le reste est")
    print("    declare comme incertain.")
    print()
    # CE QUI A ETE MESURE, et pas suppose : le fichier du disque, ou celui que jio ecrira.
    # Sans cette declaration, l'utilisateur croirait lire la taille de ses fichiers alors
    # qu'il lit celle de la doctrine.
    divergents = tuple(sorted(set(etat.divergents) | set(etat_skills.divergents)
                              | set(etat_agents.divergents)))
    absents = tuple(sorted(set(etat.absents) | set(etat_skills.absents)))
    if divergents:
        print("    MESURE SUR VOS FICHIERS (ils diffèrent de la doctrine, et c'est EUX que")
        print("    vos outils chargent). `jio artifacts --write` les mettre a jour, ou les")
        print("    PRESERVERA s'ils ne portent pas la marque de jio — comparez-les :")
        for chemin in divergents[:4]:
            cible = Path.cwd() / chemin
            sur_disque_lignes = len(cible.read_text(encoding="utf-8").splitlines())
            doctrine_lignes = len(tous[chemin].splitlines())
            print(f"      {chemin} : {sur_disque_lignes} ligne(s) ici, "
                  f"{doctrine_lignes} dans la doctrine")
        print()
    if absents:
        print(f"    {len(absents)} fichier(s) pas encore ecrit(s) : la mesure porte sur ce que "
              "`jio artifacts --write` ecrira.")
        print()
    return 0


def _hermes_installer(racine: Path, *, desinstaller: bool, lier: bool) -> int:
    """`jio artifacts --install-hermes` / `--desinstaller` : le geste, et son retour en arriere.

    Le dossier cible est cree ICI si besoin : contrairement a `jio start`, l'utilisateur a
    demande explicitement l'installation — ne rien faire parce qu'un dossier n'existe pas encore
    serait une obedience litterale au lieu d'un service.
    """
    from .artifacts.install_hermes import REGISTRE, desinstaller as retirer
    from .artifacts.install_hermes import dossier_hermes, installer

    print(BANNER)
    cible = dossier_hermes()
    if desinstaller:
        rapport = retirer(racine, dossier=cible)
        print("  DESINSTALLATION DES COMPETENCES HERMES")
        print(f"    dossier : {cible}")
        print(f"    retire(s) : {len(rapport.copies)}")
        for chemin in rapport.preserves[:6]:
            print(f"    PRESERVE : {chemin} (modifie depuis l'installation : a vous)")
        print(f"    registre : {REGISTRE}")
        print()
        return 0

    rapport = installer(racine, dossier=cible, lier=lier, creer=True)
    print("  INSTALLATION DES COMPETENCES HERMES")
    print(f"    dossier : {cible}  ·  mode : {'liens' if lier else 'copies'}")
    for chemin in rapport.liens[:8]:
        print(f"    LIEN      {chemin}")
    for chemin in rapport.copies[:8]:
        print(f"    COPIE     {chemin}")
    for chemin in rapport.mises_a_jour[:8]:
        print(f"    A JOUR    {chemin}")
    for chemin in rapport.deja[:6]:
        print(f"    deja      {chemin}")
    for chemin in rapport.preserves[:6]:
        print(f"    PRESERVE  {chemin} (a vous : jamais ecrase)")
    print(f"    total : {rapport.resume()}")
    if rapport.ignores:
        print("    aucun dossier .hermes/skills dans ce projet : rien a installer.")
        return 2
    print()
    return 0


def _auditer_artefacts() -> int:
    """`jio artifacts --audit` : les competences et les agents sont-ils surs a executer ?

    Une competence n'est pas un document : c'est une INSTRUCTION pour un agent qui, lui, a
    le droit d'ecrire et de lancer des commandes. Une competence hostile s'execute donc avec
    ses droits — l'article arXiv 2608.29381 en donne un exemple complet, ou une competence
    malveillante se sert du rollback de l'agent pour restaurer un workspace hostile tout en
    gardant une verification faite sur un autre etat.

    Le controle distingue ce qui ORDONNE une action dangereuse de ce qui l'INTERDIT : une
    ligne qui dit « n'utilise jamais --no-verify » est une protection. Sans cette
    distinction, le controle accuserait les fichiers qui le protegent.
    """
    from .artifacts.audit_skills import analyser_artefacts

    print(BANNER)
    risques = analyser_artefacts()
    dangereux = [risque for risque in risques if not risque.mise_en_garde]
    gardes = [risque for risque in risques if risque.mise_en_garde]

    print("  AUDIT DES INSTRUCTIONS  ·  ce qui sera execute par un agent")
    print()
    for risque in dangereux:
        print(f"    [RISQUE]      {risque.artefact} ligne {risque.ligne} : {risque.nature}")
        print(f"                  {risque.extrait}")
    for garde in gardes:
        print(f"    [garde]       {garde.artefact} ligne {garde.ligne} : {garde.nature}")
        print(f"                  {garde.extrait}")
    print()
    if dangereux:
        print(f"    {len(dangereux)} motif(s) a instruire. Une competence sera EXECUTEE par un")
        print("    agent qui peut ecrire : ce qui y est ordonne compte autant que ce qui y est")
        print("    explique. Corriger, ou justifier dans le texte.")
        print()
        return 1
    print(f"    aucun motif dangereux · {len(gardes)} mise(s) en garde (comptees, pas condamnees)")
    print("    -> les interdictions et les explications sont reconnues comme telles : un")
    print("       controle qui accuse les fichiers qui le protegent se fait desactiver.")
    print()
    return 0


def cmd_artifacts(args: argparse.Namespace) -> int:
    """Emet les artefacts natifs. `--mcp` route vers le branchement du serveur MCP."""
    if getattr(args, "budget", False):
        return _budget_contexte(args)
    if getattr(args, "mcp", None):
        return _brancher_mcp(args)
    if getattr(args, "audit", False):
        return _auditer_artefacts()
    if getattr(args, "install_hermes", False) or getattr(args, "desinstaller", False):
        return _hermes_installer(Path(args.root), desinstaller=bool(
            getattr(args, "desinstaller", False)), lier=bool(getattr(args, "lier", False)))
    from .artifacts import TARGETS, manifest
    from .verify.coherence import manifeste_attendu

    targets = tuple(args.target) if args.target else TARGETS
    try:
        # LE MANIFESTE DU PROJET, PAS LA FORME CANONIQUE : c'est celui que `jio coherence` exige.
        # Deux formes pour un meme fichier font tourner l'utilisateur en boucle — reparer, se
        # voir reprocher la reparation, reparer. Mesure faite sur un projet ETRANGER : juste
        # apres `jio artifacts --write`, le portail declarait `.mcp.json` et `opencode.json`
        # « divergents », et la commande qu'il recommandait etait celle-la meme.
        canonique = manifest(targets)
        files = {rel: texte for rel, texte in manifeste_attendu(Path(args.root)).items()
                 if rel in canonique}
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
    if args.integrity:
        # Sortie MACHINE : une phrase, un code. C'est ce qu'un pre-commit ou une CI peut lire,
        # et c'est la seule raison d'avoir une option distincte du rapport.
        #
        # `notices` compte autant que la chaine : le CHARGEMENT a pu REFUSER un fichier
        # (chaine cassee, fichier illisible) et le mettre en quarantaine — le fichier actif est
        # alors vide et parfaitement valide. Se fier au seul `verify()` aurait donc affiche
        # « chaine valide » sur une memoire qui vient d'etre rejetee : un vert sur un fichier
        # ecarte. Toute notice signifie qu'une memoire a ete refusee ; c'est un echec du
        # controle, pas un detail.
        ok, cassee = memory.verify()
        if ok and not memory.journal.notices:
            print(f"  integrite : chaine valide ({memory.size} evenement(s), tete {memory.head})")
            return 0
        for notice in memory.journal.notices:
            print(f"  INTEGRITE : {notice}", file=sys.stderr)
        if not ok:
            print(f"  INTEGRITE : CHAINE CASSEE @ {cassee} — le fichier a ete reecrit hors de JIO.",
                  file=sys.stderr)
        print("  La chaine est la preuve que rien n'a ete modifie en silence : une rupture ne se",
              file=sys.stderr)
        print("  repare pas, elle s'inspecte. Le fichier refuse est CONSERVE (suffixe",
              file=sys.stderr)
        print("  `.corrompu-<horodatage>`) : comparez-le, puis decidez.", file=sys.stderr)
        return 1
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


def _preuve_dans_un_repertoire_temporaire(chemin: Path) -> str:
    """Avertit quand la trace d'une mesure longue est ecrite dans un repertoire temporaire.

    Ce n'est pas une precaution theorique : une campagne de vingt minutes a ete perdue EN
    ENTIER — le pilote, le cumul deja mesure, les sorties — quand le bac a sable a efface
    `/tmp`. Le programme, lui, faisait ce qu'il fallait : chaque cycle etait ecrit des qu'il
    etait mesure. C'est l'EMPLACEMENT de la preuve qui la rendait mortelle a perdre.

    On avertit au lieu de refuser : ecrire dans un temporaire est parfois volontaire (essai
    rapide). Mais une mesure longue qui doit servir de preuve doit vivre avec le depot, et le
    message dit ou.
    """
    import tempfile

    temporaires = {Path(tempfile.gettempdir()).resolve()}
    for candidat in ("/tmp", "/var/tmp", "/dev/shm"):
        temporaires.add(Path(candidat))
    resolu = chemin.resolve() if chemin.exists() else chemin.absolute()
    for racine in temporaires:
        if resolu == racine or racine in resolu.parents:
            return (
                f"cette mesure ecrit sa trace dans {racine} — un repertoire EFFACE au "
                f"redemarrage de la machine. Une campagne de vingt minutes y a deja ete "
                f"perdue en entier. Pour une preuve qui doit survivre, ecrivez-la dans le "
                f"depot : `--cumul evidence/{chemin.name}`."
            )
    return ""


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "cycles", 0) > 0:
        return _learn_cycles(args)
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


#: Cout d'une mission du protocole multi-cycles, MESURE sur cette machine (2 cœurs) :
#: 3 bras par mission mesuree, ~2,3 s chacun. Sert a annoncer une duree, pas a decider.
_SECONDES_PAR_MISSION = 2.3


def _apprendre_le_gain(args: argparse.Namespace) -> float:
    """Calibre la MODELISATION du gain d'avertissement — elle ne peut pas etre inventee.

    Cette constante (0,20 par defaut) est la seule chose que le banc ne mesure pas : elle
    modelise l'effet d'un retour d'echec structure sur un modele reel. Elle borne donc TOUT
    ce que le protocole peut conclure. La calibration A/B dirait, sur un vrai modele, quel
    gain une reprise apres echec produit — c'est ce que fait l'option `--calibrer-gain`.
    """
    if getattr(args, "calibrer_gain", False) and float(getattr(args, "gain", 0.20)) == 0.20:
        print("  [CALIBRATION] --calibrer-gain demande : le gain d'avertissement sera")
        print("    MESURE par le protocole A/B au lieu d'etre declare. Non implemente a ce")
        print("    jour : le protocole multi-cycles refuse de tourner avec une modelisation")
        print("    non calibree plutot que de publier un chiffre dont la borne est supposee.")
        return -1.0
    return float(getattr(args, "gain", 0.20))


def _learn_cycles(args: argparse.Namespace) -> int:
    """Le protocole MULTI-CYCLES. Mesure separee de l'A/B, jamais melangee.

    L'A/B repond a « la mecanique apporte-t-elle quelque chose en moyenne » ; ce protocole
    repond a « la memoire qui S'ACCUMULE apporte-t-elle quelque chose, cycle apres cycle ».
    Ce sont deux questions differentes : la premiere a deja montre un gain NON MESURABLE au
    niveau du banc, et c'est precisement pour cela que la seconde existe.
    """
    from .learn.cycles import TASKS, Cumul, depuis_cumul, run_cycles

    missions = args.cycles * 3 * len(TASKS) * max(args.runs, 1)
    print()
    print("  AUTO-AMELIORATION MULTI-CYCLES  ·  trois bras apparies par cycle")
    print(f"    competence simulee {args.skill}  ·  {args.cycles} cycles  ·  {args.runs} "
          f"tirage(s) par tache  ·  {args.rounds} tours  ·  {len(TASKS)} taches")
    # Le cout par mission est un DEBIT MESURE (2,3 s/mission, 3 bras, 2 cœurs), pas une
    # estimation d'intention : la version precedente annoncait 1,1 s et sous-estimait la
    # duree reelle d'un facteur deux — une duree annoncee sert a decider, elle doit etre vraie.
    secondes = missions * _SECONDES_PAR_MISSION
    print(f"    cout annonce : {missions} mission(s) x {_SECONDES_PAR_MISSION} s/mission "
          f"mesure = ~{secondes / 60:.0f} min sur 2 cœurs")
    if missions > args.plafond_missions:
        print()
        print(f"  [INDETERMINE] {missions} missions depassent le plafond de "
              f"{args.plafond_missions} : ce n'est pas une mesure impossible, c'est une")
        print(f"    mesure qui prendrait ~{secondes / 60:.0f} min sur cette machine.")
        print(f"    Reduire --cycles ou --runs, ou assumer le cout avec "
              f"`--plafond-missions {missions}`.")
        print("    Le protocole ne se degrade PAS en silence : il refuse plutot que de")
        print("    rendre un chiffre qu'il n'a pas les moyens de rendre.")
        return 2
    import time

    debut = time.monotonic()
    print("    Par mission : CHAUD (memoire, avertissement actif) -> TEMOIN (memoire")
    print("    presente, avertissement desactive) -> FROID (aucune memoire). Memes taches,")
    print("    memes graines, MEME bras : le temoin separe l'effet de la memoire du bruit.")
    print()
    gain = _apprendre_le_gain(args)
    if gain < 0.0:
        return 2
    # -- le cumul ------------------------------------------------------------------------ #
    # Une mesure de 300 missions dure une vingtaine de minutes et n'etait ecrite qu'a la fin :
    # une coupure a la 18e minute perdait tout (vecu deux fois). Les cycles sont donc ecrits
    # au fur et a mesure, et `--cumul` empile les executions.
    chemin = Path(args.cumul) if getattr(args, "cumul", "") else None
    seed_base = 0
    cumul: Cumul | None = None
    if chemin is not None:
        avertissement = _preuve_dans_un_repertoire_temporaire(chemin)
        if avertissement:
            print(f"  [ATTENTION] {avertissement}")
            print()
        deja = len(depuis_cumul(chemin).cycles)
        if deja:
            # DES GRAINES DISTINCTES, sinon ce n'est pas une replication. Rejouer les memes
            # graines donnerait exactement le meme resultat : le nombre d'essais doublerait
            # sans qu'une seule preuve soit ajoutee, et l'intervalle se resserrerait autour de
            # rien. C'est le piege le plus dangereux de tout ce protocole.
            seed_base = 1000 * deja
            print(f"    CUMUL : {deja} cycle(s) deja mesure(s) dans {chemin.name} ; cette")
            print(f"    execution utilise des graines DISTINCTES (bloc {seed_base}) — rejouer les")
            print("    memes graines doublerait le compte sans ajouter une seule preuve.")
            print()
        try:
            cumul = Cumul(chemin, skill=args.skill, runs=args.runs, rounds=args.rounds,
                          gain=gain, seed_base=seed_base)
        except ValueError as erreur:
            print(f"  [PROBLEME] {erreur}")
            return 1
        print("    Chaque cycle est ECRIT des qu'il est mesure : une coupure ne perd que le")
        print(f"    cycle en cours (fichier {chemin}). Le cumul est VERROUILLE pendant la mesure :")
        print("    deux mesures simultanees rejoueraient les memes graines.")
        print()
    try:
        res = run_cycles(
            skill=args.skill, runs=args.runs, cycles=args.cycles, rounds=args.rounds,
            warning_gain=gain, seed_base=seed_base,
            sur_cycle=cumul.ajouter if cumul is not None else None,
        )
    finally:
        if cumul is not None:
            cumul.lever_le_verrou()
    # Le debit est MESURE pendant ce run, pas suppose : c'est lui qui convertit un budget
    # d'essais en duree reelle, et une duree annoncee est ce qui fait prendre une decision.
    ecoule = max(time.monotonic() - debut, 1e-6)
    debit = missions / ecoule
    if not res.cycles:
        print("  [INDETERMINE] aucun cycle mesure (cycles ou runs nul).")
        return 2
    if chemin is not None:
        # Le cumul a deja ete ecrit cycle par cycle ; on le RELIT depuis le disque, ce qui
        # verifie au passage que ce qui a ete ecrit est relisible.
        res = depuis_cumul(chemin)
        print(f"  CUMUL : {len(res.cycles)} cycle(s) au total dans {chemin}")
        if res.replications_independantes:
            blocs = ", ".join(str(b) for b in res.blocs_de_graines)
            print(f"  REPLICATIONS INDEPENDANTES : {res.replications_independantes} "
                  f"(blocs de graines : {blocs})")
            if res.replications_independantes < len(res.replications):
                print("    ATTENTION : deux executions ont utilise le MEME bloc de graines — "
                      "elles ne comptent que pour une.")
        print()
    _afficher_le_rapport_cycles(res, debit=debit)
    return 0


def _afficher_le_rapport_cycles(res: object, *, debit: float) -> None:
    """L'affichage du protocole multi-cycles. Sorti de la commande pour etre lisible."""
    print(f"    {'cycle':>5} {'memoire':>8} {'rappels':>7} {'jetons':>6} "
          f"{'froid':>9} {'temoin':>9} {'chaud':>9} {'artef':>6} {'ecart':>7}")
    print(f"    {'-' * 5} {'-' * 8} {'-' * 7} {'-' * 6} {'-' * 9} {'-' * 9} {'-' * 9} "
          f"{'-' * 6} {'-' * 7}")
    for cycle in res.cycles:
        print(cycle.ligne())
    print()
    print(f"  MEMOIRE ACCUMULEE : {res.memo_final} souvenir(s) apres {len(res.cycles)} cycle(s)")
    print(f"  BRUIT DE FOND (froid -> temoin, sans effet de memoire) : "
          f"{res.artefact_max} reussite(s) au pire cycle")
    armes = sum(c.avertis for c in res.cycles)
    total = sum(c.appels for c in res.cycles)
    print(f"  PORTEE DU LEVIER : {armes}/{total} appel(s) de generation avertis "
          f"({res.portee:.1%}) — c'est ce qui borne tout effet possible de la memoire.")
    b, c = res.paires
    bas, haut = res.intervalle_apparie
    print(f"  TEST APPARIE (McNemar exact, le plan experimental) : la memoire fait REUSSIR "
          f"seule {b} fois, ECHOUER seule {c} fois — p = {res.p_valeur_appariee:.4f}")
    print(f"    IC95 de la difference (paires) : [{bas:+.3f} ; {haut:+.3f}]"
          + ("   -> zéro EXCLU" if res.tranche_apparie else "   -> contient zéro"))
    blocs = res.effet_par_bloc()
    if len(blocs) > 1:
        print("  REPLICATIONS INDEPENDANTES (un cumul est une somme de tirages, pas une "
              "moyenne) :")
        for bloc, ecart, b, c in blocs:
            print(f"    bloc de graines {bloc:>5} : {ecart:+d} reussite(s) "
                  f"({b} contre {c} dissociation(s))")
    requis = res.essais_requis()
    if requis:
        # 3 bras par paire mesuree : c'est le cout reel du protocole, pas une estimation.
        minutes = requis * 3 / debit / 60.0 if debit else 0.0
        print(f"  PAIRES REQUISES POUR DEMONTRER LA DISSOCIATION : ~{requis}, soit "
              f"~{minutes:.0f} min ici au debit mesure ({debit:.2f} essai/s).")
        print("    (Mesure a 95 % de confiance et 80 % de puissance, formule du banc ; "
              "c'est un budget, pas un verdict.)")
    print(f"  DEBIT MESURE : {debit:.2f} essai(s)/s sur cette machine.")
    if res.bras:
        print("  ROUTAGE (le bandit, mesure sur tout l'historique) :")
        for nom, tirages, recompense in res.bras:
            print(f"    {nom:<10} {tirages:>3} tirage(s)   recompense moyenne {recompense:+.3f}")
    if res.meilleur_bras:
        print(f"    concentration sur le meilleur bras ({res.meilleur_bras}) : "
              f"{res.concentration:.0%}   ·   regret mesure : {res.regret:.2f}")
    print()
    print(f"  VERDICT : {res.verdict()}")
    print()
    for ligne in res.explication().split("\n"):
        print(f"    {ligne}")
    print()
    print("  CE QUE CE PROTOCOLE NE DIT PAS")
    print("    - le modele est SIMULE : ce n'est pas une mesure de modele reel.")
    print("    - l'effet d'un souvenir injecte est une MODELISATION declaree (gain relatif).")
    print("    - un plateau ici ne condamne pas la memoire : il dit qu'a ce niveau de")
    print("      difficulte la VERIFICATION suffisait deja. Le banc ne represente pas le")
    print("      regime ou la verification ne voit pas l'erreur (plausibilite, conception).")
    print()


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

    # LA PROSE DE JIO N'EST PAS CELLE DU PROJET. Mesure faite sur un projet ETRANGER, apres
    # `jio start` : le scan y trouvait 22 « chemin cite INTROUVABLE » — `jio/artifacts/doctrine.py`,
    # `jio/artifacts/definitions.py` — tous cites par les documents que jio venait d'installer
    # (`.github/copilot-instructions.md`, `.hermes/skills/*/SKILL.md`, `AGENTS.md`, `CLAUDE.md`).
    # Ces chemins existent dans le depot de jio, pas chez l'utilisateur, et ils ne PEUVENT pas y
    # exister : ce n'est pas un defaut de son projet, c'est le notre, installe chez lui. Un
    # balayage qui reproche a l'utilisateur nos propres fichiers obtient exactement ce qu'il
    # merite : il est ignore, et avec lui les vrais defauts qu'il aurait trouves.
    #
    # Deux preuves de provenance, parce qu'une ne suffisait pas : la MARQUE du garde d'ecriture
    # (les documents generes la portent) et l'ORIGINE du fichier (les competences installees sont
    # des copies, et leurs `SKILL.md` ne portent pas la marque). Un document est de jio quand il
    # vit dans un dossier que jio gere (`SKILL.md` d'une competence, agents `.opencode`, consignes
    # d'agent) — ce que `artifacts.definitions` declare — ou quand il porte la marque.
    from .artifacts.write_guard import _porte_la_marque
    from .scan_champ import est_un_document_de_jio

    # SAUF DANS LE DEPOT DE JIO. Ici, les chemins cites par nos documents existent (c'est leur
    # maison), et exclure nos propres documents reduirait l'audit de 28 a 2 — mesure faite, et
    # c'est exactement le genre de « correction » qui rend un outil aveugle en le rendant
    # silencieux. Le filtre ne sert qu'a un projet qui N'EST PAS jio.
    proscrits: list[Path] = []
    if (root.is_dir() and not getattr(args, "tout", False)
            and not (root / "jio" / "__init__.py").is_file()):
        gardes_documents = []
        for document in documents:
            marque = False
            try:
                marque = _porte_la_marque(document.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
            if marque or est_un_document_de_jio(document, root):
                proscrits.append(document)
                continue
            gardes_documents.append(document)
        documents = gardes_documents

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
                # Le vrai chemin : le fichier audite recoit son propre `__file__`, donc un
                # test qui situe ses donnees par rapport a lui-meme les trouve. Sans cela
                # il cherchait sous /tmp et le scan concluait « non testable ».
                chemin=path,
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
            cible = target if target.exists() else finding.path
            # Un constat qui DECLARE une limite de l'analyseur n'accuse pas le code : il est
            # affiche en reserve, avec sa raison. Le message de `pyparsing` (« unable to
            # detect undefined names ») le disait deja ; c'est nous qui l'accusions.
            limite = finding.limite_de_l_analyse
            if limite:
                reserves.append((cible, finding.rule, limite[:160]))
            else:
                problems.append((cible, finding.rule, finding.label[:160]))
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
    if proscrits:
        # Ce qui est ecarte est DIT : un balayage qui se tairait sur ce qu'il n'a pas regarde
        # serait le silence que ce projet refuse. Et la raison est donnee, pour que l'utilisateur
        # qui veut vraiment auditer nos documents puisse le faire (`--tout` les remet dedans).
        print(f"  document(s) de jio hors du champ : {len(proscrits)} "
              "(ils citent les chemins de jio, pas ceux de ce projet) — `--tout` pour les inclure")
    print()
    # --- les DEPENDANCES du projet : un rouge qui attend son heure ---------------- #
    # Un test qui importe un paquet non declare passe chez celui qui l'a installe un jour
    # pour autre chose, et echoue sur un clone neuf. Mesure sur CE depot : la CI
    # installait `pytest ruff` et son commentaire affirmait qu'aucune autre dependance
    # n'etait necessaire ; `tests/test_hooks.py` importe `yaml`, donc deux tests rouges.
    # Un defaut qui ne se voit que sur la machine des autres doit etre cherche ici.
    dependances: list[str] = []
    if root.is_dir():
        from .verify.dependances import manquants

        dependances = [str(manque) for manque in manquants(root)]

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
    if dependances:
        print(f"    {len(dependances)} dependance(s) de test NON declaree(s) — un clone neuf")
    if remembered:
        print(f"    {remembered} probleme(s) memorise(s) : la prochaine execution saura quoi")
        print(f"    eviter, et pourquoi. Consulter : jio memory --state {args.state}")
    print("    Lecture du resultat : code 0 = rien trouve ; code 1 = au moins un defaut")
    print("    reel avec sa preuve. Un fichier sans regle executable n'est PAS un")
    print("    fichier correct : c'est un fichier que ces regles-la ne savent pas juger.")

    if dependances:
        print(f"  {len(dependances)} DEPENDANCE(S) DES TESTS NON DECLAREE(S) :")
        for detail in dependances:
            print(f"    {detail}")
        print("    un test qui importe un paquet non declare passe sur la machine ou il est")
        print("    installe, et echoue sur un clone neuf. Declarer dans `pyproject.toml`")
        print("    (dependances ou extras) ou installer explicitement dans la CI.")
        print()

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
    return 1 if (problems or dependances) else 0


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

    # `jio mcp` LANCE un serveur : il parle JSON-RPC sur son entree standard, et un humain qui
    # le tape dans un terminal n'y verrait RIEN — la commande attendrait un message qui ne
    # viendra jamais, puis rendrait 0 sans un mot. Un chemin qui sort en 0 sans rien produire
    # est indistinguable d'un succes : c'est exactement ce que ce depot refuse partout ailleurs.
    # Reconnaitre le terminal et MONTRER ce que le serveur sert, c'est la meme information que
    # `--list`, plus la raison pour laquelle la commande ne bloque pas ici.
    if args.list or sys.stdin.isatty():
        _outils_mcp(TOOLS, interactif=not args.list)
        return 0
    return mcp_main()


def _outils_mcp(tools: Sequence[Mapping[str, object]], *, interactif: bool) -> None:
    """Ce que le serveur MCP expose — et, dans un terminal, pourquoi il ne demarre pas."""
    from .artifacts.wiring import _COMMANDE

    print()
    print("  SERVEUR MCP JIO  ·  transport stdio, JSON-RPC 2.0, zero dependance")
    print()
    if interactif:
        print("  Cette commande demarre un SERVEUR : elle parle JSON-RPC 2.0 sur son entree")
        print("  standard et sur sa sortie standard. Lancee dans un terminal, elle n'aurait")
        print("  rien a repondre — donc elle montre a la place ce qu'elle sert.")
        print()
        print("  Pour l'interroger : `jio mcp --prove` demarre le serveur et compte les outils")
        print(f"  qu'il rend vraiment, par la commande `{' '.join(_COMMANDE)}`.")
        print()
    for tool in tools:
        print(f"    {tool['name']:<14} {str(tool['description'])[:80]}")
    print()
    print("  Configuration : `jio artifacts --mcp <dialecte>` pour opencode, Hermes,")
    print("  Codex, Claude Code ou Cursor ; `jio artifacts --target mcp --write` pour")
    print("  `.mcp.json` (dialecte de Claude Code, lu aussi par Cursor).")
    print("  Preuve du cablage : `jio mcp --prove`. Securite : chemins confines a JIO_ROOT.")
    print()


def cmd_trace(args: argparse.Namespace) -> int:
    """Rejoue et verifie un journal — meme sans indiquer lequel.

    `jio trace` sans argument echouait : il fallait connaitre le chemin exact du
    journal pour savoir ce qui s'etait passe. Exiger de connaitre la reponse pour
    poser la question est une mauvaise interface. On cherche donc le journal, du
    plus recent au plus ancien, et on dit clairement quoi faire s'il n'y en a pas.
    """
    explicite = bool(args.journal)
    path = Path(args.journal) if explicite else Path(
        str_env("JIO_JOURNAL", ".jio/journal.jsonl")
    )
    if explicite and not path.is_file():
        # DEFAUT MESURE, corrige ici : `jio trace /tmp/inexistant.jsonl` cherchait un AUTRE
        # journal, en trouvait un, et repondait « INTEGRITE : propre » en code 0 — sur un
        # fichier que l'utilisateur n'avait pas demande. Pire qu'un mauvais code : une
        # verification qui porte sur autre chose que ce qu'on lui a donne.
        print()
        print(f"  Le journal demande n'existe pas : {path}")
        candidats = sorted(
            (p for p in Path(".jio").rglob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidats:
            print(f"  Journal(x) disponible(s) ici : {', '.join(str(c) for c in candidats[:3])}")
            print("  Relancez avec un de ces chemins si c'est celui que vous voulez verifier.")
        else:
            print("  Aucun journal dans ce depot : rien n'a encore ete execute.")
            print("  Un journal se cree a la premiere mission :")
            print("      jio run \"corriger la somme des pairs\" --task sum_even --simulate")
        print()
        from .core.codes import ACTION, INDETERMINE

        print(f"  -> code {INDETERMINE} : {ACTION[INDETERMINE]}")
        return INDETERMINE
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
            from .core.codes import ACTION, INDETERMINE

            print(f"  -> code {INDETERMINE} : {ACTION[INDETERMINE]}")
            return INDETERMINE
    contenu = path.read_text(encoding="utf-8", errors="replace")
    if not contenu.strip():
        # Un fichier VIDE n'est pas un journal : la chaine se verifie sur zero evenement, donc
        # « propre » ne veut rien dire. On le dit, au lieu de rendre un quitus sur du vide.
        print()
        print(f"  {path} est vide : il n'y a rien a verifier.")
        print("  Un journal vide n'est pas un journal intact — c'est un journal absent.")
        print()
        from .core.codes import ACTION, INDETERMINE

        print(f"  -> code {INDETERMINE} : {ACTION[INDETERMINE]}")
        return INDETERMINE
    journal = Journal.from_jsonl(contenu)
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
    courant = journal._sceau_du_moment()
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

    doc = sub.add_parser("doctor", help="etat du systeme")
    doc.set_defaults(func=cmd_doctor)
    doc.add_argument(
        "--root", default=".", metavar="CHEMIN",
        help="depot a diagnostiquer (defaut : le dossier courant)",
    )
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
    b.add_argument("--taches", type=int, default=0, dest="taches",
                   help="limite le banc aux N premieres taches (0 = toutes). Un premier tour "
                        "court sert a voir si le dispositif tourne, pas a mesurer un gain")
    b.add_argument("--sans-oracle-reel", action="store_true", dest="sans_oracle_reel",
                   help="n'execute PAS le bras « aucun oracle » avec votre modele (il coute "
                        "un moteur complet de plus par tirage ; c'est pourtant le cas de "
                        "toute mission reelle)")
    b.add_argument("--prose", action="store_true",
                   help="mesure le harness sur des DOCUMENTS (rapports) au lieu de code")
    b.add_argument(
        "--rapport", default="", metavar="CHEMIN.md",
        help=(
            "ECRIT le resultat de la mesure a cet emplacement (Markdown + JSON a cote). "
            "Un chiffre qui ne vit que dans un terminal ne se compare pas : le rapport date, "
            "porte les intervalles, les bras temoins et ce qu'il ne prouve PAS. C'est lui "
            "qu'on archive et qu'on transmet."
        ),
    )
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
    r.add_argument(
        "--sans-competences", action="store_true",
        help="ne PAS charger les procedures du depot dans le prompt de mission. Par defaut, le "
             "routeur en injecte jusqu'a 3 (budget 1500 jetons), choisies pour CET objectif, et "
             "le journal dit lesquelles ; ce drapeau mesure ce qu'elles apportent",
    )
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
    r.add_argument(
        "--strict", action="store_true",
        help="refuse de commencer si la porte de clarification a des questions sans reponse "
             "(code 3) : c'est le mode a utiliser quand une IA doit DEMANDER avant d'agir",
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
    # Les artefacts sont des INSTRUCTIONS executees par un agent. Les auditer est un acte de
    # securite, pas de qualite : une competence hostile s'execute avec les droits de l'agent.
    ar.add_argument(
        "--audit",
        action="store_true",
        help="verifie que les competences et les agents ne contiennent pas d'ordre dangereux",
    )
    # L'INSTALLATION chez Hermes, accessible hors de `jio start` — et surtout desinstallable :
    # une installation dont on ne peut pas revenir est une prise d'otage.
    ar.add_argument(
        "--install-hermes", dest="install_hermes", action="store_true",
        help=(
            "installe les competences dans ~/.hermes/skills (copie enregistree ; un fichier a "
            "vous n'est JAMAIS ecrase). `jio start` le fait deja : cette option sert a le "
            "refaire seul, ou dans un autre projet."
        ),
    )
    ar.add_argument(
        "--desinstaller", dest="desinstaller", action="store_true",
        help="retire de ~/.hermes/skills ce que jio y a installe — et rien d'autre",
    )
    ar.add_argument(
        "--lier", dest="lier", action="store_true",
        help=(
            "avec --install-hermes : poser des LIENS au lieu de copies (synchronisation "
            "permanente). Attention : editer la copie ecrit alors dans le fichier du projet."
        ),
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
    # L'option existait dans le rapport (« integrite : chaine valide ») mais pas dans la
    # commande : un utilisateur qui voulait VERIFIER la chaine — et obtenir un code de sortie
    # exploitable en CI — tombait sur `error: unrecognized arguments: --integrity`, code 2,
    # apres avoir lu que l'integrite etait quelque chose que l'outil savait dire.
    me.add_argument("--integrity", action="store_true",
                    help="verifie la chaine d'integrite et sort en 1 si elle est cassee "
                         "(pour un pre-commit ou une CI)")
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
    le.add_argument(
        "--cumul", default="",
        help="fichier ou EMPILER les cycles mesures (JSONL). Chaque execution est une "
             "replication independante : les graines sont decalees pour ne jamais rejouer "
             "la meme, et le rapport affiche est le CUMUL. Une mesure longue survit ainsi a "
             "une coupure, et la resolution s'accumule execution apres execution.",
    )
    le.add_argument(
        "--gain", type=float, default=0.20,
        help="gain RELATIF declare par avertissement (modelisation, defaut 0.20). Le "
             "protocole mesure l'effet d'un mecanisme DECLARE : le regler haut sert de "
             "CONTROLE POSITIF — un instrument qui ne detecte jamais un signal connu ne "
             "peut pas etre cru quand il n'en detecte aucun.",
    )
    le.add_argument(
        "--calibrer-gain", action="store_true",
        help="mesurer le gain d'avertissement par le protocole A/B au lieu de le declarer "
             "(refuse de tourner tant que ce n'est pas implemente : une modelisation non "
             "calibree borne toutes les conclusions du protocole)",
    )
    le.add_argument(
        "--plafond-missions", type=int, default=200,
        help="nombre de missions au-dela duquel le protocole multi-cycles REFUSE de "
             "mesurer (defaut 200). Ce n'est pas une limite technique : c'est un garde-fou "
             "de duree. Le relever est un choix, et il s'assume explicitement.",
    )
    le.add_argument(
        "--cycles", type=int, default=0,
        help="0 = comparaison A/B (defaut). N > 0 = protocole MULTI-CYCLES : la memoire "
             "s'accumule pendant N cycles et chaque cycle compare froid/chaud a bras "
             "IDENTIQUE (la seule variable restante est le souvenir). Cout : "
             "N x 2 x taches x runs missions — refus au-dela de 200 missions.",
    )
    le.set_defaults(func=cmd_learn)

    mu = sub.add_parser(
        "mutants",
        help="score de mutation de NOTRE suite : quelle ligne du depot aucun test ne protege ?",
    )
    mu.add_argument("--budget", type=int, default=2,
                    help="mutants par fichier (defaut 2 : le but est de mesurer, pas d'epuiser)")
    mu.add_argument("--plafond-tests", type=int, default=6,
                    help="fichiers de test lances par mutant (heuristique declaree)")
    mu.add_argument("--tout", dest="tous_les_tests", action="store_true",
                    help="lancer la suite ENTIERE pour chaque mutant (lent, exact)")
    mu.add_argument("--timeout", type=int, default=300, help="timeout par mutant (s)")
    mu.add_argument("--fichiers", default="",
                    help="liste de fichiers separes par des virgules (defaut : tout jio/)")
    mu.add_argument("--root", default=".", help="racine du depot a muter")
    mu.set_defaults(func=cmd_mutants)

    ab = sub.add_parser(
        "ablation",
        help="enleve une brique du harness et mesure ce qui change (apparie)",
    )
    ab.add_argument("--missions", type=int, default=10,
                    help="CIBLE de missions par bras (defaut 10), reparties sur les taches "
                         "du banc : le rapport dit le nombre EXACT qu'il a mesure")
    ab.add_argument("--levers", default="",
                    help="leviers a mesurer, separes par des virgules (defaut : tous). "
                         "`--levers liste` affiche les noms et ce que « sans » veut dire.")
    ab.add_argument("--skill", type=float, default=0.35, help="competence du modele simule")
    ab.add_argument("--rounds", type=int, default=int_env("JIO_MAX_ROUNDS", 4),
                    help="tours de boucle maximum")
    ab.add_argument("--sans-oracle", dest="sans_oracle", action="store_true",
                    help="retire les oracles de la mission : les regles doivent alors etre "
                         "TRADUITES en temoins (c'est la que le levier « temoins » compte)")
    ab.add_argument("--json", action="store_true", help="rapport lisible par une machine")
    ab.set_defaults(func=cmd_ablation)

    st = sub.add_parser(
        "start",
        help="INTEGRE JIO dans tes outils en une commande : detecte, ecrit, cable, prouve",
    )
    st.add_argument("--root", default=".", help="racine du projet a equiper (defaut : ici)")
    st.add_argument("--dry-run", action="store_true",
                    help="montre ce qui serait fait, sans rien ecrire")
    st.add_argument("--sans-mcp", dest="sans_mcp", action="store_true",
                    help="n'ecrit pas les fichiers de cablage MCP (artefacts seuls)")
    st.add_argument(
        "--sans-hermes", dest="sans_hermes", action="store_true",
        help=(
            "n'installe PAS les competences dans ~/.hermes/skills. Par defaut `jio start` les y "
            "installe (par LIEN, pour qu'une mise a jour du depot les mette a jour), sans jamais "
            "ecraser un fichier qui n'est pas de nous."
        ),
    )
    st.set_defaults(func=cmd_start)

    au = sub.add_parser(
        "auto",
        help="travaille SEUL sur un plan dont chaque etape doit porter sa preuve",
    )
    au.add_argument("objective", nargs="?", default="", help="l'objectif global")
    au.add_argument("--cible", default="jio", help="cible du plan (chemin, module)")
    au.add_argument("--entrypoint", default="", help="fonction attendue, si le plan en a besoin")
    au.add_argument(
        "--budget", type=int, default=6,
        help="nombre maximum d'etapes executees (defaut 6) : au-dela, le reste est declare "
             "NON TENTE au lieu d'etre fait en silence",
    )
    au.add_argument(
        "--plan", default="", metavar="FICHIER",
        help="plan JSON a executer. Sans ce fichier, un plan de REFERENCE deterministe est "
             "utilise et ANNONCE comme tel (le modele reel fournirait le sien)",
    )
    au.add_argument("--strict", action="store_true",
                    help="refuse de commencer si la porte de clarification a des questions")
    au.add_argument("--etat", default=".jio/plan.json", help="ou enregistrer l'etat du plan")
    au.add_argument("--root", default=".",
                    help="racine du projet (les preuves s'executent LA, l'etat y est ecrit) : "
                         "une IA peut travailler sur un depot qu'elle n'a pas ouvert comme "
                         "repertoire courant")
    au.add_argument("--reprendre", action="store_true",
                    help="reprend le plan enregistre dans --etat : les etapes deja PROUVEES sont "
                         "sautees SI la revision git n'a pas bouge ; sinon le plan est rejoue "
                         "ENTIER, parce qu'une preuve obtenue dans un autre monde ne vaut rien")
    au.add_argument("--json", action="store_true", help="resultat lisible par une machine")
    au.set_defaults(func=cmd_auto)

    cl = sub.add_parser(
        "clarify",
        help="pose les questions ESSENTIELLES avant de travailler (ou dit qu'il n'y en a pas)",
    )
    cl.add_argument("objective", nargs="?", default="", help="l'objectif, tel qu'ecrit")
    cl.add_argument("--contexte", default="",
                    help="fichier dont le contenu peut fournir ce qui manque (README, "
                         "AGENTS.md) : un objectif court dans un projet documente n'est "
                         "pas ambigu")
    cl.add_argument("--strict", action="store_true",
                    help="code de sortie 3 si des questions restent sans reponse (a utiliser "
                         "quand une IA doit DEMANDER avant d'agir)")
    cl.add_argument("--json", action="store_true", help="analyse lisible par une machine")
    cl.add_argument(
        "--controle", dest="controle", action="store_true",
        help="passer a la porte le jeu de CONTROLE : des objectifs d'un AUTRE projet "
             "(aucun chemin de ce depot) — le banc seul ne peut pas dire si la porte "
             "generalise hors de ce depot",
    )
    cl.add_argument(
        "--mesure", "--bench", dest="mesure", action="store_true",
        help="mesure la porte sur le banc d'objectifs REELS annote a la main "
             "(`jio/bench/objectifs.py`) : precision, rappel, et chaque erreur en clair",
    )
    cl.add_argument("--max", type=int, default=MAX_QUESTIONS, dest="maximum",
                    help=f"nombre maximum de questions (defaut {MAX_QUESTIONS})")
    cl.set_defaults(func=cmd_clarify)

    pr = sub.add_parser(
        "pr",
        help="genere le corps de la PR a partir des COMMITS (rapport reconstruit, jamais recopie)",
    )
    pr.add_argument("--root", default=".", help="depot a resumer")
    pr.add_argument("--depuis", default="", help="ref de base (defaut : la branche par defaut du "
                                                 "depot, puis main, puis master, puis la racine)")
    pr.add_argument("--sortie", default="", help="fichier a ecrire (defaut : la sortie standard, "
                                                 "aucune ecriture)")
    pr.add_argument("--limite", type=int, default=0,
                    help="longueur maximale en caracteres (0 = sans limite). Au-dela, le rapport "
                         "garde la LISTE complete des commits et le DETAIL des plus recents, et "
                         "DECLARE ce qu'il a omis. GitHub limite un corps de PR a 65536")
    pr.add_argument("--complet", default="",
                    help="fichier ou ecrire AUSSI le rapport non tronque (facultatif : il se "
                         "regenere par `jio pr` sans option)")
    pr.set_defaults(func=cmd_pr)

    sk = sub.add_parser(
        "skills",
        help="QUELLES competences charger pour cet objectif, et pourquoi — la question qui rend "
             "la bibliotheque utile sans la charger en entier",
    )
    sk.add_argument("objectif", nargs="*", help="l'objectif, en une phrase (entre guillemets)")
    sk.add_argument("--maximum", type=int, default=3, help="nombre de competences a charger (3)")
    sk.add_argument("--banc", action="store_true",
                    help="passer le banc annote au routeur et a ses temoins (mesure, pas avis)")
    sk.add_argument("--seuil", type=int, default=-1,
                    help="nombre de concepts de domaine en dessous duquel ne rien charger "
                         "(defaut : la valeur mesuree). 0 = ne jamais s'abstenir, -1 = defaut")
    sk.add_argument("--controle", action="store_true",
                    help="passer au routeur le jeu de CONTROLE : des objectifs jamais vus, "
                         "ecrits AVANT la derniere retouche des fiches — l'ecart avec le banc "
                         "est la generalisation reelle")
    sk.add_argument("--seuil-balaye", action="store_true",
                    help="le seuil contre ses consequences : rappel et abstentions justes")
    sk.add_argument("--json", action="store_true", help="verdict lisible par une machine")
    sk.set_defaults(func=cmd_skills)

    so = sub.add_parser(
        "sorties",
        help="les exemples de sortie declares dans les documents sont-ils ENCORE la sortie "
             "reelle des outils ?",
    )
    so.add_argument("--root", default=".", help="racine du depot (.)")
    so.add_argument("--document", default="",
                    help="un seul document (defaut : les documents du depot)")
    so.add_argument("--appliquer", action="store_true",
                    help="reecrire les blocs `sortie-exacte` perimes, avec sauvegarde "
                         "`.avant-jio`. Les extraits ne sont JAMAIS reecrits : choisir les "
                         "lignes a montrer demanderait de deviner l'intention")
    so.add_argument("--liste", action="store_true",
                    help="ce que chaque document promet, sans rien executer")
    so.add_argument("--json", action="store_true", help="verdict lisible par une machine")
    so.set_defaults(func=cmd_sorties)

    co = sub.add_parser(
        "coherence",
        help="LES NEUF CONTROLES d'un coup : tout ce que ce depot affirme est-il encore vrai ?",
    )
    co.add_argument("--root", default=".", help="racine du depot a controler")
    co.add_argument(
        "--reparer", action="store_true",
        help="repare ce qui est MECANIQUE (artefacts generes, valeurs mesurees), puis repasse la "
             "porte. Ne touche JAMAIS a ce qui demanderait d'inventer : un document faux, une "
             "competence dangereuse, une commande inexistante, un journal casse (une piece a "
             "conviction ne se lave pas)",
    )
    co.add_argument("--json", action="store_true", help="verdict lisible par une machine")
    co.set_defaults(func=cmd_coherence)

    return p


def cmd_ablation(args: argparse.Namespace) -> int:
    """Mesure ce que chaque brique du harness apporte REELLEMENT.

    Le principe : au lieu d'affirmer qu'une brique sert, on l'ENLEVE et on compare sur les
    MEMES missions (appariement par tache et par graine). Ce qui change est son apport.
    La metrique qui decide n'est pas le taux de reussite mais le nombre d'erreurs
    SILENCIEUSES — livrees sans reserve et fausses : c'est ce que le harness existe pour
    empecher. Une seule erreur silencieuse apparue a l'ablation est une preuve d'existence,
    qu'aucune statistique ne relativise ; un levier sans effet visible est declare NON
    DISTINGUABLE, jamais « inutile ».

    Code de sortie : 1 si le moteur COMPLET livre une erreur silencieuse (le harness a
    failli a son travail), 0 sinon — un levier non distingue n'est pas une panne, c'est une
    mesure honnete.
    """
    from .bench.ablation import LEVIERS, Issue, appliquer, formater, levier, mesurer

    if args.levers.strip() == "liste":
        print()
        print("  LEVIERS MESURABLES")
        print()
        for lev in LEVIERS:
            print(f"    {lev.nom:<14} {lev.quoi}")
            print(f"    {'':<14} sans : {lev.sans}")
        print()
        return 0

    noms = [n.strip() for n in args.levers.split(",") if n.strip()] or None
    try:
        for nom in noms or []:
            levier(nom)
    except KeyError as exc:
        print(f"  {exc.args[0]}", file=sys.stderr)
        return 2

    missions = max(1, args.missions)
    taches = min(len(TASKS), missions)
    graines = max(1, math.ceil(missions / taches))

    def executer(indice: int, graine: int, ablations: tuple[str, ...]) -> Issue:
        tache: Task = TASKS[indice % len(TASKS)]
        moteur = _simulated_engine(
            tache,
            skill=args.skill,
            seed=graine,
            max_rounds=args.rounds,
            # Sans oracle, la traduction des regles en temoins est ce qui REMPLACE les
            # tests absents : sans elle, le moteur ne peut que s'abstenir et on mesurerait
            # l'absence d'oracle au lieu de l'apport du levier.
            traducteur=(
                TraducteurSimule(taches=TASKS, fidelite=1.0) if args.sans_oracle else None
            ),
        )
        appliquer(moteur, ablations)
        debut = time.monotonic()
        rapport = moteur.run(
            Mission(objective=tache.objective, id=f"{tache.id}-{graine}", max_rounds=args.rounds),
            WorkItem(
                objective=tache.objective,
                entrypoint=tache.entrypoint,
                # En mode sans oracle, la mission ne fournit AUCUN test : le moteur doit
                # traduire les regles lui-meme, et sans cette traduction il ne peut rien
                # prouver. C'est le seul mode ou le levier « temoins » est mesurable.
                checks={} if args.sans_oracle else tache.checks,
                spec=tache.spec(),
            ),
        )
        duree = time.monotonic() - debut
        juste = _check(rapport.subject, tache)
        sans_reserve = rapport.status is MissionStatus.DELIVERED
        avec_reserve = rapport.status is MissionStatus.DELIVERED_WITH_RESERVATION
        return Issue(
            juste=juste,
            livree=sans_reserve,
            reservee=avec_reserve,
            # Livree SANS reserve et fausse. « Avec reserve » n'est pas silencieux : le
            # systeme a dit quelque chose, et c'est toute la difference que ce module
            # mesure. Les confondre effacerait le seul chiffre qui compte.
            silencieuse=sans_reserve and not juste,
            abstention=rapport.status is MissionStatus.ABSTAINED,
            appels=int(rapport.usage.get("calls", 0)) or 1,
            duree_s=duree,
        )

    print(BANNER)
    print(f"  Ablation du harness  ·  competence simulee {args.skill:.2f}  ·  "
          f"{taches * graines} mission(s) par bras  ·  {len(noms) if noms else len(LEVIERS)} levier(s)"
          + ("  ·  SANS ORACLE" if args.sans_oracle else ""))
    print("  Aucune cle API requise : les reponses sont simulees, la VERIFICATION est reelle.")
    print()
    rapport = mesurer(
        executer, taches=taches, graines=graines, leviers=noms,
        # Le progres va sur la sortie d'erreur, avec le temps ecoule : il sert a DECIDER s'il
        # faut attendre ou interrompre. Sans lui, la commande est indistinguable d'un blocage.
        avancer=_Progression(
            taches * graines * ((len(noms) if noms else len(LEVIERS)) + 1),
            quoi="ablation",
        ),
    )
    if args.json:
        _charge_utile(json.dumps(rapport.en_dict(), ensure_ascii=False, indent=2))
        return 1 if rapport.silencieuses else 0
    print(formater(rapport))
    print()
    prouves = len(rapport.prouves)
    non_distingues = len(rapport.non_distingues)
    couts = len(rapport.couts)
    print(f"    {prouves} levier(s) prouve(s) par l'ablation  ·  "
          f"{couts} au cout mesure (le retrait AMELIORE)  ·  "
          f"{non_distingues} non distingue(s)  ·  "
          f"{rapport.silencieuses} erreur(s) silencieuse(s) du moteur complet")
    if rapport.silencieuses:
        print("    -> le moteur COMPLET a livre une erreur sans reserve : c'est un defaut")
        print("       du harness, pas du levier. A corriger avant toute autre mesure.")
        return 1
    print("    -> le moteur complet n'a livre aucune erreur sans reserve sur ces missions.")
    return 0


def cmd_mutants(args: argparse.Namespace) -> int:
    """Mesure ce que la suite de tests du depot attrape REELLEMENT.

    Le principe est celui de la porte de mutation, applique au depot lui-meme : un test
    qui ne peut pas echouer ne tient rien. Chaque survivant est une ligne du depot sans
    preuve, et le code de sortie vaut 1 tant qu'il en reste un — un chiffre qu'on peut
    citer sans le mesurer serait exactement ce que ce depot refuse.
    """
    from .verify.mutants_suite import formater, mesurer

    racine = Path(args.root).resolve()
    if not (racine / "tests").is_dir():
        # « Rien a mesurer » n'est pas « tout va bien » : sans dossier de tests, le score de
        # mutation est IMPOSSIBLE, pas bon. Rendre 0 ferait passer une CI sur une absence —
        # meme doctrine que `jio trace` sans journal (voir `jio/core/codes.py`).
        from .core.codes import ACTION, INDETERMINE

        print(f"  aucun dossier tests/ sous {racine} : rien a mesurer.")
        print(f"  -> code {INDETERMINE} : {ACTION[INDETERMINE]}")
        return INDETERMINE
    fichiers = None
    if args.fichiers:
        fichiers = [
            (racine / nom.strip()) for nom in args.fichiers.split(",") if nom.strip()
        ]
    rapport = mesurer(
        racine,
        fichiers=fichiers,
        budget_par_fichier=max(1, args.budget),
        plafond_tests=max(1, args.plafond_tests),
        timeout=max(30, args.timeout),
        tous_les_tests=args.tous_les_tests,
    )
    print()
    print(formater(rapport))
    print()
    if not rapport.mutants:
        print("    aucun mutant mesure : le score serait un chiffre sans contenu.")
        return 1
    # Le verdict porte sur les survivants CONFIRMES : un survivant apparent a ete tue par la
    # suite complete, donc il n'y a aucune ligne du depot sans preuve. Sortir en echec pour une
    # erreur de SELECTION ferait passer un probleme d'outil pour un probleme de code — et
    # l'utilisateur corrigerait le mauvais.
    if rapport.confirmes:
        print(f"    -> {len(rapport.confirmes)} ligne(s) du depot sans preuve. Chacune demande")
        print("       soit un test, soit une raison ECRITE de ne pas en avoir.")
        return 1
    if rapport.apparents:
        print(f"    -> aucune ligne sans preuve : les {len(rapport.apparents)} survivant(s) "
              "apparent(s) viennent")
        print("       de la SELECTION de tests, pas du code. Relancer avec `--tout` les confirme.")
        return 0
    print("    -> la suite attrape chaque mutation mesuree : les affirmations du depot")
    print("       sont tenues par des tests qui savent echouer.")
    return 0


def cmd_pr(args: argparse.Namespace) -> int:
    """`jio pr` : le corps de la PR, reconstruit depuis les commits.

    Ne fait que deux choses : lire le depot et ecrire un fichier si on le demande. C'est
    volontaire — un generateur qui decide de ce qu'il faut dire devient une plaidoirie, et
    ce document sert precisement a ce qu'on puisse VERIFIER ce qui a ete fait.
    """
    from .pr import GitAbsent, construire, ecrire

    racine = Path(getattr(args, "root", ".") or ".").expanduser()
    depuis = (getattr(args, "depuis", "") or "").strip() or None
    limite = int(getattr(args, "limite", 0) or 0) or None
    complet = (getattr(args, "complet", "") or "").strip()
    try:
        corps = construire(racine, depuis=depuis, limite=limite, complet=complet)
    except GitAbsent as exc:
        print(f"  corps de la PR impossible : {exc}", file=sys.stderr)
        print("  Ce rapport resume des COMMITS : sans depot git, il n'y a rien a resumer.",
              file=sys.stderr)
        return 1

    sortie = (getattr(args, "sortie", "") or "").strip()
    if not sortie:
        print(corps)
        return 0

    if complet:
        # Le rapport NON TRONQUE, ecrit a part et dans le meme mouvement : separer les deux
        # ecritures laisserait la porte ouverte a un rapport complet d'une generation et un
        # corps d'une autre.
        entier = construire(racine, depuis=depuis)
        ecrire(complet, entier)
        print(f"  {complet} — rapport complet, non tronque ({len(entier)} octets)")

    sauvegarde, ecrit = ecrire(sortie, corps)
    chemin = Path(sortie)
    if not ecrit:
        print(f"  {chemin} — inchange, rien n'a ete reecrit "
              f"({len(corps)} octets, identiques)")
        return 0
    print(f"  {chemin} — {len(corps)} octet(s) ecrit(s)")
    if sauvegarde is not None:
        print(f"  version precedente conservee : {sauvegarde.name}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    """`jio skills` : le routeur de competences — quelles competences charger, et POURQUOI.

    Trois modes, et le troisieme est le juge des deux premiers :

      * `jio skills "<objectif>"`        le classement, avec les termes qui l'ont produit ;
      * `jio skills --banc`              la mesure sur le banc annote, temoins compris ;
      * `jio skills --seuil-balaye`      le seuil d'abstention contre ses consequences.

    Un classement sans raison affichee n'est pas verifiable, et un routeur non verifie n'est
    qu'un gout personnel. Chaque choix porte donc les termes qui l'ont fait gagner, et la
    reponse NEGATIVE (« aucune competence ne s'applique ») est un resultat de plein droit :
    charger une procedure qui ne s'applique pas coute plus cher que ne rien charger.
    """
    from .skills import (
        SEUIL_CONCEPTS,
        balayer_seuils,
        catalogue_du_depot,
        choisir,
        comparer,
        cout,
        mesurer,
    )
    from .skills.banc import BANC

    if getattr(args, "seuil_balaye", False):
        print()
        print("  LE SEUIL D'ABSTENTION CONTRE SES CONSEQUENCES")
        print()
        print(f"    {'concepts':>9}  {'equilibre':>9}  {'abstention juste':>16}  {'rappel':>7}")
        for seuil, equilibre, negatifs, rappel in balayer_seuils(maximum=args.maximum):
            marque = "  <- retenu" if seuil == SEUIL_CONCEPTS else ""
            print(f"    {seuil:>9}  {equilibre:>9.3f}  {negatifs:>10}/{len([o for o in BANC if not o.positif]):<5}  {rappel:>6}%{marque}")
        print()
        print("  Le seuil porte sur le nombre de CONCEPTS de domaine que l'objectif met en jeu,")
        print("  jamais sur un score : un score BM25 n'a pas d'unite, donc pas de seuil honnete.")
        print()
        return 0

    if getattr(args, "controle", False):
        from .skills.controle import CAS, resume

        print()
        print("  LE JEU DE CONTROLE — la mesure que le banc ne peut pas faire")
        print()
        print(resume())
        print()
        for objectif, attendu, langue in CAS:
            obtenu = choisir(objectif, maximum=args.maximum)
            premier = obtenu[0].nom if obtenu else "(abstention)"
            marque = "ok " if premier == attendu else "RATE"
            print(f"    [{marque}] [{langue}] {objectif[:66]}")
            if premier != attendu:
                print(f"           attendu {attendu} — obtenu {premier}")
        print()
        return 0

    if getattr(args, "banc", False):
        print()
        print("  LE ROUTEUR ET SES TEMOINS SUR LE MEME BANC ANNOTE")
        print()
        rapport = mesurer(maximum=args.maximum)
        for nom, resume, equilibre in comparer(maximum=args.maximum):
            marque = "routeur" if nom.startswith("routeur") else "temoin "
            print(f"    [{marque}] {nom:<20} equilibre {equilibre:.3f}")
            print(f"             {resume}")
        print()
        print(f"    banc : {len(BANC)} objectifs, "
              f"{len([o for o in BANC if o.positif])} pertinents / "
              f"{len([o for o in BANC if not o.positif])} hors sujet")
        for erreur in rapport.erreurs:
            print(f"      {erreur}")
        print()
        print("  Le banc est la LIMITE de l'affirmation, pas sa preuve : il a ete ecrit par la")
        print("  personne qui a ecrit le routeur. Ce qui vaut ici est l'ECART aux temoins —")
        print("  `alphabetique` dit ce que vaut un choix qui ne regarde pas l'objectif, et")
        print("  `mots-cles bruts` ce que BM25, la saturation et la ponderation apportent.")
        print()
        from .skills.controle import mesurer as mesurer_controle
        ctrl = mesurer_controle()
        print(f"  ET SUR DES OBJECTIFS JAMAIS VUS (`jio skills --controle`) : "
              f"{ctrl['premier_choix']:.0%} de premier choix juste "
              f"({ctrl['premier_choix_en']:.0%} en anglais). L'ecart avec le banc est la")
        print("  generalisation reelle du routeur : le banc seul ne peut pas la montrer.")
        print()
        return 0

    objectif = " ".join(getattr(args, "objectif", []) or []).strip()
    if not objectif:
        print()
        print("  usage : jio skills \"<objectif en une phrase>\"")
        print("          jio skills --banc            (la mesure sur le banc annote)")
        print("          jio skills --controle        (des objectifs JAMAIS VUS : le banc ne")
        print("                                        peut pas mesurer la generalisation)")
        print("          jio skills --seuil-balaye    (le seuil d'abstention et ses consequences)")
        print()
        catalogue = catalogue_du_depot()
        fiches = sum(d.cout_jetons for d in catalogue.documents)
        corps = sum(1 for d in catalogue.documents)  # le nombre, pour la phrase ci-dessous
        print(f"  {corps} competences disponibles.")
        print(f"  Les ENUMERER (fiche tier 0) coute {fiches} jetons ; charger leurs CORPS en coute")
        print(f"  environ 6424. Le routeur en charge {args.maximum} au plus, et dit pourquoi.")
        print()
        return 0

    seuil = args.seuil if getattr(args, "seuil", -1) >= 0 else SEUIL_CONCEPTS
    choix = choisir(objectif, maximum=args.maximum, seuil=seuil)

    if getattr(args, "json", False):
        import json

        _charge_utile(json.dumps(
            {
                "objectif": objectif,
                "seuil_concepts": seuil,
                "choix": [
                    {"nom": c.nom, "categorie": c.categorie, "score": c.score,
                     "raisons": list(c.raisons), "cout_jetons": c.cout_jetons}
                    for c in choix
                ],
                "cout_jetons": cout(choix),
            },
            ensure_ascii=False, indent=2,
        ))
        return 0 if choix else 0

    print()
    print(f"  OBJECTIF  {objectif}")
    print()
    if not choix:
        print("  AUCUNE COMPETENCE A CHARGER")
        print()
        print(f"  Moins de {seuil} concept(s) de domaine reconnu(s) dans l'objectif : rien ne")
        print("  garantit qu'une competence s'applique ici. Charger une procedure hors sujet")
        print("  coute plus cher que ne rien charger — elle detourne le travail en plus de")
        print("  l'occuper. Pour forcer une reponse, baissez le seuil :")
        print()
        print("      jio skills \"...\" --seuil 0")
        print()
        return 0

    for rang, c in enumerate(choix, start=1):
        print(f"  {rang}. {c.nom}  [{c.categorie}]  score {c.score}  {c.cout_jetons} jetons")
        print(f"     pourquoi : {', '.join(c.raisons) if c.raisons else 'aucun terme commun'}")
    fiches = sum(d.cout_jetons for d in catalogue_du_depot().documents)
    desordre = any(choix[i].score > choix[i - 1].score for i in range(1, len(choix)))
    if desordre:
        print()
        print("  L'ordre n'est pas exactement celui des scores : la DIVERSIFICATION a fait")
        print("  passer devant une competence moins bien classee mais qui n'apprend rien de")
        print("  plus que la precedente. Deux competences quasi identiques occuperaient deux")
        print("  places dans le contexte pour une seule information.")
    print()
    print(f"  cout d'injection : {cout(choix)} jetons, contre {fiches} pour la fiche tier 0 des 12")
    print("  competences et environ 6424 pour leurs corps : le choix est ce qui rend la")
    print("  bibliotheque abordable, pas sa taille.")
    print()
    return 0


def cmd_sorties(args: argparse.Namespace) -> int:
    """`jio sorties` : les exemples de sortie des documents contre la sortie REELLE.

    Un document qui montre `jio artifacts --budget` affirme ce que l'outil repond. Cette
    affirmation vieillit toute seule : elle est longue, datee, pleine de chiffres, et personne
    ne relit une capture d'ecran. Ce depot en a fait l'experience — le README annoncait
    « 11 fichier(s), ~5715 jetons » alors que l'outil disait 12 et 6424, pendant que la porte
    annoncait neuf controles verts.

    Un `<!-- sortie: jio ... -->` est donc un CONTRAT : soit les lignes montrees se retrouvent
    dans la sortie reelle (extrait, coupures declarees par `...`), soit le document est faux.
    Les commandes sont executees en LISTE d'arguments, sans shell, et seules les commandes
    `jio` sans option d'ecriture sont acceptees : un document est un contenu hostile par defaut.
    """
    import json as _json

    from .verify.sorties import blocs, liste as lister, reparer, verifier

    racine = Path(getattr(args, "root", ".") or ".").expanduser()
    document = (getattr(args, "document", "") or "").strip()

    if document:
        chemin = Path(document) if Path(document).is_absolute() else racine / document
        if not chemin.is_file():
            # DEFAUT MESURE : `jio sorties --document /tmp/absent.md` repondait « aucun exemple
            # declare dans ces documents » et rendait 0 — il ne verifiait RIEN, mais il le disait
            # comme un resultat. Verifier un document nomme qui n'existe pas est impossible :
            # c'est INDETERMINE, et l'appelant doit fournir le document.
            from .core.codes import ACTION, INDETERMINE

            print()
            print(f"  Le document demande n'existe pas : {chemin}")
            print("  Rien n'a ete verifie — et une verification qui n'a pas eu lieu n'est pas")
            print("  un succes. Sans `--document`, la commande parcourt les documents du depot.")
            print()
            print(f"  -> code {INDETERMINE} : {ACTION[INDETERMINE]}")
            return INDETERMINE
        chemins = [chemin]
    else:
        from .verify.coherence import _documents

        chemins = [c for c in _documents(racine)]
    chemins = [c for c in chemins if c.is_file()]

    if getattr(args, "liste", False):
        print()
        print("  CE QUE CHAQUE DOCUMENT PROMET  ·  aucun effet de bord")
        print()
        total = 0
        for chemin in chemins:
            lignes = lister(chemin.read_text(encoding="utf-8", errors="replace"))
            if not lignes:
                continue
            print(f"    {chemin.name}")
            for ligne in lignes:
                print(f"    {ligne}")
            total += len(lignes)
        print()
        print(f"    TOTAL : {total} exemple(s) declare(s) sur {len(chemins)} document(s)")
        if not total:
            print("    Un exemple non declare n'est verifie par RIEN : c'est ainsi qu'un")
            print("    README a pu annoncer « 11 fichier(s), ~5715 jetons » sans que")
            print("    personne ne le relise.")
        print()
        return 0

    if getattr(args, "appliquer", False):
        code_total = 0
        print()
        for chemin in chemins:
            code, signalements, message = reparer(chemin, racine)
            code_total = max(code_total, code)
            print(f"    [{ 'ok ' if code == 0 else 'ko ' }] {chemin.name} : {message}")
            for signalement in signalements[:8]:
                print(f"          {signalement}")
        print()
        return code_total

    divergences: list[tuple[str, str]] = []
    total_blocs = 0
    for chemin in chemins:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        total_blocs += len(blocs(texte))
        for divergence in verifier(texte, racine):
            divergences.append((chemin.name, str(divergence)))

    if getattr(args, "json", False):
        _charge_utile(_json.dumps(
            {
                "documents": [str(c) for c in chemins],
                "blocs": total_blocs,
                "divergences": [{"document": d, "detail": t} for d, t in divergences],
            },
            ensure_ascii=False, indent=2,
        ))
        return 1 if divergences else 0

    print()
    print("  EXEMPLES DE SORTIE D'OUTIL  ·  ce que le document montre est-il encore vrai ?")
    print()
    if not total_blocs:
        print("    aucun exemple declare dans ces documents.")
        print()
        print("    Un bloc se declare en nommant la commande qui doit le produire :")
        print()
        print("        <!-- sortie: jio artifacts --budget -->")
        print("        ... les lignes de la sortie ...")
        print("        <!-- /sortie -->")
        print()
        print("    `sortie:` accepte un extrait, les coupures etant declarees par `...` ;")
        print("    `sortie-exacte:` exige la sortie complete (celui-la se repare tout seul).")
        print()
        return 0
    if divergences:
        print(f"    {len(divergences)} bloc(s) sur {total_blocs} ne correspondent plus :")
        print()
        for document, detail in divergences[:10]:
            print(f"    {document} · {detail}")
        print()
        print("    Relancez avec --appliquer pour reecrire les blocs `sortie-exacte`.")
        print("    Les extraits ne sont pas reecrits : choisir les lignes a montrer")
        print("    demanderait de deviner — le document doit etre corrige a la main.")
        print()
        return 1
    print(f"    {total_blocs} exemple(s) verifie(s) : chacun est un EXTRAIT fidele de la")
    print("    sortie reelle de sa commande. Les lignes sautees sont celles declarees par")
    print("    `...`, et les commandes tournent sans shell, en liste d'arguments.")
    print()
    return 0


def cmd_coherence(args: argparse.Namespace) -> int:
    """`jio coherence` : neuf controles, un verdict, et la preuve de chaque constat.

    Passe d'un coup ce que le depot sait verifier separement — artefacts, chiffres, documents,
    commandes citees, variables d'environnement, portes du paquet, plan autonome. Le code de
    sortie vaut 0 seulement si TOUT est coherent : c'est un PORTAIL, donc un appelant
    automatise peut declarer « fini » sur cette base au lieu de le croire.

    Trois familles d'incoherences, toutes arrivees ici : un document qui annoncait un nombre
    de tests d'une autre epoque, un artefact qui citait une commande inexistante, un fichier
    de contexte au-dela de sa propre limite. Aucune n'etait un bug du code — toutes etaient
    des affirmations devenues fausses que personne ne relisait.
    """
    import json as _json

    from .verify.coherence import controler, formater, reparer

    print(BANNER)
    racine = getattr(args, "root", ".") or "."
    if getattr(args, "reparer", False):
        rapport, faits, restants = reparer(racine)
        print("  REPARATION  ·  ce qui est mecanique seulement")
        if faits:
            for fait in faits:
                print(f"    [fait] {fait[:92]}")
        else:
            print("    aucune reparation mecanique n'etait possible")
        if restants:
            print()
            print("    CE QUI ATTEND UNE DECISION HUMAINE (jamais devine a votre place) :")
            for reste in restants:
                print(f"      - {reste[:92]}")
        print()
        rapport = controler(racine)
    else:
        rapport = controler(racine)
    if getattr(args, "json", False):
        _charge_utile(_json.dumps(rapport.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(formater(rapport))
    return rapport.code


def cmd_clarify(args: argparse.Namespace) -> int:
    """Pose les questions essentielles — ou dit qu'il n'y en a pas, et pourquoi.

    Sortie : 0 si l'objectif est actionnable (travaille), 3 s'il manque quelque chose
    d'essentiel et que `--strict` est demande (l'appelant doit alors POSER les questions),
    1 si l'objectif est vide.

    Cette commande existe pour une seule raison : une IA qui part sans question choisit a la
    place de son utilisateur, et livre quelque chose de plausible qui repond a une autre
    question. Une IA qui pose quinze questions est insupportable. Le milieu est mesurable :
    au plus trois questions, chacune pesant une consequence ecrite.
    """
    from .clarify import analyser, formater, resume

    if getattr(args, "controle", False):
        from .bench.controle_clarify import CAS, resume_controle

        print(BANNER)
        print(resume_controle())
        print()
        for objectif, question_attendue, langue in CAS:
            analyse = analyser(objectif)
            obtenu = bool(analyse.questions)
            marque = "ok " if obtenu == question_attendue else "RATE"
            attendu = "question" if question_attendue else "travaille"
            print(f"    [{marque}] [{langue}] {objectif[:64]}")
            if obtenu != question_attendue:
                obtenu_txt = "question posee" if obtenu else "partie sans demander"
                print(f"           attendu : {attendu} — obtenu : {obtenu_txt}")
        return 0

    if getattr(args, "mesure", False):
        from .bench.objectifs import formater as formater_banc, mesurer as mesurer_banc

        rapport = mesurer_banc()
        print(BANNER)
        print(formater_banc(rapport))
        print()
        if not rapport.exact:
            print("    -> la porte se trompe : chaque erreur ci-dessus est un cas a corriger")
            print("       avant de lui faire confiance sur une vraie mission.")
            return 1
        from .bench.controle_clarify import mesurer_controle

        controle = mesurer_controle()
        print("    -> sur ce corpus annote, la porte ne se trompe pas. Le corpus est la")
        print("       limite de cette affirmation, et il est ecrit dans le depot.")
        print()
        print(f"    ET SUR DES OBJECTIFS D'UN AUTRE PROJET (`jio clarify --controle`) : "
              f"{controle['exactitude']:.0%} d'exactitude "
              f"({controle['exactitude_en']:.0%} en anglais, "
              f"{controle['exactitude_fr']:.0%} en francais), "
              f"{controle['faux_positifs']:.0f} question(s) inutile(s).")
        print("       Le banc cite les chemins de CE depot : il ne peut pas dire si la porte")
        print("       fonctionne sur le projet de quelqu'un d'autre.")
        return 0

    contexte = ""
    if args.contexte:
        chemin = Path(args.contexte).expanduser()
        if chemin.is_file():
            contexte = chemin.read_text(encoding="utf-8", errors="replace")[:200_000]
        else:
            print(f"  contexte introuvable : {chemin} (ignore, et dit)", file=sys.stderr)

    mode = "strict" if args.strict else "assume"
    analyse = analyser(
        args.objective, contexte=contexte, max_questions=max(1, args.maximum), mode=mode
    )
    if args.json:
        _charge_utile(json.dumps(analyse.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(BANNER)
        print(formater(analyse))
        print()
        print(f"    {resume(analyse)}")
        print()
    if not analyse.objectif:
        return 1
    if analyse.bloquant:
        print("    -> QUESTIONS EN ATTENTE : je ne commence pas avant tes reponses.")
        print("       (mode strict : c'est la seule facon de ne pas deviner a ta place.)")
        return 3
    if analyse.questions:
        print("    -> HYPOTHESES DECLAREES (mode assume) : je commence, et je les annonce.")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """INTEGRE JIO dans les outils deja installes, sans rien demander : une seule commande.

    C'est la commande de la premiere minute, et elle doit marcher sans cle d'API, sans
    configuration, et sans rien detruire :

      1. ecrit les artefacts natifs de tous les dialectes (AGENTS.md, CLAUDE.md, GEMINI.md,
         .cursor, Copilot, agents opencode, competences Hermes) ;
      2. cable le serveur MCP dans les fichiers de configuration que CHAQUE outil lit
         vraiment, et jamais dans un fichier qui existe deja sans nous ;
      3. PROUVE le cablage en demarrant reellement le serveur MCP et en comptant les outils
         qu'il sert : une configuration correcte qui ne branche rien est le defaut que cette
         commande existe pour attraper ;
      4. ecrit `.jio/ACTIVE.md`, la fiche que l'IA lit en premier — etat reel, commandes
         utiles, et ce qui reste non verifie.

    Elle est IDEMPOTENTE : relancee, elle ne reecrit rien et le dit.
    """
    from .artifacts import TARGETS, manifest
    from .artifacts.wiring import (
        _COMMANDE as _COMMANDE_DEFAUT,
        DIALECTES,
        NOM_SERVEUR,
        brancher,
        commande_qui_marche,
        prouver_branchement,
    )
    from .artifacts.write_guard import ecrire_manifest
    from .providers.registry import detect_clis

    racine = Path(args.root).expanduser().resolve()
    etat = racine / ".jio"
    detectees = [p.name.replace("cli::", "") for p in detect_clis()]
    # LA COMMANDE QUI MARCHE ICI, resolue une fois et utilisee partout : les artefacts ecrits,
    # les fragments affiches et la preuve parlent alors de la MEME commande. Mesure faite sur un
    # projet etranger : `python3 -m jio.mcp_server` y sert zero outil (il resout `jio` par le
    # dossier courant), la configuration etait ecrite quand meme, et la preuve — correcte —
    # arrivait APRES la panne. Une integration qui s'avere fausse en le disant reste fausse.
    commande, note_commande = (
        commande_qui_marche(racine=racine) if not args.sans_mcp else (_COMMANDE_DEFAUT, "")
    )

    print(BANNER)
    print(f"  INTEGRATION  ·  racine : {racine}")
    if detectees:
        print(f"  Outils detectes sur cette machine : {', '.join(detectees)}")
    else:
        print("  Aucune CLI d'agent detectee sur le PATH : les artefacts seront ecrits")
        print("  quand meme (ils sont lus par l'outil qui ouvrira ce dossier).")
    print()

    # `--sans-mcp` retire les cibles de CABLAGE autant que l'etape `brancher` : `opencode.json`
    # et `.hermes/mcp-fragment.yaml` SONT du cablage. La premiere version les ecrivait quand
    # meme, donc l'option ne tenait pas ce que son nom promettait — trouve par
    # `tests/test_start.py`, qui a vu `opencode.json` dans une racine en `--sans-mcp`.
    cibles = tuple(t for t in TARGETS if not (args.sans_mcp and t.endswith("-mcp")))

    if args.dry_run:
        for rel in sorted(manifest(cibles)):
            print(f"    [simulation] {rel}")
        print()
        print("    mode simulation : rien n'a ete ecrit. Relance SANS --dry-run.")
        return 0

    decisions = ecrire_manifest(racine, manifest(cibles, commande=commande))
    # Ce qui compte comme ECRIT : les actions qui touchent le disque. `preserve` n'en est pas
    # une, et la compter en etait une : mesure faite sur un projet ETRANGER, la seconde
    # execution de `jio start` annoncait « 29 deja a jour, 1 ecrit(s) » — le fichier de
    # l'utilisateur qu'elle venait de NE PAS ecrire. La promesse du README (« relancee, elle ne
    # reecrit rien ») etait donc fausse au rapport, alors qu'elle etait tenue au disque.
    ecrits = [d for d in decisions if d.action not in {"inchange", "preserve"}]
    print(f"    artefacts : {len(decisions) - len(ecrits)} deja a jour, {len(ecrits)} ecrit(s)")
    for decision in sorted(ecrits, key=lambda d: d.chemin):
        marque = {"preserve": "PRESERVE (le tien)", "remplace": "mis a jour",
                  "sauvegarde": "mis a jour (ton original en .avant-jio)"}.get(
                      decision.action, decision.action)
        print(f"      {marque:<38} {decision.chemin}")

    # L'ETAT, et pas seulement l'activite de cette execution. La fiche d'integration est lue par
    # la prochaine IA : ce qu'elle doit savoir, c'est ce qui est en place — pas ce que la
    # commande qui l'a ecrite a eu besoin de faire. Mesure a l'origine, et c'est le defaut qui a
    # paye ce commentaire : la fiche disait « artefacts natifs ecrits ou mis a jour : 30 » au
    # premier passage et « : 0 » au second. Deux executions identiques, deux fiches differentes,
    # alors que le README promet « relancee, elle ne reecrit rien ». Un rapport d'ACTIVITE dans
    # un fichier d'ETAT, c'est un fichier qui bat.
    preserves = [d for d in decisions if d.action == "preserve"]
    presents = sum(1 for d in decisions if (racine / d.chemin).is_file())
    a_jour = len(decisions) - len(preserves)

    cablages: list[str] = []
    cables: list[str] = []      # l'ETAT du cablage, toutes cibles confondues
    if not args.sans_mcp:
        print()
        if note_commande:
            print(f"    COMMANDE MCP RESOLUE ICI : {note_commande}")
            print()
        print("    cablage MCP (jamais dans un fichier qui existe sans nous)")
        # `brancher` a DEUX formes de retour selon le dialecte : `(ecrit, message)` pour le
        # cablage, `(deja, message)` pour les dialectes sans fichier (Hermes, Codex, Claude
        # Code lisent une configuration utilisateur, que ce depot ne modifie pas). On ne
        # devine pas : on lit le couple rendu, et on dit lequel des deux cas on a.
        for dialecte, _fichier, description in DIALECTES:
            try:
                ecrit, message = brancher(racine, dialecte, commande=commande)
            except (KeyError, ValueError, OSError) as exc:
                print(f"      {dialecte:<12} impossible : {exc}")
                continue
            if ecrit is True:
                cablages.append(dialecte)
                cables.append(dialecte)
                print(f"      {dialecte:<12} BRANCHE  ({description})")
            elif _fichier is None:
                # Rien a ecrire : la configuration appartient a l'utilisateur. Le fragment
                # est livre EN ENTIER (pas « voir la doc ») pour qu'il n'ait qu'a coller.
                print(f"      {dialecte:<12} a coller  ({description}) — fragment ci-dessous")
                for ligne in str(message).rstrip().splitlines():
                    print(f"                   {ligne}")
            else:
                # « laisse tel quel » recouvre deux cas qu'un fichier d'ETAT doit separer :
                # un cablage DEJA en place, et un fichier de l'utilisateur que ce depot ne
                # touche pas. Le premier est un fait du monde (« ce projet est cable pour
                # Cursor »), le second n'en est pas un.
                if f"contient deja `{NOM_SERVEUR}`" in str(message):
                    cables.append(dialecte)
                print(f"      {dialecte:<12} laisse tel quel ({description}) : {message}")

    print()
    print("    PREUVE DU CABLAGE (le serveur est reellement demarre)")
    preuve = prouver_branchement(commande, racine=racine)
    for ligne in str(preuve).splitlines():
        print(f"    {ligne.strip()}" if ligne.strip() else "")

    # La fiche que l'agent lit en premier. Elle est ECRITE, pas promise : un fichier d'etat
    # qui decrit ce qui a ete fait est la seule chose qu'une IA puisse verifier seule.
    # L'etat de COHERENCE du depot, mesure maintenant et ecrit dans la fiche. Une IA qui arrive
    # doit savoir si le depot qu'elle herite tient deja debout : sinon elle prendra pour
    # references des artefacts perimes, des chiffres faux ou des commandes inexistantes.
    from .verify.coherence import controler

    rapport = controler(racine)
    if rapport.ok:
        # La DUREE est affichee a l'ecran, jamais ecrite dans la fiche. Mesure : avec la duree
        # dans le fichier, deux `jio start` consecutifs ecrivaient `1.2s` puis `1.4s` — la fiche
        # changeait a chaque execution, et la promesse « relancee, elle ne reecrit rien » etait
        # fausse. Une duree n'est pas un fait dont un agent a besoin ; le VERDICT, si.
        etat_coherence = f"COHERENT ({len(rapport.constats)} controles)"
        ecran_coherence = f"{etat_coherence[:-1]}, {rapport.duree_s:.1f}s)"
    else:
        noms = ", ".join(c.controle for c in rapport.incoherents)
        etat_coherence = f"{len(rapport.incoherents)} controle(s) en echec : {noms}"
        ecran_coherence = etat_coherence

    # --- les competences, installees la ou Hermes les LIT ------------------------------- #
    # Ecrire `.hermes/skills/` dans le projet ne suffisait pas : Hermes lit `~/.hermes/skills/`.
    # Entre les deux il y avait un `cp -r` a taper a la main — donc une etape que personne ne
    # fait, et douze procedures qui dorment sur le disque sans jamais entrer dans la boucle.
    hermes_etat = ""
    if not getattr(args, "sans_hermes", False):
        from .artifacts.install_hermes import REGISTRE, dossier_hermes, installer

        print()
        print("    COMPETENCES HERMES (la ou l'agent les lit : ~/.hermes/skills)")
        cible_hermes = dossier_hermes()
        install = installer(racine)
        if install.ignores:
            print(f"      rien installe : {cible_hermes} n'existe pas encore.")
            print("      Lance Hermes une fois (ou cree le dossier), puis relance `jio start` :")
            print(f"          mkdir -p {cible_hermes} && jio start")
            print("      Sinon, installe-les a la main :")
            print(f"          cp -r {racine / '.hermes' / 'skills'}/* {cible_hermes}/")
            hermes_etat = "aucune (dossier Hermes absent)"
        else:
            for chemin in install.liens[:8]:
                print(f"      LIEN      {chemin}")
            for chemin in install.copies[:8]:
                print(f"      COPIE     {chemin}")
            for chemin in install.mises_a_jour[:8]:
                print(f"      A JOUR    {chemin}  (version precedente de jio, remplacee)")
            for chemin in install.deja[:4]:
                print(f"      deja      {chemin}")
            for chemin in install.preserves[:4]:
                print(f"      PRESERVE  {chemin} (a vous : non touche)")
            if install.preserves:
                print("      Ces fichiers ne seront JAMAIS ecrases : comparez-les, puis")
                print("      supprimez-les si vous voulez que jio les gere.")
            print(f"      total : {install.resume()}  ·  registre : {REGISTRE}")
            hermes_etat = install.resume()

    etat.mkdir(parents=True, exist_ok=True)
    fiche = etat / "ACTIVE.md"
    texte_fiche = _fiche_active(
        racine, detectees, cables, presents, len(decisions), a_jour, etat_coherence,
        hermes=hermes_etat,
    )
    # « Ne reecrit rien » se mesure sur le contenu ET sur la date : ecrire un texte identique
    # laisse git propre mais fait bouger la date de modification, donc un generateur qui
    # « ne change rien » finit quand meme par apparaitre comme un changement. On ne touche pas
    # le fichier quand son contenu est le meme — et on le DIT, parce que « rien n'a ete ecrit »
    # et « une fiche a ete ecrite » doivent pouvoir se distinguer depuis la sortie.
    fiche_inchangee = fiche.is_file() and fiche.read_text(encoding="utf-8") == texte_fiche
    if not fiche_inchangee:
        fiche.write_text(texte_fiche, encoding="utf-8")
    print()
    print(f"    COHERENCE DU DEPOT : {ecran_coherence}")
    if not rapport.ok:
        for constat in rapport.incoherents:
            print(f"      [{constat.marque}] {constat.controle:<13} {constat.resume[:60]}")
            for detail in constat.details[:2]:
                print(f"           - {detail[:84]}")
        print("      -> `jio coherence` donne le detail, la ligne et la correction.")
    print()
    print(
        f"    fiche d'integration : {fiche.relative_to(racine)}  (l'IA la lit en premier)"
        + ("  — inchangee, rien n'a ete reecrit" if fiche_inchangee else "")
    )
    print()
    print("    PROCHAINES ETAPES")
    print("      1. `jio doctor`               etat reel : ce qui marche, ce qui manque")
    print("      2. `jio clarify \"<objectif>\"`   les questions essentielles avant de travailler")
    print("      3. `jio run \"<objectif>\"`       mission complete, avec preuves et reserves")
    print()
    return 0


def _fiche_active(
    racine: Path,
    detectees: list[str],
    cables: list[str],
    presents: int,
    total: int = 0,
    a_jour: int = 0,
    coherence: str = "non mesuree",
    hermes: str = "",
) -> str:
    """`.jio/ACTIVE.md` : ce qu'une IA doit lire avant de toucher ce projet.

    Deux principes y sont ecrits parce qu'ils sont mesurables : les artefacts sont GENERES
    (`jio artifacts`), et la revendication sans preuve est refusee (`jio claims`). La fiche ne
    contient donc que ce qui a ete verifie a l'instant de son ecriture.

    CE QU'ELLE A DU APPRENDRE, et c'est la meme lecon que le reste de l'integration. Ecrite dans
    un projet ETRANGER, elle parlait encore de NOTRE depot : elle demandait d'editer
    `jio/artifacts/doctrine.py` — un fichier qui n'existe pas chez l'utilisateur — renvoyait a
    `docs/VISION-ARCHITECTURE.md`, absent lui aussi, et annoncait « Trois regles » suivies de
    cinq. Or c'est la premiere chose que la machine suivante lit. Une fiche qui envoie son
    lecteur vers des fichiers inexistants n'est pas une aide : c'est une trahison de plus, et
    elle coute la confiance dans tout le reste de la fiche.

    La regle est donc : chaque chemin cite est soit un chemin DU PROJET, soit un chemin de
    l'installation de jio — et dans ce cas il est ecrit comme tel, avec sa raison d'etre la.
    """
    # Le depot de jio lui-meme se reconnait a son paquet ; tout le reste est un projet hote.
    propre_depot = (racine / "jio" / "__init__.py").is_file()
    # Le dossier de l'installation de jio : c'est `jio/cli.py` qui parle, donc son parent EST le
    # paquet. Aucune recherche, aucun `pip show` : ce qui est ecrit est ce qui tourne.
    paquet = Path(__file__).resolve().parent
    outils = ", ".join(detectees) if detectees else "aucune CLI detectee (ce n'est pas bloquant)"
    cable = ", ".join(cables) if cables else "aucun (--sans-mcp)"
    # L'ETAT des artefacts, jamais l'activite de l'execution qui a ecrit cette fiche : c'est la
    # difference entre un fichier qui bat et un fichier qui informe.
    artefacts = f"{presents}/{total} present(s)" + (
        f", {a_jour} a jour" if total and a_jour != presents else ""
    )
    # L'installation des competences chez Hermes est un FAIT DU MONDE, pas une activite : elle
    # appartient donc a la fiche. Sans cette ligne, une IA lisait douze procedures dans le
    # depot et ne pouvait pas savoir si SON outil les avait chargees.
    competences_hermes = f"\nCOMPETENCES HERMES : {hermes}" if hermes else ""

    # Les nombres de procedures et d'agents sont COMPTES dans la doctrine qui les produit, pas
    # recopies : un chiffre annonce que rien ne mesure redevient faux au premier ajout.
    from .artifacts import manifest

    tous = manifest()
    procedures = [c for c in tous if "/skills/" in c and c.endswith("SKILL.md")]
    agents = [c for c in tous if c.startswith(".opencode/agents/") and c.endswith(".md")
              and not c.endswith("README.md")]
    # Le cout de la bibliotheque ENTIERE, mesure sur les textes qui seront charges — c'est ce
    # que paie une session qui les chargerait toutes. Un chiffre annonce que rien ne mesure
    # redevient faux au premier ajout : celui-ci est calcule ici, comme les autres.
    from .artifacts.budget import mesurer as _mesurer

    cout_procedures = sum(_mesurer(rel, tous[rel]).jetons for rel in procedures)

    # Les regles sont CONSTRUITES et leur nombre est COMPTE. « Trois regles » suivi de cinq
    # entrees est exactement le defaut qu'un chiffre verifie empeche ailleurs : la fiche doit
    # satisfaire la meme exigence qu'elle impose au reste du depot.
    regles: list[tuple[str, str]] = [
        ("Aucune affirmation sans preuve executable.",
         "`jio claims <document>` verifie un document et sort en 1 s'il refute quoi que ce "
         "soit — un document de ce projet n'a pas d'exception."),
        ("Les artefacts sont generes.",
         "Les editer a la main est perdu : "
         + ("editer `jio/artifacts/doctrine.py`, puis `jio sync`."
            if propre_depot else
            f"ils sont regeneres par `jio start` depuis l'installation de jio (`{paquet}`). "
            "Pour les faire evoluer, editer cette installation, puis relancer `jio start`.")),
        ("Trois etats, pas quatre.",
         "`DELIVERED`, `DELIVERED_UNDER_RESERVATION`, `ABSTAINED`. « Ca devrait marcher » "
         "n'est pas un etat."),
        ("Une etape sans preuve n'existe pas.",
         "En mode autonome (`jio auto`), chaque etape du plan porte la commande qui peut "
         "echouer ; un echec non resolu ARRETE le plan au lieu de l'enchainer, et ce qui reste "
         "est declare NON TENTE."),
        ("Une preuve ne se reprend pas d'un autre monde.",
         "`jio auto --reprendre` saute les etapes deja prouvees SEULEMENT si la revision git "
         "n'a pas bouge. Sinon le plan est rejoue entier : re-verifier coute une commande par "
         "etape, croire coute une mission batie sur du vide."),
    ]
    ordre = {1: "Une", 2: "Deux", 3: "Trois", 4: "Quatre", 5: "Cinq", 6: "Six", 7: "Sept"}
    titre_regles = (f"## {ordre.get(len(regles), str(len(regles)))} regles, "
                    "et ce qui les tient")
    corps_regles = "\n".join(
        f"{rang}. **{titre}** {texte}" for rang, (titre, texte) in enumerate(regles, 1)
    )

    # Ce que « fini » veut dire : la ligne sur les tests n'est ecrite que si le projet a des
    # tests. Annoncer `python -m pytest -q` a un projet qui n'a pas de dossier de tests, c'est
    # envoyer l'IA vers une commande qui echoue — le petit mensonge qui fait douter du reste.
    fini: list[str] = []
    if (racine / "tests").is_dir() or (racine / "test").is_dir():
        fini.append("la suite de tests passe (`python -m pytest -q` s'il s'agit de pytest) et "
                    "`jio scan .` ne signale rien ;")
    else:
        fini.append("`jio scan .` ne signale rien sur le code et les documents du projet ;")
    fini.append("`jio claims` sur les documents touches : 0 refutation ;")
    fini.append("les reserves restantes sont NOMMEES, jamais tues ;")
    fini.append("`jio mutants` ne regresse pas (une ligne non protegee est une preuve "
                "manquante).")

    # Le renvoi final : dans le depot de jio, il nomme nos fichiers ; ailleurs, il nomme
    # l'installation (et dit que le README du projet decrit, lui, le projet).
    detail = (
        "Detail complet : `README.md`, `docs/VISION-ARCHITECTURE.md`, doctrine : "
        "`jio/artifacts/doctrine.py`."
        if propre_depot else
        "La documentation de l'outil vit a cote du paquet, dans "
        f"`{paquet.parent}` : `README.md` pour la vue d'ensemble, `docs/DOSSIER-TECHNIQUES.md` "
        "pour les mesures qui la fondent. Le `README.md` de CE projet decrit, lui, ce projet."
    )

    return f"""# JIO est actif sur ce projet

> Fiche ecrite par `jio start`. Elle decrit l'etat REEL au moment de l'ecriture.
> Pour la reecrire : `jio start`. Pour la contredire : les commandes ci-dessous.

PROJET : {racine}{competences_hermes}

## Ce qui a ete fait

- artefacts natifs : {artefacts}
- outils detectes sur cette machine : {outils}
- cablage MCP : {cable}
- coherence du depot a l'instant de l'ecriture : {coherence}

## Avant de travailler : les commandes, dans cet ordre

```sh
jio doctor                  # etat reel : fournisseurs, artefacts, journal, garde-fous
jio clarify "<objectif>"    # les questions ESSENTIELLES ; code 3 si la reponse manque
jio run "<objectif>"        # mission complete : preuve, panel, consensus, reserves
jio auto "<objectif>"       # plusieurs etapes vers un objectif large : une etape sans
                            # preuve est REFUSEE, un echec non resolu ARRETE le plan
jio auto --reprendre        # continue le plan interrompu d'apres `.jio/plan.json` : les etapes
                            # deja prouvees sont sautees SI la revision git n'a pas bouge
jio coherence               # LES NEUF CONTROLES : artefacts, chiffres, documents, commandes
                            # citees, competences, environnement, portes du paquet, journal,
                            # plan en suspens
jio coherence --reparer     # repare ce qui est MECANIQUE (artefacts generes, valeurs mesurees),
                            # puis repasse la porte. Ne touche jamais a ce qui demanderait
                            # d'inventer — et JAMAIS a un journal casse (piece a conviction)
```

`jio clarify` sort en **3** quand une question essentielle reste sans reponse. Dans ce cas,
la bonne action est de POSER la question a l'utilisateur, pas de commencer.

## Les procedures livrees avec jio : lesquelles charger, et quand

L'installation livre **{len(procedures)} procedures** (`.hermes/skills/`) et **{len(agents)}
agents** (`.opencode/agents/`). Chez Hermes, `jio start` les INSTALLE la ou l'agent les lit
(`~/.hermes/skills/`), par lien pour qu'une mise a jour les mette a jour sans recopie. Les
charger TOUTES coute **{cout_procedures} jetons** dans la fenetre — et un contexte sature fait
perdre ce que le contexte apportait. Ne pas les charger du tout revient a ignorer une
bibliotheque qui est la. La reponse est une commande, pas un choix a l'aveugle :

```sh
jio skills "<objectif>"     # les 3 procedures qui s'appliquent, avec les termes qui l'ont
                            # decide, leur cout, et « aucune » si l'objectif est hors sujet
jio skills --banc           # la mesure du classement, temoins compris
jio skills --seuil-balaye   # le seuil d'abstention et ce qu'il coute
jio sorties                 # les exemples de sortie des documents sont-ils encore vrais ?
```

`jio run` fait ce choix **tout seul** : il injecte les procedures retenues dans le prompt de
mission (3 au plus, budget 1500 jetons), refuse celles que `jio artifacts --audit` signale, et
ecrit au journal ce qui a ete charge comme ce qui a ete ecarte. Pour mesurer ce qu'elles
apportent : `jio run "<objectif>" --sans-competences`.

{titre_regles}

{corps_regles}

## Ce que "fini" veut dire ici

{chr(10).join(f"- {ligne}" for ligne in fini)}

{detail}
"""


def cmd_auto(args: argparse.Namespace) -> int:
    """Execute un plan verifie, et s'ARRETE des que la preuve manque.

    La difference avec `jio run` : `run` fait UNE mission (un artefact, une preuve). `auto`
    enchaine PLUSIEURS etapes vers un objectif plus large, avec deux garanties que rien d'autre
    ne donne dans l'ecosysteme des agents :

      * chaque etape doit porter une preuve executable : sans elle, l'etape est REFUSEE avec sa
        raison, jamais executee « en attendant ». Un plan dont on retire la moitie en silence
        n'est plus le plan du modele, et personne ne saurait ce qui a ete change ;
      * un echec non resolu ARRETE le plan (etat `bloque`) au lieu d'empiler des etapes sur une
        base qu'on sait fausse. Le budget epuise est declare `budget`, avec ce qui reste.

    Trois issues, jamais quatre : `termine`, `bloque`, `budget`. L'etat est ecrit dans
    `.jio/plan.json` — avec la revision du depot sur laquelle il a ete obtenu, parce que
    reprendre un plan apres un changement de revision, c'est changer de monde.
    """
    from .loop.auto import (
        MAX_ETAPES, enregistrer, executer, extraire_etapes, formater, lire_etat,
        plan_simule,
    )

    objectif = args.objective.strip()
    if not objectif and not getattr(args, "reprendre", False):
        print("  objectif requis : jio auto \"<objectif>\"", file=sys.stderr)
        print("  exemple : jio auto \"corrige la borne de mutation\" --cible jio/verify/mutation.py",
              file=sys.stderr)
        print("  pour continuer un plan interrompu : jio auto --reprendre", file=sys.stderr)
        return 2

    # Une seule racine pour tout : les preuves s'executent la, l'etat y est ecrit, et la
    # revision lue est celle du depot vise. Le premier jet utilisait `Path.cwd()` — donc
    # `jio auto` sur un projet qu'on n'a pas ouvert comme repertoire courant ecrivait son etat
    # ailleurs et lancait ses preuves au mauvais endroit. `jio start`, `jio scan`,
    # `jio coherence` et `jio artifacts` prennent tous `--root` ; `auto` etait l'exception.
    racine = Path(getattr(args, "root", ".") or ".").expanduser().resolve()
    if not racine.is_dir():
        print(f"  racine introuvable : {racine}", file=sys.stderr)
        return 2

    analyse = None
    if not args.plan:
        from .clarify import analyser as _analyser, formater as _formater

        analyse = _analyser(objectif, mode="strict" if args.strict else "assume")
        if analyse.bloquant:
            print(_formater(analyse))
            print()
            print("  PLAN NON COMMENCE (--strict) : reponds aux questions, puis relance.")
            return 3

    # L'etat vise, calcule une fois pour toutes : il sert a reprendre, a lire la revision, et a
    # ecrire le resultat. `.jio/plan.json` se lit toujours a la racine du projet concerne.
    chemin_etat = Path(args.etat)
    if not chemin_etat.is_absolute():
        chemin_etat = racine / chemin_etat
    from .loop.auto import _revision as _revision_de

    revision = _revision_de(racine)

    # Le plan : un fichier fourni, ou le plan de reference deterministe — ANNONCE.
    texte = ""
    simule = False
    reprise = None
    if getattr(args, "reprendre", False):
        from .loop.auto import reprendre as _reprendre

        reprise = _reprendre(chemin_etat, revision_courante=revision)
        print(BANNER)
        print("  REPRISE DE PLAN  ·  on ne croit sur parole aucune preuve")
        print(f"    {reprise.motif}")
        print()
        if not reprise.utilisable:
            print("    rien a reprendre : relance sans --reprendre pour un plan neuf.")
            return 1
        if reprise.sautees == len(reprise.etapes):
            print(f"    rien a faire : les {len(reprise.etapes)} etape(s) sont deja prouvees.")
            return 0
        if not objectif:
            # L'objectif vient de l'etat : c'est celui du plan, pas un texte invente ici.
            try:
                objectif = str(lire_etat(chemin_etat).get("objectif") or "").strip()
            except (OSError, ValueError):
                objectif = ""
            objectif = objectif or "(objectif de l'etat enregistre)"
    elif args.plan:
        chemin = Path(args.plan).expanduser()
        if not chemin.is_file():
            print(f"  plan introuvable : {chemin}", file=sys.stderr)
            return 2
        texte = chemin.read_text(encoding="utf-8")
    else:
        import json as _json

        texte = _json.dumps(plan_simule(objectif, cible=args.cible, entree=args.entrypoint))
        simule = True

    if reprise is not None:
        # Les etapes de la reprise viennent de l'ETAT, pas d'un texte a re-analyser : elles ont
        # deja ete validees (chacune porte sa preuve) et les re-valider ici risquerait de les
        # faire disparaitre en silence — exactement ce que ce module interdit.
        etapes, refusees = reprise.etapes, ()
    else:
        etapes, refusees = extraire_etapes(texte, max_etapes=MAX_ETAPES)

    print(BANNER)
    print("  MISSION AUTONOME  ·  chaque etape doit porter sa preuve")
    print(f"    objectif : {objectif}")
    if simule:
        print("    plan : REFERENCE deterministe (aucun modele n'a planifie). Chaque etape cite")
        print("    une preuve qui existe dans ce depot ; `--plan <fichier>` execute le tien.")
    print()

    questions: tuple[str, ...] = ()
    if analyse is not None and analyse.questions:
        questions = tuple(q.question for q in analyse.questions)
        print("    HYPOTHESES DECLAREES (l'objectif laissait ces points ouverts) :")
        for q in analyse.questions:
            print(f"      - {q.signal} : {q.defaut[:80]}")

    if not etapes:
        print()
        print(formater(executer((), objective=objectif, lancer=lambda e: (False, "", 0),
                                racine=racine, refusees=refusees)))
        return 1

    def lancer(etape: object) -> tuple[bool, str, int]:
        """Execute UNE etape : la preuve est une commande reelle, dans le depot.

        En reprise, une etape DEJA PROUVEE n'est pas relancee (meme revision) : on rend son
        resultat sans cout, en le declarant « deja prouvee ». La confiance ne vient pas d'un
        raccourci : elle vient de la revision, verifiee avant de commencer.
        """
        import subprocess

        if reprise is not None and getattr(etape, "id", "") in reprise.deja_prouvees:
            return True, "deja prouvee (reprise : meme revision)", 0

        commande = getattr(etape, "preuve", "")
        argv = _argv_de_preuve(commande)
        if argv is None:
            return False, (
                "preuve refusee : seules les commandes `jio ...`, `python -m pytest|ruff|mypy "
                f"` sont executees (ni chainage, ni shell). Recu : {commande[:60]}"
            ), 0
        proc = subprocess.run(
            argv, cwd=racine, capture_output=True, text=True, timeout=1800, check=False,
        )
        sortie = (proc.stdout or proc.stderr or "").strip().splitlines()
        queue = sortie[-1][:120] if sortie else "(aucune sortie)"
        return proc.returncode == 0, f"code {proc.returncode} · {queue}", 1

    resultat = executer(
        etapes, objective=objectif, lancer=lancer, racine=racine,
        budget_etapes=max(1, min(args.budget, MAX_ETAPES)), refusees=refusees, questions=questions,
    )
    # L'etat est ecrit DANS le projet vise : `.jio/plan.json` se lit toujours a la racine du
    # depot concerne, jamais dans le repertoire d'ou l'on a lance la commande.
    chemin_etat = Path(args.etat)
    if not chemin_etat.is_absolute():
        chemin_etat = racine / chemin_etat
    enregistrer(resultat, chemin_etat)
    print()
    if args.json:
        _charge_utile(json.dumps(resultat.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(formater(resultat))
        print()
        print(f"    etat enregistre : {chemin_etat} (reprise possible apres correction)")
    return {"termine": 0, "bloque": 1, "budget": 2, "refuse": 1}.get(resultat.etat, 1)


def _argv_de_preuve(commande: str) -> list[str] | None:
    """Traduit une ligne de preuve en `argv`, sans shell — et refuse ce qui n'est pas permis.

    Une preuve vient d'un modele : c'est du contenu NON FIABLE, et l'executer dans un shell
    serait lui donner le droit d'enchainer des commandes (le meme defaut que CVE-2025-53773
    chez Copilot). On accepte donc une liste blanche : `jio ...`, `python -m pytest ...`, et
    rien d'autre. Les caracteres de chainage sont refuses AVANT toute execution.
    """
    import shlex

    ligne = (commande or "").strip()
    if not ligne:
        return None
    for dangereux in (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "&"):
        if dangereux in ligne:
            return None
    try:
        argv = shlex.split(ligne)
    except ValueError:
        return None
    if not argv:
        return None
    # `jio <args>` est REECRIT en `[interpreteur courant] -m jio <args>`. Mesure a l'origine :
    # sur cette machine, `jio auto` avec une preuve « jio version » echouait avec
    # « No such file or directory: 'jio' » — le script console n'est pas toujours dans le PATH,
    # et surtout pas celui de l'interpreteur qui execute la mission. C'est EXACTEMENT le defaut
    # que `prouver_branchement` traque sur le cablage MCP, et il se rejoue ici.
    if argv[0] == "jio":
        return [sys.executable, "-m", "jio", *argv[1:]]
    if len(argv) > 1 and argv[1] == "-m" and argv[0].startswith("python"):
        return [sys.executable, *argv[1:]]
    if argv[0] in {"python", "python3"} and len(argv) > 2 and argv[1] == "-m" and argv[2] in {
        "pytest", "ruff", "mypy", "pyright",
    }:
        return [sys.executable, *argv[1:]]
    return None



# --------------------------------------------------------------------------- #
# Mode machine : une seule regle, et elle est mecanique
# --------------------------------------------------------------------------- #

#: Le VRAI stdout, garde de cote quand une commande demande une sortie lisible par une
#: machine. Voir `_mode_machine`.
_FLUX_MACHINE: Any = None


def _mode_machine(actif: bool) -> None:
    """Bascule la sortie : en mode machine, l'humain lit la sortie d'ERREUR.

    POURQUOI, mesure faite : `jio coherence --json` et `jio ablation --json` melangeaient leur
    banniere et leur en-tete avec la charge utile. `jio ablation --json > rapport.json` donnait
    un fichier qui COMMENCE par un logo, et `--json | jq .` echouait. Un mode machine qui n'est
    pas lisible par une machine ne sert a rien : celui qui veut un chiffre doit le recopier a la
    main, c'est-a-dire que la commande n'a pas de mode machine du tout.

    Le choix de conception : on ne patche PAS chaque `print` du programme (il y en a des
    centaines, et le prochain oublie recommencerait le defaut). On retourne la sortie standard
    vers la sortie d'erreur UNE fois : tout ce qui est ecrit pour l'humain — banniere, en-tete,
    progression, conseils — part alors sur la sortie d'erreur, ou personne ne le confond avec
    la charge utile. Seule la reponse finale, ecrite par `_charge_utile`, reste sur la vraie
    sortie standard. Le defaut possible devient « la charge utile part sur la sortie d'erreur »
    — visible en une seconde, et verrouille par un test qui lit la sortie de la VRAIE commande.
    """
    global _FLUX_MACHINE
    if actif:
        _FLUX_MACHINE = sys.stdout
        sys.stdout = sys.stderr
    elif _FLUX_MACHINE is not None:
        sys.stdout = _FLUX_MACHINE
        _FLUX_MACHINE = None


def _charge_utile(texte: str) -> None:
    """Ecrit la reponse lisible par une machine sur la VRAIE sortie standard."""
    flux = _FLUX_MACHINE if _FLUX_MACHINE is not None else sys.stdout
    print(texte, file=flux)
    flux.flush()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        print(BANNER)
        parser.print_help()
        return 0
    # `is True` et non « vrai » : pour `jio bench --json CHEMIN.json`, l'argument est un
    # CHEMIN, pas une demande de sortie machine — le confondre enverrait le rapport d'un
    # autre cote sans que personne ne le demande.
    _mode_machine(getattr(args, "json", None) is True)
    try:
        return int(args.func(args) or 0)
    except SystemExit as sortie:
        # LE GARDE-FOU DE DERNIER RECOURS. `main()` est l'ENTREE du programme (et ce que les
        # tests appellent) : elle doit rendre un CODE, pas laisser echapper une exception. Un
        # appelant qui enchaine sur `main(...) == 0` lisait donc une exception la ou il attendait
        # un nombre — et l'interpreteur, lui, sortait en 0 quand le message etait une chaine.
        #
        # La traduction est deliberement STRICTE : une chaine n'est JAMAIS un succes. Si un code
        # arrive sous forme de texte, c'est un message que personne n'a encore ecrit : on
        # l'ecrit, et on rend 1 (PROBLEME) — jamais 0. La doctrine des codes est dans
        # `jio/core/codes.py`, et « un message d'erreur qui sort en 0 » y est le defaut fondateur.
        code = sortie.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    finally:
        # Toujours rendre la sortie standard : `main()` est appelee plusieurs fois dans le
        # meme processus par les tests, et une bascule qui survit a un appel ferait ecrire la
        # commande SUIVANTE dans le vide.
        _mode_machine(False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
