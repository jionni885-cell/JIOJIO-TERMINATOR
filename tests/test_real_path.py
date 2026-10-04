"""Le chemin REEL est prouve, pas seulement decrit.

Il n'y a pas de cle API dans un environnement de test, donc on ne peut pas mesurer
un vrai modele. Mais on peut prouver tout ce qui est verifiable : que JIO detecte une
CLI externe, lui parle, recupere sa reponse, la verifie, la soumet au consensus puis a
la porte de conformite, et livre. Un fournisseur qui n'a jamais tourne n'est pas un
fournisseur, c'est une intention.

Ces tests verrouillent trois comportements distincts, tous constates en usage reel :

1. **trois agents distincts** -> `DELIVERED`. La chaine complete fonctionne ;
2. **un seul agent** -> reserve « ce n'est pas un consensus, c'est un echo » ;
3. **deux agents** -> plafond arithmetiquement inatteignable, et le motif doit le
   DIRE avec la solution, sinon l'utilisateur cherche pendant des heures pourquoi
   une mission parfaite n'est jamais acceptee.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from jio.core.types import MissionStatus

#: Faux agent : repond en JSON quand on lui demande une critique, et rend un code
#: correct quand on lui demande un artefact. Mimique `opencode run --format json`
#: (une ligne JSON par evenement), que le fournisseur CLI sait lire.
STUB = '''#!{python}
import json
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

if "You turn enumerated RULES into executable checks" in prompt:
    # Traduction FIDELE des regles de la tache `median` : ce qu'une CLI correcte
    # rendrait. Le test prouve le CHEMIN (prompt -> CLI -> JSON -> porte de
    # securite -> temoin executable -> preuve -> livraison), pas la qualite d'un
    # modele reel — aucune cle d'API n'existe dans un environnement de test.
    import re as _re
    PAIRES = [
        ("R-001", "assert median([3, 1, 2]) == 2, 'impair'"),
        ("R-002", "assert median([1, 2, 3, 4]) == 2.5, 'pair'"),
        ("R-003", "ok = False\\ntry:\\n    median([])\\nexcept ValueError:\\n    ok = True\\n"
                  "assert ok, 'liste vide: aucune ValueError levee'"),
        ("R-004", "assert median([5, 2, 9, 1, 7]) == 5, 'non trie'"),
    ]
    demandees = _re.findall(r"\\[(R-[0-9]+)\\]", prompt)
    rendu = dict(p for p in PAIRES if not demandees or p[0] in demandees)
    print(json.dumps(dict(type="text", text=json.dumps(rendu))))
    sys.exit(0)

if "You are a strict" in prompt:
    print(json.dumps({{"type": "text", "text": json.dumps({{
        "verdict": "pass", "confidence": 0.9,
        "reason": "la specification est satisfaite", "counterexample": None,
    }})}}))
    sys.exit(0)

CODE = """def median(nums):
    if not nums:
        raise ValueError("liste vide")
    valeurs = sorted(nums)
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2
"""

print(json.dumps({{"type": "text", "text": "```python\\n" + CODE + "```\\n"}}))
'''


def _installer_agents(tmp_path: Path, noms: tuple[str, ...], *,
                      stub: str | None = None) -> dict[str, str]:
    """Cree un faux binaire par agent et retourne les variables JIO_BIN_* associees."""
    env: dict[str, str] = {}
    for nom in noms:
        binaire = tmp_path / nom
        binaire.write_text((stub or STUB).format(python=sys.executable), encoding="utf-8")
        binaire.chmod(binaire.stat().st_mode | stat.S_IEXEC)
        env[f"JIO_BIN_{nom.upper()}"] = str(binaire)
    return env


def _mission(tmp_path: Path, monkeypatch, agents: tuple[str, ...]) -> object:
    for key in list(os.environ):
        if key.startswith("JIO_BIN_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in _installer_agents(tmp_path, agents).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("JIO_LINTERS", "off")

    from jio.bench.tasks import TASKS_BY_ID
    from jio.cli import _real_engine
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    task = TASKS_BY_ID["median"]
    engine = _real_engine(journal_path=tmp_path / "journal.jsonl", max_rounds=3)
    return engine.run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )


def _mission_sans_oracle(tmp_path: Path, monkeypatch, agents: tuple[str, ...],
                         *, stub: str | None = None) -> object:
    """Meme chemin reel, mais la mission ne fournit AUCUN test — cas de toute mission reelle."""
    for key in list(os.environ):
        if key.startswith("JIO_BIN_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in _installer_agents(tmp_path, agents, stub=stub).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("JIO_LINTERS", "off")

    from jio.bench.tasks import TASKS_BY_ID
    from jio.cli import _real_engine
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    task = TASKS_BY_ID["median"]
    engine = _real_engine(journal_path=tmp_path / "journal.jsonl", max_rounds=3)
    return engine.run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint, spec=task.spec()),
    )


def test_chemin_reel_sans_oracle_la_cli_traduit_les_regles_en_temoins(
    tmp_path: Path, monkeypatch
) -> None:
    """Le chainon manquant, prouve la ou il compte : par un SOUS-PROCESSUS.

    Sans oracle, le moteur demandait au modele de traduire les regles en tests
    executables. Ce test verifie que ce prompt part bien vers la CLI reelle
    (`opencode run --format json`), que la reponse JSON traverse la porte de
    securite, que les assertions deviennent des temoins executes dans le bac a
    sable, et que la mission est livree sur cette preuve.
    """
    report = _mission_sans_oracle(tmp_path, monkeypatch, ("opencode", "hermes", "claude"))

    assert report.status is MissionStatus.DELIVERED, report.abstention_reason
    assert report.total_checks >= 3, "les regles doivent etre devenues des temoins"
    assert report.passed == report.total_checks
    # La PROVENANCE de la preuve est declaree : elle vient d'une traduction, pas
    # d'un oracle fourni.
    assert any(f.agent == "temoins" and "TRADUIT" in f.message for f in report.findings), (
        [f.message for f in report.findings]
    )


def test_chemin_reel_une_cli_qui_repond_le_format_du_compilateur(
    tmp_path: Path, monkeypatch
) -> None:
    """La deviation la plus probable d'une vraie CLI, prouvee sur le chemin reel.

    Le compilateur de specification demande ``[{"id": "R-001", ...}]``. Un modele
    qui a vu ce format repond volontiers la meme chose au prompt de traduction : la
    reponse est donc un TABLEAU d'objets, pas l'objet demande. Perdre les temoins
    pour un emballage different serait absurde — la porte de securite juge le test,
    pas l'emballage.
    """
    tableau = STUB.replace(
        'print(json.dumps(dict(type="text", text=json.dumps(rendu))))',
        'print(json.dumps(dict(type="text", text=json.dumps([dict(id=k, test=v) '
        'for k, v in rendu.items()]))))',
    )
    report = _mission_sans_oracle(tmp_path, monkeypatch, ("opencode", "hermes", "claude"),
                                  stub=tableau)

    assert report.status is MissionStatus.DELIVERED, report.abstention_reason
    assert report.passed == report.total_checks


def test_chemin_reel_sans_oracle_une_cli_qui_ne_sait_pas_traduire_le_dit(
    tmp_path: Path, monkeypatch
) -> None:
    """Une CLI qui repond du code au lieu de tests : aveu, jamais plantage.

    C'est l'etat d'un modele moyen devant ce prompt. Le systeme doit le declarer
    (aucune regle traduite) et s'abstenir : pas de preuve, pas de livraison — et
    surtout pas une livraison presentee comme prouvee.
    """
    muet = STUB.replace(
        'if "You turn enumerated RULES into executable checks" in prompt:',
        'if False and "You turn enumerated RULES into executable checks" in prompt:',
    )
    report = _mission_sans_oracle(tmp_path, monkeypatch, ("opencode", "hermes", "claude"),
                                  stub=muet)

    assert report.status is MissionStatus.ABSTAINED, report.status.value
    assert any(f.agent == "temoins" for f in report.findings), (
        "l'impossibilite de traduire doit etre AVOUEE, pas subie en silence"
    )


def test_trois_agents_distincts_livrent(tmp_path: Path, monkeypatch) -> None:
    """La chaine complete : detecter la CLI, lui parler, verifier, livrer."""
    report = _mission(tmp_path, monkeypatch, ("opencode", "hermes", "claude"))

    assert report.status is MissionStatus.DELIVERED, report.abstention_reason
    assert report.passed == report.total_checks


def test_un_seul_agent_est_denonce_comme_un_echo(tmp_path: Path, monkeypatch) -> None:
    """Cinq agents sur un seul modele ne valent pas cinq agents.

    C'est la lecon de « Conformity Breaks Conformal Prediction » : l'accord entre
    copies d'un meme modele ne prouve rien. Le systeme doit refuser de l'appeler
    un consensus — et le dire dans ces termes.
    """
    report = _mission(tmp_path, monkeypatch, ("opencode",))

    assert report.status is MissionStatus.DELIVERED_WITH_RESERVATION
    assert "echo" in report.abstention_reason
    assert report.passed == report.total_checks, "le travail est bon : c'est le consensus qui manque"


def test_deux_agents_expliquent_le_plafond_et_la_solution(tmp_path: Path, monkeypatch) -> None:
    """Un refus doit etre calculable et actionnable, pas seulement honnete.

    Avec deux couples (modele, verdict) distincts, la decorrelation vaut
    0.55 + 0.15*2 = 0.85 : une mission PARFAITE plafonne a 0.85, sous le seuil non
    calibre de 0.90. Aucune amelioration du travail ne peut livrer. Sans cette
    explication, l'utilisateur conclut que l'outil est casse.
    """
    report = _mission(tmp_path, monkeypatch, ("opencode", "hermes"))

    assert report.status is MissionStatus.DELIVERED_WITH_RESERVATION
    motif = report.abstention_reason
    assert "PLAFOND INATTEIGNABLE" in motif
    assert "3e modele" in motif, "la solution doit etre donnee, pas seulement le constat"
    assert "decompte" in motif, "le calcul doit etre verifiable"


@pytest.mark.parametrize("agents", [("opencode",), ("opencode", "hermes"), ("opencode", "hermes", "claude")])
def test_la_cli_est_detectee_via_la_variable_documentee(
    tmp_path: Path, monkeypatch, agents: tuple[str, ...]
) -> None:
    """`JIO_BIN_<NOM>` doit reellement choisir le binaire — la variable etait ignoree."""
    for key, value in _installer_agents(tmp_path, agents).items():
        monkeypatch.setenv(key, value)

    from jio.providers.registry import detect_clis

    binaires = {p.binary for p in detect_clis()}

    for value in _installer_agents(tmp_path, agents).values():
        assert value in binaires


# --------------------------------------------------------------------------- #
# `jio providers --prove` : prouver un fournisseur REEL, avant la premiere mission
# --------------------------------------------------------------------------- #


def _sonde_avec(tmp_path: Path, monkeypatch, stub_source: str, nom: str = "opencode"):
    """Sonde un fournisseur avec un binaire REEL en sous-processus.

    `JIO_BIN_<NOM>` doit etre exporte AVANT la detection : sinon le CLI simule n'est
    pas trouve, le test est saute, et il ne prouve rien. Un test qui saute en
    silence est exactement ce que ce depot refuse — la premiere version oubliait
    l'export et les quatre tests passaient en « s ».
    """
    binaire = tmp_path / nom
    binaire.write_text(stub_source.format(python=sys.executable), encoding="utf-8")
    binaire.chmod(binaire.stat().st_mode | stat.S_IEXEC)
    for cle in list(os.environ):
        if cle.startswith("JIO_BIN_"):
            monkeypatch.delenv(cle, raising=False)
    monkeypatch.setenv(f"JIO_BIN_{nom.upper()}", str(binaire))

    from jio.providers.probe import sonder
    from jio.providers.registry import detect_clis

    # Le nom reel d'un fournisseur CLI est `cli::<nom>` (voir registry.detect_clis).
    fournisseurs = [f for f in detect_clis() if getattr(f, "name", "") == f"cli::{nom}"]
    assert fournisseurs, (
        f"le CLI simule {nom} n'a pas ete detecte malgre JIO_BIN_{nom.upper()} : "
        "le test ne prouverait rien"
    )
    return sonder(fournisseurs[0])


CAPABLE = '''#!{python}
import json
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
if "You turn enumerated RULES into executable checks" in prompt:
    rendu = {{
        "R-001": "assert moyenne([1, 2]) == 1.5",
        "R-002": ("ok = False\\ntry:\\n    moyenne([])\\nexcept ValueError:\\n    ok = True\\n"
                  "assert ok, 'liste vide'"),
    }}
    print(json.dumps({{"type": "text", "text": json.dumps(rendu)}}))
    sys.exit(0)
print(json.dumps({{"type": "text", "text": "OK"}}))
'''

AVEU = '''#!{python}
import json
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
if "You turn enumerated RULES into executable checks" in prompt:
    rendu = {{"R-001": {{"impossible": "je ne sais pas ecrire de test"}}}}
    print(json.dumps({{"type": "text", "text": json.dumps(rendu)}}))
    sys.exit(0)
print(json.dumps({{"type": "text", "text": "OK"}}))
'''

HOSTILE = '''#!{python}
import json
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
if "You turn enumerated RULES into executable checks" in prompt:
    rendu = {{"R-001": "import os\\nassert moyenne([1, 2]) == 1.5"}}
    print(json.dumps({{"type": "text", "text": json.dumps(rendu)}}))
    sys.exit(0)
print(json.dumps({{"type": "text", "text": "OK"}}))
'''

MORT = '''#!{python}
import sys
sys.stderr.write("authentication required: run `login` first\\n")
sys.exit(1)
'''


def test_sonde_reconnait_un_fournisseur_capable_de_prouver(tmp_path: Path, monkeypatch) -> None:
    """Le fournisseur traduit les regles : c'est cette capacite qui rend la preuve possible."""
    sonde = _sonde_avec(tmp_path, monkeypatch, CAPABLE)
    assert sonde.vivant, sonde.erreur
    assert sonde.traduit, sonde.temoignage.resume() if sonde.temoignage else sonde.erreur_traduction
    assert len(sonde.temoignage.tests) == 2
    assert sonde.verdict == "CAPABLE DE PROUVER SANS ORACLE"


def test_sonde_distingue_un_aveu_dune_incapacite(tmp_path: Path, monkeypatch) -> None:
    """Un fournisseur qui AVOUE ne pas savoir traduire est different d'un fournisseur muet.

    Le premier peut encore ecrire du code et etre prouve par des oracles ; le second
    ne peut rien faire. Les confondre ferait renoncer au mauvais endroit.
    """
    sonde = _sonde_avec(tmp_path, monkeypatch, AVEU)
    assert sonde.vivant
    assert not sonde.traduit
    assert sonde.temoignage is not None and sonde.temoignage.aveux
    assert "NE SAIT PAS TRADUIRE" in sonde.verdict


def test_sonde_applique_la_porte_de_securite_sans_indulgence(tmp_path: Path, monkeypatch) -> None:
    """Un test hostile propose par un fournisseur REEL doit etre refuse, pas compte.

    La sonde n'est pas plus clemente qu'une mission : la porte de securite est celle
    de `jio/spec/witness.py`, la meme. Sinon le diagnostic annoncerait une capacite
    que la mission refuserait d'utiliser.
    """
    sonde = _sonde_avec(tmp_path, monkeypatch, HOSTILE)
    assert sonde.vivant
    assert not sonde.traduit, "un test avec `import` ne doit jamais compter comme un temoin"
    assert sonde.temoignage is not None and sonde.temoignage.refuses
    assert "fragment interdit" in next(iter(sonde.temoignage.refuses.values()))


def test_sonde_nomme_la_panne_au_lieu_de_planter(tmp_path: Path, monkeypatch) -> None:
    """Un CLI non authentifie est le cas le plus courant. Il doit etre NOMME."""
    sonde = _sonde_avec(tmp_path, monkeypatch, MORT)
    assert not sonde.vivant
    assert not sonde.traduit
    assert sonde.verdict == "INJOIGNABLE"
    assert len(sonde.resume()) > 10, "le resume doit dire quelque chose d'utile"


def test_la_commande_providers_ne_plante_jamais(monkeypatch, capsys) -> None:
    """Diagnostic : il doit toujours rendre un code de sortie et une phrase utile."""
    import argparse

    for cle in list(os.environ):
        if cle.startswith("JIO_BIN_") or cle.startswith("JIO_OPENAI"):
            monkeypatch.delenv(cle, raising=False)

    from jio.cli import cmd_providers

    code = cmd_providers(argparse.Namespace(prove=False))
    sortie = capsys.readouterr().out
    assert code == 0
    assert "FOURNISSEURS DETECTES" in sortie
    assert "jio bench" in sortie, "sans fournisseur, la sortie doit dire quoi faire"


# --------------------------------------------------------------------------- #
# 4. La relance, mesuree sur le chemin reel : le harness ne doit jamais etre
#    PIRE que le modele seul
# --------------------------------------------------------------------------- #

#: Un faux agent qui rate la traduction UNE fois (il repond de la prose), puis se reprend
#: quand on lui dit ce qui a ete refuse. C'est le comportement le plus courant d'un vrai
#: modele devant ce prompt, et c'est la ou le harness pouvait perdre.
STUB_UNE_FOIS = '''#!SHEBANG
import json
import pathlib
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
marque = pathlib.Path(__MARQUE__)
appels = pathlib.Path(__APPELS__)

if "You turn enumerated RULES into executable checks" in prompt:
    with appels.open("a", encoding="utf-8") as f:
        f.write("traduction\\n")
    if not marque.exists():
        marque.write_text("1", encoding="utf-8")
        print("Sure! Let me summarise the rules in prose instead of a JSON object.")
        sys.exit(0)
    import re as _re
    PAIRES = [
        ("R-001", "assert median([3, 1, 2]) == 2, 'impair'"),
        ("R-002", "assert median([1, 2, 3, 4]) == 2.5, 'pair'"),
        ("R-003", "try:\\n    median([])\\n    ok = False\\nexcept ValueError:\\n    ok = True\\n"
                  "assert ok, 'liste vide: aucune ValueError levee'"),
        ("R-004", "assert median([5, 2, 9, 1, 7]) == 5, 'non trie'"),
    ]
    demandees = _re.findall(r"\\[(R-[0-9]+)\\]", prompt)
    rendu = {p[0]: p[1] for p in PAIRES if not demandees or p[0] in demandees}
    print(json.dumps(dict(type="text", text=json.dumps(rendu))))
    sys.exit(0)

if "You are a strict" in prompt:
    print(json.dumps(dict(type="text", text=json.dumps(dict(
        verdict="pass", confidence=0.9,
        reason="la specification est satisfaite", counterexample=None,
    )))))
    sys.exit(0)

CODE = """def median(nums):
    if not nums:
        raise ValueError("liste vide")
    valeurs = sorted(nums)
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2
"""

print(json.dumps(dict(type="text", text="```python\\n" + CODE + "```\\n")))
'''

#: Un faux agent qui AVOUE honnetement, toujours : aucune regle ne serait testable.
STUB_AVEU = '''#!SHEBANG
import json
import pathlib
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
appels = pathlib.Path(__APPELS__)

if "You turn enumerated RULES into executable checks" in prompt:
    with appels.open("a", encoding="utf-8") as f:
        f.write("traduction\\n")
    import re as _re
    demandees = _re.findall(r"\\[(R-[0-9]+)\\]", prompt)
    rendu = dict((r, dict(impossible="aucune assertion executable pour cet enonce"))
                 for r in demandees)
    print(json.dumps(dict(type="text", text=json.dumps(rendu))))
    sys.exit(0)

if "You are a strict" in prompt:
    print(json.dumps(dict(type="text", text=json.dumps(dict(
        verdict="pass", confidence=0.9,
        reason="la specification est satisfaite", counterexample=None,
    )))))
    sys.exit(0)

CODE = """def median(nums):
    if not nums:
        raise ValueError("liste vide")
    valeurs = sorted(nums)
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2
"""

print(json.dumps(dict(type="text", text="```python\\n" + CODE + "```\\n")))
'''


def _gabarit(stub: str, tmp_path: Path) -> str:
    """Prepare un stub brut pour `_installer_agents`, qui applique `.format(python=...)`.

    On ecrit le stub en clair (accolades normales) et on n'echappe QU'ICI : un stub lisible
    est un stub qu'on peut relire, et ces deux stubs sont la demonstration du correctif.
    """
    gabarit = stub.replace("#!SHEBANG", "#!{python}", 1)
    gabarit = gabarit.replace("{", "{{").replace("}", "}}")
    gabarit = gabarit.replace("{{python}}", "{python}")
    return (gabarit
            .replace("__MARQUE__", repr(str(tmp_path / "marque-traduction")))
            .replace("__APPELS__", repr(str(tmp_path / "appels-traduction.txt"))))


def test_chemin_reel_une_traduction_RATEE_est_relancee_et_la_mission_est_livree(
    tmp_path: Path, monkeypatch
) -> None:
    """LA mesure de cet axe : sans la relance, ce modele faisait livrer ZERO.

    Un modele qui ecrit du code correct mais rend de la prose au prompt de traduction etait
    mesure a 0 % — quand un tirage aveugle du MEME budget reussissait. Le harness etait donc
    pire que le modele seul sur le seul cas qui existe en vrai (aucun oracle). Ici, la CLi
    rate la premiere traduction ; la seconde, relancee AVEC le motif du rejet, reussit.
    """
    stub = _gabarit(STUB_UNE_FOIS, tmp_path)
    report = _mission_sans_oracle(tmp_path, monkeypatch, ("opencode", "hermes", "claude"),
                                  stub=stub)

    # UNE traduction de regles par mission (elle est memoisee), donc DEUX appels :
    # la reponse inexploitable, puis la relance.
    appels = (tmp_path / "appels-traduction.txt").read_text(encoding="utf-8")
    assert appels.count("traduction") == 2, "une tentative ratee, une relance, et rien de plus"
    assert report.status.value.startswith("delivered"), report.abstention_reason
    assert report.passed == report.total_checks


def test_chemin_reel_un_AVEU_honnete_ne_declenche_AUCUNE_relance(
    tmp_path: Path, monkeypatch
) -> None:
    """La borne de la relance, verifiee de bout en bout : un aveu n'est pas une panne.

    Insister apres un aveu, c'est demander a un modele d'inventer une preuve. On compte
    donc les appels de TRADUCTION : un seul par agent, malgre l'absence complete de temoins.
    """
    stub = _gabarit(STUB_AVEU, tmp_path)
    report = _mission_sans_oracle(tmp_path, monkeypatch, ("opencode", "hermes", "claude"),
                                  stub=stub)

    # UNE traduction de regles par mission, et AUCUNE relance : ce modele a repondu.
    appels = (tmp_path / "appels-traduction.txt").read_text(encoding="utf-8")
    assert appels.count("traduction") == 1, "un aveu n'est pas une panne : aucun rappel"
    assert report.status is MissionStatus.ABSTAINED, report.status.value
    assert any(f.agent == "temoins" for f in report.findings)
