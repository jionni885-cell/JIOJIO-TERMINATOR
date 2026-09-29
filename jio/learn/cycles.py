"""Auto-amelioration CONTINUE : ce qui se passe quand le systeme tourne plusieurs cycles.

LE TROU QUE CE MODULE COMBLE
----------------------------
`jio learn` mesurait UNE fois : trois bras (froid / temoin / chaud) sur un lot de missions. Cela
repond a « la memoire apporte-t-elle quelque chose ? » — pas a la question de l'auto-amelioration
CONTINUE : **est-ce que ca s'ameliore, cycle apres cycle, et est-ce que ca pourrait se degrader ?**

Ce second axe est celui qui manque partout : un systeme qui accumule des souvenirs, des
competences et des statistiques de bras peut tres bien s'ameliorer puis se DEGRADER — la litterature
le documente sous le nom de pollution de contexte (une memoire qui grossit finit par distraire
autant qu'elle aide, et 4 modes d'echec ont ete identifies : poisoning, distraction, confusion,
clash). Le seul moyen de le savoir est de MESURER PAR CYCLE, sans quoi on ne voit ni le plateau
ni la rechute.

PROTOCOLE
---------
A chaque cycle k, et sur les MEMES graines :

  * bras FROID   — aucune memoire. C'est la reference du cycle : elle peut monter toute seule
                   (loterie de graine), donc c'est ELLE qu'il faut comparer, pas le cycle 0 ;
  * bras CHAUD   — la memoire ACCUMULEE par les cycles precedents, et le routeur de confiance
                   des bras. Les echecs du cycle entrent en memoire, les succes renforcent
                   le bras choisi.

On rapporte, par cycle : succes froid, succes chaud, ecart, taille de la memoire au debut du
cycle, nombre de missions ou un souvenir a effectivement ete rappele. Puis un VERDICT qui ne
peut pas mentir :

  * `PROGRESSE`   — l'ecart du dernier cycle est positif ET l'intervalle apparié exclut zero ;
  * `PLATEAU`     — l'ecart est positif mais indetermine, ou nul : ce n'est pas un echec, c'est
                    une mesure qui ne conclut pas a cet echantillon, et le nombre d'essais
                    necessaire est donne ;
  * `REGRESSE`    — l'ecart est NEGATIF a un cycle posterieur au premier. C'est le seul verdict
                    qui condamne : la memoire devient nuisible, et le systeme doit alors
                    elaguer au lieu d'accumuler.

Le modele est simule (aucune cle requise) ; la boucle, la memoire, le routeur et la verification
sont, eux, REELS. Le chiffre mesure donc la MECANIQUE de l'auto-amelioration, et il est declare
comme tel — jamais presente comme la performance d'un modele reel.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..bench.tasks import TASKS
from ..core.types import Mission
from .memory import FailureMemory

__all__ = ["Cycle", "RapportCycles", "run_cycles", "VERDICTS"]

#: Les trois verdicts possibles, ecrits ici pour que le rapport et les tests lisent la MEME
#: liste : un verdict ajoute ailleurs serait un verdict que personne ne teste.
VERDICTS = ("PROGRESSE", "PLATEAU", "REGRESSE")


class _RouteurFige:
    """Un routeur qui rend TOUJOURS le meme bras et n'apprend rien.

    POURQUOI IL EXISTE, et c'est un defaut de protocole corrige ici. Le routeur de confiance
    choisit un bras par mission (nombre de candidats, de tours, alpha) : si le bras CHAUD tourne
    avec le routeur et le bras FROID avec la configuration par defaut, l'ecart mesure melange
    DEUX causes — la memoire et la configuration — et aucune des deux n'est attribuable.

    Mesure a l'origine : au premier cycle, « froid 3/5 contre chaud 2/5 » avec une memoire VIDE
    des deux cotes. La difference ne pouvait pas venir de la memoire ; elle venait du bras
    (`minimal`, 1 candidat) choisi pour le bras chaud. Le protocole apparie donc EXACTEMENT :
    le bras est choisi par le vrai routeur, puis le bras froid rejoue la meme mission avec le
    MEME bras, la seule difference etant l'absence de memoire.
    """

    def __init__(self, arm: object) -> None:
        self._arm = arm
        self.observations = 0

    def choose(self, objective: str, **_kw: object) -> object:
        return self._arm

    def observe(self, objective: str, arm: object, *, success: bool,
                cost: float | None = None) -> float:
        self.observations += 1
        return 0.0


@dataclass
class Cycle:
    """Un cycle mesure : ce qui etait en memoire, ce qui a ete rappele, ce qui a reussi."""

    numero: int
    memo_avant: int
    memo_apres: int
    rappels: int
    froid: int
    chaud: int
    essais: int
    #: Caracteres de memoire injectes dans les prompts du cycle (le COUT de la memoire).
    #: Sans ce chiffre, un plateau se lit comme « la memoire n'apporte rien » ; avec lui, il
    #: se lit comme « la memoire coute X et n'apporte rien » — deux phrases differentes, et
    #: la seconde est celle qui declenche une decision (elaguer, borner, ou retirer).
    caracteres_memoire: int = 0

    @property
    def ecart(self) -> int:
        return self.chaud - self.froid

    @property
    def jetons_memoire(self) -> int:
        """Estimation declaree : ~4 caracteres par jeton (prose anglaise structuree)."""
        return self.caracteres_memoire // 4

    @property
    def taux_froid(self) -> float:
        return self.froid / self.essais if self.essais else 0.0

    @property
    def taux_chaud(self) -> float:
        return self.chaud / self.essais if self.essais else 0.0

    def ligne(self) -> str:
        return (
            f"    {self.numero:>2}     {self.memo_avant:>5} {self.rappels:>5} "
            f"{self.jetons_memoire:>7} {self.froid:>4}/{self.essais:<3} "
            f"{self.chaud:>4}/{self.essais:<3} {self.ecart:>+6}"
        )


@dataclass
class RapportCycles:
    """Le resultat complet, avec le verdict et sa justification chiffree."""

    cycles: list[Cycle] = field(default_factory=list)
    skill: float = 0.0
    runs: int = 0
    rounds: int = 0
    #: Bras du routeur : nom, tirages, recompense moyenne — mesures, pas supposes.
    bras: list[tuple[str, int, float]] = field(default_factory=list)
    #: Part des missions du dernier cycle ou le routeur a choisi le bras qui a la meilleure
    #: recompense moyenne sur tout l'historique. Un bandit qui converge la fait monter.
    concentration: float = 0.0
    #: Choix du dernier cycle, par bras : ce qui a ete DECIDE, pas ce qui a ete mesure.
    choix_dernier_cycle: dict[str, int] = field(default_factory=dict)
    regret: float = 0.0
    #: Le bras que l'historique MESURE designe comme meilleur (au moins 2 tirages agreges).
    meilleur_bras: str = ""
    #: Bornes de l'ecart froid -> chaud sur le DERNIER cycle (intervalle apparie).
    bas: float = 0.0
    haut: float = 0.0
    tranche: bool = False
    @property
    def rechutes(self) -> list[int]:
        """Les cycles ou la memoire DEJA accumulee a fait perdre.

        Calculee, jamais stockee : un verdict derive d'un champ peut mentir si le champ
        n'est pas mis a jour, et un verdict est la seule chose que l'utilisateur retient.
        La regle est STRICTE — il faut que la memoire existait avant le cycle (`memo_avant
        > 0`) : au premier cycle, un ecart negatif est de la loterie de graine, et accuser
        la memoire d'une mauvaise graine serait un faux positif.
        """
        return [
            c.numero for c in self.cycles if c.memo_avant > 0 and c.ecart < 0
        ]

    @property
    def total_essais(self) -> int:
        return sum(c.essais for c in self.cycles)

    @property
    def memo_final(self) -> int:
        """Ce que la memoire contient a la fin : le stock, pas le flux."""
        return self.cycles[-1].memo_apres if self.cycles else 0

    def verdict(self) -> str:
        """Le verdict, et il ne peut pas flatter : une rechute condamne, un plateau declare."""
        if not self.cycles:
            return "PLATEAU"
        if self.rechutes:
            return "REGRESSE"
        dernier = self.cycles[-1]
        if dernier.ecart > 0 and self.tranche:
            return "PROGRESSE"
        return "PLATEAU"

    def explication(self) -> str:
        verdict = self.verdict()
        if not self.cycles:
            return "aucun cycle mesure."
        dernier = self.cycles[-1]
        if verdict == "REGRESSE":
            return (
                f"l'ecart devient NEGATIF aux cycles {', '.join(map(str, self.rechutes))} : "
                f"la memoire accumulee NUIT. Elaguer (borner la memoire) avant d'accumuler "
                f"davantage — c'est le resultat que ce protocole existe pour attraper."
            )
        if verdict == "PROGRESSE":
            return (
                f"au cycle {dernier.numero}, +{dernier.ecart} reussite(s) sur {dernier.essais} "
                f"avec la memoire accumulee ({dernier.memo_avant} souvenir(s)) et l'intervalle "
                f"exclut zero. Gain cumule sur le premier cycle : "
                f"{self.gain_cumule():+d} reussite(s)."
            )
        if dernier.ecart > 0:
            return (
                f"ecart positif (+{dernier.ecart} sur {dernier.essais}) mais l'intervalle "
                f"CONTIENT zero a {self.total_essais} essai(s) par bras : INDETERMINE. "
                f"Ce n'est pas un echec — c'est une mesure qui n'a pas encore conclu."
            )
        cout = self.cout_du_plateau()
        if cout:
            return (
                f"ecart nul ou negatif au dernier cycle ({dernier.ecart:+d}) alors que la "
                f"memoire a grandi jusqu'a {dernier.memo_apres} souvenir(s) — soit environ "
                f"{cout} jeton(s) injectes par cycle. La verification faisait DEJA le travail : "
                f"le souvenir n'ajoute rien et coute. Ce n'est pas une condamnation de la "
                f"memoire, c'est une mesure a ce niveau de difficulte — et le chiffre qui dit "
                f"qu'il faut la BORNER avant de l'enrichir."
            )
        return (
            f"ecart nul ou negatif au dernier cycle ({dernier.ecart:+d}) sans qu'une rechute "
            f"soit etablie : plateau. Un plateau n'est pas une condamnation : c'est le moment "
            f"ou l'on verifie ce que la memoire contient avant d'y ajouter."
        )

    def cout_du_plateau(self) -> int:
        """Les jetons injectes par cycle quand la memoire a grandi mais que rien ne bouge."""
        if len(self.cycles) < 2:
            return 0
        if self.cycles[-1].jetons_memoire > self.cycles[0].jetons_memoire:
            return self.cycles[-1].jetons_memoire
        return 0

    def gain_cumule(self) -> int:
        if len(self.cycles) < 2:
            return 0
        return self.cycles[-1].ecart - self.cycles[0].ecart


def run_cycles(
    *,
    skill: float = 0.12,
    runs: int = 3,
    cycles: int = 4,
    rounds: int = 3,
    seed_base: int = 0,
    warning_gain: float = 0.20,
    task_ids: tuple[str, ...] | None = None,
    max_memo: int = 200,
) -> RapportCycles:
    """Execute N cycles d'auto-amelioration et mesure chacun.

    `warning_gain` est l'effet EXPLICITE attribue a l'injection d'un souvenir (le mecanisme
    documente : retour d'echec structure). Il est declare dans le rapport : sans lui, on
    mesurerait un modele qui n'apprend pas d'un fichier JSON, ce qui ne prouve rien de la
    mecanique.
    """
    from ..cli import _check, _simulated_engine
    from ..loop.engine import WorkItem
    from ..trust import TrustRouter

    result = RapportCycles(skill=skill, runs=runs, rounds=rounds)
    taches = [t for t in TASKS if not task_ids or t.id in task_ids]
    if not taches or cycles <= 0 or runs <= 0:
        return result

    with tempfile.TemporaryDirectory(prefix="jio-cycles-") as tmp:
        racine = Path(tmp)
        memoire = FailureMemory(path=racine / "failures.jsonl")
        routeur = TrustRouter(path=racine / "trust.json")

        def _mission(
            task, seed: int, *, memoire_vive: bool, phase: str, arm: object | None = None
        ) -> tuple[bool, str, object | None]:
            """Une mission. Rend (succes, nom du bras, bras) — le bras sert a apparier le froid."""
            engine = _simulated_engine(
                task, skill=skill, seed=seed, max_rounds=rounds,
                journal_path=racine / "journal.jsonl",
            )
            if memoire_vive:
                engine.memory = memoire
                engine.router = routeur
                _set_gain(engine, warning_gain)
            elif arm is not None:
                # Meme bras, AUCUNE memoire : la seule difference restante est le souvenir.
                engine.router = _RouteurFige(arm)
            report = engine.run(
                Mission(objective=task.objective, id=f"{task.id}-{phase}-{seed}",
                        max_rounds=rounds),
                WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                         checks=dict(task.checks), spec=task.spec()),
            )
            choisi = getattr(engine, "_arm", None)
            return bool(_check(report.subject, task)), str(getattr(choisi, "name", "")), choisi

        for numero in range(1, cycles + 1):
            memo_avant = memoire.size
            rappels = 0
            froid = chaud = 0
            caracteres = 0
            choix: dict[str, int] = {}
            for task in taches:
                for run in range(runs):
                    # Memes graines dans les deux bras : la comparaison est APPARIEE.
                    graine = seed_base + (numero - 1) * 1000 + run
                    # Le CHAUD d'abord : il choisit le bras (via le vrai routeur), et le froid
                    # rejoue la meme mission avec ce bras FIGE. L'ordre compte : c'est ce qui
                    # rend la comparaison appariee sur (tache, graine, bras).
                    if memoire.recall(task.objective):
                        rappels += 1
                    caracteres += len(memoire.prompt_block(task.objective))
                    ok_chaud, bras, arm = _mission(task, graine, memoire_vive=True,
                                                   phase=f"chaud{numero}")
                    chaud += int(ok_chaud)
                    if bras:
                        choix[bras] = choix.get(bras, 0) + 1
                    ok_froid, _, _ = _mission(task, graine, memoire_vive=False,
                                              phase=f"froid{numero}", arm=arm)
                    froid += int(ok_froid)
            # Borne de securite : une memoire non bornee est la cause d'echec la plus documentee
            # (distraction, confusion). On la tronque par le HAUT, en gardant les plus recents.
            if max_memo and memoire.size > max_memo:
                _tronquer(memoire, max_memo)
            result.cycles.append(Cycle(
                numero=numero, memo_avant=memo_avant, memo_apres=memoire.size,
                rappels=rappels, froid=froid, chaud=chaud, essais=len(taches) * runs,
                caracteres_memoire=caracteres,
            ))
            result.choix_dernier_cycle = choix

        # Le bandit : ce qu'il a choisi au dernier cycle, et ce que chaque bras a rapporte.
        #
        # La table est indexee par CLASSE d'objectif : le meme bras y apparait plusieurs fois.
        # Afficher les lignes brutes ferait lire « minimal 1 fois, minimal 2 fois » — deux
        # lignes indiscernables pour un lecteur, et un « meilleur bras » couronne sur un
        # sous-echantillon. On agrege donc par NOM : tirages sommes, recompense moyenne
        # ponderee par les tirages. C'est le seul niveau ou la comparaison a un sens.
        agregat: dict[str, list[float]] = {}
        for _, nom, tirages, recompense, _cout in routeur.table():
            cumul = agregat.setdefault(nom, [0.0, 0.0])
            cumul[0] += float(tirages)
            cumul[1] += float(tirages) * float(recompense)
        solides = [
            (nom, int(cumul[0]), cumul[1] / cumul[0])
            for nom, cumul in agregat.items()
            if cumul[0] >= 2  # un bras juge sur UN tirage n'est pas un bras juge
        ]
        result.bras = sorted(
            [(nom, int(c[0]), c[1] / c[0]) for nom, c in agregat.items()],
            key=lambda r: -r[1],
        )
        if solides:
            # `solides` : (nom, tirages, recompense moyenne)
            meilleur = max(solides, key=lambda r: r[2])
            total_choix = sum(result.choix_dernier_cycle.values())
            result.concentration = (
                result.choix_dernier_cycle.get(meilleur[0], 0) / total_choix
                if total_choix
                else 0.0
            )
            result.meilleur_bras = meilleur[0]
            # Regret : ce qu'on a perdu en n'utilisant pas toujours le meilleur bras, estime
            # sur les recompenses MESUREES (et declare comme tel — ce n'est pas un oracle).
            result.regret = sum(r[1] * max(0.0, meilleur[2] - r[2]) for r in solides)

        # Intervalle apparie sur le dernier cycle : la seule affirmation causale du rapport.
        from ..bench.incertitude import intervalle_difference

        dernier = result.cycles[-1]
        if dernier.essais:
            # `intervalle_difference` prend deux ECHANTILLONS (des 0/1), pas deux couples
            # (succes, total) : on lui donne ce qu'il attend, en le construisant depuis les
            # compteurs du cycle. Une seule implementation de l'intervalle dans ce depot.
            froid = [1.0] * dernier.froid + [0.0] * (dernier.essais - dernier.froid)
            chaud = [1.0] * dernier.chaud + [0.0] * (dernier.essais - dernier.chaud)
            bas, haut = intervalle_difference(froid, chaud)
            result.bas, result.haut = bas, haut
            result.tranche = bool(bas > 0.0 or haut < 0.0)
    return result


def _set_gain(engine: object, gain: float) -> None:
    """L'effet d'avertissement est une MODELISATION declaree (retour d'echec structure)."""
    for provider in getattr(engine, "generators", ()):
        if hasattr(provider, "warning_gain"):
            provider.warning_gain = gain


def _tronquer(memoire: FailureMemory, maximum: int) -> None:
    """Garde les souvenirs les plus RECENTS. Une memoire bornee est une memoire utilisable."""
    try:
        souvenirs = list(memoire._records)
    except AttributeError:
        return
    if len(souvenirs) <= maximum:
        return
    try:
        memoire._records = souvenirs[-maximum:]
        memoire.save()
    except (AttributeError, OSError):
        return



