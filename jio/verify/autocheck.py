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
from .properties import derive_properties, docstring_examples

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


def _decorateurs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """Noms des decorateurs d'une fonction, sous forme pointee (`pytest.fixture`)."""
    noms = []
    for decorateur in node.decorator_list:
        cible = decorateur.func if isinstance(decorateur, ast.Call) else decorateur
        morceaux: list[str] = []
        while isinstance(cible, ast.Attribute):
            morceaux.append(cible.attr)
            cible = cible.value
        if isinstance(cible, ast.Name):
            morceaux.append(cible.id)
        if morceaux:
            noms.append(".".join(reversed(morceaux)))
    return tuple(noms)


def _est_une_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Vrai si la fonction est une fixture (`@pytest.fixture`, `@fixture`).

    Une fixture n'est PAS appelable directement : c'est une erreur, pas un avertissement.
    Mesure faite sur pytest 9.1.1, sur une fixture de ce depot :

        Failed: Fixture "mesures" called directly. Fixtures are not meant to be called
        directly, but are created automatically when test functions request them as
        parameters.

    L'audit la choisissait comme cible (c'est la premiere fonction publique du fichier),
    lui appliquait la regle de reproductibilite, et rapportait un PROBLEME : « appelable
    et reproductible » est une question qui ne s'applique pas a une fixture. Un faux
    positif de cette farine detruit la confiance dans le garde — c'est la doctrine de ce
    module, et elle vaut aussi pour lui.
    """
    return any(
        nom == "fixture" or nom.endswith(".fixture") for nom in _decorateurs(node)
    )


def _class_defs(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        n.name: n for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")
    }


#: Appels qui DECLARENT un champ a constructeur genere (attrs, dataclasses).
_FIELD_CALLS = ("attrib", "ib", "field")


def _is_dataclass(node: ast.ClassDef) -> bool:
    """Vrai si la classe a un `__init__` GENERE (dataclass, attrs, pydantic-like).

    Une dataclass n'a pas d'`__init__` dans son corps : le chercher dans l'AST fait
    conclure a tort que la classe s'instancie a vide. Constate au banc, puis sur une
    bibliotheque publique : `attrs.VersionInfo` (`year = attrib(type=int)`) etait
    declaree instanciable, le bac a sable repondait
    `TypeError: __init__() missing 4 required positional arguments`, et l'artefact
    etait declare fautif.
    """
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        complet = ast.unparse(target).lower()
        if complet.split(".")[-1] in ("dataclass", "define", "frozen"):
            return True
        # Formes classiques d'attrs : `@attr.s`, `@attrs.s`, `@attr.attrs`.
        if complet in ("attr.s", "attrs.s", "attr.attrs", "attrs.attrs"):
            return True
    return False


def _has_generated_init(node: ast.ClassDef) -> bool:
    """Le constructeur est-il GENERE (et donc absent du corps de la classe) ?

    Deux indices, et le second etait indispensable : le decorateur (`@dataclass`,
    `@attr.define`...), **ou** la presence de champs declares par `attrib(...)` au
    niveau classe. attrs permet d'appliquer la decoration APRES coup
    (`attr.s(VersionInfo)` en fin de module) : ne regarder que les decorateurs
    laissait passer `attrs.VersionInfo` et produisait une accusation a tort.
    """
    if _is_dataclass(node):
        return True
    for item in node.body:
        if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
            if ast.unparse(item.value.func).split(".")[-1] in _FIELD_CALLS:
                return True
        elif isinstance(item, ast.AnnAssign) and isinstance(item.value, ast.Call):
            if ast.unparse(item.value.func).split(".")[-1] in _FIELD_CALLS:
                return True
    return False


def _required_dataclass_fields(node: ast.ClassDef) -> list[str]:
    """Champs sans valeur par defaut d'un constructeur genere : ils sont obligatoires.

    Deux ecritures a traiter, et une seule ne suffisait pas :
      * `champ: int`            (dataclass, attrs avec `auto_attribs`);
      * `champ = attrib(...)`   (attrs classique) — d'autant plus obligatoire que
        `attrib()` n'a ni `default=` ni `factory=`.
    """
    required: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and item.value is None:
            required.append(ast.unparse(item.target))
        elif isinstance(item, ast.Assign) and len(item.targets) == 1:
            value = item.value
            if not isinstance(value, ast.Call):
                continue
            nom = ast.unparse(value.func).split(".")[-1]
            if nom not in _FIELD_CALLS:
                continue
            if any(kw.arg in ("default", "factory") for kw in value.keywords):
                continue
            cible = item.targets[0]
            if isinstance(cible, ast.Name):
                required.append(cible.id)
    return required


def _lie_la_sortie_standard(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> bool:
    """Vrai si un parametre LIE un flux des l'import (`file=sys.stdout` par defaut).

    Consequence pour doctest, mesuree sur du code public (`pyparsing.show_best_practices`) :
    la valeur par defaut est evaluee a la DEFINITION de la fonction, donc elle pointe la
    sortie standard d'AVANT le test. Doctest remplace `sys.stdout` pendant l'execution :
    l'exemple ecrit dans l'ancien flux, doctest ne voit rien, et conclut « Got nothing » —
    alors que le code fait exactement ce que sa docstring annonce.

    C'est notre facon de MESURER qui est en cause, pas l'artefact. L'exemple est donc
    declare en reserve avec cette raison, au lieu d'etre accuse.

    Le seul cas traite est le lien par VALEUR PAR DEFAUT, qui est detectable sans deviner :
    un `file=sys.stdout` ecrit dans le corps de la fonction, lui, est capturable.
    """
    # Une CLASSE est acceptee : ses exemples peuvent appeler une de ses methodes qui lie le
    # flux. Sans ce cas, `derive` levait `'ClassDef' object has no attribute 'args'` —
    # regression attrapee par la mesure sur pyparsing, apres avoir ete introduite par cette
    # fonction meme. Le controle doit accepter ce que les sites d'appel lui donnent.
    if isinstance(node, ast.ClassDef):
        if any(
            _lie_la_sortie_standard(item)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            return True
        return False

    defauts = list(node.args.defaults) + [
        d for d in node.args.kw_defaults if d is not None
    ]
    for defaut in defauts:
        try:
            texte = ast.unparse(defaut)
        except Exception:  # arbre partiel
            continue
        if texte in {"sys.stdout", "sys.stderr"}:
            return True
    return False


def _refuse_la_construction(constructeur: ast.FunctionDef) -> bool:
    """Vrai si le constructeur leve une exception SANS CONDITION.

    C'est la signature d'une classe a FABRIQUES : `packaging.ranges.VersionRange` refuse
    `VersionRange()` par un `__new__` dont le corps est un `raise TypeError(...)` qui
    indique les vraies portes d'entree (`to_range()`, `full()`, `empty()`, `singleton()`).

    Defaut reel, mesure sur du code public : l'audit instanciait cette classe, recevait
    `TypeError: cannot create 'VersionRange' instances directly` et rapportait CINQ
    problemes (C-001 a C-005) sur une bibliotheque qui va bien. Le refus est une decision
    d'architecture, ecrite en clair ; l'appeler un defaut est un faux positif — et un faux
    positif de cette farine detruit la confiance dans le garde.

    On ne detecte QUE le `raise` au premier niveau du corps : un `raise` dans un `if`
    depend d'un argument, donc il ne dit rien de la construction a vide. Le doute profite
    a l'artefact : on ne retire une accusation que dans le cas non ambigu.
    """
    return any(isinstance(item, ast.Raise) for item in constructeur.body)


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

    if _has_generated_init(node):
        # Piege paye au banc : une dataclass n'a PAS d'`__init__` dans son corps
        # (il est genere). La chercher dans l'AST faisait conclure a tort que la
        # classe etait instanciable a vide -> faux positif sur Calibration,
        # ProgressPoint, Event, ConsensusOutcome.
        missing = _required_dataclass_fields(node)
        if missing:
            return False, f"dataclass a champs obligatoires : {', '.join(missing)}"
        return True, ""

    constructeurs = {
        n.name: n
        for n in node.body
        if isinstance(n, ast.FunctionDef) and n.name in {"__init__", "__new__"}
    }
    if not constructeurs:
        # Aucun constructeur declare ICI. Deux cas tres differents :
        #   * classe sans base : l'instanciation a vide est acquise ;
        #   * classe DERIVEE : le constructeur vient de la base, on ignore ses
        #     arguments obligatoires -> on ne fabrique AUCUNE regle. C'est le cas de
        #     `ColorTriplet(NamedTuple)`, `Span(Segment)` dans rich : la version
        #     precedente emettait la regle, le bac a sable repondait
        #     `TypeError: __new__() missing 3 required positional arguments` et
        #     l'artefact etait declare fautif. Une capacite non concluante se declare,
        #     elle ne s'accuse pas.
        if bases:
            return False, f"constructeur herite de {', '.join(sorted(bases))}"
        return True, ""
    # Une classe qui REFUSE la construction directe n'est pas cassee : elle est
    # volontairement construite par fabriques. Aucune regle d'instance ne s'applique.
    for nom, constructeur in constructeurs.items():
        if _refuse_la_construction(constructeur):
            return False, (
                f"{nom} refuse la construction directe (exception levee sans condition) : "
                "classe a fabriques, pas un defaut"
            )

    args = constructeurs[next(iter(constructeurs))].args
    nom_constructeur = next(iter(constructeurs))
    positional = list(args.posonlyargs) + list(args.args)
    required_positional = len(positional) - len(args.defaults)
    if required_positional > 1:  # `self`/`cls` est le seul argument tolere sans defaut
        required = [a.arg for a in positional[len(args.defaults) + 1 :]]
        return False, f"arguments obligatoires de {nom_constructeur} : {', '.join(required)}"
    # `ast.arg` n'a PAS d'attribut `default` : les valeurs par defaut vivent dans
    # `arguments.kw_defaults`, alignees sur `kwonlyargs`. Lire `a.default` levait
    # `AttributeError: 'arg' object has no attribute 'default'` — plantage reel du
    # scan, declenche par un fichier de rich ayant un parametre nomme seul.
    missing_kw = [
        a.arg for a, defaut in zip(args.kwonlyargs, args.kw_defaults) if defaut is None
    ]
    if missing_kw:
        return False, f"arguments nommes obligatoires : {', '.join(missing_kw)}"
    return True, ""


#: Plafond du nombre de fonctions auditees par fichier. Un plafond explicite vaut
#: mieux qu'un silence : au-dela, le rapport dit combien de fonctions restent hors
#: audit, au lieu de laisser croire que le fichier est entierement couvert.
_MAX_AUDITED_FUNCTIONS = 8
#: Plafond des fonctions couvertes par les proprietes derivees. Chaque propriete est
#: un programme execute dans le bac a sandbox : le budget doit rester borne et
#: VISIBLE. On garde la marge la plus utile (les premieres fonctions auditees sont
#: celles qui portent des exemples, donc les plus informatives).
_MAX_PROPERTY_FUNCTIONS = 4

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


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """Table alias local -> module d'origine, pour l'analyse du non-determinisme.

    `import random as _rnd` suivi de `_rnd.randint(...)` etait invisible : le
    motif cherchait litteralement `random.`. Un alias suffisait donc a cacher une
    dependance au hasard — ce qui rendait la regle de reproductibilite contournable
    par accident. Constate sur un vrai projet.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                aliases[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            for alias in node.names:
                # On conserve le NOM importe, pas seulement le module : sans lui,
                # `from time import monotonic as clock` se resolvait en `time`, et
                # l'appel `clock()` echappait a la regle de reproductibilite.
                aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
    return aliases


def _resolve_call(node: ast.Call, aliases: dict[str, str]) -> str:
    """Nom du module reellement appele, alias resolus (`_rnd.randint` -> `random.randint`)."""
    raw = ast.unparse(node.func)
    head, _, rest = raw.partition(".")
    real = aliases.get(head)
    if real is None:
        return raw
    return f"{real}.{rest}" if rest else real


def _nondeterminism_sources(node: ast.AST, aliases: dict[str, str] | None = None) -> tuple[str, ...]:
    """Sources de non-determinisme detectees dans le corps de ``node``.

    Si le corps fixe lui-meme la graine (`random.seed(<litteral>)`), le hasard
    redevient reproductible : on ne signale alors pas `random`.
    """
    found: dict[str, str] = {}
    seeds_fixed = False
    aliases = aliases or {}
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = _resolve_call(sub, aliases)
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
    """La docstring contient-elle un exemple EXECUTABLE (et non une simple mention) ?

    La version precedente testait `">>>" in docstring`. Consequence mesuree sur ce
    depot meme : une docstring qui MENTIONNE `>>>` dans sa prose declenchait la regle
    « les exemples de la docstring sont satisfaits », et cette regle echouait faute
    d'exemple reel a executer — un fichier parfaitement correct etait declare
    fautif. On interroge donc l'analyseur de doctest lui-meme : une seule source de
    verite pour « y a-t-il un exemple ? », c'est la condition pour ne jamais accuser
    a tort.
    """
    doc = ast.get_docstring(node)
    if not doc or ">>>" not in doc:
        return False
    return bool(docstring_examples(doc))


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
#: Comparaison de resultats, PARTAGEE par les controles de reproductibilite de
#: fonction et de methode. Deux copies divergeraient un jour — et une divergence
#: ici, c'est soit une fausse accusation, soit un faux positif.
_SAME_HELPERS = '''
def _jio_opaque(value):
    """La valeur est-elle un OBJET a identite, sans egalite par valeur ?

    `object.__eq__` ne compare que l'identite. Pour une fabrique de generateurs, de
    classes ou de sessions, produire une instance NEUVE a chaque appel est le
    comportement NORMAL : l'identite ne dit rien sur la reproductibilite.
    """
    if type(value) in (int, float, str, bool, bytes, complex, type(None), tuple, list, dict, set, frozenset):
        return False
    return getattr(type(value), "__eq__", None) is object.__eq__


def _jio_meme(_a, _b):
    """Egalite par VALEUR, recursive, qui ne conclut pas sur les objets opaques.

    La version precedente comparait `('valeur', objet) == ('valeur', objet)` : sur un
    objet sans egalite de valeur, Python retombait sur l'identite et l'artefact etait
    declare « non reproductible » — faux. Constate sur des bibliotheques reelles :
    `TextWrapper().extra_indent(...)` (click) rend un gestionnaire de contexte neuf a
    chaque appel, `cmp_using(...)` (attrs) rend une classe neuve. Aucun des deux n'est
    un defaut.
    """
    if _a is _b:
        return True
    if _jio_opaque(_a) and _jio_opaque(_b):
        return type(_a) is type(_b)          # on ne peut pas conclure : on se tait
    if isinstance(_a, (list, tuple)) and isinstance(_b, (list, tuple)):
        return (
            isinstance(_a, type(_b)) and len(_a) == len(_b)
            and all(_jio_meme(x, y) for x, y in zip(_a, _b))
        )
    if isinstance(_a, dict) and isinstance(_b, dict):
        if set(_a) != set(_b):
            return False
        return all(_jio_meme(_a[k], _b[k]) for k in _a)
    if isinstance(_a, (set, frozenset)) and isinstance(_b, (set, frozenset)):
        if any(_jio_opaque(x) for x in _a):
            return len(_a) == len(_b)
        return _a == _b
    try:
        return bool(_a == _b)
    except Exception:
        return True                          # comparaison impossible : on ne condamne pas


def _jio_same(_x, _y):
    # Un resultat est un couple ("valeur", v) ou ("erreur", type, message).
    if _x[0] != _y[0]:
        return False
    return _jio_meme(_x[1:], _y[1:])
'''

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


{helpers}


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


{helpers}


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
_jio_stdout_defaut = {stdout_defaut}
import doctest as _jio_doc
_jio_fn = globals().get({name!r})
assert callable(_jio_fn), "entree {name!r} absente ou non appelable"
_jio_tests = [
    _t for _t in _jio_doc.DocTestFinder().find(_jio_fn, name=_jio_fn.__name__) if _t.examples
]
assert _jio_tests, "aucun exemple exploitable dans la docstring de {name}"

# On COLLECTE la sortie de doctest au lieu de l'effacer. La version precedente
# levait un message generique (« N exemples contredisent le code ») qui MASQUAIT
# la cause reelle. Consequence constatee sur un vrai projet : une dependance
# absente de l'environnement etait presentee comme un mensonge de l'auteur.
_jio_buf = []
_jio_runner = _jio_doc.DocTestRunner(verbose=False)
for _t in _jio_tests:
    _jio_runner.run(_t, out=_jio_buf.append)
if _jio_runner.failures:
    _jio_lines = [l.rstrip() for l in "".join(_jio_buf).splitlines() if l.strip()]
    _jio_brut = "".join(_jio_lines)
    # Le message doit PORTE LA VALEUR ATTENDUE. Les trois dernieres lignes du tampon
    # donnent souvent « 0 | Got: | -5 » : l'attendu manque, et l'auteur du code lit
    # un echec sans savoir a quoi son code devait repondre. On reprend donc
    # explicitement la ligne « Expected: » quand le desaccord est decisif.
    _jio_attend = next((l for l in _jio_lines if "Expected:" in l), "")
    _jio_tail = " | ".join(_jio_lines[-3:])[:400]
    if _jio_attend and _jio_attend not in _jio_tail:
        _jio_tail = (_jio_attend + " | " + _jio_tail)[:400]
    # Deux echecs qui ne prouvent RIEN contre l'artefact, constates sur des
    # bibliotheques reelles :
    #   * `NameError` : l'exemple suppose un objet fourni par l'environnement de test
    #     (`console`, `vi`...). Des projets executent leurs doctests avec des fixtures
    #     (pytest --doctest-modules) ; l'exemple n'est pas faux, il n'est pas isole.
    #   * « Expected nothing » : l'exemple ILLUSTRE un appel sans en annoncer la
    #     sortie. C'est une docstring pedagogique, pas une specification.
    # On les signale comme RESERVE : l'outil dit qu'il n'a pas pu conclure, il
    # n'accuse pas. Un faux positif ici rendrait l'outil inutilisable sur du vrai code.
    # Un echec DECISIF ne doit pas etre masque par un echec non concluant qui vit
    # a cote, dans la meme docstring. Consequence mesuree sur une classe reelle :
    #
    #     >>> c.ajouter(-5)      <- sortie non annoncee : « Expected nothing »
    #     >>> c.valeur           <- « Expected: 0, Got: -5 » : DECISIF
    #
    # La ligne pedagogique suffisait a faire classer l'ensemble en RESERVE, et le
    # mensonge du code passait. Or les deux echecs sont bien dans le tampon : il
    # suffit de regarder si l'un d'eux est decisif.
    # « Expected nothing / Got: ... » n'est PAS decisif : la sortie n'etait pas
    # annoncee. Un vrai desaccord s'ecrit « Expected: » (deux points), suivi de la
    # valeur attendue. Pas de `re` ici : ce code tourne dans un espace de noms neuf,
    # et un `import re` oublie a produit un `NameError` -- donc un faux KO.
    # Troisieme echec qui ne prouve RIEN contre l'artefact, constate sur une
    # bibliotheque reelle (packaging) : l'exemple attend une TRACEBACK.
    #
    #     >>> Specifier("lolwat")
    #     Traceback (most recent call last):
    #         ...
    #     packaging.specifiers.InvalidSpecifier: Invalid specifier: 'lolwat'
    #
    # Le bac a sable execute l'artefact sous un nom SYNTHETIQUE : la traceback reelle
    # commence par `InvalidSpecifier:` et non `packaging.specifiers.InvalidSpecifier:`,
    # donc doctest compare deux textes qui ne peuvent pas coincider — alors que le type
    # leve est le BON. On rejoue donc les memes exemples avec `IGNORE_EXCEPTION_DETAIL`
    # (le mecanisme prevu par doctest pour ce cas exact : il compare le NOM DE LA CLASSE
    # et ignore le chemin du module et le message). Si tout passe ainsi, l'exemple est
    # verifie quant au type : c'est une RESERVE, pas une accusation. Si un autre
    # desaccord subsiste, il est decisif et l'echec reste un echec.
    if _jio_runner.failures and "Traceback (most recent call last)" in _jio_brut:
        _jio_buf2 = []
        _jio_runner2 = _jio_doc.DocTestRunner(
            verbose=False, optionflags=_jio_doc.IGNORE_EXCEPTION_DETAIL
        )
        # Les objets de test sont RECONSTRUITS, pas rejoues. Reexecuter le meme `DocTest`
        # n'est pas idempotent : mesure faite ici, le second passage levait
        # `NameError: name 'Specifier' is not defined` — les globales du test ne
        # survivaient pas a la premiere execution, et la reprise echouait pour une raison
        # qui n'avait rien a voir avec ce qu'elle verifiait. Un `DocTestFinder` neuf coute
        # une lecture d'AST et redonne a chaque exemple l'espace de noms du module.
        _jio_tests2 = [
            _t for _t in _jio_doc.DocTestFinder().find(_jio_fn, name=_jio_fn.__name__)
            if _t.examples
        ]
        for _t in _jio_tests2:
            _jio_runner2.run(_t, out=_jio_buf2.append)
        if not _jio_runner2.failures:
            raise AssertionError(
                "[RESERVE] %d exemple(s) de docstring : le type d'exception leve est bien "
                "celui annonce, seul le nom QUALIFIE du module differe (le bac a sable "
                "execute l'artefact sous un nom synthetique) : %s"
                % (_jio_runner.failures, _jio_tail)
            )

    # Quatrieme cas, meme famille : l'exemple ecrit dans un flux LIE A L'IMPORT.
    # `def f(file=sys.stdout)` capture la sortie standard d'AVANT le test ; doctest la
    # remplace pendant l'execution, ne voit rien, et annonce « Got nothing » alors que
    # l'artefact fait exactement ce que sa docstring promet. Mesure sur
    # `pyparsing.show_best_practices`. On ne peut pas capturer ce que le code a deja lie :
    # c'est notre facon de mesurer qui est en cause, donc reserve et non accusation.
    if _jio_stdout_defaut and "Got nothing" in _jio_brut:
        raise AssertionError(
            "[RESERVE] %d exemple(s) de docstring : la sortie attendue passe par un flux "
            "lie a l'import (`file=sys.stdout` par defaut), que le bac a sable ne peut pas "
            "capter : %s" % (_jio_runner.failures, _jio_tail)
        )

    _jio_decisif = "Expected:" in _jio_brut and "Got:" in _jio_brut
    if "NameError" in _jio_brut:
        # L'exemple suppose un objet fourni par l'environnement de test (console,
        # vi...). On ne peut rien conclure du tout : le code n'a meme pas tourne.
        raise AssertionError(
            "[RESERVE] %d exemple(s) de docstring non concluants pour nous "
            "(l'exemple suppose un objet fourni par l'environnement de test) : %s"
            % (_jio_runner.failures, _jio_tail)
        )
    if "Expected nothing" in _jio_brut and not _jio_decisif:
        # Exemple d'illustration, sans sortie annoncee, et RIEN de decisif a cote :
        # une docstring pedagogique, pas une specification. On ne l'accuse pas.
        raise AssertionError(
            "[RESERVE] %d exemple(s) de docstring non concluants pour nous "
            "(exemple d'illustration, sans sortie annoncee) : %s"
            % (_jio_runner.failures, _jio_tail)
        )
    raise AssertionError(
        "%d exemple(s) de docstring en echec : %s" % (_jio_runner.failures, _jio_tail)
    )
'''


def _determinism_check(name: str, plan: list[list[object]]) -> str:
    """Source du controle de reproductibilite. Point d'entree UNIQUE.

    Deux sites d'appel formataient le gabarit chacun de son cote : en ajoutant le
    bloc d'aide `helpers`, un seul a ete mis a jour, et l'autre a plante —
    `analyse impossible : 'helpers'`, constate en scannant un vrai projet. Une
    fonction unique rend cette classe d'erreur impossible.
    """
    return _CHECK_DETERMINISM.format(
        name=name, plans=_plan_source(plan), helpers=_SAME_HELPERS
    )


def _method_stability_check(name: str, method: str, plan: list[list[object]]) -> str:
    """Source du controle de stabilite d'une methode. Point d'entree UNIQUE."""
    return _CHECK_METHOD_STABLE.format(
        helpers=_SAME_HELPERS, name=name, method=method, plans=_plan_source(plan)
    )


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
    aliases = _import_aliases(tree)
    defs = {n.name: n for n in _top_level_defs(tree)}
    classes = _class_defs(tree)
    names = _public_functions(tree)
    # Les fixtures sortent de l'audit : voir `_est_une_fixture`. On les COMPTE pour
    # pouvoir le DIRE : un fichier ou l'on n'a rien verifie ne doit pas ressembler a un
    # fichier ou tout va bien.
    fixtures = tuple(nom for nom in names if _est_une_fixture(defs[nom]))
    if fixtures:
        names = tuple(nom for nom in names if nom not in fixtures)
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
        if fixtures:
            return DerivedSpec(
                spec=Spec(
                    mission="audit d'un artefact Python",
                    rules=(),
                    under_specified=(
                        "ce fichier ne declare que des fixture(s) "
                        f"({', '.join(fixtures)}) : une fixture n'est pas appelable "
                        "directement par construction, donc il n'y a rien d'executable a "
                        "verifier ici. Ce n'est pas un defaut du fichier.",
                    ),
                ),
                notes=(f"{len(fixtures)} fixture(s) exclue(s) de l'audit",),
                preamble=preamble,
            )
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
    derived: list[str] = []

    # Une exclusion non dite est un audit partiel presente comme complet. Les fixtures sont
    # hors du champ de ces regles — on l'ECRIT, avec la raison et les noms.
    if fixtures:
        under.append(
            f"{len(fixtures)} fixture(s) hors audit ({', '.join(fixtures)}) : une fixture "
            "pytest n'est pas appelable directement par construction, donc les questions "
            "« appelable » et « reproductible » ne s'y appliquent pas. Ce n'est pas un "
            "defaut du fichier."
        )

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
    nondet = _nondeterminism_sources(node, aliases)
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
        checks[r2] = _determinism_check(chosen, plan)
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
        checks[r3] = _CHECK_DOCTESTS.format(
            name=chosen, stdout_defaut=repr(_lie_la_sortie_standard(node))
        )
        notes.append(
            "docstring : les exemples ecrits par l'auteur servent de specification executable"
        )
    else:
        under.append(
            f"aucun exemple `>>>` dans la docstring de {chosen} : le comportement "
            "attendu n'est pas specifie par l'auteur"
        )

    # ------------------------------------------------------------------ #
    # Etendue reelle de l'audit.
    #
    # Avant : UNE fonction par fichier. Consequence mesuree sur un vrai projet :
    # un bug injecte dans une deuxieme fonction documentee n'etait jamais vu, et
    # l'audit pouvait rendre un verdict « propre » a tort. On audite desormais
    # toutes les fonctions qui portent des exemples `>>>`, dans la limite d'un
    # budget declare (le nombre de regles est visible dans le rapport).
    # ------------------------------------------------------------------ #
    documented = [n for n in names if n != chosen and _has_doctest(defs[n])]
    audited = [chosen]
    for name in documented[:_MAX_AUDITED_FUNCTIONS - 1]:
        audited.append(name)
        code_call = f"A-001:{name}"
        rules.append(
            Rule(
                id=code_call,
                statement=f"L'entree {name!r} est appelable.",
                kind=RuleKind.CONTRACT,
            )
        )
        checks[code_call] = _CHECK_CALLABLE.format(name=name)

        node_n = defs[name]
        plan_n, blocked_n = _static_plan(node_n)
        nondet_n = _nondeterminism_sources(node_n, aliases)
        if plan_n is not None and not nondet_n:
            code_det = f"A-002:{name}"
            rules.append(
                Rule(
                    id=code_det,
                    statement=(
                        f"Reproductibilite : appels identiques de {name} sur les "
                        "sondes derivees renvoient le meme resultat, ou la meme erreur."
                    ),
                    kind=RuleKind.ADVISORY if env_risk else RuleKind.PROPERTY,
                )
            )
            checks[code_det] = _determinism_check(name, plan_n)

        code_doc = f"A-003:{name}"
        rules.append(
            Rule(
                id=code_doc,
                statement=f"Chaque exemple de la docstring de {name} produit le resultat annonce.",
                kind=RuleKind.TEST,
            )
        )
        checks[code_doc] = _CHECK_DOCTESTS.format(
            name=name, stdout_defaut=repr(_lie_la_sortie_standard(defs[name]))
        )

    if len(audited) > 1:
        notes.append(
            f"{len(audited)} fonctions auditees : {', '.join(audited)} "
            f"(plafond {_MAX_AUDITED_FUNCTIONS}, reglable)"
        )

    # Non-determinisme INVISIBLE : une fonction non auditée qui depend du hasard
    # ou de l'horloge peut contaminer l'API publique sans que la regle de
    # reproductibilite le voie. On le declare comme reserve avec sa localisation
    # au lieu de laisser croire que l'artefact est entierement reproductible.
    hidden_hazards: list[str] = []
    for fname, fnode in defs.items():
        if not isinstance(fnode, (ast.FunctionDef, ast.AsyncFunctionDef)) or fname in audited:
            continue
        sources = _nondeterminism_sources(fnode, aliases)
        if sources:
            hidden_hazards.append(f"{fname} ({', '.join(sources)})")
    if hidden_hazards:
        under.append(
            "non-determinisme hors des fonctions auditees : "
            + "; ".join(hidden_hazards[:4])
            + " -> si l'API publique en depend, la reproductibilite n'est PAS prouvee ici"
        )

    uncovered = [n for n in names if n not in audited]
    if uncovered:
        under.append(f"non couvert par cet audit : {', '.join(uncovered)}")

    under.append(
        "la conformite au besoin metier n'est PAS verifiable sans specification "
        "externe : fournir des oracles (--task) ou des exemples (`>>>`)"
    )
    # ------------------------------------------------------------------ #
    # Proprietes derivees du code (axe P).
    #
    # Les regles precedentes verifient des EXEMPLES : les `>>>` de l'auteur et la
    # reproductibilite des sondes. Or un artefact peut passer tous les exemples et
    # violer une propriete evidente (`return nums.sort()` renvoie la liste triee en
    # apparence, mais modifie l'entree de l'appelant et casse le contrat). La
    # litterature est nette : exemples seuls 68,75 % de detection, proprietes seules
    # 68,75 %, les deux combines 81,25 %.
    #
    # Cote cout : la derivation est STATIQUE (lecture de la signature et du nom,
    # aucun modele, aucun appel reseau). Chaque propriete tient en un programme
    # execute dans le bac a sable, exactement comme les autres regles, et le nombre
    # de fonctions couvertes est borne ci-dessous.
    # ------------------------------------------------------------------ #
    for name in audited[:_MAX_PROPERTY_FUNCTIONS]:
        node_p = defs.get(name)
        if node_p is None:
            continue
        for prop in derive_properties(node_p, name, module_functions=defs):
            rule_id = f"{prop.id}:{name}"
            if rule_id in checks:
                continue
            rules.append(
                Rule(
                    id=rule_id,
                    statement=f"{prop.statement} [derivee du code, sans exemple fourni]",
                    kind=RuleKind.PROPERTY,
                )
            )
            checks[rule_id] = prop.check
            derived.append(f"{prop.name} sur {name}")

    if derived:
        notes.append(
            f"proprietes derivees et executees : {', '.join(derived[:6])}"
            + (f" (+{len(derived) - 6} autres)" if len(derived) > 6 else "")
        )
    else:
        under.append(
            "aucune propriete derivable ici (annotations ou noms insuffisants) : "
            "non-mutation, idempotence et aller-retour NON verifies"
        )

    under.append(
        "totalite (toute entree valide rend un resultat) et type de retour ne sont "
        "PAS prouvables statiquement : declares, jamais presumes, sans effet sur le verdict"
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
        checks[rid] = _CHECK_DOCTESTS.format(
            name=name, stdout_defaut=repr(_lie_la_sortie_standard(node))
        )
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
            checks[rid] = _method_stability_check(name, method.name, plan)
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
