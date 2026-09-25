"""Quel modele a REELLEMENT tourne — et l'interdiction de faire semblant.

La mesure du harness n'a de valeur que si elle porte sur le modele de l'utilisateur. Le
banc tournait jusqu'ici sur une simulation deterministe, honnete et reproductible, mais qui
ne repond pas a la seule question qui compte : « mon modele, avec le harness, vaut-il mieux
que mon modele seul ? »

Le danger de cette brique n'est pas technique, il est moral : un repli silencieux sur la
simulation produirait un rapport credible, detaille, avec un modele qui n'a jamais tourne.
C'est exactement le mensonge que ce projet existe pour empecher. D'ou la regle, verrouillee
par les tests ci-dessous : **un modele demande et indisponible ARRETE la mesure**.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from jio.bench.provider_spec import Fournisseur, disponibles, resoudre
from jio.core.errors import ProviderError
from jio.providers.cli import CliProvider
from jio.providers.registry import KNOWN_CLIS


# --------------------------------------------------------------------------- #
# 1. La specification : ce qui est accepte, et ce qui est refuse net
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("spec", ["simule", "SIMULE", "sim", "simulation", "", "  "])
def test_la_simulation_est_le_defaut_et_accepte_sous_plusieurs_noms(spec: str) -> None:
    """Un utilisateur ne doit pas avoir a deviner l'orthographe exacte."""
    fournisseur = resoudre(spec)
    assert fournisseur.genre == "simule"
    assert fournisseur.disponible
    assert fournisseur.instances == 1


def test_un_cli_concret_est_resolu_avec_ses_instances(
    tmp_path: Path, monkeypatch
) -> None:
    """Le panel a besoin de plusieurs critiques : le CLI est instancie plusieurs fois."""
    binaire = _faux_binaire(tmp_path, "opencode")
    monkeypatch.setenv("JIO_BIN_OPENCODE", str(binaire))
    fournisseur = resoudre("cli:opencode")
    assert fournisseur.genre == "cli"
    assert fournisseur.instances >= 3
    assert isinstance(fournisseur.provider, CliProvider)
    assert fournisseur.spec == "cli:opencode"


def test_un_cli_INSTALLE_mais_ABSENT_arrete_la_mesure(monkeypatch) -> None:
    """LE test de doctrine : pas de repli silencieux sur la simulation.

    Mesure faite : aucun CLI n'est installe dans cet environnement, et `cli:opencode`
    refusait deja de continuer. Sans ce comportement, `jio bench --provider cli:opencode`
    aurait rendu un tableau complet, mesure sur la simulation, en parlant d'opencode.
    """
    for nom in KNOWN_CLIS:
        monkeypatch.delenv(f"JIO_BIN_{nom.upper()}", raising=False)
    monkeypatch.setenv("PATH", "/nonexistant")

    with pytest.raises(ProviderError) as exc:
        resoudre("cli:opencode")

    message = str(exc.value)
    assert "introuvable" in message
    assert "Aucun repli" in message


def test_un_outil_INCONNU_reste_utilisable_par_sa_ligne_de_commande(
    tmp_path: Path, monkeypatch
) -> None:
    """Le repli sur l'ecosysteme : n'importe quelle CLI, meme inconnue, avec son argv."""
    binaire = tmp_path / "mon-outil"
    binaire.write_text("#!/bin/sh\ncat\n", encoding="utf-8")
    binaire.chmod(binaire.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("JIO_BIN_MON_OUTIL", str(binaire))

    # Sans ligne de commande declaree : refus, et le message donne la forme exacte.
    with pytest.raises(ProviderError) as exc:
        resoudre("cli:mon-outil")
    assert "JIO_CLI_MON_OUTIL_ARGV" in str(exc.value)

    # Avec : accepte. Sans `{prompt}`, l'invite part sur l'entree standard.
    monkeypatch.setenv("JIO_CLI_MON_OUTIL_ARGV", "{binary}")
    fournisseur = resoudre("cli:mon-outil")
    assert isinstance(fournisseur.provider, CliProvider)
    assert fournisseur.provider.use_stdin


def test_un_nom_avec_UN_TIRET_donne_une_cle_de_variable_valide() -> None:
    """Un tiret est interdit dans un nom de variable de shell.

    Defaut trouve en essayant de brancher un binaire nomme `faux-modele` : le message
    d'erreur demandait de definir une variable IMPOSSIBLE a definir.
    """
    from jio.bench.provider_spec import _cle_env

    assert _cle_env("faux-modele") == "FAUX_MODELE"
    assert _cle_env("mon.outil 2") == "MON_OUTIL_2"


def test_openai_sans_configuration_est_refuse_au_lieu_de_simuler(monkeypatch) -> None:
    """Et le message nomme les variables QUI EXISTENT.

    Le premier jet lisait `JIO_API_KEY` et `JIO_BASE_URL` : deux variables inventees, que
    le reste du projet n'utilise nulle part. Un utilisateur les aurait definies sans que
    rien ne change. Le depot a un garde-fou pour cela (variables lues vs documentees), et
    il a fait son travail.
    """
    for variable in ("JIO_OPENAI_BASE", "JIO_OLLAMA", "JIO_OPENAI_KEY",
                     "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ProviderError) as exc:
        resoudre("openai:un-modele")

    message = str(exc.value)
    assert "JIO_OPENAI_BASE" in message
    assert "Aucun repli" in message


def test_une_specification_inconnue_dit_ce_qui_est_attendu() -> None:
    with pytest.raises(ProviderError) as exc:
        resoudre("gpt-6-astra")
    message = str(exc.value)
    assert "simule" in message and "cli:" in message and "openai:" in message


def test_disponibles_dit_la_verite_de_cette_machine() -> None:
    """L'inventaire est un fait verifiable : un chemin trouve, ou pas."""
    etat = disponibles()
    assert len(etat) == len(KNOWN_CLIS)
    for description, installe in etat:
        assert isinstance(installe, bool)
        assert description.startswith("cli:")


# --------------------------------------------------------------------------- #
# 2. Le moteur utilise VRAIMENT le fournisseur demande
# --------------------------------------------------------------------------- #


def _faux_binaire(repertoire: Path, nom: str, trace: Path | None = None) -> Path:
    """Un faux modele executables : il repond du code Python correct, et laisse une trace."""
    chemin = repertoire / nom
    lignes = ["#!/usr/bin/env python3", "import sys"]
    if trace is not None:
        lignes.append(f"open({str(trace)!r}, 'a').write('appel\\n')")
    lignes += [
        "sys.stdin.read()",
        "print('```python')",
        "print('def sum_even(nums):')",
        "print('    return sum(n for n in nums if n % 2 == 0)')",
        "print('```')",
    ]
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC)
    return chemin


def test_le_moteur_appelle_le_CLI_et_non_la_simulation(tmp_path: Path, monkeypatch) -> None:
    """La preuve que le branchement existe : le binaire est appele, sa reponse est utilisee.

    Un faux modele (script local) rend une implementation CORRECTE et laisse une trace.
    Si le moteur retombait sur la simulation, la trace n'existerait pas — et c'est
    precisement ce que ce test interdit. Construire le moteur ne suffit pas : il faut
    faire tourner une mission, sinon on ne prouve que l'assemblage.
    """
    trace = tmp_path / "appels.txt"
    binaire = _faux_binaire(tmp_path, "faux-llm", trace=trace)
    monkeypatch.setenv("JIO_BIN_FAUX_LLM", str(binaire))
    monkeypatch.setenv("JIO_CLI_FAUX_LLM_ARGV", "{binary}")

    from jio.bench.tasks import T_SUM_EVEN
    from jio.cli import _simulated_engine
    from jio.core.types import Mission, MissionStatus
    from jio.loop.engine import WorkItem

    modele = resoudre("cli:faux-llm")
    moteur = _simulated_engine(T_SUM_EVEN, seed=0, max_rounds=1, fournisseur=modele)
    rapport = moteur.run(
        Mission(objective=T_SUM_EVEN.objective, id="preuve-cli", max_rounds=1),
        WorkItem(
            objective=T_SUM_EVEN.objective, entrypoint=T_SUM_EVEN.entrypoint,
            checks=T_SUM_EVEN.checks, spec=T_SUM_EVEN.spec(),
        ),
    )

    assert trace.exists(), "le binaire n'a jamais ete appele : le branchement est faux"
    assert trace.read_text(encoding="utf-8").count("appel") >= 1
    # Et la reponse du CLI est bien celle qui est jugee : elle est correcte, donc livree.
    assert rapport.status in (
        MissionStatus.DELIVERED, MissionStatus.DELIVERED_WITH_RESERVATION
    ), rapport.abstention_reason[:200]
    assert "if n % 2 == 0" in rapport.subject
    # Le moteur ne melange pas les sources : tous ses generateurs viennent du CLI.
    assert all(
        getattr(g, "name", "") == "cli:faux-llm" for g in moteur.generators
    ), [getattr(g, "name", "?") for g in moteur.generators]


def test_sans_fournisseur_le_moteur_reste_simule() -> None:
    """Non-regression : le defaut ne change pas, et reste utilisable sans aucune cle."""
    from jio.bench.tasks import T_SUM_EVEN
    from jio.cli import _simulated_engine

    moteur = _simulated_engine(T_SUM_EVEN, seed=0, max_rounds=1)
    assert moteur.generators
    assert all("sim" in getattr(g, "name", "") or "gen" in getattr(g, "name", "")
               for g in moteur.generators), [getattr(g, "name", "?") for g in moteur.generators]


def test_le_fournisseur_reel_ne_touche_pas_aux_personas_du_panel() -> None:
    """Un panel d'une seule voix n'est pas un panel : la decorelation est le sujet."""
    from jio.bench.tasks import T_SUM_EVEN

    from jio.cli import _simulated_engine

    fournisseur = Fournisseur(spec="faux", genre="cli", provider=None, instances=5)
    moteur = _simulated_engine(T_SUM_EVEN, seed=0, fournisseur=fournisseur)
    # Sans provider reel, on reste sur la simulation : le panel garde ses 5 personas.
    assert len(moteur.panel.critics) >= 3


# --------------------------------------------------------------------------- #
# 3. Le meme choix pour une MISSION (`jio run --provider`)
# --------------------------------------------------------------------------- #


def test_run_refuse_un_modele_nomme_mais_indisponible(tmp_path: Path, monkeypatch, capsys) -> None:
    """Une mission qui n'a pas fait tourner le modele demande doit s'arreter, pas mentir."""
    from jio.cli import main

    monkeypatch.setenv("JIO_BIN_OPencode", "/nonexistant")
    monkeypatch.setenv("JIO_BIN_OPENCODE", "/aucun/chemin/opencode")

    code = main(["run", "objectif quelconque", "--provider", "cli:opencode"])

    assert code == 2
    capture = capsys.readouterr()
    assert "introuvable" in capture.err


def test_run_refuse_la_simulation_sans_simulate(capsys) -> None:
    """`--provider simule` sans `--simulate` : il n'y a rien a generer, et on le dit.

    Accepter en silence aurait lance une mission reelle avec un modele qui n'existe pas.
    """
    from jio.cli import main

    code = main(["run", "objectif", "--provider", "simule"])

    assert code == 2
    assert "--simulate" in capsys.readouterr().err


def test_run_avec_un_cli_reel_livre_les_preuves_et_NOMME_la_reserve(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Un seul modele derriere cinq critiques n'est pas un panel : le dire est le sujet.

    Le harness detecte que tous les agents partagent modele et verdict, refuse d'appeler
    cela un consensus (« ce n'est pas un consensus, c'est un echo ») et livre AVEC
    RESERVE. C'est la bonne conduite : le travail est utile, et l'illusion de pluralite
    est denoncee.
    """
    from jio.bench.tasks import T_SUM_EVEN
    from jio.cli import main

    binaire = _faux_binaire(tmp_path, "faux-run")
    monkeypatch.setenv("JIO_BIN_FAUX_RUN", str(binaire))
    monkeypatch.setenv("JIO_CLI_FAUX_RUN_ARGV", "{binary}")

    code = main([
        "run", T_SUM_EVEN.objective, "--task", T_SUM_EVEN.id,
        "--provider", "cli:faux-run", "--state", str(tmp_path / "etat"),
    ])

    sortie = capsys.readouterr().out
    assert code in (0, 1), sortie[-400:]
    assert "3/3" in sortie, sortie[-400:]
    assert "non decorrele" in sortie or "echo" in sortie, sortie[-400:]
