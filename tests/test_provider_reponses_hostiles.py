"""Ce que le modele repond est du contenu NON FIABLE, y compris dans sa FORME.

Ce projet traite le contenu d'un depot comme hostile. La reponse d'un modele l'est tout
autant : elle vient d'un serveur, d'un binaire, d'un proxy — ou d'un modele qui part en
boucle. Trois defauts reels ont ete trouves en cherchant, et ce fichier les verrouille :

1. **`content` en BLOCS.** Les API modernes renvoient
   `"content": [{"type": "text", "text": "..."}]` au lieu d'une chaine. Le texte partait
   alors tel quel dans `Completion(text=...)` : `text` devenait une LISTE, et le premier
   `re.search` en aval levait un `AttributeError` — un plantage la ou le systeme doit
   s'abstenir.

2. **Reponse de taille illimitee.** Un serveur hostile (ou un agent en boucle) peut streamer
   sans fin. `resp.read()` lisait tout avant qu'on puisse reagir. La lecture est desormais
   bornee, et depasser le plafond est un REFUS, pas une troncature silencieuse.

3. **Reponse vide.** Elle passait pour une reponse : les regles echouaient plus loin, sans
   que personne ne sache pourquoi. Un modele qui ne dit rien n'a rien prouve.

Les tests HTTP utilisent un VRAI serveur local (`http.server` sur un thread), pas une
maquette : c'est le chemin reseau qui est en cause, donc c'est lui qu'on exerce.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jio.providers import base as base_module
from jio.providers.base import Message, borner, extraire_texte
from jio.providers.cli import CliProvider
from jio.providers.openai_compat import OpenAiCompatProvider

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --------------------------------------------------------------------------- #
# 1. La normalisation du texte, seule
# --------------------------------------------------------------------------- #


def test_une_chaine_reste_une_chaine() -> None:
    assert extraire_texte("bonjour") == "bonjour"


def test_les_blocs_de_texte_sont_jointe() -> None:
    """La forme moderne des API — celle qui faisait planter le systeme."""
    valeur = [
        {"type": "text", "text": "premiere partie"},
        {"type": "text", "text": "seconde partie"},
    ]
    assert extraire_texte(valeur) == "premiere partie\nseconde partie"


def test_les_blocs_non_texte_sont_ignores() -> None:
    """Une image ou un appel d'outil ne porte pas la reponse a la question posee."""
    valeur = [
        {"type": "image_url", "image_url": {"url": "http://x"}},
        {"type": "text", "text": "la reponse"},
        {"type": "tool_use", "id": "1", "name": "rm"},
    ]
    assert extraire_texte(valeur) == "la reponse"


@pytest.mark.parametrize("valeur", [None, 42, True, {"inattendu": 1}, object()])
def test_une_forme_inconnue_ne_plante_pas(valeur: object) -> None:
    """Rendre une chaine vide est un resultat ; lever une exception serait un plantage.

    L'appelant, lui, decide : une chaine vide remonte comme « rien a verifier » (voir le
    cadrage ci-dessous). Ce qui ne doit jamais arriver, c'est un `TypeError` au milieu du
    traitement.
    """
    resultat = extraire_texte(valeur)
    assert isinstance(resultat, str)


def test_une_reponse_enorme_est_tronquee_ET_signalee() -> None:
    """`borner` ne tronque jamais en silence : le drapeau compte autant que le texte."""
    court, tronque_court = borner("petit")
    assert (court, tronque_court) == ("petit", False)

    long_texte = "x" * (base_module.MAX_REPONSE + 10)
    borne, tronque = borner(long_texte)
    assert len(borne) == base_module.MAX_REPONSE
    assert tronque is True


# --------------------------------------------------------------------------- #
# 2. Le chemin RESEAU complet, contre un vrai serveur
# --------------------------------------------------------------------------- #


class _Serveur(BaseHTTPRequestHandler):
    """Serveur local qui rend le corps prepare par le test."""

    corps: bytes = b""
    code: int = 200

    def do_POST(self) -> None:  # noqa: N802 - nom impose par http.server
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self.send_response(self.code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.corps)

    def log_message(self, *args: object) -> None:  # silence
        return


@pytest.fixture()
def serveur():
    httpd = HTTPServer(("127.0.0.1", 0), _Serveur)
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _provider(serveur: HTTPServer) -> OpenAiCompatProvider:
    return OpenAiCompatProvider(
        base_url=f"http://127.0.0.1:{serveur.server_port}",
        api_key="",
        model="test",
        timeout=10,
    )


def test_le_reseau_accepte_les_blocs_de_texte(serveur: HTTPServer) -> None:
    _Serveur.corps = json.dumps({
        "model": "test",
        "choices": [{
            "message": {"content": [
                {"type": "text", "text": "def somme(a, b):"},
                {"type": "text", "text": "    return a + b"},
            ]},
            "finish_reason": "stop",
        }],
    }).encode("utf-8")

    completion = _provider(serveur).complete([Message("user", "ecris une somme")])

    assert isinstance(completion.text, str), (
        "le texte doit etre une chaine : une liste casse tout le traitement en aval"
    )
    assert "def somme(a, b):" in completion.text
    assert "return a + b" in completion.text


def test_le_reseau_refuse_une_reponse_vide(serveur: HTTPServer) -> None:
    """Un modele qui ne dit rien n'a rien prouve : le dire ICI, pas trois couches plus bas."""
    from jio.core.errors import ProviderError

    _Serveur.corps = json.dumps({
        "choices": [{"message": {"content": None}, "finish_reason": "length"}],
    }).encode("utf-8")

    with pytest.raises(ProviderError) as erreur:
        _provider(serveur).complete([Message("user", "question")])
    assert "chaine vide" in str(erreur.value)
    assert "length" in str(erreur.value), "la raison de fin doit etre citee"


def test_le_reseau_refuse_une_reponse_sans_choix(serveur: HTTPServer) -> None:
    from jio.core.errors import ProviderError

    _Serveur.corps = json.dumps({"error": "quota"}).encode("utf-8")
    with pytest.raises(ProviderError):
        _provider(serveur).complete([Message("user", "question")])


def test_le_reseau_refuse_une_reponse_delirante(serveur: HTTPServer) -> None:
    """Une liste a la racine, un nombre, du JSON valide mais pas un objet : rien ne passe."""
    from jio.core.errors import ProviderError

    for corps in (b"[1, 2, 3]", b"42", b'"texte"'):
        _Serveur.corps = corps
        with pytest.raises(ProviderError):
            _provider(serveur).complete([Message("user", "question")])


def test_le_reseau_refuse_une_reponse_TROP_GROSSE(serveur: HTTPServer, monkeypatch) -> None:
    """Au-dela du plafond : refus, jamais chargement complet.

    On abaisse le plafond plutot que d'envoyer 32 Mo sur la boucle locale : le mecanisme
    teste est le controle de taille, pas la bande passante.
    """
    from jio.core.errors import ProviderError

    monkeypatch.setattr(base_module, "MAX_REPONSE", 1000)
    _Serveur.corps = json.dumps({
        "choices": [{"message": {"content": "x" * 50_000}, "finish_reason": "stop"}],
    }).encode("utf-8")

    with pytest.raises(ProviderError) as erreur:
        _provider(serveur).complete([Message("user", "question")])
    assert "refusee plutot que chargee" in str(erreur.value)


def test_une_reponse_longue_mais_legitime_est_tronquee_et_MARQUEE(
    serveur: HTTPServer, monkeypatch
) -> None:
    """Le cas ou l'on accepte : sous le plafond de lecture, au-dessus du plafond de texte."""
    monkeypatch.setattr(base_module, "MAX_REPONSE", 500)
    _Serveur.corps = json.dumps({
        "choices": [{"message": {"content": "a" * 2000}, "finish_reason": "stop"}],
    }).encode("utf-8")

    completion = _provider(serveur).complete([Message("user", "question")])

    assert len(completion.text) == 500
    assert completion.metadata.get("tronque") is True, "une troncature doit se voir"


# --------------------------------------------------------------------------- #
# 3. Le chemin CLI : un binaire se comporte comme un serveur distant
# --------------------------------------------------------------------------- #


def _faux_binaire(tmp_path, script: str) -> str:
    chemin = tmp_path / "faux-agent"
    chemin.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    chemin.chmod(0o755)
    return str(chemin)


def test_un_agent_jsonl_en_blocs_est_lu(tmp_path) -> None:
    """`opencode run --format json` emet une ligne par evenement ; `content` peut etre en blocs."""
    binaire = _faux_binaire(
        tmp_path,
        "cat > /dev/null\n"
        "printf '%s\\n' '{\"type\":\"text\",\"part\":{\"type\":\"text\",\"text\":\"bonjour\"}}'\n"
        "printf '%s\\n' '{\"content\":[{\"type\":\"text\",\"text\":\"monde\"}]}'",
    )
    provider = CliProvider(binary=binaire, argv_template="{binary} {prompt}", timeout=20)

    completion = provider.complete([Message("user", "salut")])

    assert completion.text.strip() in {"bonjour\nmonde", "monde\nbonjour"}
    assert completion.metadata.get("format") == "jsonl"


def test_un_agent_muet_est_signale(tmp_path) -> None:
    """Exit 0 et aucune sortie : ce n'est pas une reponse, et l'aval ne doit pas le deviner."""
    from jio.core.errors import ProviderError

    binaire = _faux_binaire(tmp_path, "cat > /dev/null\nexit 0")
    provider = CliProvider(binary=binaire, argv_template="{binary} {prompt}", timeout=20)

    with pytest.raises(ProviderError) as erreur:
        provider.complete([Message("user", "salut")])
    assert "aucun texte" in str(erreur.value)


def test_un_agent_bavard_est_borne_et_marque(tmp_path, monkeypatch) -> None:
    # Un SEUL plafond, dans `base` : `borner` le lit la. Patcher un autre module donnerait
    # un test qui croit avoir change la regle sans rien changer.
    monkeypatch.setattr(base_module, "MAX_REPONSE", 300)

    binaire = _faux_binaire(tmp_path, "cat > /dev/null\nhead -c 2000 /dev/zero | tr '\\0' 'a'")
    provider = CliProvider(binary=binaire, argv_template="{binary} {prompt}", timeout=20)

    completion = provider.complete([Message("user", "salut")])

    assert len(completion.text) <= 300
    assert completion.metadata.get("tronque") is True


def test_un_agent_en_erreur_donne_son_stderr(tmp_path) -> None:
    """Un echec de binaire doit citer ce qu'il a dit : sinon on cherche au mauvais endroit."""
    from jio.core.errors import ProviderError

    binaire = _faux_binaire(tmp_path, "cat > /dev/null\necho 'non authentifie' >&2\nexit 3")
    provider = CliProvider(binary=binaire, argv_template="{binary} {prompt}", timeout=20)

    with pytest.raises(ProviderError) as erreur:
        provider.complete([Message("user", "salut")])
    assert "non authentifie" in str(erreur.value)
    assert "exit=3" in str(erreur.value)


def test_le_retour_d_echec_est_reconnu_par_sa_MARQUE_et_son_IDENTIFIANT() -> None:
    """Deux exigences, et la seconde est celle qui compte.

    « ca a rate » n'informe personne ; « la regle R-003 attend 9 » informe. Le simulateur
    ne traite donc un prompt comme un retour d'echec structure que s'il porte la marque ET
    un identifiant de regle. Mesure a l'origine : `jio mutants` a montre que la borne
    `if at < 0: return False` de la recherche pouvait passer a `at >= 0` sans qu'aucun test
    ne bouge — un prompt SANS marque aurait alors ete traite comme un echec structure, et
    tous les bancs simules auraient mesure un modele qui apprend de plaintes vagues.
    """
    from jio.providers.simulated import _has_structured_feedback

    assert not _has_structured_feedback("rien du tout")
    assert not _has_structured_feedback("PREVIOUS ATTEMPT FAILED")  # marque seule
    assert _has_structured_feedback("PREVIOUS ATTEMPT FAILED : la regle R-003 attend 9")
    assert _has_structured_feedback("PREVIOUS ATTEMPT FAILED (rule 3 wants 9)")
    # Un identifiant de regle SANS la marque n'est pas un retour d'echec : le prompt peut
    # simplement citer une regle.
    assert not _has_structured_feedback("la regle R-003 attend 9")

def test_un_retour_d_echec_qui_COMMENCE_par_la_marque_est_reconnu() -> None:
    """La marque trouvee a la position 0 est encore une marque.

    Mesure a l'origine : `jio mutants` a montre que le test `at < 0` pouvait devenir `at < 1`
    sans qu'aucun test ne bouge. Un prompt dont la PREMIERE ligne est le retour d'echec
    n'aurait alors plus ete reconnu comme structure : le modele aurait rejoue la meme
    reponse, la boucle aurait consomme un tour pour rien, et le budget aurait servi a
    repeter une erreur.
    """
    from jio.providers.simulated import _has_structured_feedback

    assert _has_structured_feedback("PREVIOUS ATTEMPT FAILED : la regle R-003 attend 9") is True
    assert _has_structured_feedback("bla bla PREVIOUS ATTEMPT FAILED - rule R-1") is True
    assert _has_structured_feedback("PREVIOUS ATTEMPT FAILED sans identifiant") is False
    assert _has_structured_feedback("PREVIOUS ATTEMPT") is False
    assert _has_structured_feedback("ca a rate") is False
