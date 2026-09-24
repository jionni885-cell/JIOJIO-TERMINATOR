"""Verification executable — le garde **fail-closed**.

Regle absolue du systeme :

    Aucune affirmation n'est acceptee sans temoin executables.

Un « je pense que ca marche » vaut zero. Un temoin, c'est une commande
reellement executee, un code de sortie, une sortie horodatee et hashee.

Le mode est **fail-closed** : dans le doute on REJETTE, on ne logge pas
en esperant que ca passe.

Pourquoi c'est le levier le plus rentable : le SPEC grounding (un test par
regle enumeree) apporte **+38 points** de code correct et fait tomber les
fausses alertes de **33 % a 0 %** — bien plus que passer a un modele plus gros.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..core.errors import FailClosed
from ..core.journal import Journal
from ..core.types import Rule, RuleKind, Spec, Stage, Witness

DEFAULT_TIMEOUT = 30
MAX_OUTPUT = 20_000  # au-dela : le resultat part sur disque, seule une reference reste


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class Sandbox:
    """Execute du code ou une commande dans un sous-processus isole.

    Mesures appliquees :
      * **timeout** dur (jamais de boucle infinie) ;
      * **environnement minimal** — les secrets de l'hote ne fuient pas dans le
        processus teste (cloisonnement des variables sensibles) ;
      * **repertoire temporaire dedie** ;
      * **sortie plafonnee** — au-dela de 20 000 caracteres, le contenu est
        ecrit sur disque et remplace par une reference (Levier 2 du harness).
    """

    timeout: int = DEFAULT_TIMEOUT
    workdir: Path | None = None
    offload_dir: Path | None = None

    _SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")

    def _env(self) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "JIO_SANDBOX": "1",
        }
        return {k: v for k, v in env.items() if v}

    def _offload(self, text: str, tag: str) -> str:
        if len(text) <= MAX_OUTPUT or self.offload_dir is None:
            return text[:MAX_OUTPUT]
        self.offload_dir.mkdir(parents=True, exist_ok=True)
        path = self.offload_dir / f"{tag}-{int(time.time()*1000)}.log"
        path.write_text(text, encoding="utf-8", errors="replace")
        head = text[:2000]
        return f"{head}\n…[{len(text) - 2000} caracteres offloades vers {path}]"

    def run_python(self, source: str, *, tag: str = "candidate") -> SandboxResult:
        """Ecrit la source dans un fichier temporaire et l'execute.

        Le chemin du dossier temporaire est NORMALISE avant de rendre le
        resultat. Sans cela, deux executions identiques produisent des sorties
        differentes (un chemin aleatoire apparait dans la moindre trace), donc
        des empreintes de temoin differentes — et toute decision qui en derive
        devenait non reproductible. Une preuve qu'on ne peut pas rejouer n'est
        pas une preuve.
        """
        tmp = Path(tempfile.mkdtemp(prefix="jio-", dir=str(self.workdir) if self.workdir else None))
        script = tmp / "main.py"
        script.write_text(source, encoding="utf-8")
        try:
            res = self.run_command([sys.executable, "-u", str(script)], cwd=tmp, tag=tag)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        marker = str(tmp)
        return SandboxResult(
            exit_code=res.exit_code,
            stdout=res.stdout.replace(marker, "<sandbox>"),
            stderr=res.stderr.replace(marker, "<sandbox>"),
            duration_s=res.duration_s,
            timed_out=res.timed_out,
        )

    def run_command(
        self, argv: Sequence[str], *, cwd: Path | None = None, tag: str = "cmd"
    ) -> SandboxResult:
        started = time.perf_counter()
        try:
            proc = subprocess.run(  # noqa: S603 — argv explicite, jamais de shell=True
                list(argv),
                cwd=str(cwd) if cwd else (str(self.workdir) if self.workdir else None),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._env(),
            )
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - started
            return SandboxResult(
                exit_code=124,
                stdout="",
                stderr=f"TIMEOUT apres {self.timeout}s — le code ne termine pas",
                duration_s=elapsed,
                timed_out=True,
            )
        except FileNotFoundError as exc:
            return SandboxResult(exit_code=127, stdout="", stderr=str(exc), duration_s=0.0)

        return SandboxResult(
            exit_code=proc.returncode,
            stdout=self._offload(proc.stdout or "", f"{tag}-out"),
            stderr=self._offload(proc.stderr or "", f"{tag}-err"),
            duration_s=time.perf_counter() - started,
        )


@dataclass
class ProverResult:
    """Resultat complet d'une passe de preuve."""

    witnesses: tuple[Witness, ...] = ()
    failures: tuple[Witness, ...] = ()
    codes: Mapping[str, tuple[int, str]] = field(default_factory=dict)
    #: Identifiants des regles ADVISORY : leur echec est une suspicion, pas une preuve.
    advisory_ids: frozenset[str] = frozenset()

    @property
    def hard_failures(self) -> tuple[Witness, ...]:
        """Echecs qui PROUVENT un defaut (les regles advisory en sont exclues)."""
        return tuple(w for w in self.failures if w.rule_id not in self.advisory_ids)

    @property
    def reservations(self) -> tuple[Witness, ...]:
        """Echecs de regles advisory : a signaler, sans condamner l'artefact."""
        return tuple(w for w in self.failures if w.rule_id in self.advisory_ids)

    @property
    def passed(self) -> bool:
        return bool(self.witnesses) and not self.hard_failures

    @property
    def ratio(self) -> float:
        """Part des regles PROUVABLES satisfaites, dans [0, 1].

        Les regles advisory sont exclues du calcul : on ne peut pas reprocher a un
        artefact ce qu'on n'a pas les moyens de prouver.
        """
        hard = [w for w in self.witnesses if w.rule_id not in self.advisory_ids]
        if not hard:
            return 1.0 if self.witnesses else 0.0
        failed = {w.rule_id for w in self.hard_failures}
        return (len(hard) - len(failed)) / len(hard)


@dataclass
class ExecutableProver:
    """Execute un artefact contre chaque regle de la specification.

    Deux modes de preuve :
      * regle de type ``TEST``  -> la commande de la regle est executee ;
      * regle ``PROPERTY``/``BOUNDARY``/``CONTRACT`` -> la source de test associee
        est executee avec la source du candidat.
    """

    sandbox: Sandbox = field(default_factory=Sandbox)
    journal: Journal | None = None

    def prove(
        self,
        source: str,
        spec: Spec,
        *,
        hidden_checks: Mapping[str, str] | None = None,
        entrypoint: str = "",
        stage: Stage = Stage.PROVE,
        preamble: str = "",
    ) -> ProverResult:
        hidden = dict(hidden_checks or {})
        if not hidden and not any(r.check for r in spec.rules):
            raise FailClosed(
                "aucune preuve disponible : ni test par regle, ni commande de verification. "
                "Le mode fail-closed interdit de poursuivre sans temoin."
            )

        witnesses: list[Witness] = []
        failures: list[Witness] = []
        codes: dict[str, tuple[int, str]] = {}

        for rule in spec.rules:
            if rule.id in hidden:
                w = self._run_check(
                    rule=rule,
                    source=source,
                    check_src=hidden[rule.id],
                    entrypoint=entrypoint,
                    stage=stage,
                    preamble=preamble,
                )
            elif rule.check:
                w = self._run_shell_rule(rule, source)
            else:
                # Regle non verifiable : elle est declaree, jamais supposee.
                continue

            witnesses.append(w)
            codes[rule.id] = (w.exit_code, w.output_hash)
            if not w.ok:
                failures.append(w)
            if self.journal is not None:
                self.journal.append(
                    "witness",
                    {
                        "rule": rule.id,
                        "command": w.command,
                        "exit_code": w.exit_code,
                        "ok": w.ok,
                        "hash": w.output_hash,
                        "stage": stage.value,
                    },
                )

        return ProverResult(
            witnesses=tuple(witnesses),
            failures=tuple(failures),
            codes=codes,
            advisory_ids=frozenset(
                r.id for r in spec.rules if r.kind is RuleKind.ADVISORY
            ),
        )

    # -- executions --------------------------------------------------------- #

    def _run_check(
        self,
        *,
        rule: Rule,
        source: str,
        check_src: str,
        entrypoint: str,
        stage: Stage,
        preamble: str = "",
    ) -> Witness:
        """Un test par regle : la source du candidat puis la verification de la regle.

        ``preamble`` est execute AVANT la source (imports relatifs d'un module de
        paquet, chemins d'import) : sans lui, auditer un fichier interne au projet
        echouerait sur un ImportError et le verificateur accuserait l'artefact a
        tort.
        """
        head = textwrap.dedent(
            f"""
            # --- JIO verification: {rule.id} ---
            import sys as _jio_sys
            _jio_rule = {rule.id!r}
            """
        )
        if preamble:
            # Le preambule doit s'executer AVANT la source (imports relatifs,
            # chemins). Or une ligne `from __future__ import ...` doit rester la
            # premiere instruction de SON unite de compilation : la coller
            # derriere le preambule provoque un SyntaxError et le verificateur
            # accuserait l'artefact a tort (faux positif constate).
            # On compile donc la source separement, via exec(), ce qui preserve
            # a la fois ses imports `__future__` et ses numeros de ligne.
            program = (
                preamble
                + "_jio_source = "
                + repr(source)
                + "\n"
                + "exec(compile(_jio_source, '<artefact>', 'exec'), globals())\n"
                + head
                + "\n"
                + textwrap.dedent(check_src)
            )
        else:
            program = source + "\n\n" + head + "\n" + textwrap.dedent(check_src)
        res = self.sandbox.run_python(program, tag=f"rule-{rule.id}")
        detail = _extract_assertion(res.stderr)
        return Witness(
            rule_id=rule.id,
            command=f"python -c <candidat + {rule.id}>",
            exit_code=res.exit_code,
            ok=res.ok,
            stdout=res.stdout,
            stderr=res.stderr or detail,
            duration_s=res.duration_s,
        )

    def _run_shell_rule(self, rule: Rule, source: str) -> Witness:
        from shlex import split as shsplit

        argv = shsplit(rule.check or "")
        res = self.sandbox.run_command(argv, tag=f"cmd-{rule.id}")
        return Witness(
            rule_id=rule.id,
            command=rule.check or "",
            exit_code=res.exit_code,
            ok=res.ok,
            stdout=res.stdout,
            stderr=res.stderr,
            duration_s=res.duration_s,
        )


def _extract_assertion(stderr: str) -> str:
    """Extrait la ligne d'assertion echeue — retour d'erreur STRUCTURE."""
    for line in reversed((stderr or "").splitlines()):
        s = line.strip()
        if s.startswith("AssertionError") or "assert" in s.lower():
            return s[:300]
    for line in reversed((stderr or "").splitlines()):
        if line.strip():
            return line.strip()[:300]
    return ""


__all__ = ["Sandbox", "SandboxResult", "ExecutableProver", "ProverResult"]
