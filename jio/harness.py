"""Diagnostic deterministe du harness d'un depot de code.

Le rapport privilegie les signaux verifiables localement (instructions, tests,
configuration et outils) et ne pretend pas evaluer la qualite d'un modele.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .verify.executable import Sandbox


@dataclass(frozen=True)
class Finding:
    id: str
    status: str
    message: str
    recommendation: str = ""


INSTRUCTION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
)


def _outil_disponible(tool: str) -> bool:
    """Detecte aussi les outils installes dans l'environnement courant mais hors PATH."""
    if shutil.which(tool):
        return True
    if tool == "pytest":
        from importlib.util import find_spec

        return find_spec("pytest") is not None
    # Ruff peut etre expose comme module ou console-script dans sys.prefix/bin.
    if tool == "ruff":
        from importlib.util import find_spec

        return (
            find_spec("ruff") is not None
            or (Path(sys.prefix) / "bin" / "ruff").is_file()
        )
    return False


def inspect_harness(root: str | Path = ".", *, instruction_budget: int = 150) -> dict:
    """Inspecte un depot et renvoie un rapport stable, exploitable en CI ou par un humain."""
    base = Path(root).resolve()
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    findings: list[Finding] = []
    files: list[dict[str, int | str]] = []
    for relative in INSTRUCTION_FILES:
        path = base / relative
        if path.is_file():
            lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            files.append({"path": relative, "lines": lines})
            if lines > instruction_budget:
                findings.append(
                    Finding(
                        "instruction_budget",
                        "warning",
                        f"{relative} contient {lines} lignes (budget conseille : {instruction_budget}).",
                        "Gardez les invariants ici ; deplacez les procedures detaillees dans des fichiers specialises.",
                    )
                )
    if not files:
        findings.append(
            Finding(
                "instructions",
                "warning",
                "Aucun fichier d'instructions d'agent reconnu.",
                "Ajoutez un AGENTS.md concis avec les commandes de verification et les contraintes du depot.",
            )
        )
    else:
        findings.append(
            Finding(
                "instructions",
                "ok",
                f"{len(files)} fichier(s) d'instructions detecte(s).",
            )
        )

    tests = (
        list(base.glob("test_*.py")) + list((base / "tests").glob("test_*.py"))
        if (base / "tests").exists()
        else list(base.glob("test_*.py"))
    )
    test_count = len({p.resolve() for p in tests})
    findings.append(
        Finding(
            "tests",
            "ok" if test_count else "warning",
            f"{test_count} fichier(s) de tests detecte(s).",
            "Ajoutez des tests reproductibles avant de confier des changements a un agent."
            if not test_count
            else "",
        )
    )
    configs = [
        name
        for name in (
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "Makefile",
        )
        if (base / name).is_file()
    ]
    findings.append(
        Finding(
            "project_config",
            "ok" if configs else "warning",
            "Configuration(s) de projet : "
            + (", ".join(configs) if configs else "aucune detectee"),
            "Documentez une commande unique de test/lint." if not configs else "",
        )
    )
    verification_commands: list[str] = []
    pyproject = base / "pyproject.toml"
    if pyproject.is_file():
        contenu = pyproject.read_text(encoding="utf-8", errors="replace")
        if "[tool.pytest" in contenu or "pytest" in contenu:
            verification_commands.append("python -m pytest")
    package = base / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            if isinstance(scripts, dict) and "test" in scripts:
                verification_commands.append("npm test")
        except (json.JSONDecodeError, OSError):
            findings.append(
                Finding(
                    "verification_commands",
                    "warning",
                    "package.json illisible : commande de test non déterminée.",
                )
            )
    if (base / "Cargo.toml").is_file():
        verification_commands.append("cargo test")
    if (base / "go.mod").is_file():
        verification_commands.append("go test ./...")
    makefile = base / "Makefile"
    if makefile.is_file() and any(
        line.startswith("test:")
        for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines()
    ):
        verification_commands.append("make test")
    verification_commands = list(dict.fromkeys(verification_commands))
    if not any(f.id == "verification_commands" for f in findings):
        findings.append(
            Finding(
                "verification_commands",
                "ok" if verification_commands else "warning",
                "Commande(s) de vérification détectée(s) : "
                + (
                    ", ".join(verification_commands)
                    if verification_commands
                    else "aucune"
                ),
                "Déclarez explicitement une commande de test reproductible ; JIO ne l'exécutera pas lors de cet audit."
                if not verification_commands
                else "Ces commandes sont détectées statiquement, pas exécutées.",
            )
        )
    available = {tool: _outil_disponible(tool) for tool in ("git", "pytest", "ruff")}
    missing_required = [tool for tool in ("git", "pytest") if not available[tool]]
    findings.append(
        Finding(
            "tools",
            "warning" if missing_required else "ok",
            "Disponibilite des outils : "
            + ", ".join(f"{k}={'oui' if v else 'non'}" for k, v in available.items()),
            "Installez pytest pour executer la suite et git pour fournir un etat de depot fiable."
            if missing_required
            else "ruff est facultatif.",
        )
    )
    blockers = sum(f.status == "warning" for f in findings)
    score = round(100 * (len(findings) - blockers) / max(1, len(findings)))
    return {
        "schema_version": 1,
        "root": str(base),
        "score": score,
        "summary": {
            "checks": len(findings),
            "warnings": blockers,
            "instruction_files": files,
            "test_files": test_count,
            "project_configs": configs,
            "verification_commands": verification_commands,
        },
        "findings": [asdict(item) for item in findings],
    }


def run_verification_commands(
    report: dict, root: str | Path, *, timeout: int = 120
) -> list[dict]:
    """Execute explicit opt-in project checks via argv allowlist (never a shell).

    Commands run from a temporary copy of the repository, not the user's working tree.
    VCS metadata and bulky local environments/caches are excluded. Symlinks are refused to
    prevent the copy from becoming a path back into the original tree. This is useful against
    accidental test side effects, NOT a security boundary: test code can still read/write
    elsewhere on the host or use the network. Callers must opt in. Commands use fixed argv;
    strings from package metadata are never executed or interpolated.
    """
    if not 1 <= timeout <= 900:
        raise ValueError("timeout doit etre compris entre 1 et 900 secondes")
    base = Path(root).resolve()
    argv_by_command = {
        # Use JIO's own interpreter so `jio` and its test runner do not accidentally
        # execute in different Python environments because PATH is shadowed.
        "python -m pytest": [sys.executable, "-m", "pytest"],
        "npm test": ["npm", "test"],
        "cargo test": ["cargo", "test"],
        "go test ./...": ["go", "test", "./..."],
        "make test": ["make", "test"],
    }
    ignored = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".jio",
        "build",
        "dist",
        "coverage",
    }
    for current, directories, filenames in os.walk(base, followlinks=False):
        directories[:] = [name for name in directories if name not in ignored]
        for name in [*directories, *filenames]:
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError(
                    f"copie de test refusee : lien symbolique detecte ({path.relative_to(base)})"
                )

    results: list[dict] = []
    try:
        with tempfile.TemporaryDirectory(prefix="jio-harness-") as scratch:
            worktree = Path(scratch) / "workspace"
            shutil.copytree(base, worktree, ignore=shutil.ignore_patterns(*ignored))
            sandbox = Sandbox(timeout=timeout, workdir=worktree)
            for command in report.get("summary", {}).get("verification_commands", []):
                argv = argv_by_command.get(command)
                started = time.monotonic()
                if argv is None:
                    results.append(
                        {"command": command, "status": "unsupported", "exit_code": None}
                    )
                    continue
                executable = (
                    argv[0] if Path(argv[0]).is_absolute() else shutil.which(argv[0])
                )
                if executable is None or not Path(executable).is_file():
                    results.append(
                        {"command": command, "status": "unavailable", "exit_code": None}
                    )
                    continue
                argv[0] = executable
                try:
                    result = sandbox.run_command(
                        argv, cwd=worktree, tag="harness-check"
                    )
                    passed = result.ok and not result.output_limited
                    results.append(
                        {
                            "command": command,
                            "status": "passed" if passed else "failed",
                            "exit_code": result.exit_code,
                            "duration_s": round(time.monotonic() - started, 3),
                            "timed_out": result.timed_out,
                            "output_limited": result.output_limited,
                            "stdout": result.stdout[-4000:],
                            "stderr": result.stderr[-4000:],
                        }
                    )
                except OSError as exc:
                    results.append(
                        {
                            "command": command,
                            "status": "failed",
                            "exit_code": None,
                            "duration_s": round(time.monotonic() - started, 3),
                            "error": str(exc)[:300],
                        }
                    )
    except shutil.Error as exc:
        raise OSError(f"copie de travail impossible : {exc}") from exc
    return results


def render_report(report: dict) -> str:
    lines = [f"Harness readiness : {report['score']}/100", f"Depot : {report['root']}"]
    for item in report["findings"]:
        lines.append(f"[{item['status'].upper()}] {item['message']}")
        if item["recommendation"]:
            lines.append(f"  Conseil : {item['recommendation']}")
    return "\n".join(lines)


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
