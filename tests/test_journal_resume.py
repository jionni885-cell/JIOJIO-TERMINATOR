"""Un journal doit survivre au deuxieme processus — sinon il ne sert a rien.

Defaut constate en usage reel, pas en theorie : chaque nouveau processus repartait a
`seq=0` avec `prev=GENESIS` et AJOUTAIT au meme fichier. Resultat : chaine invérifiable
des la deuxieme execution (9 redemarrages mesures sur un journal de 545 evenements).

C'est exactement le moment ou l'on a besoin du journal — verifier ce qui s'est
passe la fois precedente. Un journal qui ne verifie plus n'est pas un journal, c'est
un fichier de texte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.core.errors import IntegrityViolation
from jio.core.journal import Journal
from jio.core.types import TrustLevel


def _append_some(path: Path, count: int, marker: str) -> Journal:
    """Simule un processus : journal neuf sur un fichier existant, puis ecritures."""
    journal = Journal(path=path)
    for i in range(count):
        journal.append("etape", {"i": i, "processus": marker})
    return journal


def test_deux_processus_successifs_produisent_une_chaine_valide(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"

    _append_some(path, 3, "premier")
    second = _append_some(path, 2, "second")

    ok, bad = second.verify_chain()
    assert ok, f"chaine cassee a l'evenement {bad}"
    assert len(second) == 5, "les ecritures du premier processus doivent etre reprises"
    assert [e.seq for e in second] == [0, 1, 2, 3, 4]


def test_l_ecriture_reprise_survit_a_un_rechargement(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    _append_some(path, 2, "a")
    _append_some(path, 2, "b")

    relu = Journal.from_jsonl(path.read_text(encoding="utf-8"))

    ok, bad = relu.verify_chain()
    assert ok, f"la relecture du fichier ne verifie plus (evenement {bad})"
    assert len(relu) == 4


@pytest.mark.parametrize("processus", range(4))
def test_quatre_processus_en_serie_restent_verifiables(tmp_path: Path, processus: int) -> None:
    """Le cas d'usage banal : on relance l'outil plusieurs fois dans la meme journee."""
    path = tmp_path / "journal.jsonl"
    for i in range(processus + 1):
        _append_some(path, 2, f"p{i}")

    relu = Journal.from_jsonl(path.read_text(encoding="utf-8"))

    assert relu.verify_chain() == (True, None)
    assert len(relu) == 2 * (processus + 1)


def test_une_chaine_cassee_est_mise_en_quarantaine_et_dite(tmp_path: Path) -> None:
    """On n'ecrit JAMAIS a la suite d'un journal falsifie, et on ne supprime rien."""
    path = tmp_path / "journal.jsonl"
    _append_some(path, 3, "authentique")

    # Falsification : on modifie un payload, la chaine casse.
    lignes = path.read_text(encoding="utf-8").splitlines()
    lignes[1] = lignes[1].replace('"i": 1', '"i": 999')
    path.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    journal = Journal(path=path)
    journal.append("apres_falsification", {"ok": True})

    assert journal.notices, "la mise en quarantaine doit etre annoncee, pas silencieuse"
    assert any("chaine cassee" in n for n in journal.notices)
    quarantaines = list(tmp_path.glob("journal.jsonl.corrompu-*"))
    assert len(quarantaines) == 1, "le fichier falsifie doit etre conserve, jamais supprime"
    assert '"i": 999' in quarantaines[0].read_text(encoding="utf-8")
    assert journal.verify_chain() == (True, None), "la chaine neuve doit etre saine"


def test_un_journal_vide_ne_declenche_aucune_rotation(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text("", encoding="utf-8")

    journal = Journal(path=path)
    journal.append("debut", {})

    assert journal.notices == []
    assert not list(tmp_path.glob("*.corrompu-*"))


def test_le_niveau_de_confiance_est_conserve_a_la_reprise(tmp_path: Path) -> None:
    """La reprise doit restituer l'evenement entier, pas seulement son numero."""
    path = tmp_path / "journal.jsonl"

    premier = Journal(path=path)
    premier.append("sourdine", {"x": 1}, trust=TrustLevel.EXTERNAL)
    premier.append("normal", {"y": 2})

    second = Journal(path=path)
    second.append("suite", {})

    assert second.events("sourdine")[0].trust is TrustLevel.EXTERNAL
    assert [e.kind for e in second] == ["sourdine", "normal", "suite"]


def test_impossible_de_deplacer_le_fichier_echoue_ouvert(tmp_path: Path, monkeypatch) -> None:
    """Si la quarantaine est impossible, on refuse d'ecrire plutot que de falsifier.

    Fail-closed : un journal falsifie sur lequel on continue d'ecrire detruirait la
    seule preuve de ce qui s'est passe.
    """
    path = tmp_path / "journal.jsonl"
    _append_some(path, 2, "authentique")
    lignes = path.read_text(encoding="utf-8").splitlines()
    lignes[1] = lignes[1].replace('"i": 1', '"i": 42')
    path.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    def refus(*args, **kwargs):
        raise OSError("disque en lecture seule")

    monkeypatch.setattr(Path, "rename", refus)

    with pytest.raises(IntegrityViolation):
        Journal(path=path).append("suite", {})


def test_from_jsonl_ne_relit_pas_le_fichier_deux_fois(tmp_path: Path) -> None:
    """`from_jsonl` remplit deja les evenements : la reprise ne doit rien dupliquer."""
    path = tmp_path / "journal.jsonl"
    _append_some(path, 3, "a")

    journal = Journal.from_jsonl(path.read_text(encoding="utf-8"), path=path)
    journal.append("suite", {})

    assert len(journal) == 4
    assert journal.verify_chain() == (True, None)
