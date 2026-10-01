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

UNE RELANCE, ET UNE SEULE, quand la reponse n'etait pas exploitable — jamais sur un aveu.
La mesure qui a motive cette branche : sans oracle, un modele qui ecrit du code correct mais
rend de la prose faisait livrer 0 % la ou un tirage aveugle du meme budget reussissait 100 %.
Le harness etait donc PIRE que le modele seul, sur le seul cas qui existe en vrai. Dire au
modele ce qui a ete refuse corrige ce resultat pour un appel de plus — et insister apres un
aveu, a l'inverse, fabriquerait un faux temoin, donc ne se fait pas.

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
from dataclasses import dataclass, field, replace
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


#: Prompt de CONTROLE : le temoin doit venir avec de quoi le METTRE EN DEFAUT.
#:
#: POURQUOI, et c'est la reponse a une mesure : avec des traductions imparfaites (le regime
#: reel d'une mission sans oracle), un temoin faux fait echouer TOUS les candidats — y compris
#: les bons — et le harness n'a rien a livrer. Mesure : 15 missions sur 15 en abstention a
#: 60 % de fidelite de traduction. Le moteur re-demandait des CANDIDATS quand la preuve
#: echouait ; il ne re-demandait jamais l'INSTRUMENT.
#:
#: La correction ne demande AUCUNE confiance supplementaire, et c'est ce qui la rend utilisable :
#: le modele doit fournir, avec son test, une implementation CORRECTE de reference et une
#: implementation FAUSSE. Le harness execute alors les deux et exige : le test PASSE sur la
#: reference, le test ECHOUE sur la contrefacon. Un test qui passe sur les deux ne prouve rien ;
#: un test qui echoue sur sa propre reference se contredit. Les deux cas sont refuses
#: mecaniquement, sans croire le modele sur parole — et un instrument refuse est redemande une
#: fois, en lui disant exactement pourquoi.
SYSTEME_CONTROLE = (
    "You turn enumerated RULES into executable checks, and each check must come with the\n"
    "PROOF THAT IT CAN FAIL. Output ONLY a JSON object. For each rule id, either:\n"
    '  {"test": "assert ...", "reference": "<python defining the entrypoint>",\n'
    '   "contrefacon": "<same entrypoint, WRONG on purpose>"}\n'
    'or an explicit refusal: {"impossible": "why it cannot be tested"}.\n'
    "\n"
    "The three parts are EXECUTED before anything else:\n"
    "  * `test` must PASS on `reference` — otherwise it contradicts its own reference;\n"
    "  * `test` must FAIL on `contrefacon` — otherwise it proves nothing at all.\n"
    'A pair that fails either check is discarded. Keep `reference` MINIMAL (the entrypoint\n'
    "and nothing else) and make `contrefacon` differ in the way the rule talks about.\n"
    "\n"
    "Same constraints as always: no imports in `test`, no files, no network, no time, no\n"
    "randomness, and a single assertion with the observed value in the message.\n"
    "A rule you cannot translate must be declared impossible WITH its reason."
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
    #: Vrai quand il a fallu DEUX appels : le rapport doit pouvoir le dire, parce que
    #: deux appels ne sont pas le meme budget qu'un seul.
    relance: bool = False
    #: Regles dont le temoin a ete VALIDE par execution : le test passe sur la reference
    #: fournie avec lui et echoue sur sa contrefacon. Un temoin valide est un instrument qui
    #: peut echouer — ce qui est exactement ce qu'un temoin doit etre.
    valides: frozenset[str] = frozenset()
    #: Regles dont le temoin a ete ACCEPTE sans etre mis a l'epreuve : le modele a rendu un
    #: test seul, executable et conforme a la porte statique, mais sans la reference et la
    #: contrefacon qui prouveraient qu'il peut echouer. Ce temoin JUGE (il vaut mieux qu'aucune
    #: preuve) mais la regle n'est pas declaree prouvee : le rapport nomme la difference.
    non_eprouves: frozenset[str] = frozenset()
    #: Regles dont le temoin s'est CONTREDIT (test refuse sur sa propre reference, ou passant
    #: sur sa contrefacon) : motif lisible, pour que la relance puisse dire quoi corriger.
    incoherents: Mapping[str, str] = field(default_factory=dict)
    #: Regles dont l'instrument a ete REPARE : la premiere reponse se contredisait, la seconde
    #: a passe les deux executions. C'est un fait de la mesure, pas un detail — l'instrument
    #: livre n'est pas celui du premier essai.
    reparations: frozenset[str] = frozenset()

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


def _candidats_json(texte: str) -> list[object]:
    """Toutes les lectures plausibles d'une reponse de modele, dans l'ordre d'essai.

    Un modele reel ne rend pas toujours la forme demandee, et le format le plus
    probable n'est pas un objet mais un TABLEAU — c'est celui que le compilateur de
    specification demande juste a cote, donc un modele qui a vu
    ``[{"id": "R-001", ...}]`` repond volontiers la meme chose. On rend donc TOUS
    les candidats, et c'est l'appelant qui choisit celui qui parle des regles de la
    specification : la porte de securite juge le TEST, pas l'emballage.

    Ecrire cette fonction a d'ailleurs corrige un bug reel : chercher d'abord
    ``{...}`` dans un tableau trouve l'OBJET IMBRIQUE, pas le tableau, donc toutes
    les reponses en tableau etaient jetees en silence.
    """
    t = (texte or "").strip()
    if "```" in t:
        blocs = re.findall(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
        if blocs:
            t = blocs[0].strip()
    out: list[object] = []
    premier = t[:1]
    spans = [(t.find("{"), t.rfind("}")), (t.find("["), t.rfind("]"))]
    if premier == "[":
        spans.reverse()
    for debut, fin in spans:
        if debut < 0 or fin <= debut:
            continue
        try:
            data = json.loads(t[debut : fin + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(data, (dict, list)) and data:
            out.append(data)
    # Dernier recours : un objet JSON par ligne (une CLI qui diffuse ses evenements).
    fusion: dict[str, object] = {}
    for ligne in t.splitlines():
        ligne = ligne.strip().rstrip(",")
        if not ligne.startswith("{") or not ligne.endswith("}"):
            continue
        try:
            objet = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if isinstance(objet, dict):
            fusion.update(objet)
    if fusion and fusion not in out:
        out.append(fusion)
    return out


def _extraire_json(texte: str) -> object | None:
    """Premier candidat exploitable — conserve pour les appelants simples."""
    candidats = _candidats_json(texte)
    return candidats[0] if candidats else None


#: Cles sous lesquelles un modele peut bien nommer l'identifiant d'une regle.
_CLES_ID = ("id", "rule", "rule_id", "rule-id", "regle", "regle_id")
#: ... et le test lui-meme.
_CLES_TEST = ("test", "check", "assert", "assertion", "code", "source", "body")
#: ... et un refus motive.
_CLES_REFUS = ("impossible", "impossible_reason", "reason", "raison", "why", "motif")


def _normaliser(data: object) -> dict[str, object] | None:
    """Ramene la reponse d'un modele a ``{rule_id: test ou refus}``, ou rend None."""
    if isinstance(data, list):
        out: dict[str, object] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            rid = next((str(item[c]).strip() for c in _CLES_ID if item.get(c)), "")
            if not rid:
                continue
            refus = next((item[c] for c in _CLES_REFUS
                          if isinstance(item.get(c), str) and item.get(c).strip()), None)
            if refus is not None:
                out[rid] = {"impossible": str(refus)}
                continue
            test = next((item[c] for c in _CLES_TEST
                         if isinstance(item.get(c), str) and item.get(c).strip()), None)
            out[rid] = test if test is not None else {"impossible": "aucun test fourni"}
        return out or None
    if isinstance(data, dict):
        # Forme enveloppee : {"rules": {...}} ou {"tests": [...]}
        for cle in ("rules", "tests", "checks", "resultat", "result"):
            if len(data) == 1 and isinstance(data.get(cle), (dict, list)):
                return _normaliser(data[cle])
        return data
    return None


#: Fragments interdits dans une IMPLEMENTATION fournie comme reference ou contrefacon.
#: Plus courte que celle des tests, et pour une raison : une implementation correcte a le
#: DROIT d'importer `re` ou `math` (les solutions du banc le font). Ce qui reste interdit est
#: ce qui sortirait du bac a sable : fichiers, reseau, processus, execution dynamique.
INTERDITS_IMPLEMENTATION: tuple[tuple[str, str], ...] = (
    ("open(", "acces au systeme de fichiers"),
    ("exec(", "execution dynamique"),
    ("eval(", "execution dynamique"),
    ("compile(", "execution dynamique"),
    ("subprocess", "lancement de processus"),
    ("socket", "acces reseau"),
    ("urllib", "acces reseau"),
    ("requests", "acces reseau"),
    ("input(", "attente d'une saisie"),
    ("while True", "boucle infinie"),
    ("__import__", "chargement dynamique"),
    ("importlib", "chargement dynamique"),
    ("os.system", "acces au systeme"),
)


def valider_implementation(code: str, *, entrypoint: str) -> tuple[bool, str]:
    """Une implementation fournie est-elle exploitable par le bac a sable ?"""
    texte = (code or "").strip()
    if not texte:
        return False, "implementation absente"
    if entrypoint and f"def {entrypoint}" not in texte:
        return False, f"l'implementation ne definit pas `{entrypoint}`"
    for fragment, motif in INTERDITS_IMPLEMENTATION:
        if fragment in texte:
            return False, f"fragment interdit ({fragment}) : {motif}"
    try:
        ast.parse(texte)
    except SyntaxError as exc:
        return False, f"l'implementation ne compile pas : {exc.msg}"
    return True, ""


def valider_triplet(
    sandbox: object,
    *,
    test: str,
    reference: str,
    contrefacon: str,
    entrypoint: str,
) -> tuple[bool, str]:
    """LE coeur de l'instrument auto-valide : deux executions, aucune confiance.

    Un temoin ne vaut rien s'il ne peut pas echouer. On l'EXECUTE donc deux fois, avant de
    l'utiliser pour juger quoi que ce soit :

      * sur l'implementation de reference fournie AVEC lui : il doit PASSER ;
      * sur la contrefacon fournie avec lui : il doit ECHOUER.

    Ce que chaque echec veut dire, et c'est tout l'interet :

      * il echoue sur sa propre reference  -> l'instrument se CONTREDIT (le modele a ecrit une
        assertion qui contredit l'implementation correcte qu'il donne lui-meme) ;
      * il passe sur la contrefacon       -> l'instrument ne prouve RIEN (il ne distingue pas
        une implementation fausse de la bonne) ;
      * un couple reference/contrefacon identique -> il n'y a rien a distinguer.

    Le tout est verifie par le bac a sable deja utilise pour les artefacts : meme confinement,
    meme delai, aucun reseau.
    """
    ok, motif = valider_test(test, entrypoint=entrypoint)
    if not ok:
        return False, motif
    for role, code in (("reference", reference), ("contrefacon", contrefacon)):
        ok, motif = valider_implementation(code, entrypoint=entrypoint)
        if not ok:
            return False, f"{role} : {motif}"
    if reference.strip() == contrefacon.strip():
        return False, "reference et contrefacon sont identiques : rien a distinguer"

    sur_reference = sandbox.run_python(f"{reference}\n{test}\n", tag="triplet-reference")
    if sur_reference.exit_code != 0:
        detail = _derniere_ligne(sur_reference.stderr) or _derniere_ligne(sur_reference.stdout)
        return False, (
            "le test ECHOUE sur l'implementation de reference fournie avec lui "
            f"(l'instrument se contredit : {detail[:120]})"
        )
    sur_contrefacon = sandbox.run_python(f"{contrefacon}\n{test}\n", tag="triplet-contrefacon")
    if sur_contrefacon.exit_code == 0:
        return False, (
            "le test PASSE sur la contrefacon fournie avec lui : il ne distingue pas une "
            "implementation fausse de la bonne, donc il ne prouve rien"
        )
    return True, ""


def _derniere_ligne(texte: str) -> str:
    for ligne in reversed((texte or "").splitlines()):
        if ligne.strip():
            return ligne.strip()
    return ""


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


def _triplet(valeur: object) -> tuple[str, str, str, str]:
    """Rend (test, reference, contrefacon, refus) depuis une entree de traduction.

    Les formes acceptees, dans l'ordre de tolerance : le triplet complet, le couple
    test+reference sans contrefacon (refuse plus loin, avec la raison), la chaine simple
    (l'ancien format — un temoin n'est alors PAS valide, et le rapport le dit).
    """
    if isinstance(valeur, dict):
        test = valeur.get("test") or valeur.get("check") or valeur.get("assert")
        ref = valeur.get("reference") or valeur.get("correct") or valeur.get("reference_ok")
        faux = (
            valeur.get("contrefacon") or valeur.get("contrefaçon")
            or valeur.get("wrong") or valeur.get("faux") or valeur.get("mutation")
        )
        if isinstance(test, str) and test.strip():
            return (
                test.strip(),
                ref.strip() if isinstance(ref, str) else "",
                faux.strip() if isinstance(faux, str) else "",
                "",
            )
    test, refus = _valeur_brute(valeur)
    return test, "", "", refus


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


def _rappel(motifs: Sequence[str], motif_global: str) -> str:
    """Ce qu'on renvoie au modele apres une reponse inexploitable.

    Une relance qui ne dit PAS pourquoi la reponse a ete rejetee n'est pas une relance :
    c'est un deuxieme tirage aveugle, et il ne change rien. Ce qui fait gagner des dizaines
    de points a un meme modele, dans toute la litterature du domaine, c'est le FORMAT —
    pas le nombre d'essais. On rend donc les motifs de rejet, bornes et sur une seule
    ligne (un motif multiligne casserait la structure du message).
    """
    lignes = [
        "SYSTEM NOTE: your previous answer was REJECTED by the security gate."
        if not motif_global else
        f"SYSTEM NOTE: your previous answer was unusable ({motif_global})."
    ]
    for m in list(motifs)[:3]:
        lignes.append(f"- {_une_ligne(m)[:200]}")
    lignes.append(
        "Return ONLY a JSON object: {\"R-XXX\": \"assert ...\"} for every rule, or "
        "{\"R-XXX\": {\"impossible\": \"why\"}} if the rule genuinely cannot be tested. "
        "No prose, no markdown, no explanation."
    )
    return "\n".join(lignes)


def _une_ligne(texte: str) -> str:
    return " ".join(str(texte).split())


def _tentative(
    spec: Spec,
    provider: Provider,
    *,
    entrypoint: str,
    objectif: str,
    regles: Sequence[Rule],
    seed: int | None,
    rappel: str = "",
    controle: bool = False,
    sandbox: object | None = None,
) -> Temoignage:
    """UNE tentative de traduction, avec sa porte de securite. Aucune relance ici.

    En mode CONTROLE, chaque temoin doit venir avec sa reference et sa contrefacon, et les deux
    sont EXECUTEES avant que le temoin serve a quoi que ce soit. Un temoin qui se contredit ne
    juge personne : il est refuse, avec le motif exact qui servira a le redemander.
    """
    utilisateur = _prompt_utilisateur(spec, entrypoint, objectif, regles)
    if rappel:
        utilisateur = f"{utilisateur}\n\n{rappel}"
    try:
        completion = provider.complete(
            [Message("system", SYSTEME_CONTROLE if controle else SYSTEME),
             Message("user", utilisateur)],
            temperature=0.0,
            max_tokens=2048,
            seed=seed,
        )
    except Exception as exc:  # noqa: BLE001 — une traduction qui echoue est un aveu, pas un plantage
        return Temoignage(motif=f"appel de traduction en echec : {exc}")

    connues_vrac = {r.id for r in regles}
    candidats = _candidats_json(getattr(completion, "text", "") or "")
    data: dict[str, object] | None = None
    for candidat in candidats:
        normalise = _normaliser(candidat)
        if normalise and set(normalise) & connues_vrac:
            # Celui-ci PARLE des regles de la specification : c'est le bon.
            data = normalise
            break
    if data is None:
        data = next((n for n in (_normaliser(c) for c in candidats) if n), None)
    if data is None:
        return Temoignage(
            motif="le modele n'a pas rendu de reponse JSON exploitable",
            appels=1,
            modele=str(getattr(completion, "model", "") or ""),
        )

    tests: dict[str, str] = {}
    aveux: dict[str, str] = {}
    refuses: dict[str, str] = {}
    valides: set[str] = set()
    #: Temoins acceptes SANS avoir ete mis a l'epreuve (l'ancien format, un test seul). Ils
    #: restent utilisables — un test executable vaut mieux que pas de preuve — mais la regle
    #: qu'ils jugent n'est PAS declaree prouvee, et le rapport le dit.
    non_eprouves: set[str] = set()
    incoherents: dict[str, str] = {}
    connues = {r.id for r in regles}
    for brut, valeur in data.items():
        rid = str(brut).strip().strip("[]").strip()
        if rid not in connues:
            # Une regle inventee n'est pas un temoin : le modele n'en est pas l'autorite.
            refuses[rid] = "regle inconnue de la specification"
            continue
        # DEUX CHEMINS, DEUX FORMES — et surtout pas un tuple construit a la volee : la
        # version qui empilait `(*_valeur_brute(valeur), "", "")` mettait le REFUS dans
        # `reference` et laissait `refus` vide. Tout devenait « test vide », y compris les
        # aveux honnetes, et le moteur relancait ce qu'il aurait du lire du premier coup.
        if controle:
            test, reference, contrefacon, refus = _triplet(valeur)
        else:
            test, refus = _valeur_brute(valeur)
            reference, contrefacon = "", ""
        if refus:
            aveux[rid] = refus
            continue
        if controle:
            if not reference or not contrefacon:
                # L'ANCIEN FORMAT, et il ne doit pas bloquer la mission. Un modele qui rend un
                # test seul ne se contredit pas : il n'a pas fourni de quoi le mettre a
                # l'epreuve. Le refuser ferait s'abstenir le moteur sur un simple FORMAT de
                # reponse — c'est precisement le blocage que ce controle existe pour reparer.
                # On le garde donc, on le NOMME `non eprouve`, et on ne le compte jamais parmi
                # les regles prouvees.
                ok, motif = valider_test(test, entrypoint=entrypoint)
                if ok:
                    tests[rid] = test
                    non_eprouves.add(rid)
                else:
                    refuses[rid] = f"{motif} — test : {test[:120]}"
                continue
            if sandbox is None:
                # Sans bac a sable, on ne peut pas PROUVER l'instrument : on refuse plutot
                # que de faire semblant. C'est la doctrine du depot, appliquee au dernier
                # endroit ou elle pourrait etre oubliee.
                refuses[rid] = "aucun bac a sable : l'instrument ne peut pas etre mis a l'epreuve"
                continue
            ok, motif = valider_triplet(
                sandbox, test=test, reference=reference, contrefacon=contrefacon,
                entrypoint=entrypoint,
            )
            if not ok:
                # Le temoin se contredit : il n'entre PAS dans `tests` (il ne jugera aucun
                # candidat), et il n'est pas un aveu non plus — le modele n'a pas dit qu'il
                # ne savait pas, il a rendu un instrument faux. Le motif part tel quel dans
                # la relance, sinon le second essai repetterait la meme erreur.
                incoherents[rid] = motif
                continue
            tests[rid] = test
            valides.add(rid)
            continue
        ok, motif = valider_test(test, entrypoint=entrypoint)
        if ok:
            tests[rid] = test
        else:
            refuses[rid] = f"{motif} — test : {test[:120]}"

    manquantes = [r.id for r in regles if r.id not in tests and r.id not in aveux
                  and r.id not in refuses and r.id not in incoherents]
    for rid in manquantes:
        aveux[rid] = "aucune reponse du modele pour cette regle"

    return Temoignage(
        tests=tests,
        aveux=aveux,
        refuses=refuses,
        appels=1,
        modele=str(getattr(completion, "model", "") or ""),
        valides=frozenset(valides),
        non_eprouves=frozenset(non_eprouves),
        incoherents=dict(incoherents),
    )


def traduire(
    spec: Spec,
    provider: Provider | None,
    *,
    entrypoint: str,
    objectif: str = "",
    seed: int | None = None,
    max_tests: int = MAX_TESTS,
    controle: bool = False,
    sandbox: object | None = None,
) -> Temoignage:
    """Traduit les regles d'une specification en temoins executables.

    Les regles ADVISORY sont ecartees : leur echec ne prouve rien, et une regle
    de suspicion ne doit pas devenir un verrou par un detour de traduction.

    UNE RELANCE, ET UNE SEULE — quand la reponse n'etait pas exploitable ET que le modele
    n'a rien avoue. Mesure a l'origine de cette branche : sans oracle, un modele qui ecrit
    du code correct mais rend de la prose au prompt de traduction faisait tomber le harness
    a ZERO la ou un tirage aveugle du meme budget reussissait : le harness etait PIRE que
    le modele seul, sur le seul cas qui existe en vrai. Une seconde tentative qui dit
    POURQUOI la premiere a ete refusee coute un appel et change ce resultat.

    JAMAIS de relance sur un aveu. Un modele qui a declare une regle non testable a
    repondu ; insister pour obtenir une assertion, c'est fabriquer un faux temoin — et
    c'est exactement ainsi qu'un harness transforme une abstention honnete en mensonge
    verifie. Meme raison pour les refus de la porte : ils portent deja sur une reponse
    RENDUE, et le modele a eu sa chance.
    """
    regles = [r for r in spec.rules if r.kind is not RuleKind.ADVISORY][:max_tests]
    if not regles:
        return Temoignage(motif="la specification ne contient aucune regle traduisible")
    if provider is None:
        return Temoignage(motif="aucun modele disponible pour traduire les regles")

    temoignage = _tentative(
        spec, provider, entrypoint=entrypoint, objectif=objectif, regles=regles, seed=seed,
        controle=controle, sandbox=sandbox,
    )
    if controle and temoignage.incoherents:
        # LA REPARATION DE L'INSTRUMENT. Mesure a l'origine : quand les temoins sont
        # imparfaits (le regime reel d'une mission sans oracle), un instrument qui se
        # contredit fait echouer TOUS les candidats — et le harness n'avait rien a livrer :
        # 15 missions sur 15 en abstention. Le moteur re-demandait des candidats ; il ne
        # re-demandait jamais l'instrument.
        #
        # Une seule passe, pour les seules regles concernees, avec le motif EXACT de chaque
        # refus. Le cout est borne et compte (deux appels ne sont pas un appel) ; le fait est
        # journalise (`reparations`), parce qu'un instrument repare n'est pas l'instrument du
        # premier essai et qu'un rapport doit pouvoir le dire.
        temoignage = _reparer(
            spec, provider, entrypoint=entrypoint, objectif=objectif, regles=regles,
            seed=seed, premier=temoignage, sandbox=sandbox,
        )
    if temoignage.tests or temoignage.aveux or temoignage.incoherents:
        return temoignage

    temoignage = _relancer(
        spec, provider, entrypoint=entrypoint, objectif=objectif, regles=regles,
        seed=seed, premier=temoignage, controle=controle, sandbox=sandbox,
    )
    return temoignage


def _rappel_incoherence(premier: Temoignage, regles: Sequence[Rule]) -> str:
    """Dit au modele ce qui a ete refuse, et POURQUOI — le meme fait, sans interpretation.

    La raison est celle rendue par l'EXECUTION (`le test ECHOUE sur l'implementation de
    reference fournie avec lui`), jamais un jugement de style : c'est ce qui rend la seconde
    tentative capable de corriger, au lieu de retirer au hasard.
    """
    lignes = [
        f"- [{rid}] votre essai a ete REJETE : {motif}"
        for rid, motif in sorted(premier.incoherents.items())
    ]
    ids = ", ".join(sorted(premier.incoherents))
    return (
        "YOUR PREVIOUS ATTEMPT WAS REJECTED BY EXECUTION:\n"
        + "\n".join(lignes)
        + "\n\nRewrite ONLY these rules: " + ids + ".\n"
        "A check that fails on the reference you wrote yourself, or that passes on your own\n"
        "wrong implementation, is refused before it is ever used. Make the pair COHERENT:\n"
        "the reference must satisfy the rule, the contrefacon must violate it, and the test\n"
        "must tell them apart."
    )


def _reparer(
    spec: Spec,
    provider: Provider,
    *,
    entrypoint: str,
    objectif: str,
    regles: Sequence[Rule],
    seed: int | None,
    premier: Temoignage,
    sandbox: object | None,
) -> Temoignage:
    """Redemande UNIQUEMENT les instruments refuses, avec leur motif de refus."""
    a_refaire = [r for r in regles if r.id in premier.incoherents]
    if not a_refaire:
        return premier
    seconde = _tentative(
        spec, provider, entrypoint=entrypoint, objectif=objectif, regles=a_refaire,
        seed=None if seed is None else seed + 1,
        rappel=_rappel_incoherence(premier, a_refaire),
        controle=True, sandbox=sandbox,
    )
    tests = dict(premier.tests)
    tests.update(seconde.tests)
    incoherents = dict(premier.incoherents)
    reparations: set[str] = set()
    for rid in seconde.tests:
        if rid in incoherents:
            incoherents.pop(rid, None)
            reparations.add(rid)
    for rid, motif in seconde.incoherents.items():
        incoherents[rid] = motif
    aveux = dict(premier.aveux)
    aveux.update(seconde.aveux)
    refuses = dict(premier.refuses)
    refuses.update(seconde.refuses)
    return Temoignage(
        tests=tests,
        aveux=aveux,
        refuses=refuses,
        motif=premier.motif,
        appels=premier.appels + seconde.appels,
        modele=seconde.modele or premier.modele,
        relance=True,
        valides=frozenset(premier.valides | seconde.valides),
        non_eprouves=frozenset(premier.non_eprouves | seconde.non_eprouves),
        incoherents=incoherents,
        reparations=frozenset(reparations),
    )


def _relancer(
    spec: Spec,
    provider: Provider,
    *,
    entrypoint: str,
    objectif: str,
    regles: Sequence[Rule],
    seed: int | None,
    premier: Temoignage,
    controle: bool = False,
    sandbox: object | None = None,
) -> Temoignage:
    """La seconde tentative : elle dit au modele ce qui a ete refuse, et pourquoi.

    `appels` compte les DEUX appels : un rapport qui annoncerait un appel la ou deux ont
    eu lieu fausserait la comparaison a budget egal, qui est la seule qui compte.
    """
    seconde = _tentative(
        spec, provider, entrypoint=entrypoint, objectif=objectif, regles=regles,
        seed=None if seed is None else seed + 1,
        rappel=_rappel(list(premier.refuses.values()), premier.motif),
        # La RELANCE garde le mode : une seconde tentative sans le controle rendrait un temoin
        # non mis a l'epreuve apres avoir refuse le premier pour cette raison precise.
        controle=controle, sandbox=sandbox,
    )
    appels = premier.appels + seconde.appels
    if seconde.tests or seconde.aveux:
        return replace(seconde, appels=appels, relance=True)
    return replace(premier, appels=appels, relance=True)
