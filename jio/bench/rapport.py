"""Le rapport du duel : ce qu'on peut te renvoyer, archiver, et comparer.

POURQUOI CE MODULE EXISTE
-------------------------
Le banc mesurait deja tout : modele seul, echantillonnage a budget egal, verification
executable, harness complet, et les bras sans oracle avec leur controle apparié. Mais le
resultat ne vivait que dans un flux d'affichage : il fallait lire la console, et il ne restait
rien a comparer six semaines plus tard — ni entre deux modeles, ni avant/apres une modification
du harness.

Or c'est precisement la question de l'utilisateur : « est-ce que mon IA, avec ce harness, atteint
puis depasse les modeles frontieres ? ». Une reponse ne se lit pas ligne a ligne dans une sortie
terminale ; elle se lit dans un rapport DATE, avec ses intervalles de confiance, ses bras
temoins, et l'enonce EXPLICITE de ce qu'il ne prouve pas.

LA REGLE DE CE MODULE : aucun chiffre invente.
---------------------------------------------
Un bras sans donnee est declare « non mesure », jamais « 0 % ». Un intervalle sur une base
nulle n'existe pas. Un ecart dont l'intervalle contient zero est INDETERMINE, pas « positif ».
Et le rapport DIT ce qu'il ne peut pas trancher : les chiffres de la litterature (Terminal-Bench,
SWE-bench) portent sur d'autres taches, d'autres budgets d'appels et d'autres modeles ; les
comparer a ce banc serait un raccourci faux, donc ils n'apparaissent nulle part comme reference.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = ["Bras", "Ecart", "RapportDuel", "construire", "ecrire"]

#: Sous ce nombre d'essais apparies, un ecart est annonce comme peu concluant quel que soit son
#: intervalle : la stabilite d'un verdict ne se deduit pas de la seule significativite.
SEUIL_ESSAIS_SERIEUX = 20


@dataclass(frozen=True)
class Bras:
    """Un bras mesure : ce qui a tourne, son taux, et SON intervalle."""

    cle: str
    libelle: str
    reussite: float | None
    bas: float | None
    haut: float | None
    appels: float | None
    essais: int

    @property
    def mesure(self) -> bool:
        return self.reussite is not None

    def table(self) -> dict[str, Any]:
        if not self.mesure:
            return {"cle": self.cle, "libelle": self.libelle, "mesure": False}
        return {
            "cle": self.cle,
            "libelle": self.libelle,
            "mesure": True,
            "reussite": round(float(self.reussite), 4),
            "ic95": [round(float(self.bas), 4), round(float(self.haut), 4)],
            "appels_moyens": round(float(self.appels), 3),
            "essais": self.essais,
        }

    def ligne(self) -> str:
        if not self.mesure:
            return f"| {self.libelle} | non mesure | — | — | 0 |"
        return (
            f"| {self.libelle} | {self.reussite:.1%} "
            f"| [{self.bas:.0%} ; {self.haut:.0%}] | {self.appels:.1f} | {self.essais} |"
        )


@dataclass(frozen=True)
class Ecart:
    """Une comparaison APPARIEE entre deux bras, avec son verdict honnete."""

    gauche: str
    droite: str
    question: str
    delta: float | None
    bas: float | None
    haut: float | None
    tranche: bool
    essais: int

    @property
    def intervalle_degenere(self) -> bool:
        """Un intervalle de largeur NULLE n'est pas une precision : c'est un echantillon trop
        petit pour estimer une variance (toutes les differences observees sont identiques).
        L'afficher tel quel ferait croire a une certitude — vu sur ce depot : `[+100 ; +100]`
        a UN essai."""
        return self.bas is not None and self.haut is not None and abs(self.haut - self.bas) < 1e-9

    @property
    def verdict(self) -> str:
        if self.delta is None:
            return "non mesurable : un des deux bras n'a pas de donnees."
        if abs(self.delta) < 1e-9:
            return "aucune difference sur ce jeu de taches."
        if self.delta < 0:
            return "le bras de droite fait MOINS bien : a exhiber tel quel, pas a masquer."
        if not self.tranche:
            return (
                f"ecart de {self.delta:+.1f} points mais l'intervalle CONTIENT zero : "
                f"INDETERMINE a {self.essais} essai(s). Augmenter `--runs` avant de conclure."
            )
        if self.essais < SEUIL_ESSAIS_SERIEUX:
            motif = (
                "l'intervalle est DEGENERE (largeur nulle) : l'echantillon est trop petit "
                "pour estimer une variance, pas assez grand pour etre precis"
                if self.intervalle_degenere
                else "l'intervalle exclut zero"
            )
            return (
                f"ecart de {self.delta:+.1f} points, {motif}, mais {self.essais} essai(s) "
                f"seulement : solide en signe, a confirmer en amplitude (`--runs` plus grand)."
            )
        return f"ecart de {self.delta:+.1f} points, intervalle excluant zero a {self.essais} essais."

    def table(self) -> dict[str, Any]:
        return {
            "de": self.gauche,
            "vers": self.droite,
            "question": self.question,
            "delta_points": None if self.delta is None else round(float(self.delta), 2),
            "ic95_points": None if self.bas is None else [
                round(float(self.bas), 2), round(float(self.haut), 2)
            ],
            "intervalle_exclut_zero": bool(self.tranche) if self.delta is not None else None,
            "intervalle_degenere": self.intervalle_degenere,
            "essais": self.essais,
            "verdict": self.verdict,
        }

    def ligne(self) -> str:
        if self.delta is None:
            return f"| {self.question} | non mesurable | — | non mesure |"
        if self.bas is None:
            cadre = "—"
        elif self.intervalle_degenere:
            cadre = f"[{self.bas:+.1f} ; {self.haut:+.1f}] degenere"
        else:
            cadre = f"[{self.bas:+.1f} ; {self.haut:+.1f}]"
        tranche = "oui" if self.tranche else "NON"
        return f"| {self.question} | {self.delta:+.1f} pts | {cadre} | {tranche} |"


@dataclass(frozen=True)
class RapportDuel:
    """Le resultat complet d'une mesure, sous une forme que l'on garde et que l'on compare."""

    horodatage: str
    modele: str
    genre: str
    note: str
    skill: float
    runs: int
    taches: int
    rounds: int
    duree_s: float
    commit: str
    bras: tuple[Bras, ...]
    ecarts: tuple[Ecart, ...]
    integrite: dict[str, Any] = field(default_factory=dict)
    hypotheses: tuple[str, ...] = ()

    # --- sorties ---------------------------------------------------------- #

    def table(self) -> dict[str, Any]:
        return {
            "horodatage": self.horodatage,
            "modele": self.modele,
            "genre": self.genre,
            "note_modele": self.note,
            "competence_simulee": self.skill,
            "tirages": self.runs,
            "taches": self.taches,
            "tours_max": self.rounds,
            "duree_s": round(self.duree_s, 2),
            "commit": self.commit,
            "bras": [b.table() for b in self.bras],
            "ecarts": [e.table() for e in self.ecarts],
            "integrite": self.integrite,
            "hypotheses": list(self.hypotheses),
        }

    def en_json(self) -> str:
        return json.dumps(self.table(), indent=2, ensure_ascii=False) + "\n"

    def en_markdown(self) -> str:
        """Le rapport que TU peux lire, et que tu peux me renvoyer tel quel."""
        lignes = [
            "# Duel : ce que le harness apporte, sur CE modele",
            "",
            f"- **date** : {self.horodatage}",
            f"- **modele mesure** : `{self.modele}` ({self.genre})",
            f"- **taches** : {self.taches} tache(s) du banc · **{self.runs} tirage(s)** · "
            f"{self.rounds} tour(s) de boucle maximum",
            f"- **duree** : {self.duree_s:.1f} s · **commit** : `{self.commit}`",
        ]
        if self.note:
            lignes.append(f"- **note** : {self.note}")
        lignes += [
            "",
            "## Les bras, avec leurs intervalles",
            "",
            "| config | reussite | IC95 | appels/tache | essais |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        lignes += [b.ligne() for b in self.bras]
        lignes += [
            "",
            "Lire la colonne IC95 avant toute conclusion : un bras dont l'intervalle est large "
            "situe la mesure, il ne la tranche pas. Et un bras « non mesure » n'est pas un bras "
            "a zero — c'est un bras qui n'a pas tourne.",
            "",
            "## Les comparaisons qui tranchent",
            "",
            "| question | ecart | IC95 | intervalle exclut zero |",
            "| --- | ---: | ---: | --- |",
        ]
        lignes += [e.ligne() for e in self.ecarts]
        lignes += [""]
        for e in self.ecarts:
            lignes.append(f"- **{e.question}** — {e.verdict}")
        if self.integrite:
            lignes += ["", "## Integrite (ce qui doit rester a zero)", ""]
            for cle, valeur in self.integrite.items():
                lignes.append(f"- {cle} : {valeur}")
        lignes += [
            "",
            "## Ce que ce rapport prouve, et ce qu'il ne prouve pas",
            "",
            "**Il prouve** : ce que le harness change sur CE modele, a budget d'appels EGAL — "
            "le controle apparie utilise autant d'appels du modele que le bras qu'il controle, "
            "donc un gain ne peut pas venir du nombre d'essais.",
            "",
            "**Il ne prouve pas** : le niveau absolu du modele sur un benchmark public. Les "
            "chiffres de la litterature (Terminal-Bench, SWE-bench) portent sur d'autres taches, "
            "d'autres budgets et d'autres reglages ; les citer ici comme reference serait un "
            "raccourci faux. Ce rapport repond a une question locale, et il y repond avec ses "
            "intervalles.",
            "",
            "**Pour aller plus loin** : `--runs` elargit l'echantillon (les intervalles se "
            "resserrent), `--taches 0` prend tout le banc, et `jio ablation` retire une brique "
            "du harness pour dire laquelle porte le gain.",
            "",
        ]
        return "\n".join(lignes)


def construire(
    *,
    resultats: dict[str, Sequence[float]],
    appels: dict[str, Sequence[int]],
    libelles: dict[str, str],
    ordre: Iterable[str],
    modele: Any,
    skill: float,
    runs: int,
    taches: int,
    rounds: int,
    duree_s: float,
    commit: str,
    integrite: dict[str, Any] | None = None,
    hypotheses: Sequence[str] = (),
    ecarts: Sequence[
        tuple[str, str, str, float | None, tuple[float, float] | None, bool]
    ] = (),
) -> RapportDuel:
    """Assemble le rapport a partir des mesures DEJA faites par le banc.

    Aucun calcul de mesure n'est refait ici : la moyenne, l'intervalle de Wilson et l'ecart
    apparie viennent de `jio.bench`, ou ils sont testes. Ce module ne fait que les METTRE EN
    FORME — deux implementations d'une meme mesure, ce serait deux verites possibles.
    """
    from .incertitude import intervalle_wilson

    def moyenne(valeurs: Sequence[float]) -> float:
        return sum(valeurs) / len(valeurs) if valeurs else 0.0

    bras: list[Bras] = []
    for cle in ordre:
        valeurs = list(resultats.get(cle, ()))
        if not valeurs:
            bras.append(Bras(cle, libelles.get(cle, cle), None, None, None, None, 0))
            continue
        bas, haut = intervalle_wilson(int(round(sum(valeurs))), len(valeurs))
        bras.append(Bras(
            cle, libelles.get(cle, cle), moyenne(valeurs), bas, haut,
            moyenne(list(appels.get(cle, ()))), len(valeurs),
        ))

    liste_ecarts: list[Ecart] = []
    for gauche, droite, question, delta, intervalle, tranche in ecarts:
        n = len(resultats.get(droite, ()))
        if delta is None or intervalle is None:
            # Un ecart sans intervalle n'est pas un ecart : un bras manquait. On le declare
            # plutot que d'inventer une borne.
            liste_ecarts.append(Ecart(gauche, droite, question, None, None, None, False, n))
            continue
        bas, haut = intervalle
        liste_ecarts.append(Ecart(
            gauche, droite, question, float(delta), float(bas), float(haut), bool(tranche), n,
        ))

    return RapportDuel(
        horodatage=_dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        modele=str(getattr(modele, "spec", modele)),
        genre=str(getattr(modele, "genre", "inconnu")),
        note=str(getattr(modele, "note", "") or ""),
        skill=float(skill), runs=int(runs), taches=int(taches), rounds=int(rounds),
        duree_s=float(duree_s), commit=commit,
        bras=tuple(bras), ecarts=tuple(liste_ecarts),
        integrite=dict(integrite or {}), hypotheses=tuple(hypotheses),
    )


def ecrire(rapport: RapportDuel, chemin: Path | str) -> tuple[Path, Path]:
    """Ecrit le rapport en Markdown ET en JSON a cote, et renvoie les deux chemins.

    Les deux, toujours : le Markdown est ce qu'un humain lit, le JSON est ce qui se compare
    d'une execution a l'autre sans qu'on ait a le relire.
    """
    cible = Path(chemin)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(rapport.en_markdown(), encoding="utf-8")
    jumeau = cible.with_suffix(".json")
    jumeau.write_text(rapport.en_json(), encoding="utf-8")
    return cible, jumeau
