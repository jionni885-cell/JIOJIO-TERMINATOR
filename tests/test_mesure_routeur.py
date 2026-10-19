"""Le benchmark du routeur doit échouer proprement quand son holdout externe manque."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mesure-routeur.py"
_SPEC = importlib.util.spec_from_file_location("mesure_routeur", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_holdout_valide_est_charge_et_structure_est_verifiee(tmp_path: Path) -> None:
    fichier = tmp_path / "holdout.json"
    fichier.write_text(
        '{"cas": [["objectif", "skill", "fr"]], "hors_sujet": ["hors sujet"]}',
        encoding="utf-8",
    )

    assert _MODULE.charger_jeu_b(fichier) == (
        [("objectif", "skill", "fr")],
        ["hors sujet"],
    )


def test_holdout_manquant_a_un_diagnostic_actionnable(tmp_path: Path) -> None:
    absent = tmp_path / "holdout-b.json"

    with pytest.raises(ValueError, match="holdout B illisible"):
        _MODULE.charger_jeu_b(absent)


def test_holdout_mal_forme_n_est_pas_accepte(tmp_path: Path) -> None:
    fichier = tmp_path / "holdout.json"
    fichier.write_text(
        '{"cas": [["objectif", "skill"]], "hors_sujet": ["x"]}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="cas #1 invalide"):
        _MODULE.charger_jeu_b(fichier)


def test_racine_json_de_type_incorrect_a_un_diagnostic_sans_traceback(
    tmp_path: Path, capsys
) -> None:
    fichier = tmp_path / "holdout.json"
    fichier.write_text('["ceci", "n’est pas un objet"]', encoding="utf-8")

    code = _MODULE.main(["--holdout", str(fichier)])

    sortie = capsys.readouterr()
    assert code == 2
    assert "doit être un objet JSON" in sortie.err
    assert "Traceback" not in sortie.err


def test_bootstrap_refuse_les_series_non_appariees() -> None:
    with pytest.raises(ValueError, match="même longueur"):
        _MODULE.ic95_apparie([True], [True, False])


def test_cli_signale_le_holdout_absent_sans_traceback(tmp_path: Path, capsys) -> None:
    code = _MODULE.main(["--holdout", str(tmp_path / "absent.json")])

    sortie = capsys.readouterr()
    assert code == 2
    assert "holdout B illisible" in sortie.err
    assert "Traceback" not in sortie.err
