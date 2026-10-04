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

    Le backend ``process`` conserve le comportement historique (timeout,
    environnement filtré, répertoire temporaire), mais n'est pas une frontière
    de sécurité contre du code hostile. Le backend optionnel ``container`` exige
    Docker ou Podman et ajoute réseau coupé, système de fichiers racine en lecture
    seule, capacités supprimées, limites CPU/mémoire/PID et espace temporaire.
    Une absence de runtime ou d'image échoue fermement : aucun repli silencieux.

    Dans les deux modes, la sortie est plafonnée à 20 000 caractères ; au-delà,
    elle est écrite sur disque si ``offload_dir`` est fourni.
    """

    timeout: int = DEFAULT_TIMEOUT
    workdir: Path | None = None
    offload_dir: Path | None = None
    backend: str = field(
        default_factory=lambda: os.environ.get("JIO_SANDBOX_BACKEND", "process").strip().lower()
        or "process"
    )
    image: str = field(
        default_factory=lambda: os.environ.get("JIO_SANDBOX_IMAGE", "python:3.12-slim").strip()
        or "python:3.12-slim"
    )
    runtime: str = field(
        default_factory=lambda: os.environ.get("JIO_SANDBOX_RUNTIME", "auto").strip().lower()
        or "auto"
    )

    def __post_init__(self) -> None:
        if self.backend not in {"process", "container"}:
            raise ValueError("Sandbox.backend doit être 'process' ou 'container'")
        if self.runtime not in {"auto", "docker", "podman"}:
            raise ValueError("Sandbox.runtime doit être 'auto', 'docker' ou 'podman'")
        if not self.image.strip():
            raise ValueError("Sandbox.image ne peut pas être vide")

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

    def run_python(
        self, source: str, *, tag: str = "candidate", chemin_reel: Path | None = None
    ) -> SandboxResult:
        """Ecrit la source dans un fichier temporaire et l'execute.

        ``chemin_reel`` est le chemin de l'artefact DANS LE PROJET, quand l'appelant le
        connait. Le script tourne toujours dans un dossier temporaire (aucune ecriture ne
        tombe dans le projet), mais le module audite recoit alors son vrai `__file__`.
        Sans cela, un fichier qui situe ses donnees par rapport a lui-meme —
        `Path(__file__).resolve().parents[1] / "evidence"`, le geste le plus banal d'un
        fichier de test — cherchait ces donnees sous `/tmp`, ne les trouvait pas, et
        l'audit concluait « non testable » au lieu de conclure. Mesure faite sur ce depot :
        `tests/test_divergence.py`, un test qui passe sous `pytest`, etait declare
        « non testable ici » par le scan, avec pour toute preuve un FileNotFoundError sous
        `/tmp` — une consequence de NOTRE facon de mesurer, presentee comme une limite du
        projet.
        ""

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
        roots: tuple[Path, ...] = ()
        if self.backend == "container" and chemin_reel is not None:
            root = self._root_for_artifact(chemin_reel)
            if root != tmp.resolve():
                roots = (root,)
        # Dans un conteneur, le dossier temporaire est monte sur /workspace : le script
        # s'appelle donc `/workspace/main.py`, et l'interpreteur est celui de l'image
        # (le chemin de l'environnement virtuel de l'hote n'existe pas dedans).
        argv = (
            ["python3", "-u", "/workspace/main.py"]
            if self.backend == "container"
            else [sys.executable, "-u", str(script)]
        )
        try:
            res = self.run_command(
                argv,
                cwd=tmp,
                tag=tag,
                writable_workspace=True,
                read_only_roots=roots,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        markers = [str(tmp), "/workspace"] if self.backend == "container" else [str(tmp)]
        if self.backend == "container" and roots:
            markers.append(str(roots[0]))
        stdout, stderr = res.stdout, res.stderr
        for marker in markers:
            replacement = "<project>" if roots and marker == str(roots[0]) else "<sandbox>"
            stdout = stdout.replace(marker, replacement)
            stderr = stderr.replace(marker, replacement)
        return SandboxResult(
            exit_code=res.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_s=res.duration_s,
            timed_out=res.timed_out,
        )

    @staticmethod
    def _root_for_artifact(path: Path) -> Path:
        """Choisit le plus proche projet connu comme montage en lecture seule."""
        resolved = path.expanduser().resolve()
        for candidate in (resolved.parent, *resolved.parents):
            if (candidate / ".git").exists() or (candidate / "pyproject.toml").is_file():
                return candidate
        return resolved.parent

    #: Options de durcissement du conteneur. Chaque refus est une mesure de
    #: securite nommee : reseau coupe, racine en lecture seule, aucune capacite
    #: Linux, pas de nouveaux privileges, limites de ressources.
    _CONTAINER_FLAGS: tuple[tuple[str, ...], ...] = (
        ("--network=none",),
        ("--read-only",),
        ("--cap-drop=ALL",),
        ("--security-opt=no-new-privileges",),
        ("--pids-limit=512",),
        ("--memory=1024m",),
        ("--cpus=2",),
    )

    def _runtime_binaire(self) -> str:
        """Trouve Docker ou Podman — ou refuse, sans repli silencieux.

        Se replier sur le backend ``process`` apres avoir demande ``container``
        ferait croire a une isolation qui n'existe pas : c'est exactement le
        mensonge que ce projet traque. Donc on leve, et l'appelant decide.
        """
        if self.runtime in {"docker", "podman"}:
            if shutil.which(self.runtime) is None:
                raise FailClosed(
                    f"backend container demande, mais `{self.runtime}` est introuvable "
                    "sur le PATH. Installez-le, ou repassez en backend process en "
                    "assumant que ce n'est pas une frontiere de securite."
                )
            return self.runtime
        for candidate in ("docker", "podman"):
            if shutil.which(candidate) is not None:
                return candidate
        raise FailClosed(
            "backend container demande, mais ni docker ni podman n'est disponible. "
            "Installez un moteur de conteneurs, ou repassez en backend process en "
            "assumant que ce n'est pas une frontiere de securite."
        )

    def _container_argv(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        writable_workspace: bool,
        read_only_roots: Sequence[Path],
        env: Mapping[str, str],
    ) -> list[str]:
        """Assemble la ligne de commande d'un conteneur durci.

        Le dossier de travail est monte sur ``/workspace``. Les racines
        supplementaires (le projet, pour un artefact qui doit retrouver son vrai
        ``__file__``) sont montees sur ``/projet`` en LECTURE SEULE : du code
        hostile ne peut donc pas reecrire le depot qu'on audite.
        """
        command = [self._runtime_binaire(), "run", "--rm", "--init",
                   "--workdir", "/workspace", "--tmpfs", "/tmp:rw,size=256m"]
        for flag in self._CONTAINER_FLAGS:
            command.extend(flag)
        for name, value in sorted(env.items()):
            command.extend(["--env", f"{name}={value}"])
        command.extend(["--volume", f"{cwd}:/workspace:{'rw' if writable_workspace else 'ro'}"])
        # Les racines supplementaires sont montees au MEME chemin absolu, en lecture seule :
        # le `__file__` ecrit en dur dans le programme audite reste donc valide, et du
        # code hostile ne peut pas reecrire le depot qu'on lui demande d'auditer.
        for root in read_only_roots:
            command.extend(["--volume", f"{root}:{root}:ro"])
        command.append(self.image)
        command.extend(str(part) for part in argv)
        return command

    def run_command(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        tag: str = "cmd",
        writable_workspace: bool = False,
        read_only_roots: Sequence[Path] = (),
    ) -> SandboxResult:
        started = time.perf_counter()
        env = self._env()
        efface = str(cwd) if cwd else (str(self.workdir) if self.workdir else None)
        command = list(argv)
        if self.backend == "container":
            if cwd is None:
                return SandboxResult(
                    exit_code=2,
                    stdout="",
                    stderr="backend container : un dossier de travail est obligatoire pour "
                           "monter le volume ; aucune commande n'a ete executee.",
                    duration_s=0.0,
                )
            try:
                command = self._container_argv(
                    argv,
                    cwd=Path(cwd),
                    writable_workspace=writable_workspace,
                    read_only_roots=tuple(read_only_roots),
                    env=env,
                )
            except FailClosed as exc:
                return SandboxResult(
                    exit_code=126, stdout="", stderr=f"[JIO-SANDBOX] {exc}",
                    duration_s=time.perf_counter() - started,
                )
            env = self._env()
            efface = None
        try:
            proc = subprocess.run(  # noqa: S603 — argv explicite, jamais de shell=True
                command,
                cwd=efface,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
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


#: Un artefact est audite COMME MODULE, jamais comme script. Sans cela, le bloc
#: `if __name__ == "__main__":` s'execute dans le bac a sable et le verdict porte sur
#: la demonstration du fichier au lieu de son code. Constate sur une bibliotheque
#: reelle : `rich/traceback.py` divise par zero dans sa demonstration, et le module
#: etait declare « ne s'execute pas » alors qu'il s'importe parfaitement.
#: La ligne qui declare `__file__` au module audite. Quand l'appelant connait le vrai
#: chemin du fichier, il est ecrit EN DUR dans le programme : c'est un fait, pas une
#: supposition, et aucun etat ambiant ne peut le changer.
_FILE_REELLE = '_jio_module.__dict__["__file__"] = {chemin!r}\n'

_AUDIT_AS_MODULE = (
    "# L'artefact est audite COMME MODULE, jamais comme script : sinon son bloc\n"
    '# `if __name__ == "__main__":` (demonstration, script) s\'execute, et le\n'
    '# verdict porte sur la demonstration au lieu du code. Constate sur une\n'
    '# bibliotheque reelle dont la demo divise par zero : module declare fautif.\n'
    '#\n'
    '# Le nom doit aussi EXISTER dans sys.modules : dataclasses et typing y\n'
    '# cherchent le module de definition pour lire les annotations, et un nom\n'
    '# absent fait echouer tout fichier annote (`NoneType object has no\n'
    "# attribute __dict__`). On enregistre donc un module VIDE avant l'execution\n"
    '# — il suffit que son dictionnaire existe — et on le remplit APRES, quand\n'
    '# les noms sont la.\n'
    'import sys as _jio_sys, types as _jio_types\n'
    '_jio_module = _jio_types.ModuleType("__jio_artefact__")\n'
    '_jio_sys.modules["__jio_artefact__"] = _jio_module\n'
    '__name__ = "__jio_artefact__"\n'
    '# Le TYPE de l\'exception non rattrapee, ecrit AVANT le traceback habituel (qui\n'
    '# reste intact). Un traceback n\'imprime que le nom de la classe : `PilNotAvailable`\n'
    "# herite d'`ImportError` et signale une dependance absente, mais rien dans le texte\n"
    "# ne le disait — la bibliotheque etait declaree fautive. La chaine d'heritage est\n"
    '# un fait.\n'
    'def _jio_hook(_jio_t, _jio_v, _jio_tb):\n'
    '    try:\n'
    '        _jio_noms = " <- ".join(c.__name__ for c in type(_jio_v).__mro__[:6])\n'
    '    except Exception:\n'
    '        _jio_noms = type(_jio_v).__name__\n'
    '    _jio_sys.stderr.write("[JIO-TYPE] " + _jio_noms + "\\n")\n'
    '    _jio_sys.__excepthook__(_jio_t, _jio_v, _jio_tb)\n'
    '_jio_sys.excepthook = _jio_hook\n'
    '# --- Bac a sable FERME : aucune connexion sortante. ---\n'
    '#\n'
    '# Un audit ne depend jamais du reseau : un exemple qui appelle une API ne dit rien du\n'
    "# code, et un depot hostile pourrait s'en servir pour exfiltrer ce qu il lit. Mesure\n"
    '# sur du code public : le doctest de `urllib3.connectionpool` fait un vrai GET sur\n'
    '# google.com, et echouait donc pour une raison qui n appartient pas au fichier. Le\n'
    '# refus est EXPLICITE (marqueur lisible dans le rapport) : la limite se declare au\n'
    '# lieu de produire un verdict sur l environnement.\n'
    'class JioReseauFerme(RuntimeError):\n'
    '    """Le bac a sable est ferme : aucune connexion sortante."""\n'
    'def _jio_refuse_le_reseau(*_a, **_k):\n'
    '    raise JioReseauFerme(\n'
    '        "[JIO-RESEAU] connexion reseau refusee : le bac a sable est ferme "\n'
    '        "(aucune requete sortante). Cet exemple ne peut pas etre verifie ici, et un "\n'
    '        "audit ne depend jamais du reseau."\n'
    '    )\n'
    'import socket as _jio_socket\n'
    '_jio_socket.create_connection = _jio_refuse_le_reseau\n'
    '_jio_socket.getaddrinfo = _jio_refuse_le_reseau\n'
    '_jio_cnx = getattr(_jio_socket.socket, "connect", None)\n'
    'if _jio_cnx is not None:\n'
    '    _jio_socket.socket.connect = _jio_refuse_le_reseau\n'
    '_jio_cnx_ex = getattr(_jio_socket.socket, "connect_ex", None)\n'
    'if _jio_cnx_ex is not None:\n'
    '    _jio_socket.socket.connect_ex = _jio_refuse_le_reseau\n'
)

#: Preparation du module avant d'y executer la source : Python fait vivre les globales
#: d'un module dans SON dictionnaire (`module.__dict__`). Un fichier qui lit
#: `sys.modules[__name__].__dict__` — `pygments/lexers/__init__.py` le fait et se
#: recopie dedans — voyait sinon un dictionnaire VIDE, et l'audit declarait la
#: bibliotheque fautive. `__file__` et `__package__` viennent du script (le preambule
#: peut les avoir poses) pour que les chemins relatifs continuent de resoudre.
def _prepare_module(chemin: Path | None) -> str:
    """Le `__file__` que verra le module audite : le vrai quand on le connait.

    Un fichier de test qui se situe par rapport a lui-meme doit trouver ses donnees.
    Le reste (dossier de travail, ecritures) reste dans le bac a sable.
    """
    if chemin is None:
        return (
            '_jio_module.__dict__["__file__"] = globals().get("__file__") or "<artefact>"\n'
            '_jio_module.__dict__["__package__"] = globals().get("__package__") or ""\n'
        )
    return (
        _FILE_REELLE.format(chemin=str(chemin.resolve()))
        + '_jio_module.__dict__["__package__"] = globals().get("__package__") or ""\n'
        + f'_jio_sys.path.insert(0, {str(chemin.resolve().parent)!r})\n'
    )

#: La source est executee DANS le dictionnaire du module, pas dans celui du script.
_EXEC_ARTEFACT = (
    "exec(compile(_jio_source, '<artefact>', 'exec'), _jio_module.__dict__)\n"
)

#: A executer JUSTE APRES la source : le script de controle voit les noms de l'artefact.
#: Sans cette synchronisation, `typing.get_type_hints` et les dataclasses resolvent
#: `cls.__module__` vers un module vide et echouent. `__name__` est restaure : le script
#: n'est pas le module, et un module qui remplace sa propre entree dans `sys.modules`
#: (`sys.modules[__name__] = newmod`) ne doit pas renommer le controle.
_SYNC_MODULE = (
    "_jio_nom_du_script = globals()['__name__']\n"
    "globals().update(_jio_module.__dict__)\n"
    "globals()['__name__'] = _jio_nom_du_script\n"
)


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
        chemin: Path | None = None,
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
                    chemin=chemin,
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
        chemin: Path | None = None,
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
        # Le preambule doit s'executer AVANT la source (imports relatifs, chemins). Or
        # une ligne `from __future__ import ...` doit rester la premiere instruction de
        # SON unite de compilation : coller la source derriere autre chose provoque un
        # SyntaxError et le verificateur accuserait l'artefact a tort (faux positif
        # constate). La source est donc compilee SEPAREMENT, via exec() — ce qui
        # preserve ses imports `__future__` et ses numeros de ligne.
        program = (
            _AUDIT_AS_MODULE
            + preamble
            + "_jio_source = "
            + repr(source)
            + "\n"
            + _prepare_module(chemin)
            + _EXEC_ARTEFACT
            + _SYNC_MODULE
            + head
            + "\n"
            + textwrap.dedent(check_src)
        )
        res = self.sandbox.run_python(program, tag=f"rule-{rule.id}", chemin_reel=chemin)
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
