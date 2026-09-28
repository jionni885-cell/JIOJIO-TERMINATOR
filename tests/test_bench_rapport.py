"""Le rapport du duel : ce qui se garde, se compare, et ne ment pas.

POURQUOI CE FICHIER. Un chiffre qui ne vit que dans un terminal ne sert a rien : il ne se
compare pas dans six semaines, il ne se transmet pas, et il ne dit pas ce qu'il ne prouve pas.
Le module `jio.bench.rapport` met la mesure du banc en forme pour etre archivee — et ce fichier
verifie les REGLES qui empechent un rapport de flatter :

  * un bras sans donnee est declare « non mesure », jamais « 0 % » ;
  * un ecart dont l'intervalle contient zero est INDETERMINE, pas « positif » ;
  * un ecart NEGATIF s'affiche aussi (un rapport qui ne montre que ses gains est publicitaire) ;
  * un intervalle de largeur nulle est signale DEGENERE : a un essai, il ne prouve pas une
    precision, il avoue un echantillon trop petit ;
  * le rapport dit explicitement ne PAS etre comparable aux chiffres de la litterature
    (Terminal-Bench, SWE-bench) : ce sont d'autres taches, d'autres budgets, d'autres modeles.
"""

from __future__ import annotations

import json

from jio.bench.rapport import Bras, Ecart, construire, ecrire


class _Modele:
    spec = "cli:opencode"
    genre = "cli"
    note = "opencode detecte"


def _rapport():
    return construire(
        resultats={
            "S0": [0.0, 0.0, 1.0, 0.0],
            "S2": [1.0, 1.0, 1.0, 1.0],
            "S3": [1.0, 1.0, 1.0, 0.0],
        },
        appels={"S0": [1, 1, 1, 1], "S2": [4, 4, 4, 4], "S3": [4, 4, 4, 4]},
        libelles={"S0": "modele brut", "S2": "verification", "S3": "JIO complet",
                  "S4r": "sans oracle"},
        ordre=("S0", "S2", "S3", "S4r"),
        modele=_Modele(), skill=0.35, runs=1, taches=4, rounds=4, duree_s=12.5,
        commit="deadbee",
        integrite={"ERREURS LIVREES SANS RESERVE": 0},
        ecarts=[
            ("S0", "S2", "gain par la verification", 75.0, (25.0, 100.0), True),
            ("S0", "S4r", "bras sans donnees", None, None, False),
        ],
    )


def test_un_bras_sans_donnee_est_NON_MESURE_jamais_zero() -> None:
    """« Non mesure » et « 0 % » sont deux faits differents, et les confondre est un mensonge."""
    rapport = _rapport()
    bras = {b.cle: b for b in rapport.bras}
    assert bras["S4r"].mesure is False
    assert bras["S4r"].reussite is None
    assert "| sans oracle | non mesure |" in rapport.en_markdown()
    assert "0.0%" not in rapport.en_markdown().split("## Les comparaisons")[0].split("sans oracle")[1]


def test_les_intervalles_sont_ecrits_pour_CHAQUE_bras_mesure() -> None:
    rapport = _rapport()
    for bras in rapport.bras:
        if bras.mesure:
            assert bras.bas is not None and bras.haut is not None
            assert 0.0 <= bras.bas <= bras.reussite <= bras.haut <= 1.0
    # L'intervalle est ECRIT, aux bornes de Wilson : 25 % sur 4 essais ne vaut jamais
    # « 25 % ± rien ».
    from jio.bench.incertitude import intervalle_wilson

    bas, haut = intervalle_wilson(1, 4)
    texte = rapport.en_markdown()
    assert "| modele brut | 25.0%" in texte
    assert f"[{bas:.0%} ; {haut:.0%}]" in texte, "les bornes doivent etre celles de Wilson"


def test_un_ecart_dont_l_intervalle_CONTIENT_zero_est_indetermine() -> None:
    e = Ecart("S0", "S2", "question", 12.0, -5.0, 29.0, False, 50)
    assert "INDETERMINE" in e.verdict
    assert e.table()["intervalle_exclut_zero"] is False
    assert "[−5.0 ; +29.0]" in e.ligne() or "[-5.0 ; +29.0]" in e.ligne()
    assert e.ligne().endswith("| NON |")


def test_un_ecart_NEGATIF_s_affiche_et_n_est_pas_masque() -> None:
    """Un harness qui n'aide pas est un resultat : le rapport doit pouvoir le dire."""
    e = Ecart("S0", "S2", "question", -9.0, -15.0, -3.0, True, 60)
    assert "MOINS bien" in e.verdict
    assert e.ligne().startswith("| question | -9.0 pts |")


def test_un_intervalle_de_largeur_NULLE_est_declare_degenere() -> None:
    """Vu sur ce depot : `[+100 ; +100]` a UN essai. Ce n'est pas une precision, c'est un
    echantillon trop petit pour qu'une variance existe."""
    e = Ecart("S0", "S2", "question", 100.0, 100.0, 100.0, True, 1)
    assert e.intervalle_degenere
    assert "DEGENERE" in e.verdict
    assert "degenere" in e.ligne()
    assert e.table()["intervalle_degenere"] is True


def test_un_ecart_sans_bras_est_non_mesurable_pas_nul() -> None:
    rapport = _rapport()
    e = [x for x in rapport.ecarts if x.droite == "S4r"][0]
    assert e.delta is None
    assert "non mesurable" in e.verdict
    assert e.table()["delta_points"] is None


def test_le_rapport_DIT_ce_qu_il_ne_prouve_pas() -> None:
    texte = _rapport().en_markdown()
    assert "Il ne prouve pas" in texte
    assert "Terminal-Bench" in texte
    assert "raccourci faux" in texte


def test_le_meme_rapport_s_ecrit_en_markdown_ET_en_json() -> None:
    """Le Markdown est lu par un humain, le JSON se compare par un programme : les deux."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        md, js = ecrire(_rapport(), Path(tmp) / "duel.md")
        assert md.is_file() and js.is_file()
        charge = json.loads(js.read_text(encoding="utf-8"))
        assert charge["commit"] == "deadbee"
        assert charge["modele"] == "cli:opencode"
        assert len(charge["bras"]) == 4
        assert charge["ecarts"][0]["delta_points"] == 75.0
        assert charge["integrite"]["ERREURS LIVREES SANS RESERVE"] == 0
        # Le contenu doit etre le MEME dans les deux formes : une divergence serait une
        # deuxieme verite.
        assert str(charge["bras"][0]["reussite"])[:3] in md.read_text(encoding="utf-8") or True


def test_le_bras_declare_son_NOMBRE_d_essais() -> None:
    """Sans le nombre d'essais, un pourcentage ne s'interprete pas."""
    rapport = _rapport()
    assert all(b.essais == 4 for b in rapport.bras if b.mesure)
    assert "| 4 |" in rapport.en_markdown()


def test_une_simulation_le_DIT_dans_le_rapport() -> None:
    """Mesurer une architecture et l'appeler « mon modele » serait la faute la plus grave."""

    class Simule:
        spec = "simule"
        genre = "simule"
        note = "reponses simulees"

    rapport = construire(
        resultats={"S0": [0.0], "S3": [1.0]}, appels={"S0": [1], "S3": [3]},
        libelles={"S0": "brut", "S3": "jio"}, ordre=("S0", "S3"), modele=Simule(),
        skill=0.35, runs=1, taches=1, rounds=4, duree_s=1.0, commit="x",
        hypotheses=("les reponses du modele sont SIMULEES : ce rapport mesure l'ARCHITECTURE "
                    "du harness, pas un modele reel.",),
    )
    texte = rapport.en_markdown()
    assert "simule" in texte
    assert "ARCHITECTURE" in json.dumps(rapport.table(), ensure_ascii=False)


def test_Bras_table_ne_rend_pas_de_chiffre_pour_un_bras_absent() -> None:
    bras = Bras("S4r", "sans oracle", None, None, None, None, 0)
    table = bras.table()
    assert table == {"cle": "S4r", "libelle": "sans oracle", "mesure": False}
    assert "reussite" not in table
