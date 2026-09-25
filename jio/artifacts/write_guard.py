"""Ecrire des artefacts SANS jamais detruire le travail de quelqu'un d'autre.

Le probleme, et il est reel
---------------------------
`jio artifacts --write` ecrivait `AGENTS.md` par-dessus tout ce qu'il trouvait. Dans le
depot de JIO, c'est le comportement voulu : le fichier y est genere. Chez l'utilisateur,
c'est une destruction : `AGENTS.md` est precisement le fichier ou un projet met SES
conventions, editees a la main. Le script d'installation applique deja la bonne regle
(« existe deja — non ecrase ») ; le cablage MCP aussi (`brancher` n'est jamais destructif).
La commande d'ecriture ne l'appliquait pas : deux regles pour un meme risque, c'est une
regle qui tombe.

Pourquoi un REGISTRE et pas seulement une marque
------------------------------------------------
La premiere version reconnaissait ses fichiers a une marque en tete (« Genere par `jio
artifacts` »). Mesure faite : **19 des 29 fichiers emis n'en portent aucune** — les agents
opencode, les competences Hermes, et tous les fichiers JSON, ou un commentaire est
interdit par la syntaxe. Sur un projet reel, `jio sync` aurait donc PRESERVE ses propres
fichiers, en ecrivant des `.jio` a cote : l'inverse du but.

Un generateur qui ne signe pas sa sortie ne peut pas la mettre a jour. Le registre
`.jio/generated.json` signe donc l'ensemble, JSON compris : chemin -> empreinte SHA-256 de
ce qui a ete ecrit. La regle devient exacte, et elle distingue deux situations que la
marque confondait :

  * le fichier est au registre et son empreinte correspond -> personne n'y a touche, on
    met a jour sans rien sauvegarder ;
  * le fichier est au registre mais son empreinte a CHANGE -> quelqu'un l'a edite : on
    sauvegarde `.avant-jio` avant de mettre a jour, et on le dit.

La marque reste une regle de REPLI : un fichier emis avant le registre, ou copie a la main
d'un projet a l'autre, reste reconnaissable.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Decision", "ecrire_manifest", "MARQUE", "REGISTRE", "lire_registre"]

#: La marque posee en tete des fichiers generes, quand le format accepte un commentaire.
MARQUE = re.compile(r"genere par\s+`?jio\b", re.IGNORECASE)

#: Le registre des fichiers emis : chemin relatif -> empreinte de ce que NOUS avons ecrit.
#: Il vit dans un dossier a part pour ne pas encombrer la racine du projet.
REGISTRE = ".jio/generated.json"

#: Assez large pour couvrir une entete de frontmatter, assez strict pour rester une marque
#: de GENESE et pas une simple mention de jio dans un document.
FENETRE_MARQUE = 600


@dataclass(frozen=True)
class Decision:
    """Ce qui est arrive a UN fichier, et pourquoi."""

    chemin: str
    action: str          # ecrit | remplace | sauvegarde | preserve | inchange
    detail: str = ""

    @property
    def ecrit(self) -> bool:
        return self.action in {"ecrit", "remplace", "sauvegarde"}


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def lire_registre(racine: Path) -> dict[str, str]:
    """Le registre, ou un registre vide. Un registre illisible n'est pas une erreur fatale.

    Le pire cas est connu et borne : sans registre, on retombe sur la marque, qui est plus
    stricte. Refuser de travailler parce qu'un fichier d'etat est corrompu serait pire.
    """
    chemin = racine / REGISTRE
    if not chemin.is_file():
        return {}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    fichiers = donnees.get("fichiers")
    if not isinstance(fichiers, dict):
        return {}
    return {str(k): str(v) for k, v in fichiers.items()}


def _ecrire_registre(racine: Path, entrees: dict[str, str]) -> None:
    chemin = racine / REGISTRE
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(
            {
                "avertissement": (
                    "Registre des fichiers ecrits par `jio sync`. Il permet de mettre a jour "
                    "ses propres artefacts sans jamais ecraser un fichier ecrit par vous. "
                    "Le supprimer ne casse rien : jio redeviendra prudent."
                ),
                "fichiers": dict(sorted(entrees.items())),
            },
            indent=2, ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _porte_la_marque(texte: str) -> bool:
    return bool(MARQUE.search(texte[:FENETRE_MARQUE]))


def ecrire_manifest(
    racine: Path,
    fichier: dict[str, str],
    *,
    registre: bool = True,
) -> list[Decision]:
    """Ecrit `fichier` (chemin relatif -> contenu) sous `racine`, sans rien detruire.

    Trois issues par fichier, et le message dit toujours laquelle :

      * il n'existe pas -> ecrit ;
      * il est identique -> inchange (aucune date touchee, aucun bruit dans git) ;
      * il est a nous -> mis a jour, avec sauvegarde `.avant-jio` si quelqu'un l'avait
        modifie depuis ;
      * il n'est pas a nous -> PRESERVE, et notre version ecrite a cote (suffixe `.jio`).
    """
    connu = lire_registre(racine) if registre else {}
    a_jour: dict[str, str] = dict(connu)
    decisions: list[Decision] = []

    for rel, contenu in sorted(fichier.items()):
        chemin = racine / rel
        empreinte_nous = _empreinte(contenu)

        if not chemin.exists():
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(contenu, encoding="utf-8")
            a_jour[rel] = empreinte_nous
            decisions.append(Decision(rel, "ecrit", "le fichier n'existait pas"))
            continue

        existant = chemin.read_text(encoding="utf-8", errors="replace")
        if existant == contenu:
            a_jour[rel] = empreinte_nous
            decisions.append(Decision(rel, "inchange", "deja a jour"))
            continue

        # A nous ? Deux preuves possibles : le registre (exacte, JSON compris), ou la marque
        # (repli, pour un fichier recopie d'un projet a l'autre).
        notre_empreinte = connu.get(rel)
        if notre_empreinte is None and not _porte_la_marque(existant):
            apart = racine / (rel + ".jio")
            apart.parent.mkdir(parents=True, exist_ok=True)
            apart.write_text(contenu, encoding="utf-8")
            decisions.append(
                Decision(
                    rel, "preserve",
                    f"ecrit par vous, non touche — notre version est dans {rel}.jio",
                )
            )
            continue

        modifie = notre_empreinte is not None and _empreinte(existant) != notre_empreinte
        if modifie:
            sauvegarde = chemin.with_name(chemin.name + ".avant-jio")
            sauvegarde.write_text(existant, encoding="utf-8")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
        a_jour[rel] = empreinte_nous
        decisions.append(
            Decision(
                rel,
                "sauvegarde" if modifie else "remplace",
                "mis a jour, votre version est dans "
                f"{chemin.name}.avant-jio" if modifie else "genere par jio, mis a jour",
            )
        )

    if registre and any(d.ecrit for d in decisions):
        # On n'ecrit le registre que si quelque chose a bouge : un passage sans ecriture ne
        # doit rien modifier, pas meme un fichier d'etat.
        _ecrire_registre(racine, a_jour)
    return decisions
