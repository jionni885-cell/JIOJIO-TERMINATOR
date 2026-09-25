"""Les commandes citees par un document existent-elles vraiment ?

Un README qui nomme `jio scan --stricte` (au lieu de `--strict`) envoie l'utilisateur droit
dans un `error: unrecognized arguments`. C'est un mensonge verifiable, et il est detectable
avec l'ORACLE le plus fiable qui existe : le parseur d'arguments du programme lui-meme. Pas
de modele, pas d'heuristique — la commande citee existe, ou elle n'existe pas.

Ce que la verification fait, exactement
---------------------------------------
1. Elle extrait les invocations citees entre backticks qui commencent par `jio`
   (`jio scan .`, `jio claims README.md`, `jio artifacts --mcp opencode`).
2. Elle resout la SOUS-COMMANDE contre le parseur reel. Inconnue -> refutation.
3. Elle verifie chaque option longue (`--strict`) contre la sous-commande. Inconnue ->
   refutation, avec la liste des options proches (`--stricte` -> `--strict`).

Ce qu'elle ne fait PAS, et pourquoi
----------------------------------
Elle ne verifie **pas** les arguments positionnels (`jio claims README.md` : le fichier
doit-il exister ? non — un document a le droit de citer un fichier d'exemple). Elle ne
verifie pas non plus les commandes d'AUTRES outils (`ruff check`, `pytest`) : JIO ne
connait pas leur surface, et pretendre le contraire produirait exactement les faux positifs
que ce projet passe son temps a retirer.

Les commandes peuvent avoir des OPTIONS deja parsees : `jio mcp --prove 2>&1 | grep ...`
doit etre accepte, et un `--flag` place apres un `|` appartient a l'autre programme : on
s'arrete au premier caractere de coquille.
"""

from __future__ import annotations

import argparse
import difflib
import re
from dataclasses import dataclass

__all__ = ["CommandeCitee", "commandes_citees", "verifier_commande", "parser_reel"]

#: Une invocation ECRITE EN PLEINE PHRASE, entre backticks : `jio scan . --strict`.
#: C'est une INSTRUCTION : le document dit a l'utilisateur de la taper.
_MOTIF = re.compile(
    r"`(?:[$\s]*)(?:(?:python3?|py)\s+-m\s+)?jio\s+(?P<corps>[^`\n]{1,160})`"
)

#: Les blocs de code fermes. Une invocation qui y figure est un EXEMPLE — souvent la
#: demonstration d'une erreur. On la verifie quand meme, mais elle ne condamne pas : c'est
#: la meme distinction que pour les calculs cites. Sans elle, la page qui documente une
#: ancienne option fausse (`jio scan --stricte`) serait declaree non conforme, et le seul
#: moyen de la rendre conforme serait de ne plus en parler.
_BLOC = re.compile(r"```[A-Za-z0-9_+-]*\n(?P<code>.*?)```", re.DOTALL)

#: Une invocation en debut de ligne : le cas d'un bloc de terminal.
#: `$ jio scan .` et `jio scan .` sont la meme chose.
_MOTIF_LIGNE = re.compile(
    r"^[\s$>]*(?:(?:python3?|py)\s+-m\s+)?jio\s+(?P<corps>[^\n`]{1,160})",
    re.MULTILINE,
)

#: Ce qui TERMINE une invocation : une coquille, un commentaire, une redirection, un
#: enchainement. Sans cette coupe, `jio run "x" | jq .id` ferait chercher une option `jio`
#: dans la ligne de commande de `jq`.
_FIN = re.compile(r"[|;&#<>]|\s2>|\s>|\n")

@dataclass(frozen=True)
class CommandeCitee:
    """Une invocation `jio ...` trouvee dans un document."""

    extrait: str
    sous_commande: str
    options: tuple[str, ...]
    position: int
    #: Vrai si l'invocation figure dans un bloc de code : un exemple, pas une consigne.
    dans_bloc: bool = False


def parser_reel() -> argparse.ArgumentParser:
    """Le parseur de la CLI reelle. Importe tardivement : evite un cycle a l'import."""
    from ..cli import build_parser

    try:
        return build_parser()
    except TypeError:  # signature historique sans argument
        return build_parser()


def _sous_parsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Les sous-commandes declarees dans un parseur, quel que soit le niveau."""
    for action in parser._actions:  # noqa: SLF001 - API interne stable et documentee
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return dict(action.choices)
    return {}


def _options_de(parser: argparse.ArgumentParser) -> set[str]:
    """Les options longues d'un parseur (`--strict`, `--no-learn`...)."""
    trouvees: set[str] = set()
    for action in parser._actions:
        trouvees.update(opt for opt in action.option_strings if opt.startswith("--"))
    return trouvees


def _decoupe(corps: str) -> tuple[str, tuple[str, ...]]:
    """Separe la sous-commande de ses options longues."""
    morceaux = corps.split()
    sous = morceaux[0].strip(",")
    options = tuple(
        morceau if morceau.startswith("--") else morceau.split("=")[0]
        for morceau in morceaux[1:]
        if morceau.startswith("--")
    )
    return sous, options


def commandes_citees(texte: str) -> tuple[CommandeCitee, ...]:
    """Extrait les invocations `jio ...` d'un document, dans l'ordre d'apparition.

    Deux sources, et la distinction compte :

      * entre BACKTICKS, en pleine phrase : une instruction. Le document demande de taper
        cette commande, donc une faute y est bloquante ;
      * dans un BLOC de code : un exemple, souvent la demonstration d'une erreur. On la
        verifie quand meme — une coquille dans un exemple de README coute cher — mais elle
        est signalee, jamais bloquante.

    C'est la POSITION qui decide, et non la facon dont l'invocation a ete trouvee : un
    exemple de sortie de programme cite ses commandes entre backticks, donc a l'interieur
    d'un bloc. Un premier jet faisait gagner la mention entre backticks, ce qui accusait
    la documentation de ce verificateur pour avoir ose montrer une commande fausse.

    Une meme invocation trouvee plusieurs fois n'est verifiee qu'une fois, et c'est la
    mention la plus ENGAGEANTE qui l'emporte : une phrase qui ordonne quelque chose ne peut
    pas etre desamorcee par un exemple, plus bas, qui la repetterait dans un bloc.
    """
    blocs = [(m.start(), m.end()) for m in _BLOC.finditer(texte)]

    def dans_un_bloc(position: int) -> bool:
        return any(debut <= position < fin for debut, fin in blocs)

    par_cle: dict[tuple[str, tuple[str, ...]], CommandeCitee] = {}

    for bloc in _BLOC.finditer(texte):
        for correspondance in _MOTIF_LIGNE.finditer(bloc.group("code")):
            corps = _FIN.split(correspondance.group("corps").strip())[0].strip()
            if not corps:
                continue
            sous, options = _decoupe(corps)
            par_cle.setdefault(
                (sous, options),
                CommandeCitee(
                    extrait=corps, sous_commande=sous, options=options,
                    position=bloc.start() + correspondance.start(), dans_bloc=True,
                ),
            )

    for correspondance in _MOTIF.finditer(texte):
        corps = _FIN.split(correspondance.group("corps").strip())[0].strip()
        if not corps:
            continue
        sous, options = _decoupe(corps)
        position = correspondance.start()
        citation = dans_un_bloc(position)
        ancienne = par_cle.get((sous, options))
        # False gagne : si l'invocation apparait UNE fois en pleine phrase, le document
        # l'affirme, meme s'il la montre aussi dans un bloc.
        engageante = citation and (ancienne.dans_bloc if ancienne else True)
        par_cle[(sous, options)] = CommandeCitee(
            extrait=corps, sous_commande=sous, options=options,
            position=position, dans_bloc=engageante,
        )

    return tuple(sorted(par_cle.values(), key=lambda c: c.position))


def verifier_commande(commande: CommandeCitee, racine_parseur=None) -> str | None:
    """Rend un message de REFUTATION, ou `None` si la commande existe.

    Aucun avertissement « peut-etre » : soit la sous-commande est dans le parseur, soit
    elle n'y est pas. C'est tout l'interet d'avoir le programme comme oracle.
    """
    parser = racine_parseur if racine_parseur is not None else parser_reel()
    sous_parsers = _sous_parsers(parser)

    # Une OPTION de premier niveau (`jio --version`) n'est pas une sous-commande. Sans ce
    # branchement, `jio --version` etait declare INCONNU alors qu'il fonctionne — un faux
    # positif sur le document qui le cite, exactement ce que la mesure des documents reels
    # doit servir a attraper avant d'affirmer quoi que ce soit.
    if commande.sous_commande.startswith("--"):
        connues = _options_de(parser)
        if commande.sous_commande in connues:
            return None
        proches = difflib.get_close_matches(
            commande.sous_commande, sorted(connues), n=3, cutoff=0.6
        )
        piste = f" — peut-etre `{proches[0]}` ?" if proches else ""
        return (
            f"option de premier niveau INCONNUE : `{commande.sous_commande}`"
            f"{piste}. Une option inventee produit « unrecognized arguments »."
        )

    if commande.sous_commande not in sous_parsers:
        proches = difflib.get_close_matches(
            commande.sous_commande, sorted(sous_parsers), n=3, cutoff=0.6
        )
        piste = f" — peut-etre `jio {proches[0]}` ?" if proches else ""
        return (
            f"commande INCONNUE : `jio {commande.sous_commande}` n'existe pas dans cette "
            f"version de la CLI{piste}. Citer une commande inexistante envoie "
            "l'utilisateur dans une erreur."
        )

    connues = _options_de(sous_parsers[commande.sous_commande]) | _options_de(parser)
    for option in commande.options:
        if option not in connues:
            proches = difflib.get_close_matches(option, sorted(connues), n=3, cutoff=0.6)
            piste = f" — peut-etre `{proches[0]}` ?" if proches else ""
            return (
                f"option INCONNUE : `{option}` sur `jio {commande.sous_commande}`"
                f"{piste}. Une option inventee produit « unrecognized arguments »."
            )
    return None
