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
import os
import sys
import time
from pathlib import Path
from typing import Sequence

from . import __version__
from .audit.integrity import IntegrityMonitor
from .bench.tasks import TASKS, TASKS_BY_ID, Task, build_bank
from .core.journal import Journal
from .core.types import Mission, MissionReport, MissionStatus, Severity
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
) -> Engine:
    """Assemble un moteur utilisant la simulation deterministe (aucune cle requise)."""
    from .audit.panel import DEFAULT_PERSONAS, AuditPanel

    bank = build_bank()
    personas = list(DEFAULT_PERSONAS)[:panel_size]
    providers = make_panel([p.name for p in personas], skill, bank, correlated=correlated)
    generators = [
        SimulatedProvider(
            name=f"gen::{p.name}", model="sim-1",
            persona=Persona(name=f"gen-{p.name}", skill=skill), bank=bank,
        )
        for p in personas[:3]
    ]
    return Engine(
        generators=providers or generators,
        journal=Journal(path=journal_path),
        panel=AuditPanel.simulated(personas, seed=seed),
        prover=ExecutableProver(sandbox=Sandbox(timeout=20)),
        gate=ConformalGate(alpha=alpha),
        monitor=IntegrityMonitor(),
        spec_compiler=SpecCompiler(),
        config=EngineConfig(max_rounds=max_rounds, candidates_per_round=3),
    )


def _real_engine(*, journal_path: Path | None = None, max_rounds: int = 5) -> Engine:
    """Assemble un moteur adosse aux CLI/API reellement disponibles."""
    from .audit.panel import DEFAULT_PERSONAS, AuditPanel
    from .providers.registry import from_env

    registry = from_env()
    providers = list(registry)
    if not providers:
        raise SystemExit(
            "Aucun fournisseur detecte.\n"
            "Installe un CLI (opencode, hermes, claude, codex, gemini) ou definis\n"
            "une variable d'environnement d'API (OPENROUTER_API_KEY, OPENAI_API_KEY...).\n"
            "Sans cle, utilises : jio bench"
        )
    gens = providers[:3]
    return Engine(
        generators=gens,
        journal=Journal(path=journal_path),
        panel=AuditPanel.llm(providers, list(DEFAULT_PERSONAS)),
        prover=ExecutableProver(sandbox=Sandbox(timeout=30)),
        gate=ConformalGate(alpha=0.05),
        monitor=IntegrityMonitor(),
        spec_compiler=SpecCompiler(provider=gens[0]),
        config=EngineConfig(max_rounds=max_rounds, candidates_per_round=3),
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
        lines.append(_c(f"  MOTIF : {report.abstention_reason[:200]}", "warn", color))

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
    print()
    return 0


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


def cmd_bench(args: argparse.Namespace) -> int:
    """Mesure le gain reel du harness sur le MEME modele, fige.

    S0  un seul appel, sans verification        (modele brut)
    S1  best-of-N, sans verification            (echantillonnage seul)
    S2  best-of-N + preuve executable + reprise (verification)
    S3  moteur complet                          (JIO)

    C'est la mesure que personne ne publie : le harness, a poids constants.
    """
    skill = args.skill
    runs = args.runs
    seeds = list(range(runs))

    print(BANNER)
    print(f"  Mesure du harness  ·  competence simulee {skill:.2f}  ·  {runs} tirage(s)  ·"
          f"  {len(TASKS)} taches")
    print("  Aucune cle API requise : les reponses sont simulees, la VERIFICATION est reelle.")
    print()

    results: dict[str, list[float]] = {"S0": [], "S1": [], "S1b": [], "S2": [], "S3": []}
    calls: dict[str, list[int]] = {k: [] for k in results}
    integrity_hits = 0
    started = time.monotonic()

    for seed in seeds:
        for task in TASKS:
            correct = task.correct
            bank = build_bank()
            generators = [
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
            engine = _simulated_engine(task, skill=skill, seed=seed, max_rounds=args.rounds)
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
    }
    base = _mean(results["S0"]) or 1e-9
    print(f"    {'config':<40} {'reussite':>9} {'appels':>7} {'vs S0':>7}")
    print(f"    {'-' * 40} {'-' * 9} {'-' * 7} {'-' * 7}")
    for key in ("S0", "S1", "S1b", "S2", "S3"):
        rate = _mean(results[key])
        budget = _mean(calls[key])
        print(f"    {labels[key]:<40} {rate:>8.1%} {budget:>7.1f} {rate / base:>6.2f}x")
    print()

    # --- la seule comparaison qui compte : a budget d'appels EGAL ---------- #
    s1b, s2 = _mean(results["S1b"]), _mean(results["S2"])
    delta = (s2 - s1b) * 100
    print("  ISOLATION DE L'EFFET")
    print("    echantillonnage seul vs verification, MEME nombre d'appels du modele :")
    print(f"      sans verification {s1b:>7.1%}   avec verification {s2:>7.1%}   "
          f"ecart {delta:+.1f} points")
    if delta > 0:
        print("      -> le gain vient bien de la VERIFICATION, pas du nombre d'essais.")
    else:
        print("      -> sur ce jeu de taches, l'echantillonnage suffisait : resultat honnete.")
    print()
    print(f"    gain total du harness : {(_mean(results['S3']) - _mean(results['S0'])) * 100:+.1f} points"
          "  (cible mesuree dans la litterature : +15 a +54)")
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


def cmd_run(args: argparse.Namespace) -> int:
    journal_path = Path(args.journal) if args.journal else None
    task = TASKS_BY_ID.get(args.task) if getattr(args, "task", "") else None

    if args.simulate and not task:
        print(
            "  Mode simulation : aucun CLI ni cle d'API requis, mais la boucle a besoin\n"
            "  d'oracles pour prouver quoi que ce soit. Associez une tache du banc :\n"
            "    jio run \"<objectif>\" --simulate --task sum_even\n"
            "  Taches disponibles : " + ", ".join(t.id for t in TASKS) + "\n"
        )
        return 2

    if args.simulate:
        engine = _simulated_engine(
            task, seed=0, journal_path=journal_path, max_rounds=args.rounds, alpha=args.alpha
        )
    else:
        engine = _real_engine(journal_path=journal_path, max_rounds=args.rounds)

    objective = task.objective if task else args.objective
    mission = Mission(objective=objective, max_rounds=args.rounds, alpha=args.alpha)
    work = WorkItem(
        objective=objective,
        entrypoint=(task.entrypoint if task else args.entrypoint or ""),
        checks=dict(task.checks) if task else {},
        spec=task.spec() if task else None,
    )
    report = engine.run(mission, work)
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


def cmd_artifacts(args: argparse.Namespace) -> int:
    from .artifacts import TARGETS, manifest, write_manifest

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
    written = write_manifest(root, targets)
    print(f"  {len(written)} fichier(s) ecrit(s) sous {root.resolve()}")
    print()
    print("  Une seule doctrine, tous les dialectes : pour modifier le contenu,")
    print("  editez jio/artifacts/doctrine.py ou definitions.py, jamais les fichiers generes.")
    print()
    return 0


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
    print(f"    A -> B  artefact de loterie de graine : {res.lottery_artifact * 100:+.1f} points")
    print("            (le prompt change, la probabilite non : attendu ~0)")
    print(f"    B -> C  gain ATTRIBUABLE a la memoire : {res.isolated_gain * 100:+.1f} points")
    print("            (prompts identiques, seule la probabilite differe : causalement propre)")
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


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import TOOLS, main as mcp_main

    if args.list:
        print()
        print("  SERVEUR MCP JIO  ·  transport stdio, JSON-RPC 2.0, zero dependance")
        print()
        for tool in TOOLS:
            print(f"    {tool['name']:<14} {tool['description'][:80]}")
        print()
        print("  Configuration : .mcp.json (genere par `jio artifacts --target mcp --write`)")
        print("  Securite : tout chemin est confine a JIO_ROOT.")
        print()
        return 0
    return mcp_main()


def cmd_trace(args: argparse.Namespace) -> int:
    path = Path(args.journal)
    if not path.exists():
        print(f"  journal introuvable : {path}", file=sys.stderr)
        return 2
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
        payload = json.dumps(ev.payload, ensure_ascii=False, default=str)
        print(f"    {ev.seq:>4}  {ev.kind:<14} {ev.trust.value:<9} {payload[:110]}")
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
    sub.add_parser("version", help="version").set_defaults(
        func=lambda a: (print(f"jio {__version__}") or 0)
    )

    b = sub.add_parser("bench", help="mesure le gain du harness (S0 -> S3)")
    b.add_argument("--skill", type=float, default=0.35, help="competence du modele simule")
    b.add_argument("--runs", type=int, default=5, help="nombre de tirages par tache")
    b.add_argument("--rounds", type=int, default=4, help="tours de boucle maximum")
    b.set_defaults(func=cmd_bench)

    r = sub.add_parser("run", help="execute une mission complete")
    r.add_argument("objective", help="objectif en langage naturel")
    r.add_argument("--entrypoint", default="", help="nom de la fonction attendue")
    r.add_argument("--simulate", action="store_true",
                   help="modele simule deterministe : aucune cle API requise")
    r.add_argument("--task", default="", help="id de tache du banc (oracles + specification)")
    r.add_argument("--rounds", type=int, default=5)
    r.add_argument("--alpha", type=float, default=0.05, help="risque d'erreur accepte")
    r.add_argument("--journal", default=".jio/journal.jsonl")
    r.add_argument("--json", default="", help="ecrit le rapport JSON a ce chemin")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("audit", help="audite un artefact contre une specification")
    a.add_argument("file")
    a.add_argument("--task", default="", help="id de tache du banc pour les oracles")
    a.add_argument("--entrypoint", default="", help="fonction a auditer (sinon la premiere)")
    a.set_defaults(func=cmd_audit)

    t = sub.add_parser("trace", help="rejoue et verifie un journal")
    t.add_argument("journal")
    t.add_argument("--kind", default="", help="filtre par type d'evenement")
    t.set_defaults(func=cmd_trace)

    ar = sub.add_parser("artifacts", help="genere les artefacts natifs de tous les outils")
    ar.add_argument("--root", default=".", help="repertoire de destination")
    ar.add_argument(
        "--target",
        action="append",
        default=[],
        help="cible : opencode, hermes, claude, agents, gemini, cursor, copilot, mcp",
    )
    ar.add_argument("--write", action="store_true", help="ecrit reellement les fichiers")
    ar.set_defaults(func=cmd_artifacts)

    mc = sub.add_parser("mcp", help="serveur MCP (stdio) ou liste des outils")
    mc.add_argument("--list", action="store_true", help="affiche les outils exposes")
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
    le.add_argument("--rounds", type=int, default=4, help="tours de boucle maximum")
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
