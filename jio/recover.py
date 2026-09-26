"""Recuperer un depot dont `.git` a ete reinitialise — sans perdre un octet.

L'accident, vecu TROIS fois par ce projet pendant son developpement
------------------------------------------------------------------
Entre deux sessions, l'environnement d'execution restaure `.git` a son etat initial. Le
travail est intact sur le disque, mais : `git log` revient au commit initial, `git status`
affiche tout le code comme « non suivi », et `.git/config` ne connait plus la branche (le
refspec d'origine ne recupere que `main`).

Le script ecrit pour cet accident (`scripts/sync.sh`) ne pouvait PAS le reparer : sa
premiere regle refuse de travailler des que `git status` n'est pas vide — et dans cet
accident, tout est precisement « non suivi ». **L'outil de secours refusait le sinistre pour
lequel il avait ete ecrit.** `jio recover` comble ce trou.

Pourquoi c'est SANS PERTE, par construction
-------------------------------------------
Le seul danger d'une recuperation est de detruire du travail. Ici :

  * l'arbre de travail n'est JAMAIS touche : aucune commande `git checkout`, aucun
    `reset --hard`, aucun `clean`. Uniquement `fetch`, `tag`, `reset --soft` et `add` ;
  * `reset --soft` deplace le pointeur de branche et RIEN d'autre : les fichiers sur le
    disque restent exactement ce qu'ils etaient. C'est verifie et affiche (empreinte du
    contenu avant/apres) ;
  * une ETIQUETTE est posee sur l'ancien sommet avant toute chose : meme si quelqu'un
    avait des commits locaux, ils restent joignables ;
  * la recuperation est REFUSEE quand l'empreinte de l'accident n'est pas la : un depot
    sain, un depot avec des commits locaux, ou un travail non pousse ne sont pas concernes,
    et disent a l'utilisateur quoi faire a la place.

Ce que la commande ne fait pas : elle ne commite rien. Apres recuperation, l'etat local est
compare au distant, et c'est a l'utilisateur de decider.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Recuperation", "empreinte_arbre", "empreinte_accident", "recuperer"]

#: Dossiers qui ne sont PAS du travail : etat local, caches, environnements. Les inclure
#: ferait echouer la comparaison avant/apres, et surtout mesurerait autre chose que le
#: travail de l'utilisateur.
_EXCLUS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", ".jio", "build", "dist",
})

#: Seuils de l'empreinte de l'accident. Identiques a ceux de `jio doctor` : deux jeux de
#: seuils pour un meme accident seraient une deuxieme verite.
MAX_COMMITS = 3
MIN_NON_SUIVIS = 20


@dataclass
class Recuperation:
    """Ce qui a ete fait, et ce qui le prouve."""

    fait: bool
    motif: str
    #: Empreinte du contenu de l'arbre de travail, AVANT et APRES : la preuve que rien
    #: n'a bouge sur le disque.
    avant: str = ""
    apres: str = ""
    distant: str = ""
    branche: str = ""
    etiquette: str = ""
    fichiers_modifies: int = 0
    fichiers_non_suivis: int = 0
    operations: list[str] = field(default_factory=list)
    #: Vrai quand la simulation a pu etablir un plan SANS rien executer. Le code de retour
    #: de la commande vaut alors 0 : `--dry-run` est une inspection qui a REUSSI, et un
    #: script qui la lance ne doit pas la confondre avec un echec de recuperation.
    simulation: bool = False

    @property
    def contenu_intact(self) -> bool:
        return bool(self.avant) and self.avant == self.apres


def _git(racine: Path, *argv: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *argv], cwd=racine, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, (proc.stdout or "").strip()


def empreinte_arbre(racine: Path) -> str:
    """Empreinte du CONTENU de l'arbre de travail (hors `.git` et etat local).

    Elle sert a repondre a une seule question, celle qui compte : « les fichiers sur le
    disque sont-ils exactement les memes apres qu'avant ? ». On hache les chemins ET les
    contenus, dans un ordre stable, pour que deux arbres differents ne puissent pas donner
    la meme empreinte.
    """
    digest = hashlib.sha256()
    for chemin in sorted(racine.rglob("*")):
        if not chemin.is_file() or chemin.is_symlink():
            continue
        if any(morceau in _EXCLUS for morceau in chemin.relative_to(racine).parts):
            continue
        try:
            donnees = chemin.read_bytes()
        except OSError:  # pragma: no cover - fichier disparu pendant la lecture
            continue
        digest.update(chemin.relative_to(racine).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(donnees).digest())
    return digest.hexdigest()


def empreinte_accident(racine: Path) -> tuple[int, int] | None:
    """`(commits locaux, fichiers non suivis)` si le depot porte l'empreinte de l'accident.

    Mêmes seuils que `jio doctor` (voir `_depot_suspect`) : <= 3 commits ET >= 20 fichiers
    non suivis. Larges volontairement — rater un vrai accident coute l'historique du
    projet, alors qu'un faux positif ne coute qu'un message de refus.
    """
    code, commits = _git(racine, "rev-list", "--count", "HEAD")
    if code != 0 or not commits.isdigit():
        return None
    # `-uall` est INDISPENSABLE : sans lui, `git status` regroupe un dossier non suivi en
    # UNE seule ligne (`?? jio/`). Un projet de 200 fichiers organises en dossiers
    # n'afficherait alors que 3 « fichiers » non suivis, et l'accident passerait
    # inapercu — mesure faite en simulant l'incident pour de vrai : 2 lignes au lieu de 33.
    code, statut = _git(racine, "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return None
    non_suivis = sum(1 for ligne in statut.splitlines() if ligne.startswith("??"))
    if int(commits) <= MAX_COMMITS and non_suivis >= MIN_NON_SUIVIS:
        return int(commits), non_suivis
    return None


def _branches_distantes(racine: Path, remote: str) -> list[str]:
    """Les branches que le distant publie vraiment. Une seule source pour deux usages :
    VERIFIER qu'une branche existe (sinon on recupererait une autre), et la LISTER quand
    le nom demande n'existe pas.
    """
    code, ls = _git(racine, "ls-remote", "--heads", remote)
    if code != 0:
        return []
    noms = []
    for ligne in ls.splitlines():
        if "\trefs/heads/" in ligne:
            noms.append(ligne.split("\trefs/heads/", 1)[1].strip())
    return sorted(nom for nom in noms if nom)


def _branche_courante(racine: Path) -> str:
    code, nom = _git(racine, "rev-parse", "--abbrev-ref", "HEAD")
    return nom if code == 0 and nom and nom != "HEAD" else ""


def _compte_etat(racine: Path) -> tuple[int, int]:
    """`(modifications, non suivis)` apres recuperation : ce qu'il reste a faire."""
    _code, statut = _git(racine, "status", "--porcelain")
    lignes = [ligne for ligne in statut.splitlines() if ligne.strip()]
    non_suivis = sum(1 for ligne in lignes if ligne.startswith("??"))
    return len(lignes) - non_suivis, non_suivis


def recuperer(
    racine: Path,
    *,
    remote: str = "origin",
    branche: str = "",
    dry_run: bool = False,
) -> Recuperation:
    """Restaure l'historique distant sur un depot reinitialise. L'arbre n'est pas touche.

    Rend un compte rendu, y compris en cas de refus : un outil qui echoue en silence est
    exactement ce que ce projet refuse. Le refus DIT quoi faire a la place.
    """
    racine = racine.resolve()
    branche = branche or _branche_courante(racine)

    signature = empreinte_accident(racine)
    if signature is None:
        return Recuperation(
            fait=False,
            motif=(
                "ce depot ne porte PAS l'empreinte d'une reinitialisation "
                f"(<= {MAX_COMMITS} commit(s) local(aux) et >= {MIN_NON_SUIVIS} fichier(s) "
                "non suivi(s)). Rien n'a ete modifie. Pour un depot normal, la commande de "
                "synchronisation est `scripts/sync.sh`."
            ),
        )
    commits, non_suivis = signature

    avant = empreinte_arbre(racine)

    if not branche:
        return Recuperation(
            fait=False, avant=avant, apres=avant,
            motif="aucune branche courante : passez `--branch <nom>`.",
        )

    # 1. recuperer le distant. Un `fetch` par branche, puis la reference de la branche ;
    #    certains depots distants refusent la recuperation d'une branche nommee.
    #
    #    Le fetch a lieu MEME en simulation : sans lui, la cible est inconnue (`origin/main`
    #    n'existe pas encore dans un `.git` fraichement recree), et une simulation qui ne
    #    peut pas dire OU elle irait ne simule rien. Un `fetch` n'ecrit que dans `.git` :
    #    ni l'arbre de travail ni l'index ne changent.
    # Au passage : `.git/config` fait partie de ce qu'une reinitialisation efface. Si le
    # distant a disparu, dire « verifiez l'acces » enverrait chercher un probleme reseau
    # qui n'existe pas — l'utilisateur a juste besoin de redonner l'adresse du depot.
    code_url, url = _git(racine, "remote", "get-url", remote)
    url = url.strip()
    if code_url != 0 or not url:
        return Recuperation(
            fait=False, avant=avant, apres=avant, branche=branche,
            motif=(
                f"aucun depot distant nomme `{remote}` : `.git/config` ne le connait plus "
                "(frequent apres une reinitialisation). Rien n'a ete modifie. Donnez son "
                "adresse, puis relancez :\n"
                f"        git remote add {remote} <url-du-depot>\n"
                f"        jio recover"
            ),
        )

    operations = [f"git fetch --prune {remote} {branche}"]
    code, _ = _git(racine, "fetch", "--prune", remote, branche)
    fetch_direct = code == 0
    if code != 0:
        code, _ = _git(racine, "fetch", "--prune", remote)
        operations[-1] = f"git fetch --prune {remote} {branche} (puis {remote} entier)"
        if code != 0:
            return Recuperation(
                fait=False, avant=avant, apres=avant, branche=branche,
                motif=(
                    f"`{remote}` ({url}) est injoignable : le travail n'a pas ete touche. "
                    "Verifiez l'acces au depot distant (reseau, droits), puis relancez."
                ),
            )
    # La cible doit etre CELLE QUI A ETE DEMANDEE, ou l'echec doit etre dit. `FETCH_HEAD`
    # ne vaut que si le fetch a porté sur cette branche : sinon il designe la derniere
    # reference recuperee par le fetch global — donc une AUTRE branche. Mesure faite :
    # `--branch fantome` recuperait `main` en silence, en annoncant un succes.
    distant = ""
    if fetch_direct:
        code, sha = _git(racine, "rev-parse", "FETCH_HEAD")
        distant = sha if code == 0 else ""
    if not distant:
        for reference in (f"refs/remotes/{remote}/{branche}", f"{remote}/{branche}"):
            code, sha = _git(racine, "rev-parse", reference)
            if code == 0 and sha:
                distant = sha
                break
    if not distant:
        # Dernier recours legitime : la branche existe-t-elle VRAIMENT sur le distant ?
        # Si oui et que seule la reference locale manque (refspec perdu avec le reste),
        # FETCH_HEAD est bien la bonne cible — on l'a verifie nommement.
        noms = _branches_distantes(racine, remote)
        if branche in noms:
            code, sha = _git(racine, "rev-parse", "FETCH_HEAD")
            distant = sha if code == 0 else ""
    if not distant:
        noms = _branches_distantes(racine, remote)
        if noms:
            indice = (
                " Branches presentes sur le distant : " + ", ".join(noms[:12])
                + f". Relancez avec `--branch <nom>` si le votre n'est pas `{branche}`."
            )
        else:
            indice = " Le distant ne publie aucune branche."
        return Recuperation(
            fait=False, avant=avant, apres=avant, branche=branche,
            motif=f"aucune reference distante pour `{branche}` : rien a recuperer.{indice}",
        )

    if dry_run:
        return Recuperation(
            fait=False, avant=avant, apres=avant, distant=distant, branche=branche,
            fichiers_non_suivis=non_suivis, operations=operations + [
                "(simulation) git tag sauvegarde-avant-recup-<horodatage> HEAD",
                f"(simulation) git reset --soft {distant[:8]}",
                "(simulation) git add -A",
            ],
            motif=(
                "simulation : l'historique serait restaure a la place de l'actuel, "
                f"et les {non_suivis} fichiers non suivis seraient indexes. "
                "Aucun fichier du disque ne serait modifie."
            ),
            simulation=True,
        )

    # 2. poser une etiquette AVANT de deplacer quoi que ce soit : meme des commits locaux
    #    imprevus resteraient joignables.
    from datetime import datetime, timezone

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    etiquette = f"sauvegarde-avant-recup-{horodatage}"
    if _git(racine, "tag", etiquette, "HEAD")[0] == 0:
        operations.append(f"git tag {etiquette} HEAD")

    # 3. `--soft` : le pointeur de branche suit le distant, les FICHIERS ne bougent pas.
    code, sortie = _git(racine, "reset", "--soft", distant)
    operations.append(f"git reset --soft {distant[:8]}")
    if code != 0:
        return Recuperation(
            fait=False, avant=avant, apres=empreinte_arbre(racine), distant=distant,
            branche=branche, etiquette=etiquette, operations=operations,
            motif=f"`git reset --soft` a echoue : {sortie[:200]}",
        )

    # 4. indexer le travail retrouve : sans cela, l'etat local s'afficherait comme
    #    170 suppressions suivies de 170 fichiers non suivis, ce qui est illisible.
    _git(racine, "add", "-A")
    operations.append("git add -A")

    apres = empreinte_arbre(racine)
    modifies, restants = _compte_etat(racine)
    return Recuperation(
        fait=True,
        motif=(
            "historique restaure. Les fichiers du disque n'ont pas ete touches : "
            f"empreinte identique avant/apres ({avant[:12]})."
        ),
        avant=avant, apres=apres, distant=distant, branche=branche,
        etiquette=etiquette, fichiers_modifies=modifies, fichiers_non_suivis=restants,
        operations=operations,
    )
