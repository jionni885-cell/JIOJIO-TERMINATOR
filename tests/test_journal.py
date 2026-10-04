"""Tests du journal hash-chaine — la colonne vertebrale d'integrite."""

from __future__ import annotations


from jio.core.journal import GENESIS, Journal
from jio.core.types import TrustLevel


def test_journal_starts_at_genesis():
    j = Journal()
    assert j.head == GENESIS
    assert len(j) == 0


def test_journal_chains_hashes():
    j = Journal()
    a = j.append("mission", {"id": "m1"})
    b = j.append("stage", {"name": "spec"})
    assert a.prev_hash == GENESIS
    assert b.prev_hash == a.digest
    assert j.head == b.digest
    ok, bad = j.verify_chain()
    assert ok and bad is None


def test_journal_detects_tampering():
    """Modifier un payload apres coup DOIT casser la chaine."""
    j = Journal()
    j.append("witness", {"rule": "R-001", "ok": True})
    j.append("verdict", {"status": "delivered"})
    assert j.verify_chain()[0]

    # Falsification : on reecrit la preuve d'un echec en succes.
    events = list(j)
    object.__setattr__(events[0], "payload", {"rule": "R-001", "ok": False})

    ok, bad = j.verify_chain()
    assert not ok
    assert bad == 0


def test_journal_replay_roundtrip():
    j = Journal()
    for i in range(5):
        j.append("step", {"i": i})
    clone = Journal.from_jsonl(j.to_jsonl())
    assert len(clone) == len(j)
    assert clone.head == j.head
    assert clone.verify_chain()[0]


def test_journal_records_trust_level():
    j = Journal()
    j.append("read", {"path": "README.md"}, trust=TrustLevel.EXTERNAL)
    assert list(j)[0].trust is TrustLevel.EXTERNAL
    assert "external" in j.to_jsonl()


def test_journal_summary_counts_kinds():
    j = Journal()
    j.append("a")
    j.append("a")
    j.append("b")
    s = j.summary()
    assert s["events"] == 3
    assert s["kinds"] == {"a": 2, "b": 1}
    assert s["chain_ok"] is True


def test_journal_persists_to_disk(tmp_path):
    path = tmp_path / "journal.jsonl"
    j = Journal(path=path)
    j.append("mission", {"x": 1})
    assert path.exists()
    assert "\"x\": 1" in path.read_text(encoding="utf-8")
    reloaded = Journal.from_jsonl(path.read_text(encoding="utf-8"))
    assert reloaded.verify_chain()[0]


# --------------------------------------------------------------------------- #
# Deux ecrivains, un seul fichier : ce que fait un journal d'ecriture standard
# --------------------------------------------------------------------------- #


def test_un_second_ecrivain_est_ADOPTE_au_lieu_de_casser_la_chaine(tmp_path):
    """Une instance qui tient la chaine en memoire doit voir le fichier AVANCER sous ses pieds.

    Defaut constate en usage NORMAL, et c'est ce qui le rend grave : un `Journal` repris au debut
    d'une mission gardait la tete de chaine chargee a ce moment-la. Si un AUTRE ecrivain ajoutait
    un evenement entre-temps — une seconde instance du meme processus, une autre commande `jio`,
    un prouveur —, le premier ecrivait ensuite `seq=N, prev=<sa tete d'il y a N evenements>` alors
    que le fichier portait deja `seq=N`. Deux evenements de meme numero, deux suites concurrentes,
    et la chaine devenait invérifiable.

    La porte disait alors, a juste titre, « chaine cassee » — mais l'accusation etait FAUSSE :
    personne n'avait rien reecrit, deux ecrivains honnetes s'etaient ignores. Un journal qui se
    casse tout seul apprend a ignorer l'alerte, et le jour ou la chaine casse pour de vrai,
    personne ne la regarde plus.

    Comportement retenu, celui d'un journal d'ecriture standard : si le fichier a avance et que
    nos evenements en sont le PREFIXE, on adopte la suite et on ecrit apres elle.
    """
    from jio.core.journal import Journal

    chemin = tmp_path / "journal.jsonl"
    premier = Journal(path=chemin)
    premier.append("un")                       # le premier tient la chaine en memoire

    autre = Journal(path=chemin)
    autre.append("deux")                       # un autre ecrivain avance le fichier

    premier.append("trois")                    # le premier croit encore que le fichier s'arrete a lui

    relu = Journal.from_jsonl(chemin.read_text(encoding="utf-8"))
    assert [e.kind for e in relu] == ["un", "deux", "trois"]
    assert [e.seq for e in relu] == [0, 1, 2]
    ok, mauvais = relu.verify_chain()
    assert ok, mauvais
    assert premier.head == relu.head, "le premier ecrivain a repris la chaine adoptee"


def test_un_fichier_qui_DIVERGE_est_mis_en_quarantaine_et_JAMAIS_supprime(tmp_path):
    """Un recul du journal n'est pas une suite : on ne l'ecrit pas par-dessus en silence.

    Le cas symetrique du precedent, et le plus dangereux : ce n'est pas un ecrivain de plus, c'est
    un fichier ETRANGER (un etat restaure, une autre mission, une reecriture). Ecrire a sa suite
    fabriquerait un embranchement — precisement ce qu'une chaine de hachages existe pour rendre
    visible. Le fichier est donc RENOMME (jamais supprime, rien n'est perdu), une chaine neuve
    commence, et le motif est ecrit dans les `notices` : jamais tu.
    """
    import json

    from jio.core.journal import Journal

    chemin = tmp_path / "journal.jsonl"
    tenant = Journal(path=chemin)
    tenant.append("un")
    tenant.append("deux")

    # Un fichier valide en lui-meme, mais qui n'est PAS la suite de celui qu'on tient.
    etranger = Journal()
    etranger.append("etranger")
    chemin.write_text(
        json.dumps(etranger.last().as_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
    )

    tenant.append("trois")

    quarantaines = sorted(tmp_path.glob("journal.jsonl.corrompu-*"))
    assert len(quarantaines) == 1, [p.name for p in tmp_path.iterdir()]
    assert "etranger" in quarantaines[0].read_text(encoding="utf-8"), (
        "rien ne doit disparaitre : le fichier ecarte est CONSERVE pour etre lu"
    )
    assert tenant.notices and "conserve sous" in tenant.notices[0]

    neuf = Journal.from_jsonl(chemin.read_text(encoding="utf-8"))
    assert [e.kind for e in neuf] == ["trois"], "une chaine NEUVE commence"
    ok, mauvais = neuf.verify_chain()
    assert ok, mauvais


def test_le_cas_courant_ne_relit_pas_tout_le_fichier(tmp_path):
    """La securite du second ecrivain ne doit pas couter un fichier entier a chaque ajout.

    La detection se fait sur la QUEUE du fichier (64 Ko) : c'est le cas courant — un seul
    ecrivain, fichier inchange — et il n'a pas a relire 100 000 evenements pour ecrire le suivant.
    Ce test fixe le contrat de l'outil de lecture, pas une duree.
    """
    from jio.core.journal import Journal

    chemin = tmp_path / "journal.jsonl"
    journal = Journal(path=chemin)
    for i in range(5):
        journal.append(f"etape-{i}")

    assert journal._digest_sur_disque() == journal.head
    lignes = chemin.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 5, "un seul ecrivain, un evenement par ligne"
    assert Journal.from_jsonl(chemin.read_text(encoding="utf-8")).verify_chain()[0]


# --------------------------------------------------------------------------- #
# `jio trace` : verifier un journal, ou DIRE qu'on ne peut pas
# --------------------------------------------------------------------------- #


def test_un_journal_EXPLICITE_inexistant_n_est_pas_remplace_par_un_autre(tmp_path, capsys, monkeypatch):
    """DEFAUT MESURE : `jio trace /tmp/inexistant.jsonl` cherchait un AUTRE journal, en
    trouvait un, et repondait « INTEGRITE : propre » en code 0 — sur un fichier que
    l'utilisateur n'avait pas demande.

    Pire qu'un mauvais code de sortie : une verification qui porte sur autre chose que ce
    qu'on lui a donne. Le chemin explicite est donc honore, ou declare introuvable.
    """
    from jio.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".jio").mkdir()
    (tmp_path / ".jio" / "journal.jsonl").write_text("", encoding="utf-8")

    code = main(["trace", str(tmp_path / "absent.jsonl")])
    sortie = capsys.readouterr().out

    assert code == 2, "un journal introuvable est INDETERMINE, jamais propre"
    assert "n'existe pas" in sortie
    assert "code 2" in sortie
    # Ce qui existe est PROPOSE, pas substitue en silence.
    assert "disponible(s) ici" in sortie
    assert "journal.jsonl" in sortie


def test_un_journal_VIDE_n_est_pas_un_journal_intact(tmp_path, capsys) -> None:
    """La chaine d'un fichier vide se verifie sur zero evenement : « propre » ne veut rien dire.

    Un journal vide n'est pas un journal intact, c'est un journal absent — et un quitus sur du
    vide est exactement le genre de succes silencieux que ce depot refuse.
    """
    from jio.cli import main

    vide = tmp_path / "vide.jsonl"
    vide.write_text("\n", encoding="utf-8")

    code = main(["trace", str(vide)])
    sortie = capsys.readouterr().out

    assert code == 2
    assert "vide" in sortie
    assert "rien a verifier" in sortie


def test_un_VRAI_journal_reste_verifie_en_0(tmp_path, capsys) -> None:
    """L'autre moitie, sans laquelle la correction serait « ne plus rien accepter »."""
    from jio.core.journal import Journal
    from jio.cli import main

    journal = Journal(path=tmp_path / "vrai.jsonl")
    journal.append("mission", {"objectif": "somme des pairs"})

    code = main(["trace", str(journal.path)])
    sortie = capsys.readouterr().out

    assert code == 0
    assert "INTEGRITE : propre" in sortie
    assert "1 evenements" in sortie or "evenements" in sortie
