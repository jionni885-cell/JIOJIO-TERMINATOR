"""Derivation de regles executables a partir de l'artefact lui-meme.

Probleme resolu
---------------
`SpecCompiler` transforme un objectif en langage naturel en regles *declarees*.
Ces regles n'ont pas de temoin executable : sans banc d'essai, le prover
fail-closed refuse de conclure (et il a raison). Resultat : `jio audit` ne
savait rien prouver sur un fichier inconnu.

Ce module comble le trou sans dependance externe, en exploitant trois sources de
verite presentes dans l'artefact lui-meme :

  1. **Signature** -> le contrat d'appel et les annotations de type.
  2. **Docstring** (:mod:`doctest`) -> des exemples fournis par l'auteur, donc une
     vraie specification, executable telle quelle.
  3. **Determinisme** -> deux appels identiques dans le meme processus doivent
     donner le meme resultat. Un artefact non reproductible invalide toute la
     chaine de verification : c'est un defaut, pas un detail.

Regle de prudence (lecon payee au banc d'essai)
-----------------------------------------------
Un faux positif detruit la confiance dans le garde. On ne transforme donc JAMAIS
une propriete *souhaitable* en regle. Sont des **regles** uniquement les
proprietes dont l'echec **prouve** un defaut :

  * l'entree nommee est absente ou non appelable ;
  * un exemple de la docstring ne produit pas le resultat annonce ;
  * deux appels identiques produisent deux resultats differents.

Les entrees de sonde sont derivees **statiquement** (AST). Si elles ne peuvent
pas l'etre, la regle de determinisme n'est PAS emise : elle est declaree
`under_specified`. Un garde qui echoue faute d'information est un faux positif.

Tout le reste (non-mutation des arguments, totalite sur des entrees arbitraires,
type de retour conforme a l'annotation) est une **attente**, pas une preuve :
ces elements sont declares dans ``under_specified`` et n'influencent jamais le
verdict. C'est la difference entre auditer et pretendre auditer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from ..core.types import Rule, RuleKind, Spec

__all__ = ["DerivedSpec", "derive", "syntax_error"]


# --------------------------------------------------------------------------- #
# Resultat
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DerivedSpec:
    """Specification derivee d'un artefact + ses temoins executables."""

    spec: Spec
    checks: dict[str, str] = field(default_factory=dict)
    functions: tuple[str, ...] = ()
    entrypoint: str = ""
    notes: tuple[str, ...] = ()
    preamble: str = ""

    @property
    def verifiable(self) -> bool:
        return bool(self.checks)


def package_preamble(path: object) -> str:
    """Preambule rendant les imports relatifs d'un module de paquet executables.

    Sans lui, auditer `jio/verify/metamorphic.py` produit un ImportError
    ("attempted relative import with no known parent package") : le verificateur
    signalait un defaut *du verificateur* comme un defaut *de l'artefact*. Un
    faux positif de cette farine detruit la confiance dans le garde.
    """
    from pathlib import Path as _Path

    if not path:
        return ""
    file = _Path(str(path)).resolve()
    parts = [file.stem]
    parent = file.parent
    while (parent / "__init__.py").exists():
        parts.append(parent.name)
        parent = parent.parent
    if len(parts) < 2:
        return ""
    root = parent
    module = ".".join(reversed(parts))
    package = module.rsplit(".", 1)[0]
    return (
        "import sys as _jio_sys\n"
        f"if {str(root)!r} not in _jio_sys.path:\n"
        f"    _jio_sys.path.insert(0, {str(root)!r})\n"
        f"__package__ = {package!r}\n"
    )


def syntax_error(source: str) -> str:
    """Message d'erreur de syntaxe, ou chaine vide si la source compile."""
    try:
        ast.parse(source)
    except SyntaxError as exc:
        where = f"ligne {exc.lineno}" if exc.lineno else "position inconnue"
        return f"{exc.msg} ({where})"
    return ""


# --------------------------------------------------------------------------- #
# Lecture statique de l'artefact
# --------------------------------------------------------------------------- #


def _top_level_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _public_functions(tree: ast.Module) -> tuple[str, ...]:
    return tuple(n.name for n in _top_level_defs(tree) if not n.name.startswith("_"))


def _class_defs(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        n.name: n for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")
    }


def _is_dataclass(node: ast.ClassDef) -> bool:
    """Vrai si la classe est decoree `@dataclass` (l'`__init__` est alors genere)."""
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = ast.unparse(target).split(".")[-1]
        if name in ("dataclass", "define", "frozen"):
            return True
    return False


def _required_dataclass_fields(node: ast.ClassDef) -> list[str]:
    """Champs sans valeur par defaut d'une dataclass : ils sont obligatoires."""
    required: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and item.value is None:
            required.append(ast.unparse(item.target))
    return required


def _instantiable_without_args(node: ast.ClassDef) -> tuple[bool, str]:
    """L'instanciation sans argument est-elle garantie possible ?

    C'est la seule condition qui autorise une regle *prouvable* : une classe dont
    tous les arguments sont optionnels DOIT pouvoir s'instancier a vide. Des
    qu'un argument est obligatoire, l'instanciation depend d'un contexte que
    l'auditeur ignore : on ne fabrique alors aucune regle.

    Renvoie ``(possible, raison_du_refus)``.
    """
    # Un Protocol ou une classe abstraite n'est PAS instanciable par conception :
    # exiger l'instanciation serait un faux positif (constate sur Critic).
    bases = {ast.unparse(b).split(".")[-1] for b in node.bases}
    if bases & {"Protocol", "ABC", "ABCMeta"}:
        return False, f"classe non instanciable par conception ({', '.join(sorted(bases))})"
    if any(
        isinstance(item, ast.FunctionDef)
        and any(
            isinstance(d, ast.Name) and d.id == "abstractmethod"
            or isinstance(d, ast.Attribute) and d.attr == "abstractmethod"
            for d in item.decorator_list
        )
        for item in node.body
    ):
        return False, "classe abstraite (methodes @abstractmethod)"

    if _is_dataclass(node):
        # Piege paye au banc : une dataclass n'a PAS d'`__init__` dans son corps
        # (il est genere). La chercher dans l'AST faisait conclure a tort que la
        # classe etait instanciable a vide -> faux positif sur Calibration,
        # ProgressPoint, Event, ConsensusOutcome.
        missing = _required_dataclass_fields(node)
        if missing:
            return False, f"dataclass a champs obligatoires : {', '.join(missing)}"
        return True, ""

    init = next(
        (n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None
    )
    if init is None:
        return True, ""
    args = init.args
    positional = list(args.posonlyargs) + list(args.args)
    required_positional = len(positional) - len(args.defaults)
    if required_positional > 1:  # `self` est le seul argument tolere sans defaut
        required = [a.arg for a in positional[len(args.defaults) + 1 :]]
        return False, f"arguments obligatoires : {', '.join(required)}"
    missing_kw = [a.arg for a in args.kwonlyargs if a.default is None]
    if missing_kw:
        return False, f"arguments nommes obligatoires : {', '.join(missing_kw)}"
    return True, ""


_SKIPPED_DECORATORS = {"property", "staticmethod", "classmethod", "abstractmethod", "cached_property"}

#: Sources de non-determinisme reconnues. Une horloge ou un generateur
#: aleatoire N'EST PAS un defaut : c'est une dependance a l'environnement qui
#: rend l'artefact non verifiable par execution. Accuser l'artefact serait un
#: faux positif (constate sur `now()` dans jio/core/types.py).
_NONDETERMINISTIC_CALLS: dict[str, str] = {
    "time.time": "horloge systeme",
    "time.time_ns": "horloge systeme",
    "time.monotonic": "horloge monotone",
    "time.perf_counter": "horloge haute resolution",
    "time.process_time": "horloge processeur",
    "datetime.now": "horloge systeme",
    "datetime.today": "horloge systeme",
    "datetime.utcnow": "horloge systeme",
    "date.today": "horloge systeme",
    "uuid.uuid1": "identifiant dependant de la machine",
    "uuid.uuid4": "identifiant aleatoire",
    "os.urandom": "source d'aleatoire du systeme",
    "secrets.token_bytes": "source d'aleatoire cryptographique",
    "secrets.token_hex": "source d'aleatoire cryptographique",
    "secrets.token_urlsafe": "source d'aleatoire cryptographique",
    "random": "generateur aleatoire",
}


_ENV_MODULES = {
    "time", "datetime", "random", "uuid", "secrets",
    "socket", "threading", "subprocess", "multiprocessing",
}


def _module_touches_environment(tree: ast.Module) -> str:
    """Nom d'un module d'environnement importe, ou chaine vide.

    Sert a distinguer deux situations tres differentes :
      * le corps audite appelle DIRECTEMENT une horloge -> aucune regle de
        reproductibilite n'est emise (verifier serait impossible) ;
      * le module importe une horloge ailleurs -> une regle de reproductibilite
        peut echouer pour une raison indirecte. Son echec devient alors une
        RESERVE (advisory), jamais un rejet. C'est le cas de Journal.replay(),
        qui depend de l'horloge par appel indirect.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _ENV_MODULES:
                    return root
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _ENV_MODULES:
                return root
    return ""


def _call_name(node: ast.Call) -> str:
    return ast.unparse(node.func)


def _nondeterminism_sources(node: ast.AST) -> tuple[str, ...]:
    """Sources de non-determinisme detectees dans le corps de ``node``.

    Si le corps fixe lui-meme la graine (`random.seed(<litteral>)`), le hasard
    redevient reproductible : on ne signale alors pas `random`.
    """
    found: dict[str, str] = {}
    seeds_fixed = False
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = _call_name(sub)
        if name == "random.seed" and sub.args:
            try:
                ast.literal_eval(sub.args[0])
                seeds_fixed = True
            except Exception:
                pass
        for pattern, why in _NONDETERMINISTIC_CALLS.items():
            if name == pattern or name.startswith(pattern + "."):
                found[name] = why
    if seeds_fixed:
        found = {k: v for k, v in found.items() if not k.startswith("random")}
    return tuple(f"{k} ({v})" for k, v in sorted(found.items()))


def _public_methods(node: ast.ClassDef) -> list[ast.FunctionDef]:
    """Methodes publiques, synchrones, appelables sur une instance."""
    out: list[ast.FunctionDef] = []
    for item in node.body:
        # ast.AsyncFunctionDef n'herite pas de ast.FunctionDef : les coroutines
        # sont donc exclues d'office (on ne pilote pas de boucle d'evenements ici).
        if not isinstance(item, ast.FunctionDef) or item.name.startswith("_"):
            continue
        decorators = {ast.unparse(d).split("(")[0] for d in item.decorator_list}
        if decorators & _SKIPPED_DECORATORS:
            continue
        out.append(item)
    return out


def _has_doctest(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return ">>>" in (ast.get_docstring(node) or "")


#: Valeurs limites associees aux types de base. Volontairement minuscule : on
#: enumere les bords des types surs et on s'arrete la. Deviner un domaine
#: metier serait une source de faux positifs.
_SAMPLES: dict[str, list[object]] = {
    "bool": [True, False],
    # Valeurs volontairement etalees : [0, 1] ne discrimine rien et laissait
    # passer une fonction aleatoire (faux negatif constate au banc).
    "int": [0, 1, -1, 7, -13],
    "float": [0.0, -1.5, 3.25],
    "str": ["", "a", "abc"],
}

_SEQ_NAMES = {"list", "List", "Sequence", "Iterable", "MutableSequence"}
_TUPLE_NAMES = {"tuple", "Tuple"}
_MAP_NAMES = {"dict", "Dict", "Mapping", "MutableMapping"}


def _samples_for_annotation(node: ast.expr | None) -> list[object] | None:
    """Valeurs de sonde pour une annotation AST, ou None si le domaine est inconnu."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # Annotation sous forme de chaine : "int", "list[int]"...
        return _samples_for_annotation_text(node.value)
    if isinstance(node, ast.Name):
        return _SAMPLES.get(node.id)
    if isinstance(node, ast.Attribute):
        return _SAMPLES.get(node.attr)
    if isinstance(node, ast.Subscript):
        return _samples_for_annotation_text(ast.unparse(node))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # `int | None` : on teste le type reel, pas None (contrat non ambigu).
        return _samples_for_annotation(  # pragma: no cover - rare
            node.left
        ) or _samples_for_annotation(node.right)
    return None


def _samples_for_annotation_text(text: str) -> list[object] | None:
    flat = text.replace(" ", "")
    if flat.endswith("|None"):
        flat = flat[: -len("|None")]
    if flat in _SAMPLES:
        return list(_SAMPLES[flat])
    head = flat.split("[", 1)[0]
    if head in _SAMPLES:
        return list(_SAMPLES[head])
    if head in _SEQ_NAMES:
        return [["a", "b"], []] if "str" in flat else [[0, 1, 2], [], [-3, 4]]
    if head in _TUPLE_NAMES:
        return [(), (0,), (1, 2)]
    if head in _MAP_NAMES:
        return [{}, {"a": 1}]
    return None


def _static_plan(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[list[object]] | None, tuple[str, ...]]:
    """Plan de sondage (produit cartesien des valeurs par parametre).

    Renvoie ``(plan, blocages)``. ``plan`` vaut None des qu'un parametre
    obligatoire n'a ni annotation reconnue ni valeur par defaut litterale : dans
    ce cas aucune sonde honnete n'est possible.
    """
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults))
    defaults += list(args.defaults)

    plan: list[list[object]] = []
    blocked: list[str] = []

    for arg, default in zip(positional, defaults):
        if arg.arg in ("self", "cls"):
            continue
        values = _samples_for_annotation(arg.annotation)
        if values is not None:
            plan.append(values)
            continue
        if default is not None:
            try:
                plan.append([ast.literal_eval(default)])
                continue
            except Exception:
                pass
        blocked.append(arg.arg)

    for arg in args.kwonlyargs:
        values = _samples_for_annotation(arg.annotation)
        if values is not None:
            plan.append(values)
        else:
            blocked.append(arg.arg)

    if blocked:
        return None, tuple(blocked)
    if args.vararg or args.kwarg:
        variadic = [a.arg for a in (args.vararg, args.kwarg) if a is not None]
        return None, tuple(variadic)
    # ATTENTION : pour une fonction sans parametre, `plan` doit rester VIDE.
    # `itertools.product(*[[]])` ne produit aucune combinaison : la sonde
    # n'aurait jamais ete executee et la regle aurait echoue a tort.
    return plan, ()


# --------------------------------------------------------------------------- #
# Temoins executes apres la source du candidat
# --------------------------------------------------------------------------- #

_CHECK_CALLABLE = '''
_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
'''

#: Reproductibilite. Le plan de sondage est fige a la derivation : aucune entree
#: inventee ici. Chaque entree est repetee plusieurs fois, car une seule
#: repetition ne prouve rien contre le hasard.
_CHECK_DETERMINISM = '''
import itertools as _jio_it
_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_plans = {plans}
_jio_rounds = 4


def _jio_outcome(*_args):
    try:
        return ("valeur", _jio_fn(*_args))
    except Exception as _exc:
        return ("erreur", type(_exc).__name__, str(_exc))


def _jio_same(_x, _y):
    try:
        return bool(_x == _y)
    except Exception:
        return _x is _y


_jio_checked = 0
for _combo in _jio_it.islice(_jio_it.product(*_jio_plans), 8):
    _observed = [_jio_outcome(*_combo) for _ in range(_jio_rounds)]
    _jio_checked += 1
    for _other in _observed[1:]:
        assert _jio_same(_observed[0], _other), (
            "non reproductible : {name}(*%r) a produit %r puis %r"
            % (_combo, _observed[0], _other)
        )
assert _jio_checked, "aucune sonde executable pour {name}"
'''

_CHECK_CLASS_INSTANTIATE = '''
_jio_cls = globals().get({name!r})
assert isinstance(_jio_cls, type), "classe {name!r} absente ou non instanciable"
_jio_obj = _jio_cls()
assert _jio_obj is not None, "construction de {name!r} impossible"
'''

#: Coherence d'une methode. Instance NEUVE a chaque appel : on ne teste pas la
#: memoire de l'objet, on teste la reproductibilite de la methode.
_CHECK_METHOD_STABLE = '''
import itertools as _jio_it
_jio_cls = globals().get({name!r})
assert isinstance(_jio_cls, type), "classe {name!r} absente"
_jio_plans = {plans}
_jio_rounds = 3


def _jio_call(*_args):
    _obj = _jio_cls()
    try:
        return ("valeur", getattr(_obj, {method!r})(*_args))
    except Exception as _exc:
        return ("erreur", type(_exc).__name__, str(_exc))


def _jio_same(_x, _y):
    try:
        return bool(_x == _y)
    except Exception:
        return _x is _y


_jio_checked = 0
for _combo in _jio_it.islice(_jio_it.product(*_jio_plans), 4):
    _observed = [_jio_call(*_combo) for _ in range(_jio_rounds)]
    _jio_checked += 1
    for _other in _observed[1:]:
        assert _jio_same(_observed[0], _other), (
            "non reproductible : {name}().{method}(*%r) a produit %r puis %r"
            % (_combo, _observed[0], _other)
        )
assert _jio_checked, "aucune sonde executable pour {name}.{method}"
'''

_CHECK_DOCTESTS = '''
import doctest as _jio_doc
_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_tests = [
    _t for _t in _jio_doc.DocTestFinder().find(_jio_fn, name=_jio_fn.__name__) if _t.examples
]
assert _jio_tests, "aucun exemple exploitable dans la docstring de {name}"
_jio_runner = _jio_doc.DocTestRunner(verbose=False)
for _t in _jio_tests:
    _jio_runner.run(_t, out=lambda _s: None)
assert _jio_runner.failures == 0, (
    "%d exemple(s) de docstring contredisent le code de {name}" % _jio_runner.failures
)
'''


def _plan_source(plan: list[list[object]]) -> str:
    """Rend un plan de sondage sous forme de source Python litterale."""
    return "[" + ", ".join("[" + ", ".join(repr(v) for v in values) + "]" for values in plan) + "]"


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #


def derive(source: str, entrypoint: str = "", path: object = None) -> DerivedSpec:
    """Construit une specification verifiable a partir de la source d'un artefact.

    Aucune execution n'a lieu ici : on lit la source, on choisit la cible (une
    fonction, ou a defaut une classe et ses methodes), et on renvoie des regles
    + les temoins a executer dans le bac a sable par
    :class:`~jio.verify.executable.ExecutableProver`.
    """
    preamble = package_preamble(path)

    err = syntax_error(source)
    if err:
        return DerivedSpec(
            spec=Spec(
                mission="audit d'un artefact Python",
                rules=(),
                under_specified=(f"la source ne compile pas : {err}",),
            ),
            notes=(f"syntaxe invalide : {err}",),
            preamble=preamble,
        )

    tree = ast.parse(source)
    defs = {n.name: n for n in _top_level_defs(tree)}
    classes = _class_defs(tree)
    names = _public_functions(tree)
    env_risk = _module_touches_environment(tree)

    if entrypoint and entrypoint in classes:
        return _class_spec(classes[entrypoint], classes, names, preamble, env_risk)
    if entrypoint and entrypoint not in defs:
        return DerivedSpec(
            spec=Spec(
                mission="audit d'un artefact Python",
                rules=(),
                under_specified=(
                    f"l'entree {entrypoint!r} est absente ; vues : "
                    f"{', '.join(names) or 'aucune fonction'}"
                    + (f" ; classes : {', '.join(classes)}" if classes else ""),
                ),
            ),
            functions=names,
            entrypoint=entrypoint,
            notes=(f"entree demandee introuvable : {entrypoint!r}",),
            preamble=preamble,
        )

    if not names:
        if classes:
            return _best_class_spec(classes, names, preamble, env_risk)
        return DerivedSpec(
            spec=Spec(
                mission="audit d'un artefact Python",
                rules=(),
                under_specified=(
                    "aucune fonction ni classe publique de premier niveau : "
                    "rien d'executable a verifier",
                ),
            ),
            notes=("l'artefact ne declare rien de verifiable",),
            preamble=preamble,
        )

    # Priorite a une fonction qui porte des exemples `>>>` : c'est une cible
    # infiniment plus informative que la premiere fonction venue.
    if not entrypoint:
        chosen = next((n for n in names if _has_doctest(defs[n])), names[0])
    else:
        chosen = entrypoint
    node = defs[chosen]
    rules: list[Rule] = []
    checks: dict[str, str] = {}
    notes: list[str] = []
    under: list[str] = []

    r1 = "A-001"
    rules.append(
        Rule(
            id=r1,
            statement=f"L'artefact s'execute et l'entree {chosen!r} est appelable.",
            kind=RuleKind.CONTRACT,
        )
    )
    checks[r1] = _CHECK_CALLABLE.format(name=chosen)

    plan, blocked = _static_plan(node)
    nondet = _nondeterminism_sources(node)
    if nondet:
        under.append(
            "source de non-determinisme detectee : "
            + ", ".join(nondet)
            + " -> la reproductibilite n'est PAS verifiable telle quelle ; ce n'est pas "
            "un defaut, mais l'artefact n'est pas verifiable par execution. "
            "Remede : injecter une horloge et une graine (parametres par defaut)."
        )
    elif plan is None:
        under.append(
            f"parametres sans annotation exploitable ni valeur par defaut litterale : "
            f"{', '.join(blocked)} -> determinisme NON verifie (aucune entree inventee)"
        )
    else:
        r2 = "A-002"
        rules.append(
            Rule(
                id=r2,
                statement=(
                    f"Reproductibilite : appels identiques de {chosen} sur les sondes "
                    "derivees renvoient le meme resultat, ou la meme erreur."
                    + (
                        f" [reserve : le module importe `{env_risk}`, une divergence peut "
                        "venir de l'environnement]"
                        if env_risk
                        else ""
                    )
                ),
                kind=RuleKind.ADVISORY if env_risk else RuleKind.PROPERTY,
            )
        )
        checks[r2] = _CHECK_DETERMINISM.format(name=chosen, plans=_plan_source(plan))
        if env_risk:
            under.append(
                f"le module importe `{env_risk}` : une divergence peut venir de "
                "l'environnement et non d'un defaut -> reproductibilite classee RESERVE"
            )

    if _has_doctest(node):
        r3 = "A-003"
        rules.append(
            Rule(
                id=r3,
                statement="Chaque exemple de la docstring produit le resultat annonce.",
                kind=RuleKind.TEST,
            )
        )
        checks[r3] = _CHECK_DOCTESTS.format(name=chosen)
        notes.append(
            "docstring : les exemples ecrits par l'auteur servent de specification executable"
        )
    else:
        under.append(
            f"aucun exemple `>>>` dans la docstring de {chosen} : le comportement "
            "attendu n'est pas specifie par l'auteur"
        )

    if len(names) > 1:
        others = ", ".join(n for n in names if n != chosen)
        under.append(f"non couvert par cet audit : {others}")

    under.append(
        "la conformite au besoin metier n'est PAS verifiable sans specification "
        "externe : fournir des oracles (--task) ou des exemples (`>>>`)"
    )
    notes.append(
        "attentes non prouvables (non-mutation des arguments, totalite, type de "
        "retour) : declarees, jamais presumees, sans effet sur le verdict"
    )

    return DerivedSpec(
        spec=Spec(
            mission=f"audit de {chosen}",
            rules=tuple(rules),
            under_specified=tuple(under),
        ),
        checks=checks,
        functions=names,
        entrypoint=chosen,
        notes=tuple(notes),
        preamble=preamble,
    )


def _best_class_spec(
    classes: dict[str, ast.ClassDef],
    names: tuple[str, ...],
    preamble: str,
    env_risk: str = "",
) -> DerivedSpec:
    """Premiere classe qui donne au moins une regle executable.

    Un module expose souvent une classe sans interet auditable (un point de
    mesure, un enum) avant l'objet qui porte la logique. S'arreter a la premiere
    rendrait l'audit muet pour une raison purement alphabetique.
    """
    first: DerivedSpec | None = None
    for node in classes.values():
        derived = _class_spec(node, classes, names, preamble, env_risk)
        if first is None:
            first = derived
        if derived.verifiable:
            return derived
    assert first is not None  # appele uniquement avec au moins une classe
    return first


def _class_spec(
    node: ast.ClassDef,
    classes: dict[str, ast.ClassDef],
    names: tuple[str, ...],
    preamble: str,
    env_risk: str = "",
) -> DerivedSpec:
    """Regles verifiables pour une classe : instanciation + coherence des methodes.

    Pourquoi c'est sur : une classe dont TOUS les arguments sont optionnels doit
    pouvoir s'instancier sans argument. L'echec prouve un defaut. Des qu'un
    argument est obligatoire, on ne fabrique aucune regle — on declare la limite.
    """
    name = node.name
    rules: list[Rule] = []
    checks: dict[str, str] = {}
    notes: list[str] = []
    under: list[str] = []

    instantiable, reason = _instantiable_without_args(node)
    methods = _public_methods(node)

    if instantiable:
        r1 = "C-001"
        rules.append(
            Rule(
                id=r1,
                statement=f"{name} s'instancie sans argument (tous ses parametres sont optionnels).",
                kind=RuleKind.CONTRACT,
            )
        )
        checks[r1] = _CHECK_CLASS_INSTANTIATE.format(name=name)

    # Exemples ecrits par l'auteur : la seule specification opposable a une classe
    # qui n'est pas instanciable a vide. Un doctest peut construire l'objet avec
    # le contexte qui manque a l'auditeur.
    if _has_doctest(node) or any(_has_doctest(m) for m in methods):
        rid = f"C-{len(rules) + 1:03d}"
        rules.append(
            Rule(
                id=rid,
                statement=f"Chaque exemple de la docstring de {name} produit le resultat annonce.",
                kind=RuleKind.TEST,
            )
        )
        checks[rid] = _CHECK_DOCTESTS.format(name=name)
        notes.append(
            "docstring : les exemples ecrits par l'auteur servent de specification executable"
        )

    if instantiable:
        probed: list[str] = []
        skipped: list[str] = []
        for method in methods:
            if len(probed) >= 3:
                skipped.append(method.name)
                continue
            sources = _nondeterminism_sources(method)
            if sources:
                skipped.append(f"{method.name} (non-deterministe : {', '.join(sources)})")
                continue
            plan, blocked = _static_plan(method)
            if plan is None:
                skipped.append(f"{method.name} (parametres non derivables : {', '.join(blocked)})")
                continue
            rid = f"C-{len(rules) + 1:03d}"
            rules.append(
                Rule(
                    id=rid,
                    statement=(
                        f"Coherence de {name}.{method.name} : sur des instances NEUVES et des "
                        "entrees derivees identiques, le resultat (ou l'erreur) est le meme."
                        + (
                            f" [reserve : le module importe `{env_risk}`, une divergence "
                            "peut venir de l'environnement]"
                            if env_risk
                            else ""
                        )
                    ),
                    kind=RuleKind.ADVISORY if env_risk else RuleKind.PROPERTY,
                )
            )
            checks[rid] = _CHECK_METHOD_STABLE.format(
                name=name, method=method.name, plans=_plan_source(plan)
            )
            probed.append(method.name)
        if skipped:
            under.append(
                "methodes non sondees (limite de 3 ou parametres non derivables) : "
                + ", ".join(skipped)
            )
    else:
        under.append(
            f"{name} n'est pas instanciable a vide ({reason}) : l'instanciation depend "
            "d'un contexte que l'auditeur ne connait pas -> non verifie"
        )
        if not any(r.kind is RuleKind.TEST for r in rules):
            under.append(
                "pour rendre cette classe verifiable : ajouter un exemple `>>>` dans sa "
                "docstring, ou fournir des oracles via --task"
            )
    under.append(
        "les proprietes metier de la classe ne sont PAS verifiables sans specification "
        "externe : fournir des oracles (--task) ou des exemples (`>>>`)"
    )
    notes.append(
        "instances neuves a chaque appel : la coherence testee est celle de la methode, "
        "pas celle d'un etat volontairement accumule"
    )
    if env_risk:
        under.append(
            f"le module importe `{env_risk}` : une divergence de resultat peut venir de "
            "l'environnement et non d'un defaut -> regles de coherence classees "
            "RESERVE (jamais un rejet). Pour les rendre prouvables : injecter l'horloge "
            "et la graine via des parametres."
        )
    if len(classes) > 1:
        others = ", ".join(k for k in classes if k != name)
        under.append(f"classes non couvertes par cet audit : {others}")

    return DerivedSpec(
        spec=Spec(
            mission=f"audit de {name}",
            rules=tuple(rules),
            under_specified=tuple(under),
        ),
        checks=checks,
        functions=names + tuple(m.name for m in methods),
        entrypoint=name,
        notes=tuple(notes),
        preamble=preamble,
    )
