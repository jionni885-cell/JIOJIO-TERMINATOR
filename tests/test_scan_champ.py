"""Quels documents du projet `jio scan` doit-il juger, dans un projet qui n'est pas le sien ?

Le defaut, mesure sur un projet ETRANGER apres `jio start` : le balayage y produisait 22 constats
« chemin cite INTROUVABLE » — `jio/artifacts/doctrine.py`, `jio/artifacts/definitions.py` — tous
cites par les documents que jio venait d'installer chez l'utilisateur. Ces chemins existent dans
le depot de jio, pas chez lui, et ils ne peuvent pas y exister. Le balayage ne trouvait alors
aucun defaut du projet, et apprenait a l'utilisateur a ignorer ses constats — ce qui coute ensuite
les vrais.

La reponse est structurelle : un document qui vit dans un emplacement gere par jio
(`.jio/`, `.hermes/skills/`, `.opencode/agents/`, consignes d'agent a la racine) est du contenu de
jio, pas du projet. Et surtout : dans le depot DE JIO, rien n'est filtre — les chemins cites y
existent, c'est leur maison, et exclure nos documents reduirait l'audit de 28 documents a 2.
"""

from __future__ import annotations

from pathlib import Path


def test_les_emplacements_geres_par_jio_sont_reconnus(tmp_path: Path) -> None:
    from jio.scan_champ import est_un_document_de_jio

    chemins = [
        ".jio/ACTIVE.md",
        ".hermes/skills/anti-error/failure-memory/SKILL.md",
        ".opencode/agents/jio-builder.md",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
    ]
    for rel in chemins:
        chemin = tmp_path / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("# contenu\n", encoding="utf-8")
        assert est_un_document_de_jio(chemin, tmp_path), f"{rel} devrait etre reconnu comme de jio"

    # Ce qui appartient au PROJET : la reponse conservatrice, parce que se tromper dans l'autre
    # sens ferait disparaitre de vrais defauts du champ du balayage.
    for rel in ("README.md", "docs/guide.md", "src/NOTES.md", "CHANGELOG.md"):
        chemin = tmp_path / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("# contenu\n", encoding="utf-8")
        assert not est_un_document_de_jio(chemin, tmp_path), (
            f"{rel} appartient au projet et ne doit pas etre ecarte"
        )


def test_un_lien_vers_l_installation_de_jio_est_du_contenu_de_jio(tmp_path: Path) -> None:
    """Les competences installees par `jio start` peuvent etre des LIENS vers le depot de jio.

    Un `SKILL.md` lie ne vit pas sous la racine du projet : le filtre doit le reconnaitre, sinon
    ses chemins cites (`jio/...`) sont juges contre le projet de l'utilisateur.
    """
    from jio.scan_champ import est_un_document_de_jio

    ailleurs = tmp_path.parent / (tmp_path.name + "-ailleurs")
    (ailleurs / "skills").mkdir(parents=True)
    cible = ailleurs / "skills" / "SKILL.md"
    cible.write_text("# competence\n", encoding="utf-8")

    lien = tmp_path / "SKILL.md"
    lien.symlink_to(cible)
    assert est_un_document_de_jio(lien, tmp_path)


def _projet(racine: Path, *, avec_paquet_jio: bool) -> None:
    """Un projet minimal qui cite, dans deux documents, un chemin qui n'existe pas chez lui."""
    if avec_paquet_jio:
        (racine / "jio").mkdir()
        (racine / "jio" / "__init__.py").write_text("", encoding="utf-8")
    (racine / "README.md").write_text(
        "Le projet, avec un chemin cite qui manque : `jio/artifacts/doctrine.py`.\n",
        encoding="utf-8",
    )
    (racine / "AGENTS.md").write_text(
        "Consignes installees par jio, avec un chemin cite qui manque : "
        "`jio/artifacts/definitions.py`.\n",
        encoding="utf-8",
    )


def test_le_balayage_du_DEPOT_DE_JIO_ne_filtre_RIEN(tmp_path: Path, capsys) -> None:
    """Dans le depot de jio, tous les documents restent dans le champ de l'audit.

    Mesure qui a paye ce test : le filtre applique sans discernement faisait passer le balayage du
    depot de 36 documents a 10 — une « correction » qui rend un outil aveugle en le rendant
    silencieux. Ici la racine porte le paquet `jio/`, donc les chemins cites peuvent exister : le
    filtre est DESACTIVE, `AGENTS.md` est audite comme le reste, et le constat est rendu.
    """
    from jio.cli import main

    _projet(tmp_path, avec_paquet_jio=True)
    main(["scan", str(tmp_path)])
    sortie = capsys.readouterr().out

    assert "hors du champ" not in sortie, (
        "le depot de jio ne doit rien ecarter : ses documents citent des chemins qui existent "
        "chez lui\n" + sortie[-500:]
    )
    # La preuve affichee est TRONQUEE a 160 caracteres, et `…/definitions.py` y perd son
    # extension quand le chemin est long : on cherche le fragment qui survit toujours au
    # prefixe. (Mesure : la premiere version de ce test cherchait « definitions.py » et
    # echouait alors que le constat etait bien rendu.)
    assert "jio/artifacts/definitions" in sortie, "AGENTS.md n'a pas ete audite dans le depot de jio"


def test_sur_un_projet_ETRANGER_les_documents_de_jio_sortent_du_champ(
    tmp_path: Path, capsys
) -> None:
    """Le meme projet, sans paquet `jio` : ses consignes installees ne sont plus ses documents.

    Le README, lui, reste audite — c'est le document de l'utilisateur, et un chemin qu'il cite
    et qui n'existe pas est un vrai defaut de son depot.
    """
    from jio.cli import main

    _projet(tmp_path, avec_paquet_jio=False)
    main(["scan", str(tmp_path)])
    sortie = capsys.readouterr().out

    assert "hors du champ" in sortie, sortie[-400:]
    assert "jio/artifacts/doctrine" in sortie, (
        "le README de l'utilisateur n'est plus audite : " + sortie[-400:]
    )
    assert "jio/artifacts/definitions" not in sortie, (
        "un document installe par jio est juge contre le projet de l'utilisateur : " + sortie[-400:]
    )
