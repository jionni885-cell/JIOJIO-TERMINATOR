"""Proprietes derivees du code — l'axe que les exemples ne couvrent jamais.

Pourquoi ce module existe
-------------------------
Jusqu'ici JIO verifiait des **exemples** (les `>>>` de l'auteur, les sondes tirees
des annotations) et la reproductibilite. La litterature 2026 montre que c'est
insuffisant, et de facon mesuree :

* les tests par exemples **surestiment** la correction : 30-32 % des solutions
  generatees ne respectent que partiellement les proprietes attendues et 18-23 %
  echouent franchement (« From Prompts to Properties », ASE 2025) ;
* un agent d'inference de proprietes a trouve de **vrais bugs dans NumPy, SciPy et
  Pandas** (Anthropic, janvier 2026) ;
* combiner tests d'exemples et tests de proprietes porte la detection de 68,75 % a
  **81,25 %** : les deux sont complementaires, pas concurrents ;
* Property-Generated Solver (2025) fait chuter les « Wrong Answer » de 25,3 % a
  10,5 %, et note le point decisif : **ecrire une propriete est plus facile et plus
  fiable que d'ecrire le code correct qu'elle decrit.**

Ce module apporte les proprietes les plus universelles, deduites STATIQUEMENT du
code — aucun modele, aucun appel reseau, deterministe :

* **P-001 non-mutation des arguments** : la fonction ne modifie pas ce qu'on lui
  passe. Attrape la classe de bug la plus banale et la plus vicieuse (`return
  nums.sort()` renvoie `None` ET detruit l'entree de l'appelant).
* **P-002 idempotence** : `f(f(x)) == f(x)` quand le type de retour est celui de
  l'argument — chercher deux fois ne doit pas changer le resultat.
* **P-003 aller-retour** : quand deux fonctions du module forment une paire
  (`encode`/`decode`, `to_x`/`from_x`, `dump`/`load`…), `decode(encode(x)) == x`.
  C'est la propriete qui a trouve des bugs reels dans des bibliotheques majeures.

Ce qui rend un echec exploitable
--------------------------------
Une entree fautive de 5000 elements n'aide personne. Quand un cas echoue, le
temoin est **reduit automatiquement** (plus courte liste, plus petit entier) tant
que l'echec persiste : on livre le plus petit contre-exemple. C'est ce que fait
Hypothesis, et c'est ce qui transforme « quelque chose casse » en « voici le
defaut, trois caracteres ».
"""

from __future__ import annotations

import ast
import random
import re
from dataclasses import dataclass

__all__ = [
    "DerivedProperty",
    "docstring_examples",
    "derive_properties",
    "generate_inputs",
    "MUTABLE_TYPES",
]

#: Types dont une fonction ne devrait pas modifier l'argument. On ne teste que
#: ceux-la : un entier ne peut pas etre mute, le verifier serait du bruit.
MUTABLE_TYPES = frozenset(
    {"list", "dict", "set", "bytearray", "deque", "Counter", "defaultdict", "OrderedDict"}
)

#: Paires de noms qui promettent un aller-retour. Deduites du NOM, jamais devinees :
#: on ne declare pas une propriete qu'on ne peut pas prouver.
_ROUND_TRIP_PAIRS: tuple[tuple[str, str], ...] = (
    ("encode", "decode"),
    ("dump", "load"),
    ("dumps", "loads"),
    ("serialize", "deserialize"),
    ("pack", "unpack"),
    ("compress", "decompress"),
    ("to_bytes", "from_bytes"),
    ("to_json", "from_json"),
    ("to_dict", "from_dict"),
    ("to_str", "from_str"),
    ("to_string", "from_string"),
)

#: Noms qui PROMETTENT une sortie triee. Volontairement restreints a `sort`/`order` :
#: `rank` peut legitimement rendre des RANGS (`rank([3,1,2]) -> [2,0,1]`), qui ne sont
#: pas tries — l'inclure serait un faux positif programme.
_SORT_CLAIMS = ("sort", "sorted", "order")

#: Les MOTS d'un nom, separes sur `_`, les changements de casse et les chiffres. C'est l'unite
#: de comparaison des promesses de nom, et elle remplace la sous-chaine.
#:
#: POURQUOI, mesure faite sur CE depot : `jio scan .` accusait `jio/core/codes.py` d'enfreindre
#: la propriete « tri fidele » (P-004) sur la fonction `sortir` — dont le nom francais veut dire
#: « quitter le programme ». La sous-chaine « sort » y est, la promesse de tri n'y est pas. Un
#: outil qui accuse a tort est desactive au bout de deux jours ; la meme regle vaut pour nos
#: propres regles, et c'est le seul endroit ou l'erreur coute plus cher que l'omission.
_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+")


def _mots(nom: str) -> set[str]:
    """Les segments d'un identifiant : `sort_values` -> {sort, values} ; `sortir` -> {sortir}."""
    return {mot.lower() for mot in _WORDS.findall(nom)}


def _annonce(nom: str, promesses: tuple[str, ...]) -> bool:
    """Le nom promet-il l'une de ces choses — en MOT, jamais en bout de mot francais ?

    `sort` est une promesse quand c'est un mot du nom (`sort_values`, `sorted`, `sort_by_key`,
    `order_lines`) ; ce n'est pas une promesse quand le mot est `sortir`, `sortie`, `sorte` ou
    `triomphe`. Le prefixe `sort_` reste reconnu : c'est la convention de nommage des langages
    de programmation, et `_` est justement ce sur quoi `_mots` separe.
    """
    mots = _mots(nom)
    return any(promesse in mots or promesse in nom.lower().split("_") for promesse in promesses)

#: Noms qui degradent la fidelite (dedoublonnage volontaire) : le multiensemble n'est
#: alors PAS cense etre preserve. `sort_unique(x)` a le droit de rendre moins
#: d'elements que `x`.
_LOSSY_CLAIMS = ("unique", "dedupe", "dedup", "distinct", "nub", "set")

#: Marqueurs d'un tri decroissant.
_SORT_DESCENDING = ("desc", "reverse", "decreasing", "descending")

#: Noms qui PROMETTENT de dedoublonner sans rien perdre.
_DEDUPE_CLAIMS = ("dedupe", "dedup", "unique", "uniq", "distinct", "nub")

#: Noms qui ANNONCENT une modification volontaire de l'argument. Une API « en
#: place » (`sort_in_place`, `fill`, `update`) mute par conception : la declarer
#: fautive serait une fausse alerte sur du code parfaitement correct.
_IN_PLACE_NAMES = (
    "in_place", "inplace", "sort_in", "fill", "update", "set_", "append", "extend",
    "clear", "pop", "push", "insert", "remove", "discard", "add_", "merge_into",
    "apply_", "mutate",
)

_ROUND_TRIP_PREFIXES: tuple[tuple[str, str], ...] = (
    ("to_", "from_"),
    ("pack_", "unpack_"),
    ("encode_", "decode_"),
)


@dataclass(frozen=True)
class DerivedProperty:
    """Une propriete executable, deduite du code lui-meme."""

    id: str
    name: str
    statement: str
    check: str
    kind: str = "property"   # property | advisory


# --------------------------------------------------------------------------- #
# Generation d'entrees
# --------------------------------------------------------------------------- #

_EDGE_INTS = (0, 1, -1, 2, -2, 7, 10, 255, -128, 10**6)
_EDGE_FLOATS = (0.0, 1.0, -1.0, 0.5, -0.5, 1e-9, 1e9)


def _annotation_text(node: ast.expr | None) -> str:
    """Texte de l'annotation, sans les commentaires de type."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


def _elements(inner: str) -> str:
    """Type des elements d'une annotation generique (`list[int]` -> `int`)."""
    head, _, rest = inner.partition("[")
    return rest.rstrip("]") or "int"


def _value_for(kind: str, rng: random.Random, depth: int = 0) -> object:
    """Valeur tiree dans le domaine declare — avec biais systematique sur les bords.

    Le biais est le point important : les cas qui revelent les defauts sont
    presque toujours aux frontieres (vide, zero, un element, doublon, negatif).
    Un tirage uniforme les rate ; c'est exactement pour cela que les tests par
    exemples les ratent aussi.
    """
    flat = kind.replace(" ", "")
    base = flat.split("[", 1)[0]
    if base in {"int", "bool"}:
        return rng.choice(_EDGE_INTS) if base == "int" else rng.choice((True, False))
    if base == "float":
        return rng.choice(_EDGE_FLOATS)
    if base == "str":
        # Le vivier doit contenir des chaines LONGUES : une troncature a 4
        # caracteres ne se voit pas sur des mots de 4 lettres. Defaut constate au
        # banc : `url_encode` qui coupe a 4 etait declare sain parce que toutes les
        # entrees testees faisaient 4 caracteres ou moins.
        return rng.choice(
            (
                "", "a", "ab", "abc", "aa", " ", "0", "test",
                "abcdef", "abcabc", "a" * 16, "0123456789", "  espaces  ",
                "a,b", "a/b", "a b",
            )
        )
    if base in {"list", "tuple", "set", "frozenset", "Sequence", "Iterable", "deque"}:
        if depth >= 2:
            return []
        inner = _elements(flat) if "[" in flat else "int"
        size = rng.choice((0, 1, 1, 2, 3, 5))
        items = [_value_for(inner, rng, depth + 1) for _ in range(size)]
        if base in {"set", "frozenset"}:
            return base if not items else (set(items) if base == "set" else frozenset(items))
        return items if base != "tuple" else tuple(items)
    if base in {"dict", "Mapping", "Counter", "defaultdict", "OrderedDict"}:
        if depth >= 2 or "[" not in flat:
            return {}
        inner = flat.split("[", 1)[1].rstrip("]")
        key_kind, _, value_kind = inner.partition(",")
        size = rng.choice((0, 1, 2))
        return {
            _value_for(key_kind or "str", rng, depth + 1): _value_for(
                value_kind or "int", rng, depth + 1
            )
            for _ in range(size)
        }
    if base in {"Any", "object"}:
        return rng.choice((0, 1, "", [], {}, [0, 1], {"a": 1}))
    return 0


def generate_inputs(
    annotation: str, count: int, seed: int, *, mutable_only: bool = False
) -> list[object] | None:
    """Entrees deterministes pour une annotation. None si le domaine est inconnu.

    Deterministe par construction : meme graine, memes entiers. Une verification
    qu'on ne peut pas rejouer n'est pas une verification.
    """
    base = annotation.replace(" ", "").split("[", 1)[0]
    if not base:
        return None
    if base not in {
        "int", "float", "str", "bool", "list", "tuple", "set", "frozenset", "dict",
        "Sequence", "Iterable", "Mapping", "deque", "Counter", "defaultdict",
        "OrderedDict", "Any", "object",
    }:
        return None
    if mutable_only and base not in MUTABLE_TYPES:
        return None

    rng = random.Random(seed)
    out: list[object] = []
    # Les bords d'abord, explicitement, pour qu'ils soient TOUJOURS presents :
    # ce sont eux qui portent les defauts.
    for edge in (0, 1, 2):
        try:
            out.append(_value_for(annotation, random.Random(edge)))
        except Exception:  # pragma: no cover - domaine exotique
            return None
    while len(out) < count:
        out.append(_value_for(annotation, rng))
    return out[:count]


# --------------------------------------------------------------------------- #
# Gabarits de verification
# --------------------------------------------------------------------------- #

#: Reducteur de contre-exemple. Il s'execute DANS le bac a sable, avec le candidat,
#: parce que seul le bac a sable peut dire si un cas plus petit echoue encore.
_SHRINKER = '''
def _jio_fails(case):
    # Chaque gabarit definit sa propre notion de violation, et gere lui-meme les
    # exceptions : une exception n'est jamais une violation de propriete (le
    # domaine declare ne couvre pas forcement toutes les entrees acceptees).
    return _jio_violated(case)


def _jio_shrink(case):
    """Reduit le contre-exemple tant que le defaut persiste.

    `[0, 1, 2, 3, 4]` n'apprend rien ; `[0, 0]` designe le defaut. C'est la
    difference entre un rapport et une piste.
    """
    best = tuple(case)

    def _reductions(arg):
        """Reductions par ordre de gain : retirer un element, puis reduire sa valeur.

        La troncature seule ne suffit pas : sur `[1, 2, 3, 4, 5, 6, 1, 2, 3]`, couper
        la fin rend la liste TRIEE, donc saine — le reducteur s'arrete trop tot et
        livre un temoin inutile. Retirer element par element atteint `[2, 1]`, qui
        designe le defaut.
        """
        out = []
        if isinstance(arg, (list, tuple)):
            for index in range(len(arg)):
                out.append(arg[:index] + arg[index + 1:])
            if len(arg) > 1:
                out.append(arg[: len(arg) // 2])
                out.append(arg[len(arg) // 2:])
        elif isinstance(arg, str) and arg:
            out.append(arg[: len(arg) // 2])
            out.append(arg[: max(1, len(arg) - 1)])
        return out

    def _value_reductions(arg):
        out = []
        if isinstance(arg, list):
            for index, item in enumerate(arg):
                if isinstance(item, (int, float)) and not isinstance(item, bool) and item != 0:
                    for smaller in (0, 1, -1, item // 2):
                        if smaller != item:
                            cand = list(arg)
                            cand[index] = smaller
                            out.append(cand)
        elif isinstance(arg, (int, float)) and not isinstance(arg, bool) and arg != 0:
            for smaller in (0, 1, -1):
                if smaller != arg:
                    out.append(smaller)
        return out

    for _ in range(12):
        changed = False
        for i, arg in enumerate(best):
            for replacement in _reductions(arg) + _value_reductions(arg):
                cand = list(best)
                cand[i] = replacement
                if _jio_fails(tuple(cand)):
                    best, changed = tuple(cand), True
                    break
        if not changed:
            break
    return best
'''

_NON_MUTATION = (
    '''
import copy as _jio_copy

_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_cases = [{cases}]


def _jio_violated(case):
    # On passe une COPIE du cas, et on compare l'ETAT DE CETTE COPIE avant/apres.
    # Deux exigences distinctes :
    #   * le cas de test reste intact, sinon le contre-exemple rapporte a
    #     l'utilisateur est le residu d'apres mutation (defaut constate : le temoin
    #     livre etait une liste deja triee, donc irreproductible) ;
    #   * la comparaison porte bien sur l'objet reellement passe a la fonction,
    #     sinon la propriete ne mesure plus rien.
    target = _jio_copy.deepcopy(case)
    before = _jio_copy.deepcopy(target)
    try:
        _jio_fn(*target)
    except Exception:
        return False          # une exception n'est pas une mutation
    return before != target


_jio_failed = [c for c in _jio_cases if _jio_violated(tuple(c))]
'''
    + _SHRINKER
    + '''
assert not _jio_failed, (
    "l'argument a ete MODIFIE par {name} : le plus petit contre-exemple est "
    f"{{_jio_shrink(_jio_failed[0])!r}}. Une fonction qui modifie ce qu'on lui passe "
    "surprend l'appelant (et `return liste.sort()` renvoie None en plus de tout casser)."
)
'''
)

_IDEMPOTENCE = (
    '''
import copy as _jio_copy

_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_cases = [{cases}]


def _jio_violated(case):
    try:
        once = _jio_fn(*_jio_copy.deepcopy(case))
    except Exception:
        return False
    try:
        # Le deuxieme appel recoit une copie : si la fonction mute son entree, on
        # ne veut pas mesurer l'effet de cette mutation sur elle-meme.
        twice = _jio_fn(_jio_copy.deepcopy(once))
    except Exception:
        return False          # l'entree rejetee n'est pas une violation
    return once != twice


_jio_failed = [c for c in _jio_cases if _jio_violated(tuple(c))]
'''
    + _SHRINKER
    + '''
assert not _jio_failed, (
    "appliquer {name} deux fois ne donne pas le meme resultat qu'une fois : plus petit "
    f"contre-exemple {{_jio_shrink(_jio_failed[0])!r}}. Une operation idempotente qui ne "
    "l'est pas trahit une accumulation ou une double transformation."
)
'''
)

_SORTED = (
    '''
import copy as _jio_copy

_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_cases = [{cases}]
_jio_ascending = {ascending}
_jio_fidelity = {fidelity}


def _jio_violated(case):
    target = _jio_copy.deepcopy(case)
    try:
        out = _jio_fn(*target)
    except Exception:
        return False          # une exception n'est pas une violation
    try:
        items = list(out)
    except TypeError:
        return False          # la sortie n'est pas une collection : hors de la promesse
    if len(items) < 2:
        return False
    try:
        ordered = all(
            (items[i] <= items[i + 1]) if _jio_ascending else (items[i] >= items[i + 1])
            for i in range(len(items) - 1)
        )
    except TypeError:
        return False          # elements non comparables : hors de la promesse
    if not ordered:
        return True
    if _jio_fidelity:
        source = target[0]
        try:
            if isinstance(source, (list, tuple, set, frozenset)):
                if sorted(map(repr, items)) != sorted(map(repr, source)):
                    return True
        except Exception:
            return False
    return False


_jio_failed = [c for c in _jio_cases if _jio_violated(tuple(c))]
'''
    + _SHRINKER
    + '''
assert not _jio_failed, (
    "{name} ne tient pas la promesse de son nom : plus petit contre-exemple "
    f"{{_jio_shrink(_jio_failed[0])!r}}. Une sortie non triee — ou un element perdu, ou "
    "invente, au passage — est un defaut silencieux : l'appelant ne verifie pas."
)
'''
)

_DEDUPE = (
    '''
import copy as _jio_copy

_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_cases = [{cases}]


def _jio_violated(case):
    target = _jio_copy.deepcopy(case)
    try:
        out = _jio_fn(*target)
    except Exception:
        return False
    try:
        items = list(out)
    except TypeError:
        return False          # la sortie n'est pas une collection : hors promesse
    source = target[0]
    try:
        if not isinstance(source, (list, tuple, set, frozenset)):
            return False
        # Comparaison par repr : deux types differents ne se comparent pas toujours,
        # et une erreur de comparaison ne doit JAMAIS devenir une accusation.
        return sorted(map(repr, items)) != sorted(map(repr, set(source)))
    except Exception:
        return False


_jio_failed = [c for c in _jio_cases if _jio_violated(tuple(c))]
'''
    + _SHRINKER
    + '''
assert not _jio_failed, (
    "{name} perd ou invente des elements : plus petit contre-exemple "
    f"{{_jio_shrink(_jio_failed[0])!r}}. Un dedoublonnage doit retirer les REPETITIONS, "
    "jamais une valeur qui n'apparaissait qu'une seule fois."
)
'''
)

_ROUND_TRIP = (
    '''
import copy as _jio_copy

_jio_fwd = globals().get({forward!r})
_jio_bwd = globals().get({backward!r})
assert callable(_jio_fwd) and callable(_jio_bwd), "paire {forward}/{backward} incomplete"
_jio_cases = [{cases}]


def _jio_violated(case):
    original = _jio_copy.deepcopy(case[0])
    try:
        middle = _jio_fwd(original)
        back = _jio_bwd(_jio_copy.deepcopy(middle))
    except Exception:
        return False          # les domaines ne se recouvrent pas : on ne conclut pas
    return back != original


_jio_failed = [c for c in _jio_cases if _jio_violated(tuple(c))]
'''
    + _SHRINKER
    + '''
assert not _jio_failed, (
    "'{backward}({forward}(x))' ne rend pas x : plus petit contre-exemple "
    f"{{_jio_shrink(_jio_failed[0])!r}}. Un aller-retour qui perd de l'information est "
    "un defaut silencieux : chaque usage croyait pouvoir revenir en arriere."
)
'''
)


# --------------------------------------------------------------------------- #
# Inference statique
# --------------------------------------------------------------------------- #

def _mutable_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """(index, annotation) des parametres mutables declares."""
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    names = [a.arg for a in positional]
    if names and names[0] in {"self", "cls"}:
        return []
    out: list[tuple[int, str]] = []
    for index, arg in enumerate(positional):
        text = _annotation_text(arg.annotation)
        base = text.replace(" ", "").split("[", 1)[0]
        if base in MUTABLE_TYPES:
            out.append((index, text))
    for arg in args.kwonlyargs:
        text = _annotation_text(arg.annotation)
        if text.replace(" ", "").split("[", 1)[0] in MUTABLE_TYPES:
            out.append((-1, text))   # nomme : index inconnu dans un appel positionnel
    return out


#: Noms qui PROMETTENT l'idempotence : appliquer deux fois donne le meme resultat.
#: Liste volontairement courte et justifiee — chaque entree est une affirmation de
#: l'auteur du code, pas une supposition de notre part.
_IDEMPOTENT_NAMES = (
    "normalize", "normalise", "normalize_", "sanitize", "sanitise", "clean", "cleanup",
    "canonical", "canonicalize", "dedupe", "unique", "uniq", "flatten", "strip",
    "clip", "clamp", "round", "quantize", "simplify", "compact", "squeeze", "dedup",
)

#: Mots de la docstring qui affirment la meme chose.
_IDEMPOTENT_WORDS = ("idempotent", "idempotente", "normalis", "canoniqu", "sans effet si repete")


def _claims_idempotence(node: ast.FunctionDef) -> bool:
    """L'auteur a-t-il affirme l'idempotence ? Nom, ou docstring.

    Sans cette evidence, la propriete serait une supposition et produirait de
    fausses alertes (`double`, `increment`, `abs`... sont `int -> int` sans etre
    idempotentes). Un verificateur qui accuse a tort est desactive au bout de deux
    jours : cette fonction est ce qui l'empeche.
    """
    name = node.name.lower()
    if any(name == candidate or name.startswith(candidate) for candidate in _IDEMPOTENT_NAMES):
        return True
    doc = ast.get_docstring(node) or ""
    low = doc.lower()
    return any(word in low for word in _IDEMPOTENT_WORDS)


def _literal(node: ast.AST) -> tuple[bool, object]:
    """Valeur Python d'un litteral AST. (False, None) si ce n'en est pas un.

    On refuse tout ce qui n'est pas un litteral pur : un appel, un nom, un f-string
    ne sont pas des entrees dont on connait le domaine. Inventer ici serait le debut
    des faux positifs.
    """
    if isinstance(node, ast.Constant):
        return True, node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        good, value = _literal(node.operand)
        if good and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True, (-value if isinstance(node.op, ast.USub) else value)
        return False, None
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = []
        for element in node.elts:
            good, value = _literal(element)
            if not good:
                return False, None
            values.append(value)
        if isinstance(node, ast.List):
            return True, values
        if isinstance(node, ast.Tuple):
            return True, tuple(values)
        try:
            return True, set(values)
        except TypeError:
            return False, None
    if isinstance(node, ast.Dict):
        out: dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                return False, None
            good_key, key = _literal(key_node)
            good_value, value = _literal(value_node)
            if not (good_key and good_value):
                return False, None
            try:
                out[key] = value
            except TypeError:
                return False, None
        return True, out
    return False, None


def docstring_examples(doc: str) -> list[object]:
    """Exemples de doctest reellement exploitables dans une docstring.

    Expose comme source de verite unique : `autocheck` s'en sert pour decider s'il
    existe un exemple a verifier, et ce module pour en tirer des temoins d'entree.
    Ecrire deux fois la meme detection garantirait qu'elles divergent un jour — et
    une divergence ici, c'est un fichier correct declare fautif.
    """
    if not doc or ">>>" not in doc:
        return []
    try:
        import doctest

        return list(doctest.DocTestParser().get_examples(doc))
    except Exception:  # pragma: no cover - docstring exotique
        return []


def _doctest_seeds(node: ast.FunctionDef, limit: int = 4) -> list[tuple[object, ...]]:
    """Entrees tirees des exemples `>>>` de l'auteur.

    C'est la ressource la plus fiable du fichier : ces entrees ont ete ecrites et
    validees par l'auteur, donc elles appartiennent au domaine. La ou une annotation
    manque (cas majoritaire dans du code reel), l'exemple fournit a la fois le TYPE et
    un TEMOIN — et on peut ensuite le deformer (vider, dupliquer, reduire) sans
    quitter le domaine declare.
    """
    doc = ast.get_docstring(node)
    if not doc:
        return []
    examples = docstring_examples(doc)
    seeds: list[tuple[object, ...]] = []
    for example in examples:
        line = example.source.strip()
        if not line:
            continue
        try:
            tree = ast.parse(line)
        except SyntaxError:
            continue
        if not tree.body or not isinstance(tree.body[0], ast.Expr):
            continue
        call = tree.body[0].value
        if not isinstance(call, ast.Call) or call.keywords or not call.args:
            continue
        values: list[object] = []
        for arg in call.args:
            good, value = _literal(arg)
            if not good:
                values = []
                break
            values.append(value)
        if values:
            seeds.append(tuple(values))
        if len(seeds) >= limit:
            break
    return seeds


def _seed_variants(seed: tuple[object, ...], limit: int = 8) -> list[tuple[object, ...]]:
    """Deformations structurelles d'un temoin valide.

    L'exemple de l'auteur couvre un point du domaine ; les defauts vivent aux bords.
    On reste DANS le domaine : vider une liste, la dupliquer, la reduire, mettre un
    zero — jamais inventer un type que l'auteur n'a pas utilise. Une entree hors
    domaine produirait une exception, et une exception n'est pas une violation : au
    pire on ne trouve rien, jamais on n'accuse a tort.
    """
    out: list[tuple[object, ...]] = [seed]
    for index, value in enumerate(seed):
        candidates: list[object] = []
        if isinstance(value, list):
            candidates = [[], value[:1], value + value, value[: max(1, len(value) - 1)]]
        elif isinstance(value, str):
            candidates = ["", value[:1], value + value]
        elif isinstance(value, dict):
            candidates = [{}, dict(list(value.items())[:1]) if value else {}]
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            candidates = [0, 1, -1]
        for candidate in candidates:
            case = list(seed)
            case[index] = candidate
            out.append(tuple(case))
            if len(out) >= limit:
                return out
    return out


def _cases_from_annotations(
    node: ast.FunctionDef,
    positional: list[ast.arg],
    names: list[str],
    inputs: int,
    seed: int,
) -> list[tuple[object, ...]]:
    """Cas construits depuis les annotations. Vide si une annotation manque."""
    columns: dict[int, list[object]] = {}
    for index, annotated in enumerate(positional):
        text = _annotation_text(annotated.annotation)
        values = generate_inputs(text, inputs, seed + index)
        if values is None:
            return []
        columns[index] = values
    smallest = min((len(v) for v in columns.values()), default=0)
    return [tuple(columns[i][k] for i in range(len(positional))) for k in range(smallest)]


def _cases_for(
    node: ast.FunctionDef, positional: list[ast.arg], inputs: int, seed: int
) -> tuple[list[tuple[object, ...]], str]:
    """Cas d'entree + provenance ('annotations', 'docstring' ou '').

    Les cas tires des annotations sont ENRICHIS par les memes deformations
    structurelles que ceux tires des exemples : sans cela, une liste generee peut
    n'avoir aucun doublon, et un tri qui perd les doublons (`sorted(set(x))`) passe
    inapercu. Defaut constate au banc, corrige ici.
    """
    cases = _cases_from_annotations(node, positional, [a.arg for a in positional], inputs, seed)
    if cases:
        enriched: list[tuple[object, ...]] = []
        seen: set[str] = set()
        for case in cases[:6]:
            for variant in _seed_variants(case, limit=6):
                key = repr(variant)
                if key not in seen:
                    seen.add(key)
                    enriched.append(variant)
        for case in cases:
            key = repr(case)
            if key not in seen:
                seen.add(key)
                enriched.append(case)
        return enriched[: inputs + 8], "annotations"
    seeds = _doctest_seeds(node)
    if not seeds:
        return [], ""
    variants: list[tuple[object, ...]] = []
    for witness in seeds:
        variants.extend(_seed_variants(witness))
    return variants[: inputs + 4], "docstring"


def _returns_a_value(node: ast.FunctionDef) -> bool:
    """La fonction rend-elle quelque chose ?

    C'est le critere decisif pour la non-mutation, et il est verifiable sans
    annotation. Une fonction qui ne rend rien (`-> None` implicite ou explicite) est
    une API « en place » : `sort_in_place(x)` DOIT modifier x, l'accuser serait une
    fausse alerte. Une fonction qui rend une valeur ET modifie son argument est au
    contraire le cas suspect : l'appelant croit recevoir un resultat, il recoit en
    plus une modification qu'il n'a pas demandee.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return):
            if sub.value is None:
                continue
            if isinstance(sub.value, ast.Constant) and sub.value.value is None:
                continue
            return True
    return False


def _round_trip_candidates(names: set[str]) -> list[tuple[str, str, int | None]]:
    """Paires (aller, retour, type d'entree) promises par les NOMS du module."""
    pairs: list[tuple[str, str, int | None]] = []
    for forward, backward in _ROUND_TRIP_PAIRS:
        if forward in names and backward in names:
            pairs.append((forward, backward, None))
    for prefix, inverse in _ROUND_TRIP_PREFIXES:
        for name in names:
            if name.startswith(prefix) and len(name) > len(prefix):
                twin = inverse + name[len(prefix):]
                if twin in names:
                    pairs.append((name, twin, None))
    # Variantes par suffixe : `url_encode`/`url_decode`, `json_dump`/`json_load`.
    for name in names:
        for forward, backward in _ROUND_TRIP_PAIRS:
            if name.endswith("_" + forward):
                twin = name[: -len(forward)] + backward
                if twin in names:
                    pairs.append((name, twin, None))
    return pairs


def derive_properties(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
    *,
    module_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
    inputs: int = 12,
    seed: int = 20260101,
) -> list[DerivedProperty]:
    """Proprietes universelles deduites de la signature, du nom et des exemples.

    Trois sources, dans cet ordre de fiabilite : les ANNOTATIONS (domaine declare),
    les EXEMPLES `>>>` de l'auteur (temoin valide et deformable), le NOM (pour les
    proprietes que seul un nom peut promettre, comme `normalize` -> idempotence).

    Aucune source -> aucune propriete. C'est volontaire : une propriete inventee est
    une fausse alerte en puissance, et un verificateur qui accuse a tort finit
    desactive. Deterministe, sans modele, sans reseau.
    """
    out: list[DerivedProperty] = []
    if not isinstance(node, ast.FunctionDef):   # les fonctions async ont un autre contrat
        return out

    positional = list(node.args.posonlyargs) + list(node.args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        return out

    cases, provenance = _cases_for(node, positional, inputs, seed)

    # --- P-001 non-mutation ------------------------------------------------ #
    # Deux garde-fous contre la fausse alerte, avant meme de regarder la signature :
    #   * une fonction qui ne renvoie RIEN et mute son argument est une API « en
    #     place » par conception (`sort_in_place(x)`) ;
    #   * un nom qui annonce la mutation (`fill_`, `update_`, `append_`) aussi.
    # Sans eux, la propriete accuserait du code correct.
    returns_text = _annotation_text(node.returns).replace(" ", "")
    in_place_name = any(token in node.name.lower() for token in _IN_PLACE_NAMES)
    mutation_plausible = (
        returns_text in {"None", "NoneType"}
        or in_place_name
        or not _returns_a_value(node)
    )
    if cases and not mutation_plausible:
        rendered = ", ".join("(" + ", ".join(repr(v) for v in case) + ",)" for case in cases)
        out.append(
            DerivedProperty(
                id="P-001",
                name="non-mutation-des-arguments",
                statement=(
                    f"{name} ne modifie pas ses arguments : ce qu'on lui passe "
                    "reste intact apres l'appel."
                ),
                check=_NON_MUTATION.format(name=name, cases=rendered),
            )
        )

    # --- P-002 idempotence -------------------------------------------------- #
    # ATTENTION : le type ne prouve RIEN. `double(1) = 2` et `double(2) = 4` : une
    # fonction `int -> int` n'est pas idempotente, et l'accuser serait une fausse
    # alerte sur du code correct. On ne declare la propriete que si le NOM ou la
    # DOCSTRING la promettent explicitement — meme regle que pour l'aller-retour :
    # on ne verifie que ce que l'auteur a affirme.
    if cases and len(positional) == 1 and _claims_idempotence(node):
        rendered = ", ".join("(" + repr(case[0]) + ",)" for case in cases)
        out.append(
            DerivedProperty(
                id="P-002",
                name="idempotence",
                statement=f"{name}({name}(x)) == {name}(x) pour tout x du domaine.",
                check=_IDEMPOTENCE.format(name=name, cases=rendered),
            )
        )

    # --- P-004 tri fidele, P-005 dedoublonnage sans perte ---------------- #
    # Deux promesses que seul le NOM peut faire : `sort_*` promet une sortie triee ET
    # fidele (rien perdu, rien invente), `dedupe`/`unique` promet de retirer les
    # repetitions mais AUCUNE valeur unique. On ne verifie donc que les fonctions dont
    # le nom s'engage — une fonction de tri maison appelee `arrange` ne sera jamais
    # accusee sur une promesse qu'elle n'a pas faite.
    if cases and len(positional) >= 1:
        rendered = ", ".join("(" + ", ".join(repr(v) for v in case) + ",)" for case in cases)
        if _annonce(node.name, _SORT_CLAIMS):
            lossy = _annonce(node.name, _LOSSY_CLAIMS)
            ascending = not _annonce(node.name, _SORT_DESCENDING)
            out.append(
                DerivedProperty(
                    id="P-004",
                    name="tri-fidele",
                    statement=(
                        f"{name} rend une collection triee "
                        f"({'croissante' if ascending else 'decroissante'}) et fidele : "
                        + (
                            "aucun element invente ou perdu."
                            if not lossy
                            else "elle peut dedoublonner, son nom l'annonce."
                        )
                    ),
                    check=_SORTED.format(
                        name=name,
                        cases=rendered,
                        ascending=ascending,
                        fidelity=not lossy,
                    ),
                )
            )
        elif _annonce(node.name, _DEDUPE_CLAIMS):
            out.append(
                DerivedProperty(
                    id="P-005",
                    name="dedoublonnage-sans-perte",
                    statement=(
                        f"{name} ne retire que les repetitions : aucune valeur "
                        "apparaissant une seule fois ne disparait."
                    ),
                    check=_DEDUPE.format(name=name, cases=rendered),
                )
            )

    # --- P-003 aller-retour ------------------------------------------------- #
    functions = module_functions or {}
    for forward, backward, _ in _round_trip_candidates(set(functions)):
        if forward != name:
            # La propriete appartient a l'ALLER, pas a tout le module : sinon chaque
            # fonction du fichier porterait la meme regle, et un seul defaut serait
            # signale autant de fois qu'il y a de fonctions.
            continue
        fwd_node = functions.get(forward)
        bwd_node = functions.get(backward)
        if not isinstance(fwd_node, ast.FunctionDef) or not isinstance(bwd_node, ast.FunctionDef):
            continue
        fwd_args = list(fwd_node.args.posonlyargs) + list(fwd_node.args.args)
        bwd_args = list(bwd_node.args.posonlyargs) + list(bwd_node.args.args)
        if len(fwd_args) != 1 or len(bwd_args) != 1:
            continue
        pair_cases, _ = _cases_for(fwd_node, fwd_args, inputs, seed + 11)
        if not pair_cases:
            # Aucun domaine cote aller. Mais pour une paire SANS PERTE, le retour de
            # la fonction inverse a exactement le type de x : `decode(encode(x))`
            # est de type `str -> str`, donc le type de retour de `decode` est le
            # domaine d'entree de `encode`. C'est une inference SURE (elle decoule de
            # la propriete elle-meme), pas une supposition : si le domaine obtenu est
            # faux, l'appel leve une exception et une exception n'est jamais une
            # violation.
            returned = _annotation_text(bwd_node.returns)
            fallback = generate_inputs(returned, inputs, seed + 23)
            if fallback:
                pair_cases = [(value,) for value in fallback]
        if not pair_cases:
            continue
        out.append(
            DerivedProperty(
                id="P-003",
                name=f"aller-retour-{forward}-{backward}",
                statement=f"{backward}({forward}(x)) == x (aller-retour sans perte).",
                check=_ROUND_TRIP.format(
                    forward=forward,
                    backward=backward,
                    cases=", ".join(
                        "(" + ", ".join(repr(v) for v in case) + ",)" for case in pair_cases
                    ),
                ),
            )
        )
    return out
