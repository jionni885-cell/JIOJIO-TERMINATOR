"""Ce qui est une CONSIGNE, et ce qui est un document.

Un document parle DE quelque chose ; une consigne dit quoi FAIRE. La difference n'est pas
litteraire, elle est mesurable, et elle a ete mesuree :

  * un document qui montre `jio scna` illustre un message d'erreur — le refuser ferait
    condamner les documents qui expliquent le produit ;
  * une competence Hermes qui ecrit `jio prouve-tout` dans un bloc `sh` n'illustre rien :
    c'est la ligne que l'agent va taper. Il la tapera, elle echouera, et il conclura que
    l'outil est casse.

Defaut a l'origine de ce module : `jio coherence` annoncait « 36 commande(s) citee(s), toutes
existantes » alors qu'une competence citee une commande inexistante ne produisait AUCUN
constat. Le controle ne regardait que `README.md`, `docs/` et les trois fichiers d'instructions
racine — les 12 competences et les 7 agents opencode, exactement ce qui va etre execute,
n'etaient pas dans le champ.

Ce module est volontairement minuscule et sans dependance : il est importe par le portail de
coherence ET par la verification des documents, et deux listes recopiees auraient fini par
diverger.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["ARTEFACTS_EXECUTES", "consigne", "relatif_si_possible"]

#: Motifs, relatifs a la racine du projet, des fichiers qu'un AGENT lit comme une consigne.
#: Chaque entree correspond a un outil reel : `.hermes/skills` est lu par Hermes (revelation
#: progressive), `.opencode/agents` par opencode, `.cursor/rules` par Cursor, etc.
ARTEFACTS_EXECUTES: tuple[str, ...] = (
    ".hermes/skills/**/*.md",
    ".opencode/agents/*.md",
    ".cursor/rules/*.mdc",
    ".github/copilot-instructions.md",
    ".mcp.README.md",
    ".jio/ACTIVE.md",
)

#: Le meme ensemble, par PREFIXE de chemin relatif. Les motifs servent a `glob` ; ces prefixes
#: servent a decider d'un fichier DEJA NOMME (le hook pre-commit passe des chemins, pas des
#: motifs). Les deux formes sont derivees l'une de l'autre a la lecture, pas recopiees.
_PREFIXES: tuple[str, ...] = (
    ".hermes/skills/",
    ".opencode/agents/",
    ".cursor/rules/",
)


def relatif_si_possible(chemin: Path, racine: Path | None) -> str:
    """Le chemin relatif a `racine`, ou le chemin tel quel si la racine ne le contient pas."""
    if racine is not None:
        try:
            return str(chemin.resolve().relative_to(racine.resolve()))
        except (ValueError, OSError):
            pass
    return str(chemin)


def consigne(chemin: Path, racine: Path | None = None) -> bool:
    """Vrai si ce fichier est une CONSIGNE pour un agent, et non un document a lire.

    La decision se prend sur le chemin, jamais sur le contenu : un fichier qui ressemble a une
    competence mais n'est pas range la ou un agent la lit n'a aucun effet, et l'auditer serait
    un faux sentiment de securite.
    """
    relatif = relatif_si_possible(chemin, racine).replace("\\", "/")
    if relatif in {
        ".github/copilot-instructions.md",
        ".mcp.README.md",
        ".jio/ACTIVE.md",
    }:
        return True
    return relatif.startswith(_PREFIXES)
