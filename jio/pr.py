"""Le corps de la PR : un RAPPORT GENERE a partir des commits, jamais recopie.

POURQUOI CE MODULE EXISTE, et il existe a cause d'un incident reel. Le corps de la pull
request vivait dans un fichier unique, hors du depot, ecrit a la main section par section
pendant plusieurs jours. Un evenement exterieur a efface ce fichier ; le tour suivant a
pousse une PR dont le corps ne contenait plus que la derniere section ajoutee, et l'historique
des corps n'est pas consultable par l'API GitHub. Autrement dit : **le seul endroit ou vivait
la synthese de 82 commits etait aussi le seul endroit qui n'en gardait aucune copie.** Un
rapport qui ne peut pas etre reconstruit n'est pas un rapport, c'est un fichier qu'on espere.

La source de verite etait pourtant sous les yeux : les COMMITS. Chacun porte son sujet, son
raisonnement et ses mesures. Ce module les relit et en fait le corps de la PR — dans l'ordre,
numerote, avec les compteurs mesures AU MOMENT de la generation.

Trois proprietes en decoulent, et ce sont elles qui valent :

  * **reconstructible** — le corps se regenere par une commande, a tout moment, depuis le
    depot lui-meme. S'il disparait, il revient ; s'il est perime, une commande le rafraichit ;
  * **verifiable** — les chiffres annonces (tests, competences, agents, objectifs) ne sont pas
    ecrits par l'auteur : ils viennent de `jio.chiffres.mesurer`, la meme mesure que celle du
    controle de documentation. Un nombre faux dans le corps de la PR casse le meme jour ;
  * **honnete sur lui-meme** — le corps declare sa base (`<ref> (<sha>)`), donc on sait
    EXACTEMENT ce qui est resume. Un corps qui ne dit pas d'ou il part ne dit rien.

Ce que ce module ne fait pas : il ne trie pas, ne resume pas, ne choisit pas les meilleurs
commits. Il rapporte. Un filtre editoral ferait de ce rapport une plaidoirie.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Commit", "base", "commits", "construire", "ecrire", "Versions"]

#: Separateurs de controle peu probables dans un message de commit : le protocole de lecture
#: reste analysable sans jamais dependre d'un guillemet ou d'un retour a la ligne du message.
#: `\x1e` (record separator) entre deux commits, `\x1f` (unit separator) entre deux champs.
#:
#: Le premier jet utilisait `\x00`, et l'erreur a ete instructive : `subprocess` REFUSE un
#: argument contenant un octet nul (« embedded null byte »), parce que les arguments d'un
#: processus sont des chaines C. Un separateur doit donc etre un caractere que `execve` accepte.
_FIN_ENREGISTREMENT = "\x1e"
_FIN_CHAMP = "\x1f"

INTRO = """## Ce que fait cette PR

Amene au monde executable la conception decrite dans `docs/` : un **noyau anti-erreur** pour
agents d'IA — mesure, auto-audite, sans aucune dependance obligatoire.

> **Objectif, formule honnetement :** aucune erreur ne passe silencieusement. Elle est detectee,
> localisee, attribuee, corrigee — ou le systeme **s'abstient explicitement**. Zero erreur est
> impossible (Rice 1953, Turing 1936) ; l'absence d'erreur *silencieuse* est atteignable et
> mesurable.

Les sections ci-dessous sont **les commits eux-memes**, dans l'ordre, reproduits integralement.
Chacun dit le defaut trouve, la mesure qui l'a montre, le correctif et ce qui le verrouille. Le
corps du document est un **rapport genere** (`jio pr`) : il se reconstruit depuis le depot, et
les compteurs annonces viennent d'une mesure faite a l'instant de la generation.

### Verifier en trois commandes

```
jio coherence      # 9 controles : tout ce que ce depot affirme est-il encore vrai ?
jio clarify --mesure   # la porte de clarification, mesuree sur son banc d'objectifs
jio bench          # le gain du harness a budget d'appels strictement egal
```
"""


@dataclass(frozen=True)
class Commit:
    """Un commit, tel qu'il sera publie : son sujet, son corps, et son identite."""

    sha: str
    sujet: str
    corps: str

    @property
    def court(self) -> str:
        return self.sha[:7]


@dataclass(frozen=True)
class Versions:
    """Les compteurs mesures au moment de la generation — jamais saisis a la main."""

    tests: int
    competences: int
    agents: int
    objectifs: int

    def ligne(self) -> str:
        return (
            f"**{self.tests} tests verts · {self.competences} competences · "
            f"{self.agents} agents · {self.objectifs} objectifs · "
            "aucune cle API requise · `jio` en un seul point d'entree.**"
        )


class GitAbsent(RuntimeError):
    """`git` n'est pas utilisable ici : ce n'est pas une erreur de l'appelant, c'est un fait."""


def _git(racine: Path, *arguments: str) -> str:
    """Lance git et rend sa sortie. Toute panne devient `GitAbsent`, jamais un traceback."""
    try:
        proc = subprocess.run(
            ["git", *arguments], cwd=str(racine), capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - environnement
        raise GitAbsent(f"git n'a pas pu etre lance : {exc}") from exc
    if proc.returncode != 0:
        raise GitAbsent((proc.stderr or proc.stdout).strip()[:200] or "git a echoue")
    return proc.stdout


def base(racine: Path | str, depuis: str | None = None) -> tuple[str, str]:
    """Rend `(ref, sha)` de la base : ce qui existe AVANT cette branche.

    L'ordre de recherche est volontaire, et il est prudent : ce que l'appelant demande, puis
    la branche par defaut du depot distant, puis `main`, puis `master`. Faute de tout cela, le
    PREMIER commit : un rapport qui part de la racine du depot est exhaustif, donc jamais faux —
    il peut etre plus long que necessaire, ce qui n'est pas un mensonge.
    """
    racine = Path(racine)
    if depuis:
        return depuis, _git(racine, "rev-parse", "--short", depuis).strip()
    for candidat in ("origin/HEAD", "origin/main", "origin/master", "main", "master"):
        try:
            sha = _git(racine, "rev-parse", "--short", candidat).strip()
        except GitAbsent:
            continue
        # `origin/HEAD` est une reference SYMBOLIQUE : `rev-parse` la resout, mais le nom
        # employe dans `git log` doit etre celui qui existe.
        return candidat, sha
    premier = _git(racine, "rev-list", "--max-parents=0", "HEAD").strip().splitlines()
    if not premier:  # pragma: no cover - depot sans commit
        raise GitAbsent("aucun commit dans ce depot")
    return premier[-1], premier[-1][:7]


def commits(racine: Path | str, depuis: str | None = None) -> list[Commit]:
    """Les commits de la branche courante, du PLUS ANCIEN au plus recent."""
    racine = Path(racine)
    ref, _sha = base(racine, depuis)
    brut = _git(
        racine,
        "log", f"{ref}..HEAD", "--reverse",
        f"--format=%H{_FIN_CHAMP}%s{_FIN_CHAMP}%b{_FIN_ENREGISTREMENT}",
    )
    out: list[Commit] = []
    for enregistrement in brut.split(_FIN_ENREGISTREMENT):
        if not enregistrement.strip():
            continue
        morceaux = enregistrement.strip("\n").split(_FIN_CHAMP)
        if len(morceaux) < 2:  # pragma: no cover - sortie inattendue
            continue
        sha, sujet = morceaux[0].strip(), morceaux[1].strip()
        corps = morceaux[2].strip() if len(morceaux) > 2 else ""
        out.append(Commit(sha=sha, sujet=sujet, corps=corps))
    return out


def construire(racine: Path | str, *, depuis: str | None = None) -> str:
    """Le corps complet de la PR : intro, compteurs mesures, un section par commit, pied."""
    from .chiffres import mesurer

    racine = Path(racine)
    ref, sha = base(racine, depuis)
    liste = commits(racine, ref)
    # La mesure peut ECHOUER sans que le rapport doive disparaitre : un depot sans dossier de
    # tests n'a aucun compteur a donner, et `mesurer` le dit en levant. Refuser de produire le
    # corps pour cette raison serait disproportionne ; l'annoncer en clair ne l'est pas — un
    # compteur faux ou absent doit se VOIR, jamais se deviner dans un nombre a zero.
    try:
        m = mesurer(racine)
    except RuntimeError as exc:
        m = {}
        lignes_mesure = (
            "**Compteurs non mesures dans cette racine** — "
            f"{str(exc)[:120]} Le rapport reste valable : il vient des commits."
        )
        versions = None
    else:
        lignes_mesure = ""
        versions = Versions(
            tests=int(m.get("tests", 0)), competences=int(m.get("competences", 0)),
            agents=int(m.get("agents", 0)), objectifs=int(m.get("objectifs", 0)),
        )

    lignes = [INTRO.rstrip(), ""]
    lignes.append(versions.ligne() if versions is not None else lignes_mesure)
    lignes += ["", "---", ""]
    lignes.append(
        f"**Base du rapport** : `{ref}` (`{sha}`) — **{len(liste)} commit(s)** resumes ci-dessous. "
        "Ce document est genere (`jio pr`) : il se reconstruit a l'identique depuis le depot."
    )
    if not liste:
        # Un corps vide sans explication serait un rapport qui ne dit pas qu'il ne dit rien.
        lignes += [
            "**Aucun commit au-dessus de la base.** La branche courante n'a rien a resumer "
            "ici : soit elle EST la base, soit la ref donnee a `--depuis` est deja a jour. "
            "`jio pr --depuis <ref>` choisit une autre origine.",
            "", "---", "",
        ]
    for rang, commit in enumerate(liste, start=1):
        lignes.append(f"## {rang}. {commit.sujet}")
        lignes.append("")
        lignes.append(f"`{commit.court}`")
        lignes.append("")
        if commit.corps:
            lignes.append(commit.corps)
            lignes.append("")
        lignes.append("---")
        lignes.append("")
    lignes += [
        "## Comment lire ce document",
        "",
        "Chaque section est un commit, reproduit sans retouche. Un commit qui annonce un chiffre",
        "le tire d'une commande du depot : `jio coherence` (les 9 controles), `jio chiffres` (les",
        "compteurs de la documentation), `jio mutants` (ce que la suite de tests protege",
        "reellement) et `jio claims` (les affirmations verifiables des documents).",
        "",
        "**Rien ici n'est merge automatiquement.** La PR reste ouverte jusqu'a decision.",
        "",
    ]
    return "\n".join(lignes)


def ecrire(chemin: Path | str, texte: str) -> tuple[Path | None, bool]:
    """Ecrit le corps, en CONSERVANT l'ancien s'il differait. Rend `(sauvegarde, ecrit)`.

    La sauvegarde n'est pas un ornement : l'incident qui a motive ce module est exactement une
    perte de ce fichier. Un ecrivain qui ecrase sans copie transforme une erreur de chemin en
    perte definitive. On n'ecrit rien si le contenu est identique — et on le DIT, sinon
    « rien n'a change » et « une ecriture a eu lieu » seraient indiscernables.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if chemin.is_file():
        ancien = chemin.read_text(encoding="utf-8")
        if ancien == texte:
            return None, False
        sauvegarde = chemin.with_name(chemin.name + ".avant-jio")
        sauvegarde.write_text(ancien, encoding="utf-8")
        chemin.write_text(texte, encoding="utf-8")
        return sauvegarde, True
    chemin.write_text(texte, encoding="utf-8")
    return None, True
