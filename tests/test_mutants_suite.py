"""Le score de mutation mesure la SUITE : il doit donc etre juste avant d'etre flatteur.

Deux exigences, et la seconde compte plus que la premiere :

* un mutant qu'un test attrape est compte TUE ;
* un mutant que rien n'attrape est compte SURVIVANT — surtout quand c'est le fichier de ce
  module qui est mute, cas ou le rapport doit dire que rien ne peut le tuer plutot que de
  faire croire a une mesure.

Le troisieme test est celui qui protege l'outil contre lui-meme : un score vide ne doit
JAMAIS s'afficher comme un succes.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from jio.verify.mutants_suite import (
    MutantDeLaSuite,
    RapportSuite,
    famille,
    formater,
    mesurer,
)


def _mini_depot(tmp_path: Path, *, avec_test: bool) -> Path:
    """Un depot minuscule : un module avec une comparaison, et un test qui la couvre."""
    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "jio" / "limite.py").write_text(
        '"""Module mesure."""\n\n\ndef autorise(valeur: int) -> bool:\n'
        "    return valeur <= 10\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    if avec_test:
        (tmp_path / "tests" / "test_limite.py").write_text(
            "from jio.limite import autorise\n\n\n"
            "def test_limite() -> None:\n"
            "    assert autorise(10) is True\n"
            "    assert autorise(11) is False\n",
            encoding="utf-8",
        )
    else:
        (tmp_path / "tests" / "test_ailleurs.py").write_text(
            "def test_rien() -> None:\n    assert True\n", encoding="utf-8"
        )
    return tmp_path


def test_un_mutant_attrape_est_compte_TUE(tmp_path: Path) -> None:
    """Le mutant `<=` devient `<` : le test qui verifie la borne doit le tuer."""
    racine = _mini_depot(tmp_path, avec_test=True)
    rapport = mesurer(
        racine,
        fichiers=[racine / "jio" / "limite.py"],
        budget_par_fichier=4,
        plafond_tests=2,
        timeout=120,
    )
    assert rapport.mutants, "aucun mutant genere : le test ne prouve rien"
    assert rapport.tues >= 1, [
        (m.label, m.preuve) for m in rapport.mutants
    ]
    assert rapport.score > 0


def test_sans_test_le_mutant_survit_et_le_rapport_le_DIT(tmp_path: Path) -> None:
    """Un module qu'aucun test ne mentionne : le rapport doit le declarer inteste.

    C'est le cas qui compte : un outil qui compterait ce mutant comme « tue » parce que la
    suite a echoue pour une autre raison (import casse, collection en erreur) mentirait
    dans le sens qui flatte.
    """
    racine = _mini_depot(tmp_path, avec_test=False)
    rapport = mesurer(
        racine,
        fichiers=[racine / "jio" / "limite.py"],
        budget_par_fichier=2,
        plafond_tests=2,
        timeout=120,
    )
    assert rapport.survivants, "sans test, un mutant ne peut pas etre tue"
    assert "ne mentionne" in rapport.note or "SURVIVANT" in formater(rapport)


def test_un_score_vide_n_est_pas_un_succes() -> None:
    """Zero mutant mesure = zero preuve : le score vaut 0, jamais 1."""
    vide = RapportSuite()
    assert vide.score == 0.0
    assert vide.tues == 0
    assert vide.tests_lances == 0, "aucun mutant lance : le compte doit rester a zero"
    assert "0/0" in formater(vide)


def test_la_famille_d_un_mutant_est_lue_sur_l_etiquette() -> None:
    """Un score bas fait de plafonds n'a pas le meme sens qu'un score bas de comparaisons."""
    assert famille("booleen True -> False") == "booleen"
    assert famille("comparaison LtE -> Gt") == "comparaison"
    assert famille("constante 0 -> 1") == "constante"
    assert famille("etiquette inconnue") == "autre"
    rapport = RapportSuite(
        mutants=[
            MutantDeLaSuite(Path("a.py"), "booleen True -> False", True),
            MutantDeLaSuite(Path("a.py"), "constante 0 -> 1", False),
        ]
    )
    texte = formater(rapport)
    assert "par famille" in texte
    assert "booleen 1/1" in texte and "constante 0/1" in texte


def test_le_formater_nomme_les_survivants_et_la_lecture() -> None:
    rapport = RapportSuite(
        mutants=[MutantDeLaSuite(Path("jio/x.py"), "comparaison LtE -> Gt", False, "p")]
    )
    texte = formater(rapport)
    assert "SURVIVANT  jio/x.py" in texte
    assert "preuve manquante" in texte
    assert "0%" in texte


# --------------------------------------------------------------------------- #
# Les survivants mesures, transformes en tests qui les tuent
# --------------------------------------------------------------------------- #


def test_un_enregistrement_fige_refuse_la_modification() -> None:
    """`jio mutants` a mesure que rien ne protegeait `frozen=True` sur ces dataclasses.

    L'immutabilite n'est pas un detail : ces enregistrements servent de cles et de traces,
    et une modification en place rendrait un historique faux sans que rien ne le signale.
    Le mutant les rendait MUTABLES ; ce test le tue.
    """
    from jio.audit.oscillation import ProgressPoint
    from jio.verify.imports import ImportProblem

    point = ProgressPoint(round_index=0, score=1.0, digest="abc")
    with pytest.raises(dataclasses.FrozenInstanceError):
        point.score = 0.0  # type: ignore[misc]
    probleme = ImportProblem(Path("a.py"), 1, "message")
    with pytest.raises(dataclasses.FrozenInstanceError):
        probleme.message = "autre"  # type: ignore[misc]


def test_un_historique_vide_n_a_pas_de_premier_pas_fautif() -> None:
    """La borne `<= 0` de `FirstErrorLocator` n'etait pas testee : un mutant la passait a 1.

    Taille nulle, taille un : ce sont les deux cas ou la bissection n'a rien a chercher.
    """
    from jio.audit.blame import FirstErrorLocator

    jamais = FirstErrorLocator(faulty=lambda _index: True, length=0)
    assert jamais.locate() is None
    assert FirstErrorLocator(faulty=lambda _index: True, length=1).locate() == 0
    assert FirstErrorLocator(faulty=lambda _index: False, length=5).locate() is None


def test_le_nombre_d_erreurs_d_un_tour_vaut_zero_par_defaut() -> None:
    """Defaut mesure : `errors: int = 0` devenait 1 sans qu'un test s'en apercoive."""
    from jio.audit.oscillation import ProgressPoint

    assert ProgressPoint(round_index=0, score=1.0, digest="x").errors == 0


def test_la_selection_des_tests_classe_par_pertinence(tmp_path: Path) -> None:
    """Un test qui IMPORTE le module vise passe avant un test qui le cite en passant.

    Mesure faite : un mutant de `jio/verify/imports.py` survivait parce que le fichier de
    test qui couvrait la classe mutee arrivait cinquieme dans l'ordre alphabetique, et que
    le plafond en gardait quatre. Le classement par pertinence corrige la cause ; ce test
    l'empeche de revenir a l'ordre alphabetique sans qu'on s'en apercoive.
    """
    from jio.verify.mutants_suite import _tests_pour

    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "module_vise.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    # `aaa` cite le module en passant, `zzz` l'importe explicitement.
    (tmp_path / "tests" / "test_aaa.py").write_text(
        "# on parle de module_vise.py ici\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_zzz.py").write_text(
        "from jio.module_vise import x\n\n\ndef test_x():\n    assert x == 1\n",
        encoding="utf-8",
    )
    choisis = _tests_pour(tmp_path, tmp_path / "jio" / "module_vise.py", 1)
    assert choisis == [str(tmp_path / "tests" / "test_zzz.py")], choisis
    # Et les deux restent candidats quand le plafond le permet.
    assert len(_tests_pour(tmp_path, tmp_path / "jio" / "module_vise.py", 5)) == 2


# --------------------------------------------------------------------------- #
# 6. Les mutants EQUIVALENTS : declares, justifies, jamais maquilles
# --------------------------------------------------------------------------- #


def test_une_equivalence_declaree_porte_toujours_sa_raison() -> None:
    """Un mutant equivalent sans raison serait une exclusion muette, sous un autre nom."""
    from jio.verify.mutants_suite import EQUIVALENTS

    assert EQUIVALENTS, "la table est vide : ce test ne prouve alors rien de plus"
    for (fichier, label), raison in EQUIVALENTS.items():
        assert fichier.endswith(".py"), f"chemin suspect : {fichier}"
        assert label.strip(), f"{fichier} : etiquette vide"
        assert len(raison.strip()) > 40, (
            f"{fichier} [{label}] : la raison est trop courte pour dire quoi que ce soit"
        )


def test_aucune_equivalence_declaree_n_est_un_fantome() -> None:
    """Le mutant declare doit EXISTER encore, avec cette etiquette exacte.

    Une equivalence ecrite pour un mutant qui n'existe plus est une raison qui ment : elle
    protege une ligne qui n'est plus mutee, et personne ne s'en apercevrait puisque rien ne
    la contredit. On rejoue donc le moteur de mutation sur le fichier vise.
    """
    from jio.verify.mutants_suite import EQUIVALENTS
    from jio.verify.mutation import mutate

    racine = Path(__file__).resolve().parents[1]
    for (fichier, label) in EQUIVALENTS:
        source = (racine / fichier).read_text(encoding="utf-8")
        etiquettes = {m.label for m in mutate(source, budget=6)}
        assert label in etiquettes, (
            f"{fichier} : le mutant declare [{label}] n'existe plus "
            f"(etiquettes mesurees : {sorted(etiquettes)})"
        )


def test_un_mutant_equivalent_est_compte_a_part_et_ne_tue_pas_le_score(tmp_path: Path) -> None:
    """Un equivalent declare n'est NI un kill, NI un survivant : c'est une troisieme case."""
    from jio.verify.mutants_suite import MutantDeLaSuite, RapportSuite, formater

    equivalent = MutantDeLaSuite(
        Path("jio/exemple.py"), "bloc conditionnel vide", False,
        "la suite passe AVEC le mutant",
        equivalent="le retour retire est rattrape par le except juste en dessous",
    )
    survivant = MutantDeLaSuite(Path("jio/exemple.py"), "constante 0 -> 1", False)
    rapport = RapportSuite(mutants=[equivalent, survivant])

    assert rapport.survivants == [survivant], "l'equivalent ne doit pas etre un survivant"
    assert rapport.equivalents == [equivalent]
    assert rapport.tues == 0
    assert rapport.score == 0.0
    texte = formater(rapport)
    assert "SURVIVANT  jio/exemple.py  [constante 0 -> 1]" in texte
    assert "EQUIVALENT DECLARE" in texte
    assert "rattrape par le except" in texte, "la raison doit apparaitre dans le rapport"


def test_le_rapport_n_ampute_plus_la_liste_des_survivants() -> None:
    """Chaque survivant doit etre lisible : un survivant cache ne demande aucun test.

    Le rapport s'arretait a douze lignes (« ... et N autre(s) »). Sur un depot reel, cela
    voulait dire : douze preuves manquantes visibles, les autres hors de portee — alors que
    la regle du depot est que CHACUNE demande un test ou une raison ecrite.
    """
    from jio.verify.mutants_suite import MutantDeLaSuite, RapportSuite, formater

    mutants = [
        MutantDeLaSuite(Path(f"jio/f{i}.py"), "constante 0 -> 1", False)
        for i in range(20)
    ]
    texte = formater(RapportSuite(mutants=mutants))
    for i in range(20):
        assert f"jio/f{i}.py" in texte
    assert "autre(s)" not in texte


# --------------------------------------------------------------------------- #
# Les deux natures de survivant : apparente (outil) ou confirmee (code)
# --------------------------------------------------------------------------- #


def test_un_survivant_TUE_par_la_suite_complete_est_APPARENT_pas_confirme() -> None:
    """Un survivant qui meurt sur la suite entiere vient de la SELECTION, pas du code.

    Le module le dit depuis le debut : la selection des tests est une heuristique DECLAREE, et
    un survivant peut en venir. Il ne le MESURAIT pas — donc le rapport melangeait deux choses
    qui n'appellent pas la meme correction :

      * APPARENT  : la selection ne lancait pas le fichier qui le tuait. C'est un fait sur
        l'OUTIL ; la reponse est d'elargir la selection, pas d'ecrire un test ;
      * CONFIRME  : aucun test du depot ne distingue cette ligne. C'est un fait sur le CODE ;
        la reponse est un test, ou une raison ecrite.

    Melanger les deux donne un score qu'on ne sait pas corriger : on ne sait pas quoi faire de
    « 75 % » quand il additionne une erreur d'outil et une preuve manquante.
    """
    from jio.verify.mutants_suite import MutantDeLaSuite, RapportSuite

    apparent = MutantDeLaSuite(Path("jio/x.py"), "booleen True -> False", tue=False,
                               tue_par_suite_complete=True)
    confirme = MutantDeLaSuite(Path("jio/y.py"), "constante 1 -> 2", tue=False)
    tue = MutantDeLaSuite(Path("jio/z.py"), "bloc conditionnel vide", tue=True)
    equivalent = MutantDeLaSuite(Path("jio/w.py"), "bloc conditionnel vide", tue=False,
                                 equivalent="le code retire est repris juste apres")

    rapport = RapportSuite(mutants=[apparent, confirme, tue, equivalent])
    assert rapport.apparents == [apparent]
    assert rapport.confirmes == [confirme]
    # Un declare equivalent n'est ni apparent, ni confirme : il ne demande rien.
    assert all(m is not equivalent for m in rapport.apparents + rapport.confirmes)
    # Deux scores, deux significations. L'ecart EST l'erreur de l'heuristique.
    assert rapport.score == 1 / 4
    assert rapport.score_verifie == 2 / 4
    assert rapport.score_verifie >= rapport.score

    texte = formater(rapport)
    assert "APPARENT" in texte and "apparent" in texte
    assert "score apres verification de la selection : 2/4" in texte
    assert "L'ecart avec 25% EST l'erreur de l'heuristique" in texte
    assert "SURVIVANT  jio/y.py" in texte
    assert "SURVIVANT  jio/x.py" not in texte, "un apparent n'est pas un survivant a corriger"


def test_le_rejeu_ne_coute_rien_quand_tout_est_TUE(tmp_path: Path) -> None:
    """Aucun survivant : aucun rejeu de suite complete, donc aucune seconde de perdue.

    Le rejeu est reserve aux survivants (l'exception) : c'est ce qui rend l'information
    disponible sans allonger la campagne. Ce test mesure la promesse — un module qui rejoue
    tout le temps serait inutilisable sur un depot reel.
    """
    from jio.verify.mutants_suite import mesurer

    # Un module dont la ligne mutee EST couverte par un test present : le mutant meurt tout de
    # suite, donc rien n'est rejoue.
    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "jio" / "plafond.py").write_text("MAX = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_plafond.py").write_text(
        "from jio.plafond import MAX\n\n\ndef test_max():\n    assert MAX == 2\n",
        encoding="utf-8",
    )
    rapport = mesurer(
        tmp_path, fichiers=[tmp_path / "jio" / "plafond.py"], budget_par_fichier=2, timeout=120
    )
    assert rapport.mutants and rapport.tues == len(rapport.mutants)
    assert rapport.apparents == [] and rapport.confirmes == []
    assert rapport.tests_lances == len(rapport.mutants), "un seul lancement par mutant, pas deux"


def test_un_survivant_SANS_test_du_tout_est_JOUE_sur_la_suite_complete(tmp_path: Path) -> None:
    """Le cas ou la selection ne trouve rien : on rejoue, et le survivant reste CONFIRME.

    Sur un module que personne ne mentionne, la selection rend une liste vide et le document le
    dit (« le mutant est compte SURVIVANT »). Le rejeu de la suite entiere confirme que c'est
    bien le depot entier qui ne distingue pas la ligne — pas l'heuristique.
    """
    from jio.verify.mutants_suite import mesurer

    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "jio" / "orphelin.py").write_text("SEUIL = 7\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ailleurs.py").write_text(
        "def test_rien():\n    assert True\n", encoding="utf-8"
    )
    rapport = mesurer(
        tmp_path, fichiers=[tmp_path / "jio" / "orphelin.py"], budget_par_fichier=1, timeout=120
    )
    assert rapport.confirmes, rapport.mutants
    assert not rapport.apparents
    assert "aucun test ne mentionne" in rapport.note


def test_le_verdict_de_LA_CLI_ne_confond_pas_outil_et_code(tmp_path: Path) -> None:
    """Un survivant apparent ne fait PAS echouer la commande : ce n'est pas un defaut du code.

    C'est la consequence pratique de la distinction, et elle est mesurable de bout en bout : le
    depot de test est construit pour produire exactement ce cas — un test qui mentionne le
    module muté (donc la selection n'est pas vide) mais qui ne peut pas tuer le mutant, et un
    second test, non mentionnant, qui le tue. Avec `--plafond-tests 1`, la selection ne garde
    que le premier : le mutant survit au score brut et meurt a la suite complete.

    Sortir en echec ici ferait corriger le mauvais probleme : l'utilisateur ecrirait un test
    de plus alors que son depot en a deja un qui couvre la ligne.
    """
    from jio.cli import main

    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "jio" / "piece.py").write_text("SEUIL = 7\n", encoding="utf-8")
    (tmp_path / "jio" / "agrege.py").write_text(
        "from jio.piece import SEUIL\n\nTOTAL = SEUIL * 2\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    # Ce test mentionne le module : il entre dans la selection, et ne tue rien.
    (tmp_path / "tests" / "test_piece.py").write_text(
        "from jio.piece import SEUIL\n\n\ndef test_positif():\n    assert SEUIL > 0\n",
        encoding="utf-8",
    )
    # Ce test tue le mutant, sans jamais nommer le module : il est hors selection.
    (tmp_path / "tests" / "test_systeme.py").write_text(
        "from jio.agrege import TOTAL\n\n\ndef test_total():\n    assert TOTAL == 14\n",
        encoding="utf-8",
    )

    code = main([
        "mutants", "--root", str(tmp_path), "--budget", "1", "--plafond-tests", "1",
        "--fichiers", "jio/piece.py",
    ])
    assert code == 0, "un survivant APPARENT ne doit pas faire echouer la commande"

    # Et le meme depot, mesure sur la suite entiere : le survivant disparait tout simplement.
    code_exact = main([
        "mutants", "--root", str(tmp_path), "--budget", "1", "--tout",
        "--fichiers", "jio/piece.py",
    ])
    assert code_exact == 0
