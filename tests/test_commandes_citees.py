"""Un document qui cite une commande inexistante envoie l'utilisateur dans une erreur.

L'oracle est ici le plus fiable qui existe, et il ne coute rien : le parseur d'arguments du
programme lui-meme. `jio scan --stricte` n'existe pas — ce n'est pas une opinion, c'est
`argparse` qui le dit. La verification a deja trouve deux defauts reels dans les documents
de ce depot (`jio sync` documente a trois endroits, `jio --version` pris a tort pour une
sous-commande).

Ces tests portent surtout sur les FAUX POSITIFS : un verificateur qui accuse a tort un
document correct sera desactive par son utilisateur, et ne vaudra plus rien. Chaque cas
ci-dessous vient d'un document reel de ce depot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.verify.claims import Genre, verifier
from jio.verify.commands import commandes_citees, parser_reel, verifier_commande


# --------------------------------------------------------------------------- #
# 1. L'extraction : ce qui est une invocation, et ce qui n'en est pas
# --------------------------------------------------------------------------- #


def test_extrait_une_invocation_citee() -> None:
    trouvees = commandes_citees("Lancez `jio scan . --strict` pour un audit.")
    assert len(trouvees) == 1
    assert trouvees[0].sous_commande == "scan"
    assert trouvees[0].options == ("--strict",)


def test_extrait_plusieurs_invocations_dans_l_ordre() -> None:
    trouvees = commandes_citees("`jio claims README.md` puis `jio artifacts --budget`")
    assert [c.sous_commande for c in trouvees] == ["claims", "artifacts"]


def test_accepte_un_invocation_avec_prefixe_python() -> None:
    """Les documents citent `python3 -m jio ...` : c'est la meme commande."""
    trouvees = commandes_citees("`python3 -m jio scan .`")
    assert [c.sous_commande for c in trouvees] == ["scan"]


def test_une_commande_sans_backticks_n_est_pas_une_affirmation() -> None:
    """Un document peut PARLER de jio sans rien citer : il n'affirme alors rien de verifiable."""
    assert commandes_citees("Le programme jio scan . est pratique.") == ()


@pytest.mark.parametrize(
    "ligne",
    [
        "jio run \"objectif\" --prose",
        "jio mcp --prove 2>&1 | grep outil",
        "jio scan . --strict && jio claims README.md",
        "jio artifacts --write > /dev/null",
        "jio claims README.md   # verifie le README",
    ],
)
def test_les_enchainements_de_coquille_ne_sont_pas_des_options_jio(ligne: str) -> None:
    """Sinon `jio run "x" | jq .id` ferait chercher une option `jio` chez `jq`.

    Chaque cas vient d'un document ou d'un script reel de ce depot. Le fragment apres `|`,
    `&&`, `>` ou `#` appartient a l'AUTRE programme : l'analyse doit s'y arreter.
    """
    commande = commandes_citees(f"`{ligne}`")[0]
    assert verifier_commande(commande) is None, commande


# --------------------------------------------------------------------------- #
# 2. La verification : l'oracle est le parseur, pas une heuristique
# --------------------------------------------------------------------------- #


def test_la_sous_commande_du_parseur_est_reconnue() -> None:
    """Chaque sous-commande reellement declaree doit passer : aucun faux positif."""
    parser = parser_reel()
    declarees = sorted(
        action.choices
        for action in parser._actions  # noqa: SLF001
        if hasattr(action, "choices") and isinstance(action.choices, dict)
    )[0]
    assert declarees, "aucune sous-commande lue dans le parseur"
    for nom in declarees:
        commande = commandes_citees(f"`jio {nom}`")[0]
        assert verifier_commande(commande) is None, f"faux positif sur `jio {nom}`"


def test_une_faute_de_frappe_est_refutee_avec_la_bonne_piste() -> None:
    """Le message doit MONTRER la correction, pas seulement refuser."""
    refus = verifier_commande(commandes_citees("`jio scna .`")[0])
    assert refus is not None
    assert "`jio scan`" in refus


def test_une_option_inventee_est_refutee() -> None:
    refus = verifier_commande(commandes_citees("`jio scan . --stricte`")[0])
    assert refus is not None
    assert "`--strict`" in refus


def test_une_option_de_premier_niveau_existe_vraiment() -> None:
    """`jio --version` fonctionne. Le declarer inconnu etait un faux positif (mesure)."""
    assert verifier_commande(commandes_citees("`jio --version`")[0]) is None


# --------------------------------------------------------------------------- #
# 3. L'integration a `jio claims`
# --------------------------------------------------------------------------- #


def test_une_commande_inventee_est_une_violation_bloquante() -> None:
    rapport = verifier("Lancez `jio scna .` sur le projet.", racine=None)
    assert rapport.refutees == 1
    assert not rapport.conforme


def test_une_commande_correcte_est_verifiee() -> None:
    rapport = verifier("Lancez `jio scan .` sur le projet.", racine=None)
    assert rapport.verifiees == 1
    assert rapport.conforme


def test_une_commande_inline_est_une_INSTRUCTION_pas_une_citation() -> None:
    r"""\`jio scan --stricte\` en pleine phrase dit a l'utilisateur de la taper.

    La distinction est la meme que pour les calculs : une phrase qui ORDONNE quelque chose
    l'affirme. Un document ne peut donc pas recommander une commande inexistante.
    """
    rapport = verifier("Lancez `jio scan --stricte` pour un audit.", racine=None)
    assert rapport.refutees == 1
    assert not rapport.conforme


def test_une_commande_dans_un_bloc_est_une_CITATION_et_n_accuse_pas() -> None:
    """Un bloc de terminal MONTRE ce qui se passe — y compris une erreur.

    C'est ainsi que ce verificateur peut documenter ses propres refutations : sans cette
    regle, la page qui explique « l'ancienne option `--stricte` » serait declaree non
    conforme, et le seul moyen de la rendre conforme serait de ne plus en parler.
    """
    document = """
Ancien defaut, corrige depuis :

```console
$ jio scan --stricte
error: unrecognized arguments: --stricte
```

L'option correcte est `jio scan --strict`.
"""
    rapport = verifier(document, racine=None)
    assert rapport.refutees == 0, rapport.resume()
    assert rapport.signalees == 1
    assert rapport.verifiees == 1
    assert rapport.conforme


def test_la_racine_du_document_ne_change_pas_le_verdict_des_commandes(tmp_path: Path) -> None:
    """Une commande n'est pas un chemin : elle ne depend pas de l'endroit ou on regarde."""
    fichier = tmp_path / "note.md"
    fichier.write_text("`jio scan .`\n", encoding="utf-8")
    assert verifier(fichier.read_text(encoding="utf-8"), racine=tmp_path).conforme
    assert verifier(fichier.read_text(encoding="utf-8"), racine=None).conforme


def test_le_genre_commande_est_declare_bloquant() -> None:
    """La severite n'est pas un detail : elle decide du code de sortie."""
    from jio.verify.claims import SEVERITE

    assert SEVERITE[Genre.COMMANDE] == "VIOLATION"


# --------------------------------------------------------------------------- #
# Un gabarit n'est pas une invocation
# --------------------------------------------------------------------------- #


def test_un_gabarit_n_est_pas_une_commande() -> None:
    """« jio … » ou « jio <objectif> » designent une FORME, pas une commande a taper.

    Mesure : la phrase « toutes les commandes de ce document s'ecrivent donc `jio …` » a ete
    declaree « commande INCONNUE : `jio …` » — une refutation bloquante sur une phrase
    juste. Quatrieme faux positif du meme genre dans ce projet ; la lecon ne change pas : un
    controle qui accuse doit d'abord s'assurer qu'il a compris ce qu'il lit.
    """
    from jio.verify.commands import commandes_citees

    texte = (
        "Toutes les commandes s'ecrivent `jio …` avec sa sous-commande.\n"
        "Pour une mission : `jio run <objectif>`.\n"
        "Et `jio --version` fonctionne.\n"
        "Mais `jio scna .` est une faute de frappe.\n"
    )
    trouvees = [citation.sous_commande for citation in commandes_citees(texte)]

    assert "…" not in trouvees, "un gabarit a ete pris pour une commande"
    assert "<objectif>" not in trouvees
    assert "--version" in trouvees, "une option de premier niveau doit rester verifiee"
    assert "scna" in trouvees, "une vraie faute doit rester detectee"
