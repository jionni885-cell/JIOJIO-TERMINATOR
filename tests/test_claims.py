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

from jio.verify.claims import MAX_AFFIRMATIONS, Genre, extraction, verifier

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


# --------------------------------------------------------------------------- #
# 5. Un document est du contenu NON FIABLE : il ne fixe pas le temps de travail
# --------------------------------------------------------------------------- #


def test_une_ligne_de_vingt_mille_calculs_ne_bloque_pas() -> None:
    """Mesure : 114 secondes avant correction, 0,03 apres.

    La cause etait double, et les deux comptent :
      * `_plages_citees` rescannait la LIGNE entiere pour chaque calcul (O(n^2)) ;
      * au-dela de `MAX_AFFIRMATIONS`, plus rien n'etait borne.
    Un contenu non fiable ne doit pas pouvoir imposer sa duree a l'outil.
    """
    import time

    texte = "1 + 2 = 3 " * 20000
    debut = time.monotonic()
    rapport = verifier(texte, racine=None)
    ecoule = time.monotonic() - debut

    assert ecoule < 10.0, f"trop lent : {ecoule:.1f}s"
    assert rapport.verifiees == MAX_AFFIRMATIONS
    assert rapport.ignorees > 0, "le volume NON verifie doit etre declare"
    assert "NON verifiee" in rapport.resume()


def test_une_longue_chaine_sans_egal_ne_bloque_pas() -> None:
    """Le pire cas trouve : `"1 + " * 50000` faisait boucler le moteur d'expressions.

    La version precedente cherchait `gauche = droite` d'un seul motif, avec un groupe
    repete : sans `=`, le moteur essayait toutes les decoupes possibles. La descente
    bornee a partir du `=` supprime ce retour arriere — il ne peut plus y en avoir,
    la grammaire ne l'exprime plus.
    """
    import time

    debut = time.monotonic()
    rapport = verifier("1 + " * 50000 + "1", racine=None)
    assert time.monotonic() - debut < 10.0
    assert rapport.verifications == ()


@pytest.mark.parametrize("texte", ["x := 5", "y == 7", "z >= 3", "a != 4"])
def test_les_operateurs_python_ne_sont_pas_des_calculs(texte: str) -> None:
    """`=` d'affectation ou de comparaison n'annonce aucun resultat."""
    assert extraction(texte) == (), texte


def test_une_somme_longue_est_verifiee_si_elle_tient_dans_la_borne() -> None:
    juste = " + ".join(str(i) for i in range(1, 21)) + " = 210"
    assert verifier(juste, racine=None).verifiees == 1

    faux = " + ".join(str(i) for i in range(1, 21)) + " = 211"
    rapport = verifier(faux, racine=None)
    assert rapport.refutees == 1 and rapport.bloquantes


def test_une_chaine_trop_longue_est_declaree_jamais_accusee() -> None:
    """Ni verifiee, ni accusee : evaluer une PARTIE des termes inventerait un refus.

    C'est le piege du jour : une somme de 40 termes depasse la borne, et le motif
    pouvait en extraire la FIN pour la comparer au total. Le controle de continuation
    a gauche l'empeche, et le calcul est compte comme non evalue.
    """
    texte = " + ".join(str(i) for i in range(1, 41)) + " = 999"
    rapport = verifier(texte, racine=None)
    assert rapport.refutees == 0, "aucun refus invente"
    assert rapport.verifiees == 0
    assert rapport.non_evaluees == 1, rapport.resume()
    assert "trop long" in rapport.resume()


def test_la_preuve_porte_ses_propres_lacunes() -> None:
    """Un document volumineux ne doit pas pouvoir se faire passer pour entierement verifie."""
    from jio.verify.prose_prover import ProseProver

    texte = "1 + 2 = 3 " * 400
    resultat = ProseProver(racine=None).prove(texte, None)
    assert resultat.passed, "les calculs verifies sont justes"
    assert "LIMITE DE VOLUME ATTEINTE" in resultat.witnesses[-1].stdout


# --------------------------------------------------------------------------- #
# 6. « Rien a verifier » a son propre code : ni succes, ni echec
# --------------------------------------------------------------------------- #


def test_les_trois_codes_de_sortie_sont_distincts(tmp_path: pathlib.Path) -> None:
    """0 conforme · 1 refute · 3 rien a verifier.

    Sans le 3, il fallait choisir entre deux mises en scene egalement fausses : faire
    passer un document muet pour un quitus, ou le signaler comme un defaut. Un
    appelant — un hook, une CI — doit pouvoir distinguer les deux.
    """
    vide = tmp_path / "note.md"
    vide.write_text("# Note\n\nUne intention, sans aucun fait verifiable.\n",
                    encoding="utf-8")
    sain = tmp_path / "sain.md"
    sain.write_text("# Rapport\n\n12 + 30 = 42 ms.\n", encoding="utf-8")
    faux = tmp_path / "faux.md"
    faux.write_text("# Rapport\n\n12 + 30 = 99 ms.\n", encoding="utf-8")

    assert _jio("claims", str(vide)).returncode == 3
    assert _jio("claims", str(sain)).returncode == 0
    assert _jio("claims", str(faux)).returncode == 1


def test_un_document_muet_nest_pas_un_defaut_pour_le_scan(tmp_path: pathlib.Path) -> None:
    """`jio scan` distingue deja « non testable » de « probleme » : on le verrouille."""
    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / "note.md").write_text("# Note\n\nRien de verifiable ici.\n", encoding="utf-8")
    (projet / "code.py").write_text("def f(x: int) -> int:\n    return x\n", encoding="utf-8")

    resultat = _jio("scan", str(projet), "--no-learn", "--no-linters")
    assert "PROBLEME" not in resultat.stdout, resultat.stdout
    assert "NON TESTABLE" in resultat.stdout.upper(), resultat.stdout


def test_le_signe_multiplication_dans_une_citation_reste_non_bloquant() -> None:
    """Le marquage « cite » doit survivre a la remontee de l'expression.

    Regression reelle : les offsets transmis a `_est_cite` etaient ABSOLUS alors que
    la fonction les compare SUR LA LIGNE. Le calcul faux cite par un document qui en
    PARLE redevenait bloquant — le texte le plus utile devenait le seul refuse.
    """
    rapport = verifier("Le rapport annoncait `7 × 6 = 43` avant correction.", racine=None)
    assert rapport.refutees == 0 and rapport.signalees == 1
    assert "CITE" in rapport.verifications[0].message


# --------------------------------------------------------------------------- #
# 7. Une lacune declaree doit dire la VRAIE cause de son existence
# --------------------------------------------------------------------------- #


def test_mot_annonce_milieu_dexpression_nest_pas_un_resultat() -> None:
    """« le total vaut 7 x 6 = 43 » : `vaut` annonçait `7`, premier TERME.

    Le motif matchait « vaut 7 », ne trouvait aucune expression a gauche, et le
    rapport declairait « 1 calcul trop long pour etre evalue » : une lacune INVENTEE.
    Une lacune fausse est pire qu'aucune — elle apprend a ignorer les vraies.
    """
    rapport = verifier("Le total vaut 7 x 6 = 43 et le gain est de 12 + 30 = 42.",
                       racine=None)
    assert len(rapport.verifications) == 2, rapport.resume()
    assert rapport.refutees == 1 and rapport.verifiees == 1
    assert rapport.non_evaluees == 0, "aucun calcul n'est trop long ici"


@pytest.mark.parametrize(
    ("phrase", "verifiees", "refutees"),
    [
        ("3 x 4 vaut 12", 1, 0),
        ("7 x 6 vaut 43", 0, 1),
        ("la somme donne 12 + 30 = 42", 1, 0),
        ("le total fait 5 + 5 = 10 aujourd'hui", 1, 0),
    ],
)
def test_les_mots_annonce_restent_des_annonces(
    phrase: str, verifiees: int, refutees: int
) -> None:
    """Refuser un resultat suivi d'une operation ne doit pas casser `A vaut B`."""
    rapport = verifier(phrase, racine=None)
    assert (rapport.verifiees, rapport.refutees) == (verifiees, refutees), rapport.resume()


def test_une_annonce_sans_expression_nest_pas_une_lacune() -> None:
    """« le total vaut 42 ms », `seq=0` : du texte, du code — pas un calcul manque.

    Un compteur dedie a ces cas produisait DOUZE lacunes inventees sur le seul README
    de ce depot (mesure). Une lacune inventee apprend a ignorer les vraies : le
    compteur a ete retire, et la distinction ne sert plus qu'a classer.

    Seule une chaine COUPEE est une lacune : la, un calcul existe et n'a pas pu etre
    juge.
    """
    for phrase in ("le total vaut 42 ms", "Chaque processus repartait a `seq=0`.",
                   "`double(1)=2` puis `double(2)=4`"):
        rapport = verifier(phrase, racine=None)
        assert rapport.non_evaluees == 0, f"{phrase!r} -> {rapport.resume()}"
        assert "trop long" not in rapport.resume(), phrase

    somme_en_mots = "la somme de " + " + ".join(str(i) for i in range(1, 41)) + " = 820"
    declaree = verifier(somme_en_mots, racine=None)
    assert declaree.non_evaluees == 1, "la, un calcul existe vraiment et est coupe"
    assert declaree.refutees == 0, "coupee ne veut pas dire fausse"
    assert "trop long" in declaree.resume()


def test_le_mot_faux_ne_se_termine_pas_par_une_multiplication() -> None:
    """Le `x` de « faux » est une LETTRE, pas un operateur.

    Trouve en auditant le README de ce depot : la garde de continuation lisait le
    dernier caractere, declarait la chaine coupee, et annoncait « 1 calcul trop long »
    sur une phrase ou aucun calcul n'etait coupe. Un operateur alphabetique doit etre
    DETACHE pour en etre un.
    """
    rapport = verifier("preuve du calcul faux  7 x 6 vaut 42, le texte annonce 43",
                       racine=None)
    assert rapport.verifiees == 1 and rapport.non_evaluees == 0, rapport.resume()

    # Mais un vrai `x` de multiplication, detache, coupe toujours la chaine : sinon
    # on evaluerait la fin d'une longue somme et on inventerait un refus.
    coupee = verifier("3 x " + " + ".join(str(i) for i in range(1, 41)) + " = 2", racine=None)
    assert coupee.refutees == 0 and coupee.non_evaluees == 1, coupee.resume()


def test_une_fenetre_qui_coupe_ne_produit_jamais_de_refus() -> None:
    """Ligne de plus de 240 caracteres : la fenetre peut couper le DEBUT de l'expression.

    Le controle de continuation ne voit qu'un OPERATEUR a gauche ; si la coupe tombe au
    MILIEU d'un nombre, le chiffre precedent lui echappe. La chaine lue serait alors un
    fragment compare a un total qu'il n'a jamais produit : un refus invente, sur un
    document qui n'a rien annonce de faux.
    """
    nombre_gegant = "6" * 300
    rapport = verifier(f"{nombre_gegant} + 7 = 3", racine=None)
    assert rapport.refutees == 0, "un fragment de nombre ne s'accuse pas"
    assert rapport.non_evaluees == 1, rapport.resume()

    # Le meme calcul, ecrit court, est bien juge : la prudence ne coute rien ici.
    assert verifier("12 + 30 = 42", racine=None).verifiees == 1
    assert verifier("12 + 30 = 99", racine=None).refutees == 1
