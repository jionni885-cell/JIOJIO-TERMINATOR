"""Traducteur simule : un modele qui transforme des regles en tests executables.

POURQUOI CE SIMULATEUR EXISTE. Le banc fournit ses oracles ; une mission reelle
n'en a aucun. Le moteur demande donc au modele de traduire les regles en temoins
— et cette traduction est une COMPETENCE, qui peut reussir ou echouer. La mesurer
exige de pouvoir la faire varier, sinon on ne mesure que son propre optimisme.

HYPOTHESE DECLAREE, et elle est modeste : traduire une regle deja enumeree
(« une liste vide renvoie 0 » -> ``assert f([]) == 0``) est une tache PLUS FACILE
que resoudre la mission elle-meme. C'est ce que dit la litterature du domaine : un
test par regle enumeree apporte +38 points de code correct, et les proprietes
ecrites par un modele sont en moyenne mieux ecrites que le code qu'elles testent.

  * ``fidelite = 1.0`` — le modele lit correctement les regles : il rend, pour
    chaque regle, l'oracle de reference du banc. C'est la borne haute, et elle est
    DECLAREE comme telle.
  * ``fidelite = 0.0`` — le modele se trompe sur CHAQUE regle traduisible : il
    encode l'attente d'une implementation FAUSSE (un distracteur du banc), ou
    inverse un contrat d'erreur. C'est la borne basse : un traducteur mauvais.
  * entre les deux, la proportion indiquee de regles est trompee.

La borne basse n'est pas une hypothese gratuite : c'est le mode d'echec reel d'un
traducteur, et c'est celui qui coute le plus cher (il ne fait pas que manquer un
defaut : il peut accuser une implementation correcte). Le moteur doit y survivre
sans faire pire qu'un tirage aveugle — sinon la brique est nuisible, et elle
n'aurait pas sa place.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Sequence

from ..providers.base import Completion, Message
from .tasks import Task

#: Regles presentes dans un prompt de traduction : « - [R-001] (property) enonce ».
_LIGNE_REGLE = re.compile(r"^\s*-\s*\[(?P<id>[^\]]+)\]\s*(?:\((?P<kind>[^)]*)\))?\s*(?P<reste>.*)$")


def _graine(*parts: object) -> int:
    """Graine deterministe : la meme experience rejoue les memes tirages."""
    texte = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12], 16)


#: Fonctions de base : leur appel n'est pas celui de l'entree publique.
_BASES = frozenset({"print", "len", "sum", "sorted", "list", "dict", "set", "tuple",
                    "str", "int", "float", "bool", "abs", "round", "min", "max", "range"})


def _appel_entree(arbre: ast.AST) -> ast.Call | None:
    """Trouve l'appel a l'entree publique — pas seulement dans l'assertion.

    Un contrat d'erreur s'ecrit ``try: entree(...) except Valeur:`` : l'appel est
    alors HORS de l'assertion, dans le corps du ``try``. Chercher l'appel dans la
    seule assertion ne le trouvait pas, et la contrefacon de contrat d'erreur
    n'etait jamais construite — une mesure qui ne mesurait rien, encore une fois.
    """
    appels = [
        node for node in ast.walk(arbre)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id not in _BASES
    ]
    if not appels:
        return None
    return min(appels, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def contrefacon(test: str, distracteurs: Sequence[str]) -> str | None:
    """Fabrique l'attente d'une implementation FAUSSE — le mode d'echec du traducteur.

    Trois formes, essayees dans cet ordre :
      1. ``assert appel(...) == attendu`` : l'attendu devient ce que rend un
         DISTRACTEUR sur la meme entree — le modele a encode la mauvaise valeur ;
      2. contrat d'erreur lu a l'envers (« ne doit pas lever » au lieu de « doit
         lever ») : c'est le bug d'erreur silencieuse, le plus courant de tous ;
      3. negation generique de l'assertion : la regle est lue a l'envers. Elle
         couvre tout ce que les deux premieres ne couvrent pas (assertions
         composees, ``isinstance``, refus), et un distracteur la satisfait presque
         toujours.

    Rend ``None`` seulement quand aucune contrefacon n'est constructible : dans ce
    cas le traducteur reste FIDELE sur cette regle. Un mode d'echec qu'on ne sait
    pas simuler ne doit pas etre compte comme simule — sinon la borne basse qu'on
    annonce n'est pas la borne basse qu'on mesure.
    """
    try:
        arbre = ast.parse(test, mode="exec")
    except SyntaxError:
        return None

    assertion = next((n for n in ast.walk(arbre) if isinstance(n, ast.Assert)), None)
    if assertion is None:
        return None

    # -- 1. comparaison a une constante ------------------------------------ #
    if isinstance(assertion.test, ast.Compare) and len(assertion.test.comparators) == 1:
        gauche = assertion.test.left
        if isinstance(gauche, ast.Call) and isinstance(assertion.test.comparators[0], ast.Constant):
            expression = ast.unparse(gauche)
            for source in distracteurs:
                espace: dict[str, object] = {}
                try:
                    exec(source, espace)  # noqa: S102 — code du banc, pas du modele
                    valeur = eval(expression, espace)
                except Exception:  # noqa: BLE001 — un distracteur qui echoue ne
                    # contrefait rien : on essaie le suivant, sans bruit.
                    continue
                if valeur == assertion.test.comparators[0].value:
                    continue
                assertion.test.comparators[0] = ast.Constant(value=valeur)
                assertion.msg = None  # le message d'origine contredirait la contrefacon
                return ast.unparse(arbre)

    # -- 2. contrat d'erreur lu a l'envers ---------------------------------- #
    appel = _appel_entree(arbre)
    if appel is not None and re.search(r"except\s+[A-Za-z_]", test):
        expression = ast.unparse(appel)
        return (
            "ok = True\n"
            f"try:\n    {expression}\n"
            "except Exception:\n    ok = False\n"
            f"assert ok, 'contrefacon: {expression} ne doit pas lever'\n"
        )

    # -- 3. negation generique : la regle lue a l'envers -------------------- #
    neuf = ast.Assert(
        test=ast.UnaryOp(op=ast.Not(), operand=assertion.test),
        msg=ast.Constant(value="contrefacon: la regle a ete lue a l'envers"),
    )
    return ast.unparse(ast.Module(body=[neuf], type_ignores=[]))


@dataclass
class TraducteurSimule:
    """Un modele qui traduit les regles d'une tache en tests executables."""

    taches: Sequence[Task]
    fidelite: float = 1.0
    name: str = "temoins-sim"
    model: str = "sim-1"
    appels: int = 0
    #: Journal lisible des contrefacons produites (pour l'audit de la mesure).
    contrefaites: list[str] = field(default_factory=list)

    def _tache(self, prompt: str) -> Task | None:
        candidates = [t for t in self.taches if t.objective in prompt]
        if not candidates:
            return None
        return max(candidates, key=lambda t: len(t.objective))

    def _regles_du_prompt(self, prompt: str) -> list[str]:
        ids: list[str] = []
        for ligne in prompt.splitlines():
            m = _LIGNE_REGLE.match(ligne)
            if m and "(" in ligne:
                ids.append(m.group("id").strip())
        return ids

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        seed: int | None = None,
    ) -> Completion:
        self.appels += 1
        prompt = "\n".join(m.content for m in messages)
        tache = self._tache(prompt)
        if tache is None:
            return Completion(
                text="{}", model=self.model, provider=self.name,
                metadata={"sim_temoins": "tache inconnue"},
            )

        regles = self._regles_du_prompt(prompt) or list(tache.checks)
        traduits: dict[str, object] = {}
        for rid in regles:
            fidele = tache.checks.get(rid)
            if fidele is None:
                traduits[rid] = {"impossible": "aucun oracle de reference pour cette regle"}
                continue
            taux = min(1.0, max(0.0, self.fidelite))
            tirage = (_graine(tache.id, rid, seed) % 1000) / 1000.0
            if tirage < taux:
                traduits[rid] = fidele
                continue
            faux = contrefacon(fidele, tache.distractors)
            if faux is None:
                traduits[rid] = fidele  # aucune contrefacon constructible : on reste fidele
                continue
            self.contrefaites.append(f"{tache.id}:{rid}")
            traduits[rid] = faux

        return Completion(
            text=json.dumps(traduits, ensure_ascii=False),
            model=self.model,
            provider=self.name,
            metadata={"sim_temoins": tache.id, "contrefaites": len(self.contrefaites)},
        )

    def resume(self) -> str:
        return (
            f"{self.appels} traduction(s), fidelite {self.fidelite:.0%}, "
            f"{len(self.contrefaites)} regle(s) contrefaite(s)"
        )
