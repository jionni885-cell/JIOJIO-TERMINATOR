"""Installer les competences la OU Hermes les lit — sans jamais ecraser les tiennes.

LE PROBLEME, et il est mesurable
--------------------------------
`jio artifacts --write` pose les competences dans le projet, sous `.hermes/skills/`. Hermes, lui,
lit `~/.hermes/skills/`. Entre les deux il y avait un `cp -r` a taper a la main, ecrit dans le
README — c'est-a-dire une etape que PERSONNE ne fait, et une bibliotheque de procedures qui reste
sur le disque sans jamais entrer dans la boucle de l'agent. L'integration en une commande
s'arretait juste avant l'endroit qui compte.

COPIE PAR DEFAUT, LIEN SUR DEMANDE — et la raison est un defaut vu en testant
----------------------------------------------------------------------------
L'idee naturelle etait le lien symbolique : il garde la copie et le depot en phase par
construction. Essaie, et le piege apparait tout de suite : `echo x > ~/.hermes/skills/.../SKILL.md`
sur un lien ecrit DANS LE FICHIER DU PROJET, puis `jio artifacts --write` l'ecrase. L'utilisateur
croit modifier sa copie ; il detruit une source generee — en silence, dans son dossier personnel.

Donc : COPIE par defaut, enregistree par empreinte (`.jio/hermes-install.json`). Une copie
enregistree permet exactement ce qu'il faut :

  * elle est a jour -> rien a faire ;
  * elle a change et l'empreinte enregistree correspond au contenu -> c'est l'ANCIENNE version de
    jio : on la met a jour, et on le dit ;
  * elle a change et l'empreinte ne correspond PLUS -> quelqu'un l'a ecrite (l'utilisateur) :
    on la PRESERVE, on la nomme, et on ne la touche jamais.

Le lien reste disponible (`lier=True`) pour qui veut la synchronisation permanente et sait ce
qu'il fait.

LA REGLE D'ECRITURE : celle du reste du depot, appliquee a un dossier qui n'est pas a nous
-------------------------------------------------------------------------------------------
Un fichier deja present n'est ecrase que si NOUS l'avons ecrit ET que personne n'y a touche —
verifie par empreinte, exactement comme `.jio/generated.json` le fait pour les artefacts du
projet. Sinon il est PRESERVE, et on le dit : c'est le fichier de quelqu'un d'autre, dans son
dossier personnel. Un installateur qui ecrase `~/.hermes/skills/.../SKILL.md` detruit du travail
que personne ne peut recuperer.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Rapport", "dossier_hermes", "installer", "desinstaller", "REGISTRE"]

#: Ce que nous avons installe chez l'utilisateur : chemin cible -> empreinte du fichier pose.
#: Il vit DANS le projet (a cote des autres etats de jio) pour qu'un `jio start` dans un autre
#: projet ne croie pas avoir installe ce que le premier a pose.
REGISTRE = ".jio/hermes-install.json"


def dossier_hermes() -> Path:
    """Ou Hermes lit ses competences, tel que l'outil le declare.

    Trois sources, dans l'ordre : `HERMES_SKILLS` (le dossier exact), `HERMES_HOME` (la racine de
    configuration), puis `~/.hermes`. Une variable d'environnement gagne toujours : c'est ce qui
    rend l'installation testable sans toucher au dossier personnel de qui lance les tests.
    """
    exact = os.environ.get("HERMES_SKILLS", "").strip()
    if exact:
        return Path(exact).expanduser()
    maison = os.environ.get("HERMES_HOME", "").strip()
    if maison:
        return Path(maison).expanduser() / "skills"
    return Path.home() / ".hermes" / "skills"


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


@dataclass
class Rapport:
    """Ce qui est arrive, classe par DECISION — jamais un total qui melange tout."""

    dossier: Path
    ignores: bool = False                  # pas de dossier Hermes : rien tente
    liens: list[str] = field(default_factory=list)        # installe par lien
    copies: list[str] = field(default_factory=list)       # installe par copie
    mises_a_jour: list[str] = field(default_factory=list)  # ancienne version de jio, remplacee
    deja: list[str] = field(default_factory=list)         # deja en phase
    preserves: list[str] = field(default_factory=list)    # a l'utilisateur : non touche

    @property
    def installes(self) -> int:
        return len(self.liens) + len(self.copies) + len(self.mises_a_jour)

    def resume(self) -> str:
        if self.ignores:
            return f"aucune installation : {self.dossier} n'existe pas"
        morceaux = []
        if self.liens:
            morceaux.append(f"{len(self.liens)} lien(s)")
        if self.copies:
            morceaux.append(f"{len(self.copies)} copie(s)")
        if self.mises_a_jour:
            morceaux.append(f"{len(self.mises_a_jour)} mise(s) a jour")
        if self.deja:
            morceaux.append(f"{len(self.deja)} deja en place")
        if self.preserves:
            morceaux.append(f"{len(self.preserves)} PRESERVE(S) (a vous)")
        return ", ".join(morceaux) or "rien a faire"


def _lire_registre(racine: Path) -> dict[str, str]:
    fichier = racine / REGISTRE
    if not fichier.is_file():
        return {}
    try:
        charge = json.loads(fichier.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un registre illisible est traite comme absent : dans le doute, on ne s'autorise pas a
        # ecraser. C'est le sens de la regle.
        return {}
    return {str(k): str(v) for k, v in charge.items()} if isinstance(charge, dict) else {}


def _ecrire_registre(racine: Path, registre: dict[str, str]) -> None:
    fichier = racine / REGISTRE
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(
        json.dumps(registre, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def installer(
    racine: Path, *, dossier: Path | None = None, lier: bool = False, creer: bool = False
) -> Rapport:
    """Installe les competences du projet chez Hermes. Idempotent, jamais destructeur.

    `lier=False` (defaut) : COPIE enregistree par empreinte. C'est le mode sur, et la raison est
    au-dessus (un lien fait qu'editer sa copie ecrase la source du projet).
    `lier=True` : lien symbolique, pour la synchronisation permanente.
    `creer` autorise la creation du dossier Hermes quand il n'existe pas encore. Par defaut on ne
    le cree PAS : ecrire dans le dossier personnel de quelqu'un qui n'a jamais lance Hermes serait
    une installation surprise. `jio start` le refuse donc par defaut, et le DIT.
    """
    cible = dossier or dossier_hermes()
    rapport = Rapport(dossier=cible)

    source = racine / ".hermes" / "skills"
    fichiers = sorted(p for p in source.rglob("*.md") if p.is_file()) if source.is_dir() else []
    if not fichiers:
        rapport.ignores = True
        return rapport

    if not cible.is_dir():
        if not creer:
            rapport.ignores = True
            return rapport
        cible.mkdir(parents=True, exist_ok=True)

    registre = _lire_registre(racine)
    for fichier in fichiers:
        relatif = fichier.relative_to(source)
        destination = cible / relatif
        texte = fichier.read_text(encoding="utf-8")
        empreinte = _empreinte(texte)
        cle = str(destination)

        remplace = False
        if destination.is_symlink():
            if destination.resolve() == fichier.resolve():
                rapport.deja.append(cle)
                registre[cle] = empreinte
                continue
            # Un lien qui ne pointe plus sur nous : c'est nous qui l'avons pose (un lien ne
            # nait pas tout seul ici) — on le retire au lieu de le suivre.
            destination.unlink()
            remplace = True
        elif destination.is_file():
            contenu = destination.read_text(encoding="utf-8", errors="replace")
            if contenu == texte:
                rapport.deja.append(cle)
                registre[cle] = empreinte
                continue
            if registre.get(cle) != _empreinte(contenu):
                # Le fichier existe, il differe, et ce n'est pas nous qui l'avons ecrit (ou
                # quelqu'un y a touche depuis) : c'est celui de l'utilisateur. On ne le touche
                # pas, et on le NOMME — dans son dossier personnel, un ecrasement silencieux
                # detruit un travail que personne ne peut recuperer.
                rapport.preserves.append(cle)
                continue
            # C'est une version PRECEDENTE de jio, intacte : la mettre a jour est le service
            # attendu, et c'est ce qui evite qu'une procedure corrigee reste perimee chez
            # l'utilisateur sans que personne ne le voie.
            destination.unlink()
            remplace = True

        destination.parent.mkdir(parents=True, exist_ok=True)
        pose = False
        if lier:
            try:
                destination.symlink_to(fichier)
                rapport.liens.append(cle)
                pose = True
            except (OSError, NotImplementedError):
                pose = False  # repli declare : on copie, et la copie est enregistree
        if not pose:
            destination.write_text(texte, encoding="utf-8")
            (rapport.mises_a_jour if remplace else rapport.copies).append(cle)
        registre[cle] = empreinte

    _ecrire_registre(racine, registre)
    return rapport


def desinstaller(racine: Path, *, dossier: Path | None = None) -> Rapport:
    """Retire ce que NOUS avons installe, et rien d'autre.

    Sans cette fonction, la seule facon de defaire une installation serait de supprimer le dossier
    a la main — et un utilisateur qui a ses propres competences dans `~/.hermes/skills` perdrait
    tout. Ce qui a ete enregistre se retire ; le reste est PRESERVE et nomme.
    """
    cible = dossier or dossier_hermes()
    rapport = Rapport(dossier=cible)
    registre = _lire_registre(racine)
    restant: dict[str, str] = {}
    for cle, empreinte in registre.items():
        chemin = Path(cle)
        if not chemin.is_file() and not chemin.is_symlink():
            continue
        if chemin.is_symlink() or _empreinte(chemin.read_text(encoding="utf-8", errors="replace")) == empreinte:
            chemin.unlink()
            rapport.copies.append(cle)  # retire
            # Les dossiers vides laisses derriere ne genent pas Hermes ; on les retire pour ne
            # pas laisser une arborescence fantome que l'utilisateur prendrait pour une erreur.
            parent = chemin.parent
            while parent != cible and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        else:
            rapport.preserves.append(cle)
            restant[cle] = empreinte
    _ecrire_registre(racine, restant)
    return rapport
