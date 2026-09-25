"""Temoins pour la PROSE : un document a des affirmations verifiables.

Tout le harness prouvait du CODE. Sur une mission generaliste — analyse, rapport,
note — il n'y avait rien a executer, donc JIO s'abstenait. Un texte contient
pourtant des affirmations vraies ou fausses sans interpretation : un calcul annonce,
un bloc presente comme Python, un chemin cite. C'est la que se logent les
hallucinations, et cela se PROUVE au lieu de se relire.

Ce que ces tests verrouillent, dans l'ordre d'importance :

  1. AUCUNE FAUSSE ACCUSATION — un rapport sain doit rester muet. Un outil qui
     accuse a tort est desactive au bout de deux jours ;
  2. les affirmations FAUSSES sont refutees avec la preuve exacte (la valeur
     calculee, l'erreur de syntaxe) ;
  3. la retenue : un chemin introuvable est SIGNALE, jamais accuse (un document a le
     droit de decrire un fichier a creer) ; un bloc non marque n'est pas juge ;
  4. quatre bugs reels sont chacun couverts par un test, parce qu'ils etaient tous
     du meme genre — une fonction qui ne faisait rien, en silence.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from jio.verify.claims import Genre, extraction, verifier

REPO = pathlib.Path(__file__).resolve().parents[1]
CORPUS = REPO / "evidence" / "claims"


# --------------------------------------------------------------------------- #
# 1. Le corpus : sain muet, fautif refute
# --------------------------------------------------------------------------- #


def test_un_rapport_fautif_est_refute_avec_sa_preuve() -> None:
    texte = (CORPUS / "rapport_fautif.md").read_text(encoding="utf-8")
    rapport = verifier(texte, racine=REPO)

    assert not rapport.conforme
    refutations = " | ".join(v.message for v in rapport.bloquantes)
    assert "7 x 6 = 43" in refutations or "7 × 6 = 43" in refutations, refutations
    assert "42" in refutations, "la valeur REELLE doit figurer dans la preuve"
    assert "NE COMPILE PAS" in refutations, refutations


def test_un_rapport_sain_est_muet() -> None:
    """Le corpus sain compte autant que le corpus fautif.

    Le corpus sain contient A DESSEIN trois pieges qu'un verificateur naif condamne :
    un exemple en **shell** (compile comme du Python = accusation fausse), un calcul
    FAUX **cite** entre backticks (parler d'une erreur, c'est le sujet du document) et
    un bloc non marque qui est une sortie de programme. Aucun ne doit bloquer.
    """
    texte = (CORPUS / "rapport_sain.md").read_text(encoding="utf-8")
    rapport = verifier(texte, racine=REPO)

    assert rapport.conforme, [v.message for v in rapport.bloquantes]
    assert rapport.refutees == 0, "aucun calcul juste ne doit etre declare faux"
    # Un seul signalement, et c'est la citation volontaire : elle est ATTENDUE.
    assert rapport.signalees == 1, rapport.resume()
    assert "CITE" in rapport.verifications[-1].message


def test_une_note_sans_affirmation_ne_donne_pas_de_quitus() -> None:
    """Rien a verifier n'est pas la meme chose que tout va bien."""
    texte = (CORPUS / "note_sans_affirmation.md").read_text(encoding="utf-8")
    rapport = verifier(texte, racine=REPO)
    assert rapport.verifications == ()
    assert rapport.resume().startswith("0 affirmation(s)")


# --------------------------------------------------------------------------- #
# 2. Les quatre bugs reels, un test chacun
# --------------------------------------------------------------------------- #


def test_le_signe_multiplication_unicode_est_reconnu() -> None:
    """Bug 1 : la classe de caracteres ecrite a la main ne matchait pas `×`.

    Un calcul ecrit avec le vrai signe de multiplication passait donc sans etre vu.
    La classe est desormais CONSTRUITE depuis la table des operateurs.
    """
    rapport = verifier("Le total vaut 7 × 6 = 43.", racine=None)
    assert rapport.refutees == 1, rapport.resume()
    assert "42" in rapport.bloquantes[0].message


def test_un_calcul_en_fin_de_phrase_est_verifie() -> None:
    """Bug 2 : le regard final refusait un point, donc tout calcul suivi d'une phrase.

    Un rapport ecrit ses calculs en fin de phrase ; la ponctuation suffisait a les
    rendre invisibles.
    """
    rapport = verifier("Le gain atteint 7 x 6 = 43.", racine=None)
    assert rapport.refutees == 1, rapport.resume()
    rapport2 = verifier("Le gain atteint 7 x 6 = 42.", racine=None)
    assert rapport2.refutees == 0 and rapport2.verifiees == 1


def test_un_calcul_juste_est_confirme_et_chiffre() -> None:
    rapport = verifier("2 + 2 = 4, et 100/4 = 25.", racine=None)
    assert rapport.verifiees == 2 and rapport.refutees == 0, rapport.resume()


def test_levaluation_ne_permet_pas_dappeler_du_code() -> None:
    """Un document est du contenu NON FIABLE : l'evaluation est un AST restreint.

    `ast.walk` ne convenait pas (bug 3) : il visite aussi les noeuds d'OPERATEUR
    (`ast.Add`), qui n'entrent dans aucune categorie autorisee. Toute expression
    etait donc refusee, et aucun calcul n'etait jamais verifie. On descend l'arbre
    explicitement — et l'acces a des noms reste interdit.
    """
    from jio.verify.claims import _evalue_calcul

    assert _evalue_calcul("2 + 3") == 5.0
    assert _evalue_calcul("-(4)") == -4.0
    for hostile in ("__import__('os').getcwd()", "open('/etc/passwd')", "1 if True else 2"):
        assert _evalue_calcul(hostile) is None, f"expression acceptee a tort : {hostile}"


def test_un_chemin_introuvable_est_signale_jamais_accuse(tmp_path: pathlib.Path) -> None:
    """Bug 4 et regle de retenue : un document peut decrire un fichier a CREER.

    Un outil qui accuse un rapport d'architecture pour un fichier non encore ecrit
    est un outil qu'on desactive.
    """
    rapport = verifier("Voir `src/absent.py` pour le detail.", racine=tmp_path)
    assert rapport.refutees == 0, "un chemin manquant ne doit jamais etre bloquant"
    assert rapport.signalees == 1
    message = rapport.verifications[0].message
    assert "INTROUVABLE" in message
    assert "on n'accuse pas" in message, "le message doit dire ce qu'il ne fait PAS"
    assert not rapport.verifications[0].bloquant


def test_un_chemin_existant_est_confirme(tmp_path: pathlib.Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "present.py").write_text("x = 1\n", encoding="utf-8")
    rapport = verifier("Voir `src/present.py`.", racine=tmp_path)
    assert rapport.verifiees == 1 and rapport.signalees == 0


def test_un_bloc_non_marque_qui_nest_pas_du_code_nest_pas_juge() -> None:
    """Un diagramme n'est pas une specification.

    Avant : tout bloc non marque qui ne compilait pas etait signale. Sur le seul
    README de ce depot, cela produisait 18 signalements — des tableaux ASCII et des
    sorties de terminal. Un outil qui signale 18 fois pour rien cesse d'etre lu ; il
    ne juge donc plus que ce qui est MANIFESTEMENT du code.
    """
    for illustration in ("```\nregle metacode: faire quelque chose(\n```\n",
                         "```\n  config    reussite  appels\n  --------  --------  -----\n```\n"):
        rapport = verifier(illustration, racine=None)
        assert rapport.verifications == (), rapport.resume()


def test_un_bloc_non_marque_qui_est_du_code_est_signale_sans_trancher() -> None:
    """Le signal utile est conserve : du Python evident qui ne compile pas."""
    rapport = verifier("```\ndef f(\n    return 1\n```\n", racine=None)
    assert rapport.refutees == 0, "non marque : jamais bloquant"
    assert rapport.signalees == 1
    assert "manifestement du code" in rapport.verifications[0].message


def test_un_bloc_dune_autre_langue_nest_pas_compile_comme_python() -> None:
    """Le faux positif le plus couteux : accuser un exemple de terminal.

    Presque tout document technique contient une ligne de commande. La compiler comme
    du Python la declare invalide — une accusation fausse, et bloquante.
    """
    texte = "```bash\npython -m jio doctor --verify --all || echo \"echec : $?\"\n```\n"
    rapport = verifier(texte, racine=None)
    assert rapport.verifications == (), rapport.resume()

    # Meme contenu annonce comme Python : la, c'est un fait, et c'est bloquant.
    fautif = "```python\npython -m jio doctor --verify --all || echo \"echec : $?\"\n```\n"
    rapport2 = verifier(fautif, racine=None)
    assert rapport2.refutees == 1 and rapport2.bloquantes


def test_un_calcul_cite_entre_backticks_est_signale_jamais_bloquant() -> None:
    """Un document qui parle d'une erreur doit pouvoir la citer.

    La table des matieres d'un texte sur l'arithmetique cite forcement des calculs
    faux, et un README qui explique ce que JIO attrape en cite un. Les confondre avec
    des affirmations condamnait precisement les documents les plus utiles.
    """
    rapport = verifier("Une version precedente annoncait `7 x 6 = 43`, ce qui etait faux.",
                       racine=None)
    assert rapport.refutees == 0, "une citation ne condamne pas le document"
    assert rapport.signalees == 1
    assert "CITE" in rapport.verifications[0].message

    # Non citee : c'est une affirmation, et elle est bloquante.
    assert verifier("Le total vaut 7 x 6 = 43.", racine=None).bloquantes


def test_sans_racine_les_chemins_ne_sont_pas_juges() -> None:
    """Faute de reference, il n'y a rien a dire : on ne devine pas."""
    assert extraction("Voir `a/b.py`.") != ()
    rapport = verifier("Voir `a/b.py`.", racine=None)
    assert rapport.verifications == ()


# --------------------------------------------------------------------------- #
# 3. Extraction : des motifs precis, pas une heuristique floue
# --------------------------------------------------------------------------- #


def test_extraction_triee_par_position() -> None:
    texte = "3 + 4 = 7 puis ```python\nx = 1\n``` puis `a/b.md`."
    trouvailles = extraction(texte)
    positions = [a.position for a in trouvailles]
    assert positions == sorted(positions)
    assert {a.genre for a in trouvailles} == {Genre.ARITHMETIQUE, Genre.BLOC_CODE,
                                              Genre.CHEMIN}


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("12 + 30 = 42", True),
        ("12 + 30 = 43", True),
        ("1,5 + 1,5 = 3", True),
        ("la version 1.2.3 contient 4 modules", False),
        ("le fichier p1.py totalise 10 lignes", False),
        ("3 mises a jour sur 4 = 75 %", False),
    ],
)
def test_seuls_les_calculs_ecrits_sont_extraits(texte: str, attendu: bool) -> None:
    """Pas de detection d'intention : un calcul s'ecrit avec des nombres et un `=`."""
    trouve = any(a.genre is Genre.ARITHMETIQUE for a in extraction(texte))
    assert trouve is attendu, (texte, extraction(texte))


# --------------------------------------------------------------------------- #
# 4. Une seule porte : `jio audit` route vers la bonne famille de temoins
# --------------------------------------------------------------------------- #

def _jio(*args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    """Lance la CLI dans un sous-processus : on teste le CONTRAT (les codes de sortie)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, "-m", "jio", *args],
        capture_output=True, text=True, cwd=cwd or REPO, env=env, timeout=120,
        check=False,
    )


@pytest.mark.parametrize("suffixe,texte,attendu", [
    (".md", "# titre", True),
    (".markdown", "texte", True),
    (".rst", "texte", True),
    (".txt", "du texte simple", True),
    (".py", "def f(", False),
    (".py", "x = 1", False),
    ("", "du texte libre sans syntaxe", True),
    ("", "x = 1\ny = 2\n", False),
])
def test_routage_par_suffixe_et_par_syntaxe(
    tmp_path: pathlib.Path, suffixe: str, texte: str, attendu: bool
) -> None:
    """Un `.py` reste du CODE meme s'il ne compile pas : il doit etre juge comme tel."""
    from jio.verify.claims import est_un_document

    chemin = tmp_path / f"fichier{suffixe}"
    assert est_un_document(chemin, texte) is attendu


def test_audit_dun_document_utilise_les_temoins_de_prose() -> None:
    """Avant : `audit rapport.md` repondait « la source ne compile pas » — vrai, inutile."""
    resultat = _jio("audit", "evidence/claims/rapport_fautif.md")
    assert resultat.returncode == 1, resultat.stdout
    assert "AUDIT (prose)" in resultat.stdout
    assert "ne compile pas" not in resultat.stdout, "message de code sur un document"
    assert "7" in resultat.stdout and "42" in resultat.stdout


def test_audit_dun_document_sain_reste_muet() -> None:
    resultat = _jio("audit", "evidence/claims/rapport_sain.md")
    assert resultat.returncode == 0, resultat.stdout
    assert "NON CONFORME" not in resultat.stdout


def test_audit_dun_python_reste_du_code() -> None:
    """Le routage ne doit pas avaler les sources : sinon on ne prouverait plus rien."""
    resultat = _jio("audit", "jio/verify/claims.py")
    assert "AUDIT (prose)" not in resultat.stdout
    assert "AUDIT  jio/verify/claims.py" in resultat.stdout


def test_la_racine_par_defaut_est_celle_du_depot() -> None:
    """Un document cite `jio/verify/claims.py` depuis la racine du depot, pas du dossier."""
    resultat = _jio("claims", "evidence/claims/rapport_sain.md")
    assert resultat.returncode == 0
    assert f"racine des chemins cites : {REPO}" in resultat.stdout, resultat.stdout
