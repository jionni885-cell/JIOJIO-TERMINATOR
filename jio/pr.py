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


#: Limite de longueur du corps d'une issue ou d'une pull request sur GitHub : 65 536
#: caracteres. Elle n'est pas contournable, et c'est justement pour cela qu'elle doit etre
#: DECLAREE : un rapport qui depasse la limite et se fait couper par la plateforme ne le dit
#: pas, et le lecteur croit avoir tout lu.
LIMITE_GITHUB = 65_536


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


def _blocs(racine: Path, depuis: str | None) -> tuple[list[Commit], str, str]:
    """L'entete et l'index du document, separes des sections — pour pouvoir tronquer PROPREMENT.

    Separer les blocs est ce qui rend la troncature honnete : on garde l'entete (qui annonce la
    base et le nombre de commits) et la LISTE complete des commits en une ligne chacun, puis le
    detail de ceux qui tiennent — au lieu de couper au milieu d'une phrase.
    """
    from .chiffres import mesurer

    ref, sha = base(racine, depuis)
    liste = commits(racine, ref)
    try:
        m = mesurer(racine)
    except RuntimeError as exc:
        # La mesure peut ECHOUER sans que le rapport doive disparaitre : un depot sans dossier
        # de tests n'a aucun compteur a donner, et `mesurer` le dit en levant. Refuser de
        # produire le corps serait disproportionne ; l'annoncer en clair ne l'est pas — un
        # compteur faux ou absent doit se VOIR, jamais se deviner dans un nombre a zero.
        entete_mesure = (
            "**Compteurs non mesures dans cette racine** — "
            f"{str(exc)[:120]} Le rapport reste valable : il vient des commits."
        )
    else:
        entete_mesure = Versions(
            tests=int(m.get("tests", 0)), competences=int(m.get("competences", 0)),
            agents=int(m.get("agents", 0)), objectifs=int(m.get("objectifs", 0)),
        ).ligne()

    entete = "\n".join([
        INTRO.rstrip(), "", entete_mesure, "", "---", "",
        f"**Base du rapport** : `{ref}` (`{sha}`) — **{len(liste)} commit(s)** resumes "
        "ci-dessous. Ce document est genere (`jio pr`) : il se reconstruit a l'identique "
        "depuis le depot.",
        "", "---", "",
    ])
    if not liste:
        entete += (
            "**Aucun commit au-dessus de la base.** La branche courante n'a rien a resumer "
            "ici : soit elle EST la base, soit la ref donnee a `--depuis` est deja a jour. "
            "`jio pr --depuis <ref>` choisit une autre origine.\n\n---\n\n"
        )
    index = ["## Les commits couverts", ""]
    index += [f"{rang}. `{c.court}` {c.sujet}" for rang, c in enumerate(liste, start=1)]
    index += [""]
    return liste, entete, "\n".join(index)


def _sections(liste: list[Commit]) -> list[str]:
    """Une section par commit, numerotee : c'est la partie qu'on peut avoir a tronquer."""
    blocs: list[str] = []
    for rang, commit in enumerate(liste, start=1):
        blocs.append("\n".join(
            filter(None, [f"## {rang}. {commit.sujet}", "", f"`{commit.court}`", "", commit.corps])
        ))
    return blocs


PIED = """## Comment lire ce document

Chaque section est un commit, reproduit sans retouche. Un commit qui annonce un chiffre le tire
d'une commande du depot : `jio coherence` (les 9 controles), `jio chiffres` (les compteurs de la
documentation), `jio mutants` (ce que la suite de tests protege reellement) et `jio claims` (les
affirmations verifiables des documents).

**Rien ici n'est merge automatiquement.** La PR reste ouverte jusqu'a decision."""


def construire(
    racine: Path | str,
    *,
    depuis: str | None = None,
    limite: int | None = None,
    complet: str = "",
) -> str:
    """Le corps de la PR : intro, compteurs mesures, une section par commit, pied.

    `limite` : longueur maximale en caracteres. Au-dela, le document n'est pas coupe en plein
    milieu : il garde l'entete, la LISTE COMPLETE des commits (une ligne chacun) et le detail
    des commits les PLUS RECENTS qui tiennent, puis DECLARE combien de sections ont ete
    retirees et ou lire le rapport entier (`complet`).

    Ce choix est delibere. Couper a la fin garderait le recit des fondations et perdrait l'etat
    courant ; tout resumer a une ligne ferait perdre les mesures, qui sont l'interet du
    document. Un lecteur qui juge une PR a besoin du DERNIER travail en detail, et de savoir
    exactement ce qu'il ne voit pas.
    """
    liste, entete, index = _blocs(Path(racine), depuis)
    sections = _sections(liste)

    def assembler(gardees: list[str], note: str = "") -> str:
        morceaux = [entete, index, ""]
        if note:
            morceaux += [note, ""]
        morceaux += ["---", ""]
        for bloc in gardees:
            morceaux += [bloc, "", "---", ""]
        morceaux += [PIED, ""]
        return "\n".join(morceaux)

    complet_texte = assembler(sections)
    if limite is None or len(complet_texte) <= limite:
        return complet_texte

    # Troncature DECLAREE : on part de la fin (les commits les plus recents) et on remonte tant
    # que le total tient, en reservant la place de la note qui annonce la troncature elle-meme —
    # sinon la note ferait depasser la limite qu'elle explique.
    reserve = 400
    gardees: list[str] = []
    for bloc in reversed(sections):
        candidat = [bloc, *gardees]
        if len(assembler(candidat, "x" * reserve)) > limite:
            break
        gardees = candidat
    omises = len(sections) - len(gardees)
    # Le rapport complet N'EST PAS recopie ailleurs : il se REGENERE. Dupliquer 237 Ko de
    # journal dans un fichier du depot donnerait deux copies a tenir a jour — et la deuxieme
    # serait perimee sans que rien ne le dise. La commande, elle, ne peut pas etre perimee.
    ou = (
        f" Le rapport complet a ete ecrit dans `{complet}`."
        if complet else
        " Le rapport complet se regenere par `jio pr` (aucune option : il imprime sur la "
        "sortie standard)."
    )
    note = (
        f"**Rapport tronque, et il le dit.** Les {len(sections)} commits sont tous listes "
        f"ci-dessus, une ligne chacun ; le DETAIL n'est donne que pour les {len(gardees)} plus "
        f"recents, parce que le corps d'une pull request est limite a {LIMITE_GITHUB} "
        f"caracteres sur GitHub.{ou} Les {omises} sections omises sont les {omises} plus "
        "anciennes."
    )
    if len(assembler([], note)) > limite:
        # La limite demandee est plus petite que le SQUELETTE du rapport (intro, liste des
        # commits, pied). Aucun detail ne peut donc tenir — et le dire est la seule chose
        # honnete a faire : un document qui annonce une limite qu'il ne respecte pas apprend au
        # lecteur a ne plus croire ses propres chiffres.
        note += (
            f" **La limite demandee ({limite} caracteres) est plus petite que le squelette du "
            f"rapport ({len(assembler([], note))}), qui ne peut pas etre reduit sans perdre la "
            "liste des commits : aucun detail n'a donc pu etre affiche.**"
        )
    return assembler(gardees, note)


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
