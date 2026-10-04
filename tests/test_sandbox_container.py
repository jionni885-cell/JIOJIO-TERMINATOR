"""Le bac a sable : ce qu'il isole, et ce qu'il refuse de faire semblant d'isoler.

Le backend `process` (defaut) reste ce qu'il a toujours ete : timeout, environnement
filtre, dossier temporaire. Il ne protege PAS contre du code hostile — `SECURITY.md` le dit.

Le backend `container` ajoute une vraie frontiere, mais il ne doit jamais mentir : si le
moteur (`docker`/`podman`) manque, on echoue avec un message clair plutot que de retomber
silencieusement sur le mode non isole. C'est tout l'objet de ce fichier : verifier que les
options de durcissement sont REELLEMENT posees dans la ligne de commande, et que l'absence
de moteur est dite au lieu d'etre cachee.

Aucun test n'exige Docker : on remplace le moteur par un faux et on lit la ligne de
commande construite. La ou Docker existe, un test optionnel verifie la chose en vrai.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from jio.verify.executable import Sandbox


def _faux_moteur(monkeypatch, nom: str = "docker", *, retour=None) -> list[list[str]]:
    """Remplace `docker` par un faux binaire et capture les commandes lancees."""
    commandes: list[list[str]] = []

    def faux_which(binaire: str) -> str | None:
        return f"/usr/bin/{binaire}" if binaire == nom else None

    def faux_run(argv, **kwargs):  # substitut de test
        commandes.append([str(part) for part in argv])
        code, sortie, erreur = retour or (0, "ok", "")
        return SimpleNamespace(returncode=code, stdout=sortie, stderr=erreur)

    monkeypatch.setattr("jio.verify.executable.shutil.which", faux_which)
    monkeypatch.setattr("jio.verify.executable.subprocess.run", faux_run)
    return commandes


def test_le_backend_process_reste_le_defaut() -> None:
    sandbox = Sandbox(timeout=20)
    assert sandbox.backend == "process"
    resultat = sandbox.run_python("print(1 + 1)")
    assert resultat.ok and resultat.stdout.strip() == "2"


def test_un_backend_inconnu_est_un_ERREUR_de_configuration() -> None:
    """Un nom de backend mal orthographie ne doit pas retomber sur le mode non isole."""
    with pytest.raises(ValueError):
        Sandbox(backend="conteneur")


def test_sans_moteur_le_conteneur_ECHOUE_au_lieu_de_se_replier(monkeypatch) -> None:
    def aucun(binaire: str) -> None:
        return None

    def interdit(*args, **kwargs):
        raise AssertionError("aucune commande ne doit etre lancee sans moteur de conteneurs")

    monkeypatch.setattr("jio.verify.executable.shutil.which", aucun)
    monkeypatch.setattr("jio.verify.executable.subprocess.run", interdit)

    sandbox = Sandbox(timeout=10, backend="container")
    resultat = sandbox.run_python("print('hostile')")

    assert resultat.exit_code == 126
    assert "container" in resultat.stderr
    assert "backend process" in resultat.stderr, (
        "le message doit nommer l'alternative ET le fait qu'elle n'isole pas"
    )


def test_le_conteneur_coupe_le_reseau_et_les_capacites(monkeypatch, tmp_path) -> None:
    commandes = _faux_moteur(monkeypatch)
    sandbox = Sandbox(timeout=10, backend="container")

    resultat = sandbox.run_command(["python3", "-c", "print('x')"], cwd=tmp_path)

    assert resultat.exit_code == 0
    argv = commandes[0]
    for attendu in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=512",
        "--memory=1024m",
        "--cpus=2",
        "--tmpfs",
    ):
        assert attendu in argv, f"l'option de durcissement {attendu} manque a la ligne de commande"


def test_le_projet_est_monte_en_LECTURE_SEULE_au_meme_chemin(monkeypatch, tmp_path) -> None:
    """L'artefact doit retrouver son vrai `__file__`, sans pouvoir reecrire le depot."""
    commandes = _faux_moteur(monkeypatch)
    projet = tmp_path / "depot"
    (projet / "pkg").mkdir(parents=True)
    (projet / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    artefact = projet / "pkg" / "module.py"
    artefact.write_text("x = 1\n", encoding="utf-8")
    sandbox = Sandbox(timeout=10, backend="container")

    sandbox.run_python("print(1)", chemin_reel=artefact)

    argv = commandes[0]
    montages = [argv[index + 1] for index, part in enumerate(argv) if part == "--volume"]
    assert montages, "le dossier de travail doit etre monte"
    assert montages[0].endswith(":/workspace:rw")
    assert any(montage == f"{projet}:{projet}:ro" for montage in montages), (
        f"le projet doit etre monte en lecture seule, au meme chemin : {montages}"
    )
    assert "python3" in argv and "/workspace/main.py" in argv


def test_sans_dossier_de_travail_le_conteneur_refuse_de_deviner(monkeypatch) -> None:
    """Un conteneur sans volume ne verrait pas le programme : on refuse, on n'improvise pas."""
    _faux_moteur(monkeypatch)
    sandbox = Sandbox(timeout=10, backend="container")

    resultat = sandbox.run_command(["echo", "x"])

    assert resultat.exit_code == 2
    assert "dossier de travail" in resultat.stderr


def test_la_sortie_du_conteneur_ne_laisse_pas_fuir_les_chemins_de_l_hote(monkeypatch) -> None:
    """Les chemins normalises gardent les preuves reproductibles (meme doctrine qu'avant)."""
    commandes: list[list[str]] = []

    def faux_run(argv, **kwargs):
        commandes.append([str(part) for part in argv])
        return SimpleNamespace(
            returncode=1, stdout="", stderr="Traceback /workspace/main.py et /depot/projet/x.py"
        )

    def faux_which(binaire: str) -> str | None:
        return "/usr/bin/docker" if binaire == "docker" else None

    monkeypatch.setattr("jio.verify.executable.shutil.which", faux_which)
    monkeypatch.setattr("jio.verify.executable.subprocess.run", faux_run)

    sandbox = Sandbox(timeout=10, backend="container", runtime="docker")
    resultat = sandbox.run_python("raise SystemExit(1)", chemin_reel=Path("/depot/projet/x.py"))

    assert "/workspace" not in resultat.stderr and "/depot/projet" not in resultat.stderr
    assert "<sandbox>" in resultat.stderr and "<project>" in resultat.stderr


@pytest.mark.skipif(
    shutil.which("docker") is None and shutil.which("podman") is None,
    reason="aucun moteur de conteneurs sur cette machine : la verification reelle est impossible ici",
)
def test_un_conteneur_reel_execute_le_code_en_reseau_coupe() -> None:  # pragma: no cover - machine
    """Quand un moteur est disponible, on verifie le comportement REELLEMENT observe."""
    sandbox = Sandbox(timeout=120, backend="container")
    resultat = sandbox.run_python(
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "    print('RESEAU_OUVERT')\n"
        "except OSError:\n"
        "    print('RESEAU_FERME')\n"
    )
    assert resultat.exit_code == 0, resultat.stderr
    assert "RESEAU_FERME" in resultat.stdout
