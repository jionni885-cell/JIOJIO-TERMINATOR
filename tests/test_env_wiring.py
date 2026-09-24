"""La documentation et le code ne doivent plus pouvoir diverger.

Constat a l'origine de ce fichier, mesure et non suppose : sur les 17 variables
documentees dans `.env.example`, **11 n'etaient lues nulle part**. Le fichier
promettait des reglages qui n'existaient pas — plus grave qu'une absence de
documentation, puisque l'utilisateur croit regler le systeme.

Deux corrections ont suivi : cabler ce qui avait deja un parametre reel derriere,
supprimer ce qui ne correspondait a rien (dont deux variables de securite pour des
interrupteurs inexistants). Ce test est la troisieme moitie de la correction : sans
lui, le meme ecart se recreuse au prochain ajout.

C'est aussi un test de la revue : un relecteur ne peut plus oublier d'accorder
`.env.example` avec le code, la suite echoue a sa place.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
CODE_DIRS = (ROOT / "jio", ROOT / "scripts")

#: Variables fournies par d'autres outils (pas par JIO) : documentees comme
#: "reconnues automatiquement", donc legitimement lues sans etre definies ici.
#: Ecrites PAR JIO dans l'environnement du bac a sable (marqueur), jamais lues
#: depuis l'environnement de l'utilisateur : ce n'est pas un reglage.
_EXPORTED_BY_JIO = {"JIO_SANDBOX"}

_FOREIGN = {
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_BASE_URL",
    "XDG_CONFIG_HOME",
    "HERMES_SKILL_DIR",
}

_VAR = re.compile(r"\bJIO_[A-Z0-9_]+\b")


def _sources() -> list[Path]:
    out: list[Path] = []
    for directory in CODE_DIRS:
        out.extend(
            p for p in directory.rglob("*") if p.suffix in {".py", ".sh"} and "__pycache__" not in p.parts
        )
    return sorted(out)


#: Une ligne de REGLAGE : `VAR=valeur`, eventuellement commentee (`# VAR=valeur`).
#: On ne lit pas la prose : le fichier *explique* la suppression de variables de
#: securite inexistantes, et les citer dans un commentaire n'est pas les documenter.
_SETTING = re.compile(r"^\s*#?\s*(JIO_[A-Z0-9_]+)\s*=", re.MULTILINE)


def _documented() -> set[str]:
    return set(_SETTING.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _read_by_code() -> set[str]:
    found: set[str] = set()
    for path in _sources():
        found.update(_VAR.findall(path.read_text(encoding="utf-8", errors="replace")))
    return found


def test_aucune_variable_documentee_nest_morte() -> None:
    """Chaque variable documentee doit etre REELLEMENT lue par le code.

    C'est le test qui aurait attrape les 11 variables fantomes. Une variable
    documentee et jamais lue est un mensonge par omission : l'utilisateur croit
    agir sur le systeme, et le systeme l'ignore.
    """
    documented = _documented()
    read = _read_by_code()
    # Une FAMILLE documentee (`JIO_BIN_<NOM>`) est couverte si le code lit le
    # prefixe : le nom exact est construit dynamiquement (`f"JIO_BIN_{name.upper()}"`)
    # et ne peut pas apparaitre litteralement dans la source.
    families = {name for name in read if name.endswith("_")}
    ghosts = sorted(
        name for name in documented - read
        if not any(name.startswith(prefix) for prefix in families)
    )

    assert ghosts == [], (
        "variables documentees mais jamais lues par le code : "
        + ", ".join(ghosts)
        + " — soit les cabler, soit les supprimer de .env.example (mesure : "
        "11 variables fantomes au dernier audit, dont 2 reglages de securite "
        "pour des interrupteurs inexistants)"
    )


def test_aucune_variable_lue_nest_indocumentee() -> None:
    """Inversement : une variable lue par le code doit etre documentee.

    Sinon le reglage existe mais personne ne peut le decouvrir, et il faudra lire
    le code pour savoir que le comportement est configurable.
    """
    documented = _documented()
    read = _read_by_code()

    # Les prefixes dynamiques (`f"JIO_BIN_{name.upper()}"`) et les variables
    # documentees sous forme de famille sont exclus : ils ne nomment pas une
    # variable precise a la lecture du code source.
    undocumented = sorted(
        name
        for name in read - documented
        if not name.endswith("_")
        and name not in _FOREIGN
        and name not in _EXPORTED_BY_JIO
    )

    assert undocumented == [], (
        "variables lues par le code mais absentes de .env.example : "
        + ", ".join(undocumented)
    )


def test_les_reglages_de_securite_ne_sont_pas_pretendument_optionnels() -> None:
    """Aucun interrupteur de securite ne doit etre presente comme desactivable.

    Audit : `JIO_HOSTILE_CONTENT` et `JIO_ALLOW_FETCH` etaient documentes sans
    qu'aucun code ne les lise. Ils donnaient l'illusion de pouvoir fermer une
    porte inexistante. La securite de JIO est une doctrine non desactivable par
    variable d'environnement : ce test l'empeche de redevenir un reglage d'apparence.
    """
    documented = _documented()

    for ghost in ("JIO_HOSTILE_CONTENT", "JIO_ALLOW_FETCH", "JIO_ALLOW_NETWORK"):
        assert ghost not in documented, (
            f"{ghost} est documentee alors qu'aucun code ne la lit : "
            "un interrupteur de securite inexistant est plus dangereux que pas "
            "d'interrupteur du tout"
        )


def test_le_fichier_dexemple_ne_change_pas_le_comportement_silencieusement() -> None:
    """Copier `.env.example` vers `.env` ne doit RIEN changer.

    `JIO_COST_WEIGHT=0.00` etait ecrit sans commentaire dans le fichier d'exemple :
    le copier desactivait silencieusement la prise en compte du cout. Un fichier
    d'exemple qui modifie le comportement n'est plus un exemple, c'est une
    configuration imposee par surprise.
    """
    actives = [
        line.split("=")[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" in line
    ]

    assert actives == [], (
        "lignes actives dans .env.example (elles doivent toutes etre commentees) : "
        + ", ".join(actives)
    )
