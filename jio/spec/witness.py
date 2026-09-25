"""Traduire les regles en temoins executables — sinon ce ne sont que des slogans.

LE TROU, constate dans le code. Le compilateur enumere des regles (« une liste
vide renvoie 0 ») et le moteur les fait LIRE au modele, mais aucune n'est jamais
traduite en test executable. Hors banc d'essai — c'est-a-dire dans toute mission
reelle — la seule verification executable disponible est l'auto-coherence :
l'artefact doit tenir ce que sa propre signature et ses propres exemples
annoncent. Un artefact peut donc satisfaire parfaitement sa propre documentation
et ne rien faire de ce que la mission demandait. Les regles restent des slogans.

LA MESURE, dans la litterature comme ici. Le gain le plus documente du domaine
n'est ni le modele ni le nombre de tests : c'est **un test par regle enumeree**
(+38 points de code correct, fausses alertes 33 % -> 0 %). Et les proprietes
ecrites par un modele sont, en moyenne, mieux ecrites que le code qu'elles
testent.

CE QUE FAIT CE MODULE. Il demande a un modele de traduire CHAQUE regle en une
assertion executable, et il accepte trois issues, toutes explicites :

  * la regle devient un test executable (``tests``) ;
  * le modele declare ne pas savoir la traduire, avec sa raison (``aveux``) —
    « aucune regle » vaut mieux qu'une regle fausse ;
  * le test est REFUSE par les garde-fous (``refuses``) : texte dangereux,
    syntaxe invalide, reference a des noms internes, ou test qui ne s'en prend
    pas a l'entree demandee. Un modele est du contenu NON FIABLE : ses tests ne
    sont pas executes parce qu'il les a ecrits, mais parce qu'ils ont passe cette
    porte.

CE QUE CE MODULE NE FAIT PAS. Il ne juge pas les candidats, il ne decide de rien.
Il rend un :class:`Temoignage` ; le moteur s'en sert pour PROUVER, et la regle
d'honnetete qui l'accompagne est dans le moteur : un temoin qui echoue sur TOUS
les candidats ne prouve rien (il discrimine mal, ou il est faux) et ne peut donc
jamais, a lui seul, faire rejeter un candidat.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..core.types import Rule, RuleKind, Spec
from ..providers.base import Message, Provider

#: Au-dela, la traduction coute plus qu'elle ne rapporte : on borne.
MAX_TESTS = 8

#: Un test plus long que cela n'est pas un test, c'est un programme.
MAX_LONGUEUR = 600

#: Fragments interdits dans un test. Ce n'est pas une liste de confort : un test
#: ecrit par un modele est du contenu non fiable, execute dans le bac a sable.
#: Il n'a besoin que de l'entree publique et d'assertions — rien d'autre.
INTERDITS: tuple[tuple[str, str], ...] = (
    ("import", "un test n'importe rien : seules l'entree publique et les types de base"),
    ("__", "acces a des attributs internes (dunder)"),
    ("open(", "acces au systeme de fichiers"),
    ("exec(", "execution dynamique"),
    ("eval(", "execution dynamique"),
    ("compile(", "execution dynamique"),
    ("os.", "acces au systeme"),
    ("sys.", "acces au processus"),
    ("subprocess", "lancement de processus"),
    ("socket", "acces reseau"),
    ("urllib", "acces reseau"),
    ("requests", "acces reseau"),
    ("input(", "attente d'une saisie : le bac a sable n'a pas de clavier"),
    ("globals", "acces a l'espace de noms global"),
    ("setattr", "reecriture de l'objet teste"),
    ("delattr", "reecriture de l'objet teste"),
    ("importlib", "chargement dynamique"),
    ("while True", "boucle infinie"),
    ("pytest", "un test autonome, sans cadre de test"),
    ("unittest", "un test autonome, sans cadre de test"),
)

SYSTEME = (
    "You turn enumerated RULES into executable checks. Output ONLY a JSON object.\n"
    'For each rule id, either a string: {"R-001": "assert ..."}\n'
    'or an explicit refusal: {"R-002": {"impossible": "why it cannot be tested"}}.\n'
    "\n"
    "STRICT CONSTRAINTS — a check that violates one of these is discarded:\n"
    "  * the check runs in the namespace of the code under test: the entrypoint\n"
    "    is already defined at module level. Call it directly; import NOTHING.\n"
    "  * use only the public entrypoint and its documented arguments.\n"
    "  * the check must be a single assertion (or a raise) that FAILS when the\n"
    "    rule is violated and PASSES otherwise. Use a message with the observed\n"
    "    value: assert f(x) == y, f'rule R-001: {f(x)} != {y}'.\n"
    "  * never touch files, network, environment, time or randomness.\n"
    "\n"
    "A rule you cannot translate must be declared impossible WITH its reason:\n"
    "a missing rule is better than a wrong rule, and an honest refusal is better\n"
    "than a check that does not test what it claims."
)


@dataclass(frozen=True)
class Temoignage:
    """Ce qu'un modele a su (et n'a pas su) traduire d'une specification."""

    tests: Mapping[str, str] = field(default_factory=dict)     # rule_id -> assertion
    aveux: Mapping[str, str] = field(default_factory=dict)     # rule_id -> raison
    refuses: Mapping[str, str] = field(default_factory=dict)   # rule_id -> motif du refus
    motif: str = ""                                            # echec global eventuel
    appels: int = 0
    modele: str = ""

    @property
    def utilisable(self) -> bool:
        return bool(self.tests)

    @property
    def couverture(self) -> float:
        total = len(self.tests) + len(self.aveux) + len(self.refuses)
        return len(self.tests) / total if total else 0.0

    def resume(self) -> str:
        if self.motif:
            return f"traduction des regles en temoins impossible : {self.motif}"
        return (
            f"{len(self.tests)} regle(s) traduite(s) en temoin executable, "
            f"{len(self.aveux)} declaree(s) non verifiable(s), "
            f"{len(self.refuses)} test(s) refuse(s) par les garde-fous"
        )


def _prompt_utilisateur(spec: Spec, entrypoint: str, objectif: str, regles: Sequence[Rule]) -> str:
    liste = "\n".join(f"- [{r.id}] ({r.kind.value}) {r.statement}" for r in regles)
    negatif = "\n".join(
        f"- [{r.id}] entree qui DOIT echouer : {r.negative_case}"
        for r in regles if r.negative_case
    )
    return (
        f"TASK:\n{objectif or spec.mission}\n\n"
        f"ENTRYPOINT under test: `{entrypoint or '(a single public function)'}`\n\n"
        f"RULES to turn into executable checks:\n{liste}\n"
        + (f"\nNEGATIVE CASES (the entrypoint must reject them):\n{negatif}\n" if negatif else "")
        + "\nReturn the JSON object now."
    )


def _extraire_json(texte: str) -> dict[str, object] | None:
    """Extrait le premier objet JSON utile, meme entoure de texte ou de balises."""
    t = (texte or "").strip()
    if "```" in t:
        blocs = re.findall(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
        if blocs:
            t = blocs[0].strip()
    debut, fin = t.find("{"), t.rfind("}")
    if debut < 0 or fin <= debut:
        return None
    try:
        data = json.loads(t[debut : fin + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _valeur_brute(valeur: object) -> tuple[str, str]:
    """Rend (test, refus) : une seule des deux est non vide."""
    if isinstance(valeur, str):
        return valeur.strip(), ""
    if isinstance(valeur, dict):
        for cle in ("impossible", "impossible_reason", "reason", "why"):
            raison = valeur.get(cle)
            if isinstance(raison, str) and raison.strip():
                return "", raison.strip()
        test = valeur.get("test") or valeur.get("check") or valeur.get("assert")
        if isinstance(test, str) and test.strip():
            return test.strip(), ""
    return "", "entree de traduction illisible (ni test, ni refus motive)"


def valider_test(test: str, *, entrypoint: str) -> tuple[bool, str]:
    """Porte de securite : un test ecrit par un modele entre ou est refuse, et on dit pourquoi.

    Elle est volontairement stricte. Le cout d'un refus est un temoin manquant,
    explicite et compte ; le cout d'un faux positif accepte est une accusation
    fausse, c'est-a-dire exactement ce que tout ce projet refuse.
    """
    if not test.strip():
        return False, "test vide"
    if len(test) > MAX_LONGUEUR:
        return False, f"test trop long ({len(test)} > {MAX_LONGUEUR} caracteres)"
    if not re.search(r"\bassert\b|\braise\b", test):
        return False, "aucune assertion : le test ne peut pas echouer"
    bas = test.lower()
    for fragment, raison in INTERDITS:
        if fragment.lower() in bas:
            return False, f"fragment interdit {fragment!r} ({raison})"
    try:
        ast.parse(test, mode="exec")
    except SyntaxError as exc:
        return False, f"syntaxe invalide : {exc.msg}"
    # Un test qui n'appelle pas l'entree publique ne teste pas l'artefact livre :
    # il teste autre chose, ou rien.
    if entrypoint and not re.search(rf"\b{re.escape(entrypoint)}\b", test):
        return False, f"le test n'appelle jamais l'entree {entrypoint!r}"
    return True, ""


def traduire(
    spec: Spec,
    provider: Provider | None,
    *,
    entrypoint: str,
    objectif: str = "",
    seed: int | None = None,
    max_tests: int = MAX_TESTS,
) -> Temoignage:
    """Traduit les regles d'une specification en temoins executables.

    Les regles ADVISORY sont ecartees : leur echec ne prouve rien, et une regle
    de suspicion ne doit pas devenir un verrou par un detour de traduction.
    """
    regles = [r for r in spec.rules if r.kind is not RuleKind.ADVISORY][:max_tests]
    if not regles:
        return Temoignage(motif="la specification ne contient aucune regle traduisible")
    if provider is None:
        return Temoignage(motif="aucun modele disponible pour traduire les regles")

    try:
        completion = provider.complete(
            [
                Message("system", SYSTEME),
                Message("user", _prompt_utilisateur(spec, entrypoint, objectif, regles)),
            ],
            temperature=0.0,
            max_tokens=2048,
            seed=seed,
        )
    except Exception as exc:  # noqa: BLE001 — une traduction qui echoue est un aveu, pas un plantage
        return Temoignage(motif=f"appel de traduction en echec : {exc}")

    data = _extraire_json(getattr(completion, "text", "") or "")
    if data is None:
        return Temoignage(
            motif="le modele n'a pas rendu d'objet JSON exploitable",
            appels=1,
            modele=str(getattr(completion, "model", "") or ""),
        )

    tests: dict[str, str] = {}
    aveux: dict[str, str] = {}
    refuses: dict[str, str] = {}
    connues = {r.id for r in regles}
    for brut, valeur in data.items():
        rid = str(brut).strip().strip("[]").strip()
        if rid not in connues:
            # Une regle inventee n'est pas un temoin : le modele n'en est pas l'autorite.
            refuses[rid] = "regle inconnue de la specification"
            continue
        test, refus = _valeur_brute(valeur)
        if refus:
            aveux[rid] = refus
            continue
        ok, motif = valider_test(test, entrypoint=entrypoint)
        if ok:
            tests[rid] = test
        else:
            refuses[rid] = f"{motif} — test : {test[:120]}"

    manquantes = [r.id for r in regles if r.id not in tests and r.id not in aveux and r.id not in refuses]
    for rid in manquantes:
        aveux[rid] = "aucune reponse du modele pour cette regle"

    return Temoignage(
        tests=tests,
        aveux=aveux,
        refuses=refuses,
        appels=1,
        modele=str(getattr(completion, "model", "") or ""),
    )
