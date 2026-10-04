"""Quels documents appartiennent a jio, dans un projet qui n'est pas le sien ?

`jio start` installe chez l'utilisateur des documents qui parlent de jio : les competences
(`.hermes/skills/<categorie>/<nom>/SKILL.md`), les consignes d'agent (`AGENTS.md`, `CLAUDE.md`,
`.github/copilot-instructions.md`, `.cursor/rules/*.mdc`) et les agents d'opencode
(`.opencode/agents/*.md`). Ces documents citent des chemins internes de jio
(`jio/artifacts/doctrine.py`), qui n'existent evidemment pas chez l'utilisateur.

Mesure faite sur un projet ETRANGER, apres `jio start` : `jio scan .` y produisait 22 constats
« chemin cite INTROUVABLE », tous sur NOS documents, a propos de NOS chemins. Le balayage ne
trouvait aucun defaut du projet — et il apprenait a l'utilisateur a ignorer ses constats, ce qui
coute ensuite les vrais.

Ce module repond a une seule question, et il la repond par la STRUCTURE (ou vit le fichier),
jamais par le contenu : un `SKILL.md` sous `.hermes/skills/` est une competence installee, quel
que soit son texte. Le contenu, lui, peut etre reecrit par l'utilisateur — et s'il le reecrit,
c'est encore la competence qu'il a devant lui, pas un document de son projet.
"""

from __future__ import annotations

from pathlib import Path

#: Les emplacements que jio gere, par rapport a la racine du projet. Le motif `SKILL.md` est
#: volontairement nu : une competence peut vivre a n'importe quelle profondeur sous
#: `.hermes/skills/` (categorie, puis nom).
_CHEMINS_GERES: tuple[str, ...] = (
    ".jio",                   # l'etat et la fiche d'integration que jio tient ici
    ".hermes/skills",
    ".opencode/agents",
    ".claude/agents",
    ".github/copilot-instructions.md",
)

#: Noms de fichiers que jio ecrit a la racine (consignes d'agent). Un fichier qui porte ce nom
#: a la racine d'un projet qui n'est pas jio EST une consigne installee par jio : c'est ce que
#: `jio start` ecrit, et le garde d'ecriture en a fait une sauvegarde si l'utilisateur en avait
#: un avant.
_NOMS_A_LA_RACINE: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
)


def est_un_document_de_jio(chemin: Path, racine: Path) -> bool:
    """Ce document appartient-il a l'installation de jio plutot qu'au projet ?

    Rend `True` quand le fichier vit dans un emplacement que jio gere (voir `_CHEMINS_GERES`) ou
    qu'il porte un nom de consigne d'agent a la racine du projet. Tout le reste appartient au
    projet : c'est la seule reponse conservatrice, parce que se tromper dans l'autre sens ferait
    disparaitre de vrais defauts du champ du balayage.
    """
    try:
        relatif = chemin.resolve().relative_to(racine.resolve())
    except (OSError, ValueError):
        # Hors de la racine (lien symbolique vers l'installation de jio, par exemple) : c'est du
        # code de jio, pas du projet scanne.
        return True

    texte = relatif.as_posix()
    if any(texte.startswith(prefixe) or f"/{prefixe}/" in f"/{texte}" for prefixe in _CHEMINS_GERES):
        return True
    if "/" not in texte:
        return texte in _NOMS_A_LA_RACINE or (
            texte.endswith(".md") and texte.split(".")[0] in {
                nom.removesuffix(".md") for nom in _NOMS_A_LA_RACINE
            }
        )
    return False
