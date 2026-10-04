"""Ce que la configuration coute en contexte — mesure, parce qu'un fichier survole ne sert a rien.

Le budget de contexte n'existait dans ce depot que sous la forme d'un test (5 000 jetons par
competence, 25 000 au total, estimes a 4 caracteres par jeton). Un test vert ne dit rien a
l'utilisateur : il ne sait pas combien de son contexte est mange avant la premiere question,
ni lequel de ses fichiers depasse la limite.

Or c'est exactement ce qui decide si le harness AIDE ou NUIT. Trois mesures de la
litterature, toutes utilisees comme seuils ici :

  * un fichier de contexte au-dela d'environ **150 lignes** est survole, pas lu ;
  * une competence de plus d'environ **5 000 jetons** n'est plus chargeable en une fois ;
  * une bibliotheque au-dela d'environ **25 000 jetons** ne tient plus dans la fenetre avec
    la mission.

Deux principes de methode, parce qu'un chiffre faux serait pire qu'aucun chiffre :

1. **On ne pretend pas compter exactement.** Un tokenizer reel est une dependance, et la
   mesure varie d'un modele a l'autre. On rend un INTERVALLE : la borne basse compte
   3,2 caracteres par jeton, la borne haute 4,4. En dessous du seuil avec la borne HAUTE,
   c'est bon ; au-dessus avec la borne BASSE, c'est depasse ; entre les deux, c'est
   « a verifier », et on le dit.
2. **On ne compte pas ce qui n'est pas charge.** Les agents opencode et les competences
   Hermes se chargent a la demande (revelation progressive) : ils ne coutent pas au
   demarrage. Le rapport distingue donc le contexte INJECTE de l'ecosysteme DISPONIBLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Mesure",
    "SEUILS",
    "sur_disque",
    "mesurer",
    "mesurer_depuis",
    "verdict",
    "resume",
]

#: Caracteres par jeton, bornes basses et hautes. 4,4 est la valeur usuelle pour de la
#: prose anglaise ; le francais et le code tokenisent plus mal (accents, ponctuation,
#: indentations), d'ou la borne basse a 3,2. L'intervalle couvre les deux.
PAR_JETON_MIN = 3.2
PAR_JETON_MAX = 4.4

#: Seuils issus de mesures de terrain (voir la docstring du module).
SEUILS = {
    "contexte_lignes": 150,
    "competence_jetons": 5_000,
    "bibliotheque_jetons": 25_000,
}


@dataclass(frozen=True)
class Mesure:
    """Le cout d'un fichier : lignes, caracteres, et un INTERVALLE de jetons."""

    chemin: str
    lignes: int
    caracteres: int

    @property
    def jetons_min(self) -> int:
        return round(self.caracteres / PAR_JETON_MAX)

    @property
    def jetons_max(self) -> int:
        return round(self.caracteres / PAR_JETON_MIN)

    @property
    def jetons(self) -> int:
        """Meilleure estimation ponctuelle, pour les totaux."""
        return round(self.caracteres / 3.8)

    def depasse(self, seuil: int) -> bool:
        """Le seuil est-il depasse SANS ambiguite (borne basse au-dessus) ?"""
        return self.jetons_min > seuil

    def peut_depasser(self, seuil: int) -> bool:
        """Le seuil est-il peut-etre depasse (borne haute au-dessus) ?"""
        return self.jetons_max > seuil

    def intervalle(self) -> str:
        return f"~{self.jetons_min}-{self.jetons_max}"


def mesurer(chemin: str, texte: str) -> Mesure:
    """Mesure un contenu. Les lignes vides finales ne comptent pas : elles ne se lisent pas."""
    lignes = len(texte.rstrip("\n").splitlines())
    return Mesure(chemin=chemin, lignes=lignes, caracteres=len(texte))


def mesurer_depuis(racine: Path, fichiers: dict[str, str]) -> list[Mesure]:
    """Mesure un ensemble de fichiers generes, tries par cout decroissant."""
    mesures = [mesurer(chemin, texte) for chemin, texte in fichiers.items()]
    return sorted(mesures, key=lambda m: -m.jetons)


def verdict(mesures: list[Mesure], est_competence=None) -> list[str]:
    """Les lignes de diagnostic, dans l'ordre : depassements fermes, doutes, puis totaux.

    `est_competence` distingue les competences (seuil 5 000 chacune) des fichiers de
    contexte (seuil 150 lignes) : deux budgets differents, une seule fonction.
    """
    lignes: list[str] = []
    depassees: list[Mesure] = []
    douteuses: list[Mesure] = []

    for mesure in mesures:
        est_skill = bool(est_competence and est_competence(mesure.chemin))
        seuil = SEUILS["competence_jetons"] if est_skill else None
        if seuil is not None and mesure.depasse(seuil):
            depassees.append(mesure)
        elif seuil is not None and mesure.peut_depasser(seuil):
            douteuses.append(mesure)
        elif not est_skill and mesure.lignes > SEUILS["contexte_lignes"]:
            # Pour un fichier de contexte, la LIGNE est la bonne unite : c'est la
            # longueur lue par l'humain comme par le modele.
            depassees.append(mesure)

    if depassees:
        lignes.append(
            f"  {len(depassees)} fichier(s) DEPASSENT leur budget declare :"
        )
        for mesure in depassees:
            lignes.append(
                f"    {mesure.chemin} : {mesure.lignes} ligne(s), "
                f"{mesure.intervalle()} jetons"
            )
        lignes.append(
            "    Un fichier au-dela du budget est survole, pas lu : il coute du contexte"
        )
        lignes.append("    sans rien apporter — c'est pire que de ne pas l'avoir.")
    elif douteuses:
        lignes.append(f"  {len(douteuses)} fichier(s) proches du budget (a verifier) :")
        for mesure in douteuses:
            lignes.append(
                f"    {mesure.chemin} : {mesure.intervalle} jetons pour un seuil de "
                f"{SEUILS['competence_jetons']}"
            )
    else:
        lignes.append("  Aucun fichier ne depasse son budget declare.")

    return lignes


def resume(mesures: list[Mesure], titre: str, *, total: bool = True) -> list[str]:
    """Un tableau lisible : chemin, lignes, intervalle de jetons.

    `total=False` quand les fichiers sont des ALTERNATIVES et non un ensemble : un outil
    ne lit qu'UN fichier de contexte, donc additionner les cinq dialectes produirait un
    total qu'aucune session ne paie. Un chiffre faux dans un rapport sur le contexte est
    exactement ce que ce rapport existe pour eviter.
    """
    if not mesures:
        return []
    lignes = [f"  {titre}", ""]
    largeur = max(len(m.chemin) for m in mesures)
    for mesure in mesures:
        lignes.append(
            f"    {mesure.chemin:<{largeur}}  {mesure.lignes:>5} ligne(s)  "
            f"{mesure.jetons_min:>6}-{mesure.jetons_max:<6} jetons"
        )
    if total:
        cumul = sum(m.jetons for m in mesures)
        lignes.append("")
        lignes.append(f"    TOTAL : {len(mesures)} fichier(s), ~{cumul} jetons (estimation)")
    return lignes


@dataclass(frozen=True)
class EtatDisque:
    """Ce qui est REELLEMENT charge, et ce qui a ete modifie a la main.

    DEFAUT MESURE, corrige ici : `jio artifacts --budget` mesurait le MANIFESTE — le texte que
    jio regenererait — et jamais le fichier pose sur le disque. Un `AGENTS.md` edite a la main
    (donc PRESERVE par le garde-fou d'ecriture, et charge par l'outil) etait donc mesure a la
    place d'un autre. Le rapport annoncait « 150 lignes » d'un fichier qui en faisait 300.

    C'est le seul chiffre qui decide si le harness aide ou nuit : il doit porter sur ce que
    l'outil CHARGE. Deux consequences, et les deux sont declarees plutot que tues :

      * `divergents` : le fichier existe, il differe de la doctrine — la mesure porte sur VOTRE
        fichier, et on le dit, parce que `jio artifacts --write` peut le PRESERVER (il n'est pas
        a nous) : recommander une regeneration qui ne peut pas reparer serait une boucle ;
      * `absents` : le fichier n'existe pas encore — la mesure porte sur ce que jio ecrira, et
        c'est declare aussi. Mesurer un futur en le presentant comme un present, c'est le genre
        de chiffre que ce depot refuse.
    """

    fichiers: dict[str, str]
    divergents: tuple[str, ...]
    absents: tuple[str, ...]


def sur_disque(racine: Path, generes: dict[str, str]) -> EtatDisque:
    """Remplace le contenu genere par celui du disque, quand il existe."""
    fichiers: dict[str, str] = {}
    divergents: list[str] = []
    absents: list[str] = []
    for chemin, genere in generes.items():
        cible = racine / chemin
        try:
            reel = cible.read_text(encoding="utf-8") if cible.is_file() else None
        except OSError:
            reel = None
        if reel is None:
            absents.append(chemin)
            fichiers[chemin] = genere
            continue
        fichiers[chemin] = reel
        if reel != genere:
            divergents.append(chemin)
    return EtatDisque(fichiers, tuple(sorted(divergents)), tuple(sorted(absents)))
