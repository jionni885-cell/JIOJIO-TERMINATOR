"""Le monde où une preuve a ete produite : son sceau, et sa revision.

Un journal chaine par hachage prouve qu'un enregistrement n'a **pas ete altere**. Il ne
prouve pas que le monde n'a pas change depuis. Ces deux choses sont differentes, et les
confondre produit un mode d'echec precis, decrit et exploitable :

    une verification V est produite sur un etat du monde X_clair ;
    le monde est ensuite restaure (rollback, `git reset`, `jio recover`, edition manuelle)
    a un etat X_autre ;
    V reste disponible, intacte, verifiable — et porte pourtant sur un monde qui n'existe
    plus. La suite du travail peut alors s'appuyer sur V pour publier X_autre.

Ce n'est pas theorique : l'incident `.git` est arrive **trois fois** pendant ce projet, et
`jio recover` existe precisement pour restaurer un etat anterieur. L'article « Safe to
Resume? Breaking Execution Continuity of Agent Execution via Rollback » (arXiv 2608.29381)
classe ce defaut sous le nom de *inconsistent checkpoint state* : le contenu et les preuves
qui le decrivent sont restaures independamment.

La reponse tient en une ligne : **chaque enregistrement porte le sceau du monde ou il a ete
ecrit**, et un journal qui contient deux sceaux differents le dit.

D'ou **une seule mesure**, `sceau` : le contenu de chaque fichier, hache avec son chemin.
Elle sert au journal (chaque evenement dit sur quel monde il a ete ecrit) et a `jio recover`
(« aucun octet n'a bouge »). Deux metriques differentes auraient fini par ne plus etre
comparables entre elles.

Une variante plus rapide — hacher les metadonnees au lieu du contenu — a ete ecrite puis
jetee : sur le systeme de fichiers de ce bac a sable, `st_mtime_ns` **ne bouge pas** apres
une reecriture (cinq ecritures successives, la meme date au nanoseconde). Elle aurait rendu
une modification de contenu invisible. Le detail est dans `sceau`.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

__all__ = ["EXCLUSIONS", "sceau", "revision"]

#: Dossiers qui ne sont PAS du travail : etat local, caches, environnements. Les inclure
#: ferait echouer toute comparaison avant/apres (le simple fait d'executer un test ecrit un
#: cache) et mesurerait autre chose que le travail de l'utilisateur.
EXCLUSIONS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", ".jio", "build", "dist",
})


def _fichiers(racine: Path):
    """Les fichiers du travail, dans un ordre STABLE — sans entrer dans les exclusions.

    L'elagage se fait PENDANT le parcours, pas apres, et ce n'est pas un detail de style :
    `Path.rglob("*")` descendait d'abord dans tout, puis on filtrait — mesure sur ce depot,
    **3 609 fichiers parcourus pour 181 retenus**, 42 ms contre 2,5 ms. Une fonction appelee
    a chaque evenement d'une mission ne peut pas payer 20 fois le prix de ce qu'elle lit.

    L'ordre est trie profondeur d'abord : deux arbres differents ne doivent pas pouvoir
    donner le meme sceau, et un parcours non trie rendrait la mesure dependante du systeme
    de fichiers.
    """
    racine = Path(racine)
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = sorted(d for d in sous_dossiers if d not in EXCLUSIONS)
        for nom in sorted(noms):
            chemin = Path(dossier) / nom
            if chemin.is_symlink():
                continue
            yield chemin


def sceau(racine: Path | str) -> str:
    """Le sceau du monde : le contenu de chaque fichier du travail, hache avec son chemin.

    Coute ~6 ms sur ce depot (181 fichiers, elagage pendant le parcours). C'est le prix a
    payer pour qu'un evenement puisse dire *sur quel monde* il a ete ecrit.

    **Une version plus rapide a ete ecrite, puis jetee.** Elle hachait les metadonnees
    (chemin, taille, date de modification) au lieu du contenu, en supposant qu'un `stat` est
    moins cher qu'une lecture. Deux constats l'ont tuee, mesures tous les deux sur cette
    machine :

      * elle n'etait PAS plus rapide une fois le parcours elague (3 ms contre 6 ms) ;
      * elle etait **aveugle** : sur le systeme de fichiers de ce bac a sable, `st_mtime_ns`
        ne bouge pas apres une reecriture. Cinq ecritures successives du meme fichier ont
        donne la meme date au nanoseconde pres — et, la taille etant inchangee, exactement
        le meme sceau.

    Autrement dit : une modification de contenu reelle aurait ete invisible. Un sceau qui
    rate ce qu'il doit attraper ne vaut pas 3 ms d'economie.

    Elle repond a une seule question, celle qui compte : « les fichiers sur le disque sont-ils
    exactement les memes ? » On hache les chemins ET les contenus pour que deux arbres
    differents ne puissent pas donner la meme empreinte — une permutation de deux fichiers
    identiques la change, ce qu'un simple total de hachages ne ferait pas.
    """
    racine = Path(racine)
    digest = hashlib.sha256()
    for chemin in _fichiers(racine):
        try:
            donnees = chemin.read_bytes()
        except OSError:  # pragma: no cover - fichier disparu pendant la lecture
            continue
        digest.update(chemin.relative_to(racine).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(donnees).digest())
    return digest.hexdigest()


def revision(racine: Path | str) -> str:
    """La revision git courante, ou une chaine vide s'il n'y en a pas.

    Le sceau dit « le contenu est le meme » ; la revision dit « le monde est le meme pour
    tout le monde ». Les deux sont utiles : deux machines au meme commit ont la meme
    revision et pas forcement le meme arbre de travail.
    """
    try:
        resultat = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(racine), capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git absent
        return ""
    if resultat.returncode != 0:
        return ""
    return (resultat.stdout or "").strip()
