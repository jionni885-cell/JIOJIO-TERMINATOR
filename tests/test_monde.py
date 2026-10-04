"""Le monde ou une preuve a ete produite : sceau, empreinte, et detection du changement.

Un journal chaine par hachage prouve qu'un enregistrement n'a **pas ete altere**. Il ne
prouve pas que le monde n'a pas change depuis. Les confondre produit un mode d'echec precis,
decrit sous le nom d'*inconsistent checkpoint state* (arXiv 2608.29381) :

    une verification est produite sur un etat du monde ;
    le monde est ensuite restaure (`git reset`, rollback, `jio recover`, edition manuelle) ;
    la verification reste intacte, verifiable — et porte pourtant sur un monde disparu.

Le remede tient en une ligne : chaque enregistrement porte le sceau du monde ou il a ete
ecrit, et un journal qui contient deux sceaux differents le dit a voix haute.

Ces tests verifient les trois proprietes qui rendent la mesure utilisable, et une quatrieme
qui evite un piege de performance :

  * **sensible** : tout changement reel du travail change le sceau ;
  * **stable** : deux mesures du meme arbre donnent le meme sceau (sinon le journal
    signalerait un changement a chaque evenement) ;
  * **aveugle a l'etat local** : les caches et environnements virtuels ne comptent pas —
    sinon `pytest` lui-meme ferait croire que le monde a change en lancant les tests ;
  * **rapide** : le sceau est pris a CHAQUE evenement d'une mission. La premiere version
    parcourait 3 609 fichiers pour 181 retenus, faute d'elaguer pendant le parcours : 75 ms
    au lieu de 3 ms. Le test de performance est donc un test de correction comme un autre.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from jio.core.journal import Journal
from jio.core.monde import EXCLUSIONS, revision, sceau


@pytest.fixture()
def atelier(tmp_path: Path) -> Path:
    (tmp_path / "jio").mkdir()
    (tmp_path / "jio" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("bonjour\n", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# Sensibilite : tout changement reel se voit
# --------------------------------------------------------------------------- #


def test_modifier_un_fichier_change_le_sceau(atelier: Path) -> None:
    avant = sceau(atelier)
    (atelier / "jio" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert sceau(atelier) != avant


def test_ajouter_un_fichier_change_le_sceau(atelier: Path) -> None:
    avant = sceau(atelier)
    (atelier / "nouveau.md").write_text("note\n", encoding="utf-8")
    assert sceau(atelier) != avant


def test_renommer_un_fichier_change_le_sceau(atelier: Path) -> None:
    """Le chemin entre dans la mesure : deux arbres de meme contenu mais de structure
    differente ne doivent pas passer pour le meme monde."""
    avant = sceau(atelier)
    os.rename(atelier / "README.md", atelier / "LISEZMOI.md")
    assert sceau(atelier) != avant


def test_deux_fichiers_identiques_intervertis_changent_le_sceau(atelier: Path) -> None:
    """Le contenu ET le chemin comptent : sans le chemin, une permutation passerait."""
    (atelier / "p.md").write_text("A\n", encoding="utf-8")
    (atelier / "q.md").write_text("B\n", encoding="utf-8")
    avant = sceau(atelier)
    (atelier / "p.md").write_text("B\n", encoding="utf-8")
    (atelier / "q.md").write_text("A\n", encoding="utf-8")
    assert sceau(atelier) != avant


# --------------------------------------------------------------------------- #
# Stabilite : le meme arbre donne le meme sceau
# --------------------------------------------------------------------------- #


def test_le_meme_arbre_donne_le_meme_sceau(atelier: Path) -> None:
    """Sinon le journal signalerait un changement a chaque evenement."""
    assert sceau(atelier) == sceau(atelier)
    assert sceau(atelier) == sceau(atelier)


def test_le_chemin_du_dossier_ne_change_pas_le_sceau(tmp_path: Path) -> None:
    """Deux copies du meme arbre a deux endroits sont le meme monde.

    Le sceau est relatif a la racine, pas absolu : sinon deplacer le projet ferait croire a
    un changement de monde.
    """
    premier = tmp_path / "un"
    second = tmp_path / "deux"
    for dossier in (premier, second):
        dossier.mkdir()
        (dossier / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert sceau(premier) == sceau(second)


# --------------------------------------------------------------------------- #
# Aveugle a l'etat local : ce qui n'est pas du travail ne compte pas
# --------------------------------------------------------------------------- #


def test_les_caches_et_environnements_ne_comptent_pas(atelier: Path) -> None:
    """Sinon lancer les tests ferait croire que le monde a change.

    `pytest` ecrit `.pytest_cache`, l'installation ecrit `.venv` : si ces dossiers
    entraient dans le sceau, toute mission signalerait un monde different a chaque
    execution — et un avertissement qui se declenche toujours ne dit plus rien.
    """
    avant = sceau(atelier)
    for nom in sorted(EXCLUSIONS):
        if nom in {".git"}:
            continue
        dossier = atelier / nom
        dossier.mkdir(exist_ok=True)
        (dossier / "trace").write_text("bruit\n", encoding="utf-8")
    assert sceau(atelier) == avant, "un dossier non-travail a change le sceau"


def test_un_dossier_exclu_n_est_meme_pas_PARCOURU(atelier: Path) -> None:
    """Le gain mesure vient de la : 3 609 fichiers parcourus contre 181 retenus.

    On le verifie sans chronometre : un sous-dossier exclu contenant un fichier illisible
    ne doit pas faire echouer la mesure si le parcours ne s'y elague pas... plus simplement,
    le nombre de fichiers visites est compte par un espion.
    """
    from jio.core import monde

    (atelier / "node_modules" / "paquet").mkdir(parents=True)
    (atelier / "node_modules" / "paquet" / "index.js").write_text("x\n", encoding="utf-8")

    vus: list[Path] = []
    original = monde._fichiers

    def espion(racine):
        for chemin in original(racine):
            vus.append(chemin)
            yield chemin

    monde._fichiers = espion  # type: ignore[assignment]
    try:
        sceau(atelier)
    finally:
        monde._fichiers = original  # type: ignore[assignment]

    assert not [chemin for chemin in vus if "node_modules" in chemin.parts]


def test_le_sceau_est_assez_rapide_pour_chaque_evenement(atelier: Path) -> None:
    """Le sceau est pris a chaque evenement d'une mission : son cout se multiplie.

    Seuil volontairement large (200 ms pour 40 mesures) : on ne mesure pas une machine, on
    interdit un retour au parcours non elague (75 ms par appel, mesure sur ce depot).
    """
    for indice in range(40):
        (atelier / f"f{indice}.py").write_text("x = 1\n", encoding="utf-8")
    depart = time.perf_counter()
    for _ in range(40):
        sceau(atelier)
    duree = time.perf_counter() - depart
    assert duree < 0.2, f"40 sceaux en {duree:.3f} s : trop lent pour un appel par evenement"


# --------------------------------------------------------------------------- #
# Le journal porte le sceau, et le dit quand le monde change
# --------------------------------------------------------------------------- #


def test_le_journal_scelle_chaque_evenement(atelier: Path) -> None:
    journal = Journal(path=atelier / ".jio" / "journal.jsonl", racine=atelier)
    evenement = journal.append("mission", {"id": "m1"})
    assert evenement.payload["monde"]["sceau"] == sceau(atelier)


def test_le_journal_detecte_un_changement_de_monde_en_cours_de_mission(atelier: Path) -> None:
    """Le cas central : une conclusion qui s'appuie sur deux etats differents."""
    journal = Journal(path=atelier / ".jio" / "journal.jsonl", racine=atelier)
    journal.append("mission", {"id": "m1"})
    journal.append("observation", {"note": "etat initial"})

    (atelier / "jio" / "a.py").write_text("x = 999\n", encoding="utf-8")

    journal.append("verdict", {"ok": True})

    mondes = journal.mondes()
    assert len(mondes) == 2, [m["evenements"] for m in mondes]
    assert mondes[0]["evenements"] == [0, 1]
    assert mondes[1]["evenements"] == [2]

    # Et l'integrite de la chaine reste vraie : les deux constats sont independants.
    valide, mauvais = journal.verify_chain()
    assert valide, mauvais


def test_le_sceau_entre_dans_le_hachage(atelier: Path) -> None:
    """Reecrire le sceau apres coup doit casser la chaine.

    Sans cela, on pourrait reecrire l'histoire du monde dans un journal « intact » : le
    sceau doit etre protege par le hachage, pas pose a cote. Le premier essai de ce test
    falsifiait le sceau par... le sceau courant, qui etait identique : il ne falsifiait
    rien. Le controle par la valeur attendue est dans l'assertion.
    """
    import json

    atelier_init = sceau(atelier)
    journal = Journal(path=atelier / ".jio" / "journal.jsonl", racine=atelier)
    journal.append("mission", {"id": "m1"})

    (atelier / "jio" / "a.py").write_text("x = 3\n", encoding="utf-8")
    journal.append("verdict", {"ok": True})
    assert sceau(atelier) != atelier_init, "le monde n'a pas change : test sans objet"

    lignes = [json.dumps(ev.as_dict()) for ev in journal]
    objet = json.loads(lignes[1])
    objet["payload"]["monde"]["sceau"] = atelier_init  # le monde d'AVANT, reecrit apres coup
    lignes[1] = json.dumps(objet)

    relu = Journal.from_jsonl("\n".join(lignes))
    valide, mauvais = relu.verify_chain()
    assert not valide, "un sceau reecrit serait passe pour intact"
    assert mauvais == 1


def test_un_journal_sans_sceau_reste_lisible(atelier: Path) -> None:
    """Retrocompatibilite : les journaux deja ecrits ne portent pas de sceau.

    Ils restent valides (la chaine les protege) et comptent pour un seul monde inconnu —
    jamais pour une erreur. Un format qui rend illisibles les journaux deja ecrits
    detruirait exactement ce qu'il est cense proteger.
    """
    import json

    from jio.core.types import TrustLevel, digest_of
    from jio.core.journal import Event, Journal as J

    ancien = Event(
        seq=0, ts=1.0, kind="mission", payload={"id": "vieux"},
        trust=TrustLevel.SYSTEM, prev_hash="0" * 32,
        digest=digest_of(0, 1.0, "mission", {"id": "vieux"}, TrustLevel.SYSTEM.value, "0" * 32),
    )
    journal = J.from_jsonl(json.dumps(ancien.as_dict()))
    valide, _ = journal.verify_chain()
    assert valide
    mondes = journal.mondes()
    assert len(mondes) == 1
    assert mondes[0]["sceau"] == ""

    # Et on peut continuer a ecrire : les nouveaux evenements sont scelles.
    journal.racine = atelier
    nouveau = journal.append("suite", {"note": "apres"})
    assert nouveau.payload["monde"]["sceau"] == sceau(atelier)
    assert len(journal.mondes()) == 2


def test_la_revision_est_lue_quand_il_y_a_un_depot(atelier: Path) -> None:
    """Hors depot, la revision est vide — et ce n'est pas une erreur."""
    assert revision(atelier) == ""

    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=atelier, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty",
         "-m", "init"],
        cwd=atelier, check=True, capture_output=True,
    )
    lu = revision(atelier)
    assert len(lu) == 40, lu


def test_le_sceau_ne_depend_pas_des_metadonnees(atelier: Path) -> None:
    """Le test qui empeche de « reoptimiser » le sceau avec des `stat`.

    Une variante hachant (chemin, taille, date) avait ete ecrite parce qu'un `stat` semble
    moins cher qu'une lecture. Mesure : elle n'etait pas plus rapide apres elagage, et elle
    etait **aveugle** — sur le systeme de fichiers de ce bac a sable, `st_mtime_ns` ne bouge
    pas apres une reecriture (cinq ecritures successives, la meme date au nanoseconde).

    Ici la date est restauree explicitement, ce qui rend le cas deterministe sur n'importe
    quelle machine : taille identique, date identique, contenu different. Le sceau doit
    quand meme changer.
    """
    chemin = atelier / "jio" / "a.py"
    avant = chemin.stat()
    sceau_avant = sceau(atelier)

    chemin.write_text("x = 2\n", encoding="utf-8")  # meme taille que « x = 1\n »
    os.utime(chemin, ns=(avant.st_atime_ns, avant.st_mtime_ns))

    apres = chemin.stat()
    assert apres.st_size == avant.st_size
    assert apres.st_mtime_ns == avant.st_mtime_ns, "le test n'a pas su figer la date"

    assert sceau(atelier) != sceau_avant, (
        "un sceau fonde sur les metadonnees serait aveugle a cette modification : "
        "c'est exactement le defaut qui a fait jeter la variante rapide"
    )


def test_un_lien_symbolique_ne_fait_pas_entrer_l_exterieur_dans_le_sceau(
    tmp_path: Path,
) -> None:
    """Le parcours SAUTE les liens symboliques, et ce n'est pas un detail de confort.

    Mesure a l'origine : `jio mutants` a montre que le `continue` sur `chemin.is_symlink()`
    pouvait etre remplace par `pass` sans qu'aucun test ne bouge. Consequence de ce
    remplacement : un lien vers un fichier HORS du depot ferait entrer dans le sceau un
    contenu qui n'appartient pas au travail, et ce contenu pourrait changer sans qu'aucun
    fichier du depot ne bouge — le sceau detecterait alors des changements de monde qui
    n'ont pas eu lieu, ou, pire, laisserait passer une modification reelle.
    """
    # L'atelier est un SOUS-dossier : le fichier vise par le lien doit etre en dehors de
    # l'arbre scelle, sinon le test ne prouverait rien (il mesurerait un vrai changement).
    travail = tmp_path / "travail"
    travail.mkdir()
    (travail / "a.py").write_text("x = 1\n", encoding="utf-8")
    dehors = tmp_path / "hors-du-depot.txt"
    dehors.write_text("contenu exterieur\n", encoding="utf-8")
    (travail / "lien.txt").symlink_to(dehors)

    avant = sceau(travail)
    dehors.write_text("contenu CHANGE a l'exterieur\n", encoding="utf-8")
    assert sceau(travail) == avant, (
        "le sceau a suivi un lien symbolique : l'exterieur du depot est entre dedans"
    )


def test_la_revision_courante_est_le_sha_de_head(tmp_path: Path) -> None:
    """`revision` lit la sortie de git : elle est du TEXTE, et non vide dans un depot.

    Mesure a l'origine : `jio mutants` a montre que `capture_output=True` et `text=True`
    pouvaient passer a `False` sans qu'aucun test ne bouge. Les deux consequences sont
    silencieuses, donc graves :

      * sans capture de la sortie, `revision` rend TOUJOURS la chaine vide — le journal
        perdrait la revision du monde sans que rien ne le signale ;
      * sans decodage, elle rendrait des OCTETS, et toute comparaison de revision avec une
        chaine deviendrait fausse sans lever d'erreur.
    """
    import subprocess

    depot = tmp_path / "depot"
    depot.mkdir()

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=depot, capture_output=True, text=True, timeout=60
        )

    assert revision(depot) == "", "un dossier sans depot n'a pas de revision"
    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@exemple.invalid")
    git("config", "user.name", "test")
    (depot / "a.txt").write_text("x\n", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-q", "-m", "premier")
    attendu = git("rev-parse", "HEAD").stdout.strip()
    lue = revision(depot)
    assert isinstance(lue, str), f"la revision doit etre du texte, pas {type(lue).__name__}"
    assert lue == attendu and len(lue) == 40, f"revision lue : {lue!r}"
