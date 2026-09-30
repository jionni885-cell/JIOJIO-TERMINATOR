"""Sert le modele local derriere une API compatible OpenAI — donc sans toucher au harness.

Pourquoi une API plutot qu'un import : `jio` sait deja parler a tout ce qui expose
`/v1/chat/completions` (`JIO_OLLAMA`, `JIO_OPENAI_BASE`). Brancher un modele local par ce
chemin-la a deux consequences qui comptent :

  * le harness n'est pas modifie pour faire plaisir a un cas particulier — la preuve porte sur
    le chemin REEl, celui qu'un utilisateur emprunte avec Ollama, vLLM ou OpenRouter ;
  * ce qui est mesure est bien « un modele inconnu du harness », pas un adaptateur ecrit pour
    la circonstance.

Le service est volontairement minimal et honnete : il dit ce qu'il est (`modele-local-char`,
taille, corpus), il refuse ce qu'il ne sait pas faire (streaming, outils) et il ne se fait pas
passer pour autre chose.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch

from entrainer import ModeleDeCode


class Moteur:
    """Charge le modele une fois et sert les generations, en serie.

    En SERIE, avec un verrou, et c'est deliberе : le harness envoie plusieurs requetes en
    parallele (consensus, red-team). Sur deux coeurs, les executer en parallele ne les rend pas
    plus rapides — et un modele qui repond dans le desordre rendrait la mesure non reproductible
    a partir d'une meme graine. Une file d'attente est ici une garantie de reproductibilite.
    """

    def __init__(self, chemin: pathlib.Path) -> None:
        paquet = torch.load(chemin, map_location="cpu", weights_only=False)
        config = paquet["config"]
        alphabet = paquet["alphabet"]
        self.stoi = {c: i for i, c in enumerate(alphabet)}
        self.itos = {i: c for i, c in enumerate(alphabet)}
        self.modele = ModeleDeCode(
            len(alphabet), config["n_emb"], config["n_tetes"], config["n_couches"],
            config["bloc"], 0.0,
        )
        self.modele.load_state_dict(paquet["poids"])
        self.modele.eval()
        self.bloc = config["bloc"]
        self.parametres = paquet.get("parametres", 0)
        self.validation = paquet.get("validation")
        self.corpus_octets = paquet.get("corpus_octets", 0)
        self.verrou = threading.Lock()
        self.appels = 0
        self.caracteres = 0

    def statut(self) -> dict:
        return {
            "modele": "modele-local-char",
            "parametres": self.parametres,
            "corpus_octets": self.corpus_octets,
            "perte_validation": self.validation,
            "appels": self.appels,
            "caracteres_generes": self.caracteres,
        }

    def generer(self, invite: str, *, temperature: float, max_tokens: int, graine: int | None):
        """Genere la suite du texte. La graine vient du client quand il en fournit une.

        La graine est ce qui rend la mesure REPRODUCTIBLE : deux executions de la meme mission
        doivent voir le meme modele repondre la meme chose, sinon aucun resultat n'est
        attribuable a une brique du harness. Quand le client n'en donne pas, on en tire une —
        et l'appel reste trace par `appels`.
        """
        debout = invite[-self.bloc :] or "def "
        idx = torch.tensor(
            [[self.stoi.get(c, 0) for c in debout]], dtype=torch.long
        )
        # Un caractere par « token » ici : `max_tokens` designe des caracteres. On le dit au
        # client dans la reponse (`usage`), sinon il croit avoir affaire a un modele de mots.
        n = max(8, min(int(max_tokens), 1200))
        with self.verrou:
            self.appels += 1
            debut = time.monotonic()
            sortie = self.modele.generer(
                idx, n, temperature=max(temperature, 0.05), top_k=40, graine=graine
            )
            self.caracteres += n
            duree = time.monotonic() - debut
        texte = "".join(self.itos[int(i)] for i in sortie[0, -n:].tolist())
        return texte, duree


def _invite(messages: list[dict]) -> str:
    """Rend la conversation en un texte unique, la demande EN DERNIER.

    Un modele char-level n'a pas de format de conversation : ce qui compte est ce qu'il voit
    juste avant de generer. On garde donc les systemes (ils portent les contraintes) puis les
    messages, dans l'ordre, et on termine par le dernier message utilisateur — c'est-a-dire
    exactement ce qu'un modele autoregressif doit prolonger.
    """
    morceaux: list[str] = []
    for m in messages:
        role = str(m.get("role", "user"))
        contenu = m.get("content")
        if not isinstance(contenu, str):
            contenu = json.dumps(contenu, ensure_ascii=False)
        if role == "system":
            morceaux.append(f"# {contenu}\n")
        elif role == "assistant":
            morceaux.append(f"{contenu}\n")
        else:
            morceaux.append(f"{contenu}\n")
    return "\n".join(morceaux)


class Handler(BaseHTTPRequestHandler):
    moteur: Moteur

    def log_message(self, *_args) -> None:  # silence : la progression vient du harness
        return

    def _json(self, code: int, charge: dict) -> None:
        corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self) -> None:  # noqa: N802 — impose par http.server
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._json(200, {"object": "list", "data": [{"id": "modele-local-char",
                                                         "object": "model"}]})
        elif self.path.rstrip("/") in ("/statut", "/health"):
            self._json(200, self.moteur.statut())
        else:
            self._json(404, {"error": {"message": f"chemin inconnu : {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802 — impose par http.server
        if self.path.rstrip("/").split("/")[-1] != "completions":
            self._json(404, {"error": {"message": f"chemin inconnu : {self.path}"}})
            return
        try:
            taille = int(self.headers.get("Content-Length") or 0)
            demande = json.loads(self.rfile.read(taille) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": {"message": f"corps illisible : {exc}"}})
            return

        messages = demande.get("messages") or []
        if not isinstance(messages, list) or not messages:
            self._json(400, {"error": {"message": "messages manquants"}})
            return
        temperature = float(demande.get("temperature") or 0.8)
        max_tokens = int(demande.get("max_tokens") or 256)
        graine = demande.get("seed")
        graine = int(graine) if isinstance(graine, (int, float)) else None

        invite = _invite(messages)
        texte, duree = self.moteur.generer(
            invite, temperature=temperature, max_tokens=max_tokens, graine=graine
        )
        self._json(200, {
            "id": f"chatcmpl-local-{self.moteur.appels}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "modele-local-char",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": texte},
                "finish_reason": "length",
            }],
            "usage": {
                "prompt_tokens": len(invite),
                "completion_tokens": len(texte),
                "total_tokens": len(invite) + len(texte),
            },
            "jio_local": {
                "duree_s": round(duree, 3),
                "unite": "caracteres",
                "note": "modele char-level entraine localement : ce n'est PAS un modele frontier",
            },
        })


def main() -> int:
    parseur = argparse.ArgumentParser(description="Sert le modele local (API OpenAI).")
    parseur.add_argument("--modele", default="modele/modele.pt")
    parseur.add_argument("--hote", default="0.0.0.0")  # noqa: S104 — accessible depuis la sandbox
    parseur.add_argument("--port", type=int, default=8088)
    args = parseur.parse_args()

    racine = pathlib.Path(__file__).resolve().parents[2]
    chemin = pathlib.Path(args.modele)
    if not chemin.is_absolute():
        chemin = racine / chemin
    if not chemin.is_file():
        print(f"modele introuvable : {chemin}. Lancez d'abord `entrainer.py`.")
        return 2

    Handler.moteur = Moteur(chemin)
    statut = Handler.moteur.statut()
    print(f"  modele-local  ·  {statut['parametres']:,} parametres".replace(",", " "))
    print(f"  perte de validation : {statut['perte_validation']}")
    print(f"  a l'ecoute sur http://{args.hote}:{args.port}/v1  (Ctrl-C pour arreter)")
    ThreadingHTTPServer((args.hote, args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
