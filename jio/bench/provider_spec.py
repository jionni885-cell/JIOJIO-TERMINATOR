"""Quel modele fait tourner la mesure — et refuser de faire semblant.

Le banc de JIO mesure le gain du harness **a poids constants**. Par defaut, les reponses
sont simulees (aucune cle requise, mesure reproductible) et la VERIFICATION est reelle.

Mais une mesure sur un modele simule ne dit pas ce que vaut le harness sur VOTRE modele.
Il faut donc pouvoir brancher les CLI deja installes (`opencode`, `hermes`, `claude`,
`codex`, `gemini`), sans gerer la moindre cle API : l'authentification reste celle que
l'utilisateur a configuree.

Le point qui compte est le suivant : **si le modele demande n'est pas disponible, on
s'arrete**. Retomber silencieusement sur la simulation produirait un rapport qui a l'air
d'une mesure, avec un modele qui n'a jamais tourne — precisement le mensonge que ce projet
existe pour empecher. C'est pourquoi `resoudre()` ne rend jamais un fournisseur simule
quand on lui a demande un CLI.

Syntaxe des specifications :

    simule                la simulation deterministe (defaut)
    cli:opencode          un binaire connu, avec sa syntaxe non interactive
    cli:hermes
    cli:mon-outil         un binaire quelqu'un, si `JIO_CLI_MON_OUTIL_ARGV` est defini
    openai:gpt-x          un point d'acces compatible OpenAI (JIO_OPENAI_BASE / JIO_OPENAI_KEY)
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from ..core.errors import ProviderError
from ..providers.base import Provider
from ..providers.cli import CliProvider
from ..providers.registry import KNOWN_CLIS

__all__ = ["Fournisseur", "disponibles", "resoudre", "resoudre_liste"]

#: Modele simule : accepte sous plusieurs noms, parce qu'un utilisateur ne doit pas avoir
#: a deviner lequel est le bon.
_SIMULE = frozenset({"", "simule", "simulé", "sim", "simulation", "defaut", "défaut",
                     "deterministe", "déterministe"})


@dataclass(frozen=True)
class Fournisseur:
    """Ce qui a ete demande, et ce qui a ete obtenu."""

    spec: str
    genre: str                      # "simule" | "cli" | "openai"
    provider: Provider | None = None
    #: Plusieurs instances du meme modele : la boucle tire des candidats dans `generators`,
    #: et le panel a besoin d'autant de critiques que de personas.
    instances: int = 1
    note: str = ""

    @property
    def disponible(self) -> bool:
        # La simulation est disponible par construction : elle ne depend de rien. C'est
        # aussi la seule spec ou `provider` reste vide — le banc doit la construire avec
        # sa competence et sa banque de taches, qui ne sont pas connues ici.
        return self.genre == "simule" or self.provider is not None


def _cle_env(nom: str) -> str:
    """Le nom d'un binaire, transforme en cle de variable d'environnement.

    Un nom a tiret — comme `faux-modele` — ne peut pas s'ecrire tel quel en variable de
    shell : le tiret y est interdit. Sans normalisation, la variable que le message
    d'erreur demandait de definir etait... impossible a definir. Mesure faite en essayant.
    """
    return "".join(c if c.isalnum() else "_" for c in nom).upper()


def _env_cli(nom: str, suffixe: str) -> str | None:
    """Cherche `JIO_<SUFFIXE>_<NOM>` sous sa forme normalisee, puis brute."""
    return os.environ.get(f"JIO_{suffixe}_{_cle_env(nom)}") or os.environ.get(
        f"JIO_{suffixe}_{nom.upper()}"
    )


def _cli(nom: str) -> Provider:
    """Un CLI connu, ou un binaire quelconque decrit par `JIO_CLI_<NOM>_ARGV`."""
    spec = KNOWN_CLIS.get(nom)
    if spec is not None:
        binaire = _env_cli(nom, "BIN") or nom
        return CliProvider(
            binary=binaire, argv_template=spec["argv"], name=f"cli:{nom}", model=spec["model"]
        )

    # Un outil inconnu reste utilisable : il suffit de donner sa ligne de commande, avec
    # `{prompt}` la ou doit aller l'invite. Sans `{prompt}`, l'invite part sur l'entree
    # standard — plus sur avec les invites longues et les caracteres speciaux.
    gabarit = os.environ.get(f"JIO_CLI_{_cle_env(nom)}_ARGV") or os.environ.get(
        f"JIO_CLI_{nom.upper()}_ARGV"
    )
    if not gabarit:
        connus = ", ".join(sorted(KNOWN_CLIS))
        raise ProviderError(
            f"CLI inconnu : {nom!r} (connus : {connus}). Pour un autre binaire, donnez sa "
            f"ligne de commande : JIO_CLI_{_cle_env(nom)}_ARGV='{nom} {{prompt}}' "
            f"(ou '{nom}' seul : l'invite sera alors envoyee sur l'entree standard)"
        )
    binaire = _env_cli(nom, "BIN") or nom
    return CliProvider(
        binary=binaire, argv_template=gabarit, name=f"cli:{nom}", model=f"{nom}/default",
        use_stdin="{prompt}" not in gabarit,
    )


def resoudre(spec: str) -> Fournisseur:
    """Rend le fournisseur demande, ou LEVE une erreur explicite. Jamais de repli muet."""
    brut = (spec or "").strip()

    if brut.lower() in _SIMULE:
        return Fournisseur(
            spec="simule", genre="simule", instances=1, provider=None,
            note="reponses simulees deterministes ; la verification, elle, est reelle",
        )

    if brut.startswith("cli:"):
        nom = brut[4:].strip()
        if not nom:
            raise ProviderError("specification incomplete : `cli:<nom>` attend un binaire")
        provider = _cli(nom)
        if not shutil.which(provider.binary):  # type: ignore[attr-defined]
            raise ProviderError(
                f"binaire introuvable : {provider.binary!r}. Installez-le, ou indiquez son "
                f"chemin : JIO_BIN_{_cle_env(nom)}=/chemin/vers/{nom}. "
                "Aucun repli sur la simulation : un rapport qui n'a pas fait tourner le "
                "modele demande serait un mensonge."
            )
        return Fournisseur(
            spec=brut, genre="cli", provider=provider, instances=5,
            note=f"votre CLI {nom}, authentifie par vous ; 5 instances pour le panel",
        )

    if brut.startswith("openai:") or brut.startswith("openai-compat:"):
        from dataclasses import replace as _replace

        from ..providers.openai_compat import OpenAiCompatProvider
        from ..providers.registry import from_env

        modele = brut.split(":", 1)[1].strip() or "gpt"
        # On ne cree pas une DEUXIEME facon de configurer un point d'acces compatible
        # OpenAI : `from_env()` sait deja le faire depuis `JIO_OPENAI_BASE` (ou
        # `JIO_OLLAMA`) et une cle. Le premier jet de ce module lisait deux variables
        # inventees, qui n'existaient nulle part : l'utilisateur aurait suivi le message
        # d'erreur et rien n'aurait change. Le garde-fou du depot, qui compare les
        # variables LUES par le code a celles qui sont DOCUMENTEES, l'a attrape.
        candidats = [p for p in from_env() if isinstance(p, OpenAiCompatProvider)]
        if not candidats:
            raise ProviderError(
                "aucun point d'acces compatible OpenAI configure. Renseignez "
                "JIO_OPENAI_BASE (ou JIO_OLLAMA) et JIO_OPENAI_KEY — les memes variables "
                "que `jio providers` — ou utilisez `cli:<nom>` pour un outil deja "
                "authentifie. Aucun repli sur la simulation."
            )
        return Fournisseur(
            spec=brut, genre="openai", instances=5,
            provider=_replace(candidats[0], model=modele),
            note=f"point d'acces compatible OpenAI, modele {modele}",
        )

    raise ProviderError(
        f"specification de fournisseur inconnue : {brut!r}. Attendu : `simule`, "
        "`cli:<opencode|hermes|claude|codex|gemini|autre>` ou `openai:<modele>`."
    )


def resoudre_liste(specs: list[str] | tuple[str, ...]) -> list[Fournisseur]:
    """Resout PLUSIEURS specifications, dans l'ordre, sans doublon.

    Pourquoi plusieurs : le panel de red-team n'a de valeur que s'il est DECORRELE, et
    cinq appels au meme modele ne donnent pas cinq avis — le harness le detecte et le dit
    (« ce n'est pas un consensus, c'est un echo »). Avec deux ou trois modeles differents,
    la decorrelation devient possible, et le consensus redevient ce qu'il doit etre.

    Un benchmark, lui, doit faire varier UNE chose a la fois : `jio bench` garde donc une
    seule specification. La distinction est de principe, pas technique.
    """
    vus: set[str] = set()
    out: list[Fournisseur] = []
    for spec in specs:
        fournisseur = resoudre(spec)
        cle = fournisseur.spec
        if cle in vus:
            continue
        vus.add(cle)
        out.append(fournisseur)
    return out


def disponibles() -> list[tuple[str, bool]]:
    """Ce qui est reellement utilisable sur CETTE machine, avec le chemin trouve."""
    etat: list[tuple[str, bool]] = []
    for nom, spec in sorted(KNOWN_CLIS.items()):
        binaire = os.environ.get(f"JIO_BIN_{nom.upper()}") or nom
        etat.append((f"cli:{nom} ({spec['model']}) -> {binaire}", shutil.which(binaire) is not None))
    return etat
