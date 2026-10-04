"""Tests du jeu de regression : une trace reelle devient un garde, ou ne devient rien.

Ce que ces tests protegent, dans l'ordre ou les defauts sont dangereux :

  1. **un cas faux a la creation** — un cas de regression gele alors que l'echec ne se
     reproduit pas occupe la place d'un garde et ne garde rien. Le gel doit REFUSER ;
  2. **une fuite archivee** — un cas de securite gele alors que la redaction laisse
     passer la valeur figerait le defaut au lieu de le fermer. Le gel doit REFUSER ;
  3. **un silence invisible** — une version qui ne detecte plus un echec enregistre doit
     le DIRE, avec le taux, et une regression de securite doit BLOQUER ;
  4. **un cas reecrit a la main** — l'artefact d'un cas est lie par empreinte : le
     modifier doit etre vu, pas rejoue comme si de rien n'etait ;
  5. **une valeur reelle recopiee** — un champ sensible de la trace donne son NOM au cas,
     jamais sa valeur. Un secret pousse une fois dans un depot y reste, historique git
     compris.

Le dernier test verifie la seule chose qui donne de la valeur au corpus : il est bati sur
une trace REELLE du depot (`evidence/regressions/`), et il tient.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jio.core.errors import FailClosed
from jio.core.journal import Journal
from jio.eval import regressions as R

RACINE = Path(__file__).resolve().parents[1]
JEU = RACINE / "evidence" / "regressions"

ARTEFACT = "def sum_even(nums):\n    return sum(n for n in nums if n % 2 == 1)\n"
CONTROLE = "assert sum_even([1, 2, 3]) == 2"


# --------------------------------------------------------------------------- #
# Une trace qui propose, sans jamais recopier une valeur sensible
# --------------------------------------------------------------------------- #


def _journal(tmp_path: Path, evenements: list[dict]) -> Path:
    """Un journal REEL : ecrit par `Journal`, donc sa chaine de hashes est valide."""
    chemin = tmp_path / "trace.jsonl"
    journal = Journal(path=chemin)
    for kind, payload in evenements:
        journal.append(kind, payload)
    return chemin


def _trace_type(tmp_path: Path) -> Path:
    return _journal(
        tmp_path,
        [
            ("candidate", {"id": "r0-c0", "digest": R._empreinte(ARTEFACT), "code_tail": ARTEFACT}),
            (
                "witness",
                {
                    "rule": "R-001",
                    "exit_code": 1,
                    "ok": False,
                    "hash": "25e39109cfa50361",
                    "stage": "prove",
                    "monde": {"revision": "abcdef1234567", "sceau": "e23a783467f5afe6"},
                },
            ),
            ("provider", {"provider": "simule", "api_key": "sk-reel-interdit", "usage": {"input_tokens": 812}}),
        ],
    )


def test_les_propositions_viennent_de_la_trace_avec_leur_provenance(tmp_path: Path) -> None:
    items = R.propositions(_trace_type(tmp_path))
    genres = {item.genre for item in items}
    assert genres == {R.GENRE_TEMOIN, R.GENRE_SECURITE}
    temoin = next(item for item in items if item.genre == R.GENRE_TEMOIN)
    assert temoin.regle == "R-001"
    assert "revision abcdef1" in temoin.provenance
    assert "evenement #" in temoin.provenance
    assert temoin.candidats == (R._empreinte(ARTEFACT),)


def test_les_propositions_ne_recopient_jamais_la_valeur_sensible(tmp_path: Path) -> None:
    """Un cas peut nommer le champ ; recopier sa valeur serait une fuite permanente."""
    rendu = json.dumps([p.en_dict() for p in R.propositions(_trace_type(tmp_path))], ensure_ascii=False)
    assert "api_key" in rendu
    assert "sk-reel-interdit" not in rendu, "la valeur reelle ne doit jamais sortir de la trace"


def test_les_champs_sensibles_sont_trouves_meme_imbriques(tmp_path: Path) -> None:
    trace = _journal(tmp_path, [("support", {"client": {"telephone": "+33612345678"}, "note": "ok"})])
    champs = {p.champ for p in R.propositions(trace) if p.genre == R.GENRE_SECURITE}
    assert "telephone" in champs


def test_une_trace_absente_ou_cassee_est_refusee(tmp_path: Path) -> None:
    """Batir un cas sur une trace non verifiable, c'est figer une preuve douteuse."""
    with pytest.raises(FailClosed, match="aucune trace"):
        R.propositions(tmp_path / "absente.jsonl")

    chemin = _trace_type(tmp_path)
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    evenement = json.loads(lignes[1])
    evenement["payload"]["rule"] = "R-999"  # reecriture a la main : la chaine ne suit plus
    lignes[1] = json.dumps(evenement)
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    with pytest.raises(FailClosed, match="chaine"):
        R.propositions(chemin)


def test_l_artefact_est_rendu_par_la_trace_seulement_si_l_empreinte_correspond(tmp_path: Path) -> None:
    trace = _trace_type(tmp_path)
    assert R.artefact_depuis_trace(trace, R._empreinte(ARTEFACT)) == ARTEFACT
    with pytest.raises(FailClosed, match="aucun candidat"):
        R.artefact_depuis_trace(trace, "0000000000000000")


# --------------------------------------------------------------------------- #
# Le gel : un cas dont l'attente est fausse ne s'ecrit pas
# --------------------------------------------------------------------------- #


def _proposition(tmp_path: Path) -> R.Proposition:
    return next(p for p in R.propositions(_trace_type(tmp_path)) if p.genre == R.GENRE_TEMOIN)


def _juge_qui_echoue(*regles: str):
    from jio.core.types import Witness
    from jio.verify.executable import ProverResult

    class _Juge:
        def prove(self, source, spec, **kwargs):
            temoins = tuple(
                Witness(rule_id=r.id, command="factice", exit_code=0 if r.id not in regles else 1,
                        ok=r.id not in regles)
                for r in spec.rules
            )
            echecs = tuple(w for w in temoins if not w.ok)
            return ProverResult(witnesses=temoins, failures=echecs)

    return _Juge()


def test_le_gel_refuse_un_echec_qui_ne_se_reproduit_pas(tmp_path: Path) -> None:
    """Un cas qui passe des sa creation ne garde rien : c'est une place occupee."""
    proposition = _proposition(tmp_path)
    with pytest.raises(FailClosed, match="PAS reproduit"):
        R.geler_temoin(
            proposition,
            artefact=ARTEFACT,
            controles={"R-001": CONTROLE},
            prover=_juge_qui_echoue(),  # aucun echec : tout passe
        )


def test_le_gel_refuse_de_deviner_l_oracle_absent(tmp_path: Path) -> None:
    """Le controle n'est PAS dans la trace (oracle secret) : il vient de l'humain."""
    proposition = _proposition(tmp_path)
    with pytest.raises(FailClosed, match="aucun controle fourni"):
        R.geler_temoin(proposition, artefact=ARTEFACT, controles={})
    with pytest.raises(FailClosed, match="ne couvrent pas la regle"):
        R.geler_temoin(proposition, artefact=ARTEFACT, controles={"R-007": "assert True"})


def test_le_gel_accepte_un_echec_reproduit_et_enregistre_ce_qui_a_echoue(tmp_path: Path) -> None:
    proposition = _proposition(tmp_path)
    cas = R.geler_temoin(
        proposition,
        artefact=ARTEFACT,
        controles={"R-001": CONTROLE, "R-002": "assert sum_even([2]) == 2"},
        prover=_juge_qui_echoue("R-001"),
        dossier=tmp_path / "jeu",
    )
    assert cas.attendues_en_echec == ("R-001",)
    assert cas.artefact_digest == R._empreinte(ARTEFACT)
    assert cas.bloquant is False
    assert "echec reel observe" in cas.raison


def test_le_gel_de_securite_refuse_une_fuite_ACTUELLE(tmp_path: Path) -> None:
    """Archiver un defaut non corrige le figerait au lieu de le fermer."""
    proposition = R.Proposition(
        id="S-api_key-1", genre=R.GENRE_SECURITE, champ="api_key",
        resume="champ observe", provenance="evenement #1",
    )
    from jio.eval import regressions

    original = regressions.redact_data
    regressions.redact_data = lambda valeur, **_: valeur  # la redaction est neutralisee
    try:
        with pytest.raises(FailClosed, match="defaut ACTUEL"):
            R.geler_securite(proposition, dossier=tmp_path / "jeu")
    finally:
        regressions.redact_data = original


def test_le_gel_de_securite_utilise_des_valeurs_temoins(tmp_path: Path) -> None:
    proposition = R.Proposition(
        id="S-telephone-3", genre=R.GENRE_SECURITE, champ="telephone",
        resume="champ observe", provenance="evenement #3",
    )
    cas = R.geler_securite(proposition, dossier=tmp_path / "jeu")
    assert cas.bloquant is True
    assert cas.interdits, "sans valeur interdite, le cas ne mesurerait rien"
    rendu = json.dumps(cas.en_dict(), ensure_ascii=False)
    assert "temoin" in rendu.lower()


def test_les_valeurs_temoins_prennent_la_forme_de_ce_que_la_redaction_reconnait() -> None:
    """Une valeur aleatoire sans prefixe n'est attrapee par AUCUN motif.

    Defaut rencontre au premier gel, et refuse par le garde : la chaine libre
    `jioTemoin0123456789abcdef` traversait la redaction intacte. Les formes temoins sont
    donc celles des fuites reconnaissables.
    """
    from jio.core.redaction import redact_data

    for champ in ("api_key", "authorization", "telephone", "email", "compteur"):
        valeur = R.valeur_temoin(champ)
        masque = json.dumps(redact_data({"champ": valeur}), ensure_ascii=False)
        assert valeur not in masque, f"{champ} : la valeur temoin {valeur!r} n'est pas masquee"


# --------------------------------------------------------------------------- #
# Le rejeu : un cas tenu, un cas silencieux, une fuite BLOQUANTE
# --------------------------------------------------------------------------- #


def _cas_temoin() -> R.Cas:
    return R.Cas(
        id="T-001",
        genre=R.GENRE_TEMOIN,
        raison="echec reel",
        provenance="trace de test",
        attendues_en_echec=("R-001",),
        artefact=ARTEFACT,
        artefact_digest=R._empreinte(ARTEFACT),
        controles={"R-001": CONTROLE},
    )


def test_un_cas_temoin_tenu_puis_silencieux() -> None:
    tenu = R.rejouer(_cas_temoin(), prover=_juge_qui_echoue("R-001"))
    assert tenu.tenu and not tenu.durci

    silencieux = R.rejouer(_cas_temoin(), prover=_juge_qui_echoue())
    assert not silencieux.tenu
    assert "SILENCE" in silencieux.detail
    assert silencieux.bloquant is False


def test_un_cas_durci_se_dit_sans_etre_compte_comme_un_silence() -> None:
    """Detecter PLUS n'est pas une regression — mais cela ne doit pas passer inapercu."""
    cas = R.Cas(
        id="T-005", genre=R.GENRE_TEMOIN, raison="echec reel", provenance="trace de test",
        # Le cas n'exige que R-001 ; la version courante fait aussi echouer R-002.
        attendues_en_echec=("R-001",),
        artefact=ARTEFACT, artefact_digest=R._empreinte(ARTEFACT),
        controles={"R-001": CONTROLE, "R-002": "assert sum_even([2]) == 2"},
    )
    resultat = R.rejouer(cas, prover=_juge_qui_echoue("R-001", "R-002"))
    assert resultat.tenu and resultat.durci
    assert "durcissement" in resultat.detail
    assert R.evaluer([cas]).durcis and not R.evaluer([cas]).silencieux


def test_un_artefact_modifie_a_la_main_est_refuse() -> None:
    """Un cas de regression decrit un fait passe : il ne se reecrit pas."""
    cas = R.Cas(
        id="T-002", genre=R.GENRE_TEMOIN, raison="echec reel", provenance="trace de test",
        attendues_en_echec=("R-001",), artefact=ARTEFACT, artefact_digest="0000000000000000",
        controles={"R-001": CONTROLE},
    )
    resultat = R.rejouer(cas, prover=_juge_qui_echoue("R-001"))
    assert not resultat.tenu
    assert "artefact MODIFIE" in resultat.detail


def test_un_cas_sans_exigence_ne_mesure_rien_et_le_dit() -> None:
    cas = R.Cas(
        id="T-003", genre=R.GENRE_TEMOIN, raison="vide", provenance="trace de test",
        artefact=ARTEFACT, controles={},
    )
    resultat = R.rejouer(cas, prover=_juge_qui_echoue())
    assert not resultat.tenu
    assert "AUCUN echec" in resultat.detail


def test_une_regression_de_securite_BLOQUE_la_livraison() -> None:
    """Le critere qui decidait de ce module : une fuite refermee doit rouvrir au bruit."""
    cas = R.geler_securite(
        R.Proposition(
            id="S-api_key-9", genre=R.GENRE_SECURITE, champ="api_key",
            resume="champ observe", provenance="evenement #9",
        )
    )
    assert R.evaluer([cas]).bloque is False

    from jio.eval import regressions

    original = regressions.redact_data
    regressions.redact_data = lambda valeur, **_: valeur
    try:
        rapport = R.evaluer([cas])
    finally:
        regressions.redact_data = original
    assert rapport.bloque is True
    assert rapport.taux_de_silence == 1.0
    assert "livraison est refusee" in R.formater(rapport)
    assert rapport.en_dict()["bloquants"] == 1


def test_le_taux_de_silence_se_calcule_sur_le_corpus_entier() -> None:
    cas = [
        _cas_temoin(),
        R.Cas(id="T-004", genre=R.GENRE_TEMOIN, raison="x", provenance="y",
              attendues_en_echec=("R-001",), artefact=ARTEFACT,
              artefact_digest=R._empreinte(ARTEFACT), controles={"R-001": CONTROLE}),
    ]

    class _Muet:
        def prove(self, source, spec, **kwargs):
            from jio.core.types import Witness
            from jio.verify.executable import ProverResult

            return ProverResult(
                witnesses=tuple(
                    Witness(rule_id=r.id, command="muet", exit_code=0, ok=True) for r in spec.rules
                )
            )

    rapport = R.evaluer(cas, prover=_Muet())
    assert rapport.taux_de_silence == 1.0
    assert len(rapport.silencieux) == 2
    assert rapport.bloque is False, "un silence de temoin n'est pas un blocage de securite"


def test_un_cas_de_securite_edite_pour_etre_vide_est_refuse() -> None:
    """Deuxieme trou trouve en mesurant : changer la valeur interdite faisait passer le cas.

    Le cas exigeait l'absence d'une valeur qui n'etait dans aucune charge : il passait
    donc meme si la redaction disparaissait. Un garde qui ne garde plus rien est pire
    qu'une absence de garde : il rassure.
    """
    cas = R.geler_securite(
        R.Proposition(
            id="S-api_key-7", genre=R.GENRE_SECURITE, champ="api_key",
            resume="champ observe", provenance="evenement #7",
        )
    )
    vide = R.Cas(
        id=cas.id, genre=cas.genre, raison=cas.raison, provenance=cas.provenance,
        bloquant=True, charge=cas.charge, interdits=("une-valeur-inventee",),
    )
    resultat = R.rejouer(vide)
    assert not resultat.tenu
    assert "cas VIDE" in resultat.detail


def test_un_corpus_vide_n_est_pas_un_succes() -> None:
    """« Rien a mesurer » n'est pas « tout va bien » : un taux sur du vide est un chiffre."""
    rapport = R.evaluer([])
    assert rapport.taux_de_silence == 0.0
    assert not rapport.resultats
    assert "rien n'a ete mesure" in rapport.note


# --------------------------------------------------------------------------- #
# Le corpus : ecriture, relecture, refus d'ecraser
# --------------------------------------------------------------------------- #


def test_ecrire_puis_relire_un_cas(tmp_path: Path) -> None:
    cas = _cas_temoin()
    chemin = R.ecrire(cas, tmp_path / "jeu")
    assert chemin.name == "T-001.json"
    assert R.charger(tmp_path / "jeu") == (cas,)
    R.ecrire(cas, tmp_path / "jeu")  # ecrire le MEME contenu est idempotent


def test_un_cas_different_ne_s_ecrase_pas(tmp_path: Path) -> None:
    R.ecrire(_cas_temoin(), tmp_path / "jeu")
    autre = R.Cas(id="T-001", genre=R.GENRE_TEMOIN, raison="autre", provenance="x")
    with pytest.raises(FailClosed, match="existe deja"):
        R.ecrire(autre, tmp_path / "jeu")


def test_un_cas_illisible_arrete_tout_au_lieu_d_etre_ignore(tmp_path: Path) -> None:
    """Ignorer un cas qu'on ne sait pas lire, c'est mesurer un corpus plus petit en silence."""
    dossier = tmp_path / "jeu"
    dossier.mkdir()
    (dossier / "casse.json").write_text("{ceci n'est pas du json", encoding="utf-8")
    with pytest.raises(FailClosed, match="cas illisible"):
        R.charger(dossier)


def test_un_cas_sans_provenance_est_refuse() -> None:
    with pytest.raises(ValueError, match="provenance"):
        R.Cas.depuis_dict({"id": "X", "genre": R.GENRE_TEMOIN, "raison": "x"})
    with pytest.raises(ValueError, match="genre inconnu"):
        R.Cas.depuis_dict({"id": "X", "genre": "autre", "raison": "x", "provenance": "y"})


# --------------------------------------------------------------------------- #
# Le corpus versionne du depot
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not JEU.is_dir(), reason="aucun corpus versionne dans ce depot")
def test_le_corpus_du_depot_est_bati_sur_des_traces_et_il_tient() -> None:
    """Chaque cas dit d'OU il vient, et aucun ne s'est tu.

    Le corpus n'est pas decoratif : il vient d'une trace reelle du depot, ses cas portent
    leur provenance, et ils doivent encore se declencher.
    """
    corpus = R.charger(JEU)
    assert corpus, "un corpus vide ne protegerait rien"
    for cas in corpus:
        assert cas.provenance, f"{cas.id} : provenance absente"
        assert cas.raison, f"{cas.id} : raison absente"
    rapport = R.evaluer(corpus)
    assert not rapport.silencieux, R.formater(rapport)
    assert rapport.taux_de_silence == 0.0
