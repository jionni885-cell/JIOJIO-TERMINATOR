"""Le portail de coherence : la porte qui empeche « c'est fini » d'etre une opinion.

Chaque controle de `jio/verify/coherence.py` existe parce qu'une incoherence REELLE est passee
inapercue dans ce depot. Un controle qu'on ne sait pas faire ECHOUER n'est pas une porte : c'est
un affichage. Ce fichier verifie donc les deux cotes, et le second compte davantage :

  * cote vert : le depot est coherent, et le rapport le dit sans se tromper ;
  * cote ROUGE : quand on casse volontairement une affirmation (un chiffre, un artefact, une
    commande citee), le portail doit passer en echec et NOMMER le probleme.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jio.verify.coherence import CONTROLES, Constat, controler, formater

RACINE = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# 1. Le depot lui-meme : la porte doit etre VERTE, sinon elle ne sert a rien
# --------------------------------------------------------------------------- #


def test_le_depot_est_coherent() -> None:
    """Les sept controles passent sur le depot, et chaque constat porte sa preuve.

    Si ce test echoue, le message utile n'est pas « test rouge » mais la liste des details :
    le rapport nomme le fichier, la ligne, et ce qu'il faut faire. Un portail qu'on ne peut pas
    reparer est un portail qu'on apprend a ignorer.
    """
    rapport = controler(RACINE)
    details = "\n".join(
        f"  [{c.marque}] {c.controle} : {c.resume}\n" + "\n".join(f"      - {d}" for d in c.details)
        for c in rapport.incoherents
    )
    assert rapport.ok, f"le depot n'est pas coherent :\n{details}\n\n{formater(rapport)}"
    assert len(rapport.constats) == len(CONTROLES)
    assert rapport.code == 0
    assert all(c.resume for c in rapport.constats), "un constat sans resume n'informe pas"


def test_le_rapport_est_lisible_par_une_machine() -> None:
    """`--json` : un appelant automatise doit pouvoir decider sans lire le texte.

    C'est la meme exigence que partout ailleurs dans ce depot : une sortie destinee a une IA
    doit etre structuree, sinon la seule interface reelle est une analyse de prose — exactement
    ce que le harness existe pour eviter.
    """
    rapport = controler(RACINE)
    donnees = json.loads(json.dumps(rapport.as_dict(), ensure_ascii=False))
    assert set(donnees) == {"coherent", "duree_s", "constats"}
    assert donnees["coherent"] is True
    assert isinstance(donnees["duree_s"], float)
    noms = [c["controle"] for c in donnees["constats"]]
    assert noms == [
        "artefacts", "nombres", "documents", "commandes", "environnement", "sources", "plan",
    ]
    assert all(set(c) == {"controle", "ok", "resume", "details"} for c in donnees["constats"])


# --------------------------------------------------------------------------- #
# 2. Cote ROUGE : chaque controle sait ECHOUER (c'est ce qui en fait une porte)
# --------------------------------------------------------------------------- #


def _constat(rapport, nom: str) -> Constat:
    for constat in rapport.constats:
        if constat.controle == nom:
            return constat
    raise AssertionError(f"constat absent : {nom}")


def test_un_artefact_modifie_a_la_main_est_DETECTE(tmp_path: Path) -> None:
    """Regenerer en memoire et comparer : c'est la seule facon de voir une derive.

    Un artefact edite a la main reste coherent avec lui-meme — et faux. Le portail doit le
    dire, et dire QUOI faire (`jio artifacts --write`), sans ecraser le travail de personne :
    il CONSTATE, il ne repare pas.
    """
    from jio.artifacts import manifest

    rel = sorted(manifest())[0]
    chemin = tmp_path / rel
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("contenu ecrit a la main, jamais genere\n", encoding="utf-8")

    constat = _constat(controler(tmp_path), "artefacts")
    assert not constat.ok
    # Les artefacts ABSENTS sont attendus dans un dossier vide : le controle le dit aussi,
    # et c'est exact — un artefact manquant est un cablage qui n'aura pas lieu.
    assert any("a regenerer" in d for d in constat.details)
    assert any("manquant" in d for d in constat.details)


def test_un_chiffre_perime_est_DETECTE_avec_sa_LIGNE(tmp_path: Path) -> None:
    """Un chiffre faux dans la documentation principale : le portail donne la ligne exacte.

    C'est l'incoherence la plus frequente de ce depot (rencontree plusieurs fois), parce que
    rien n'est plus facile a oublier qu'un compteur. Le constat doit permettre de corriger sans
    chercher : nom du fichier, numero de ligne, ancienne et nouvelle valeur.

    La mesure des tests est REELLE : on donne au dossier un vrai (petit) fichier de test, donc
    « 123 » est bien un chiffre perime et non une mesure impossible.
    """
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_minuscule.py").write_text(
        "def test_un():\n    assert 1 == 1\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "---\n\nLe depot compte 123 tests verts.\n", encoding="utf-8"
    )
    constat = _constat(controler(tmp_path), "nombres")
    assert not constat.ok
    assert any("README.md ligne" in d and "123" in d for d in constat.details), constat.details


def test_une_commande_citee_qui_N_EXISTE_PAS_est_detectee(tmp_path: Path) -> None:
    """`jio verify` a ete cite dans un artefact : la commande n'existait pas.

    C'est le pire endroit pour une faute de ce genre : la fiche que l'IA lit en premier, celle
    qui lui dit quoi lancer. Le controle interroge le parseur REEL, jamais une liste recopiee a
    la main — une liste recopiee finit par decrire un autre programme que le programme.
    """
    # En debut de ligne : c'est la forme que l'IA lit et EXECUTE. Le contenu est ecrit
    # ligne par ligne, pour rester lisible malgre les guillemets.
    trois_backticks = chr(96) * 3
    bloc = (
        trois_backticks + "sh\n"
        + "jio volume-imaginaire --vite\n"
        + 'jio run "objectif"\n'
        + trois_backticks + "\n"
    )
    (tmp_path / "README.md").write_text(
        bloc + "\nEt dans le texte : `jio bidule` et `jio run`.\n", encoding="utf-8"
    )
    constat = _constat(controler(tmp_path), "commandes")
    assert not constat.ok
    assert {d.split("`")[1] for d in constat.details} == {
        "jio volume-imaginaire", "jio bidule",
    }
    # Les commandes REELLES ne sont pas signalees : le controle ne crie pas au loup.
    assert not any("jio run" in d for d in constat.details)


def test_un_plan_en_SUSPENS_est_signale(tmp_path: Path) -> None:
    """Un plan bloque laisse des etapes non tentees : elles doivent remonter a l'ecran.

    C'est la troisieme incoherence de la liste, et la plus discrete : l'etat existe sur le
    disque, ecrit par la machine elle-meme, et personne ne le lit. « Non tente » n'est pas
    « fait », et un rapport final qui ne le dit pas presente un travail partiel comme complet.
    """
    dossier = tmp_path / ".jio"
    dossier.mkdir()
    (dossier / "plan.json").write_text(
        json.dumps({
            "etat": "bloque", "prouvees": 1, "total": 3, "revision": "abc",
            "etapes": [
                {"id": "E01", "etat": "prouvee", "objectif": "faite", "preuve": "jio version"},
                {"id": "E02", "etat": "bloquee", "objectif": "cassee", "preuve": "jio run x"},
                {"id": "E03", "etat": "non_tentee", "objectif": "jamais lancee",
                 "preuve": "jio scan ."},
            ],
        }),
        encoding="utf-8",
    )
    constat = _constat(controler(tmp_path), "plan")
    assert not constat.ok
    assert "NON TENTEE" in constat.resume
    assert any("jamais lancee" in d for d in constat.details)


def test_un_plan_ILLISIBLE_est_un_echec_pas_un_silence(tmp_path: Path) -> None:
    """Fichier tronque : on ne peut pas conclure, donc on refuse.

    La tentation est de considérer un fichier illisible comme « pas de plan en cours ». C'est
    exactement l'inverse : quelque chose a ete ecrit et n'est plus lisible, donc l'etat du
    travail est INCONNU — et un inconnu traite comme un vide est un mensonge par omission.
    """
    dossier = tmp_path / ".jio"
    dossier.mkdir()
    (dossier / "plan.json").write_text('{"etat": "bloque", "etapes": [', encoding="utf-8")
    assert not _constat(controler(tmp_path), "plan").ok


def test_un_controle_qui_LEVE_devient_un_constat_en_echec(tmp_path: Path) -> None:
    """Fail-closed : une exception dans un controle n'est pas une porte ouverte.

    Un portail qui saute silencieusement l'etape qui plante est un portail ouvert, et c'est le
    pire des deux mondes : il rassure. Ici, l'exception devient un constat `KO` avec son message.
    """
    import jio.verify.coherence as module

    def controle_qui_leve(_racine: Path) -> Constat:
        raise RuntimeError("disque illisible")

    original = module.CONTROLES
    module.CONTROLES = (*original, controle_qui_leve)
    try:
        rapport = controler(tmp_path)
    finally:
        module.CONTROLES = original

    assert not rapport.ok
    constat = _constat(rapport, "controle_qui_leve")
    assert not constat.ok and "disque illisible" in constat.resume


# --------------------------------------------------------------------------- #
# 3. Le contrat public : sept controles, et rien de moins
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "nom",
    ["artefacts", "nombres", "documents", "commandes", "environnement", "sources", "plan"],
)
def test_chaque_controle_est_declare_et_execute(nom: str) -> None:
    """Le nombre de controles est FIGE : en retirer un doit casser un test, pas passer inapercu.

    Sans cette borne, une suppression discrète (par exemple parce qu'un controle devient
    genant) ferait maigrir le portail en silence — et personne ne verrait la difference.
    """
    assert len(CONTROLES) == 7
    assert any(c.controle == nom for c in controler(RACINE).constats)


def test_le_formateur_dit_le_verdict_et_les_PREUVES() -> None:
    """Le texte : le verdict d'abord, la preuve de chaque constat ensuite, jamais l'inverse."""
    rapport = controler(RACINE)
    texte = formater(rapport)
    assert "VERDICT" in texte
    assert "COHERENT" in texte
    for constat in rapport.constats:
        assert constat.controle in texte
    assert "7 controle(s)" in texte

    faux = Constat("chiffres", False, "un ecart", ("README.md ligne 15 : 1 -> 2",))
    texte_ko = formater(type(rapport)(constats=[faux], duree_s=0.5))
    assert "INCOHERENT" in texte_ko
    assert "README.md ligne 15" in texte_ko
    assert "Corriger, puis relancer" in texte_ko
