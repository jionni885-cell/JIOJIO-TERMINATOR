"""Mesure d'ablation : chaque brique du harness doit prouver son utilite.

Le depot affirme qu'une brique sert. Une affirmation sans mesure est exactement ce que ce
depot refuse partout ailleurs. Ce module ENLEVE donc la brique et regarde ce qui change,
sur les MEMES missions — appariement par (tache, graine) : ce qui reste de difference est
l'apport de la brique, et rien d'autre. L'appariement n'est pas un detail de methode : sur
cinq taches et deux graines, la variance entre missions domine largement l'effet cherche,
et deux echantillons INDEPENDANTS ne diraient rien.

Trois regles, ecrites ici parce qu'elles decident du rapport :

1. **`sans` dit exactement ce que le code fait.** « Sans preuve » ne veut pas dire « on
   jette le verificateur et on laisse le hasard decider » : cela veut dire que tout ce qui
   est soumis est declare prouve. Une ablation approximative mesure une autre question que
   celle posee, et son chiffre est inutilisable.

2. **Un levier qui ne bouge rien n'est PAS declare inutile.** Il est declare NON
   DISTINGUABLE a cette taille d'echantillon, avec les dissociations observees et le budget
   de mesure qu'il faudrait pour trancher. Confondre « pas d'effet » et « pas vu d'effet »
   est l'erreur que ce depot corrige partout ailleurs ; elle serait ici la plus couteuse,
   puisqu'elle ferait supprimer des briques sur la foi d'un echantillon trop petit.

3. **La metrique qui compte n'est pas le taux de reussite mais le nombre d'erreurs
   SILENCIEUSES** — livrees sans reserve ET fausses. Le harness existe pour que ce nombre
   soit nul, pas pour gagner trois points de reussite. Une brique dont l'ablation fait
   apparaitre une seule erreur silencieuse a prouve son utilite par EXISTENCE : cela ne
   demande aucune statistique, et aucune taille d'echantillon ne peut l'effacer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Mapping, Sequence

from ..audit.consensus import ConsensusOutcome
from ..audit.panel import CriticReport, Persona
from ..core.types import IntegrityReport, Verdict, Vote, Witness
from ..verify.executable import ProverResult

# --------------------------------------------------------------------------- #
# Ce que « sans » veut dire, en objets
# --------------------------------------------------------------------------- #


class ProverAveugle:
    """« Sans preuve » : tout ce qui est soumis est declare prouve.

    Le temoin rendu est VIDE de contenu (`command="(aucune)"`) mais present, parce que la
    machinerie du moteur exige un temoin pour considerer une preuve reussie. C'est
    exactement l'etat d'un systeme qui croit le generateur sur parole : il garde la forme
    de la preuve et jette sa substance.
    """

    journal: object | None = None
    appels: int = 0

    def prove(
        self,
        source: str,
        spec: object,
        *,
        hidden_checks: object = None,
        entrypoint: str = "",
        stage: object = None,
        preamble: str = "",
    ) -> ProverResult:
        self.appels += 1
        return ProverResult(
            witnesses=(
                Witness(
                    rule_id="sans-preuve",
                    command="(aucune)",
                    exit_code=0,
                    ok=True,
                    stdout="declaration de confiance, aucune execution",
                ),
            )
        )


class PanelSansRedTeam:
    """« Sans red-team » : le MEME nombre de critiques, mais tous complaisants.

    Le nombre de voix est conserve volontairement : baisser le panel declencherait le
    controle de faisabilite du moteur (« panel de 1 alors que le consensus en exige 3 »),
    et on mesurerait un blocage de configuration au lieu de l'absence de red-team. Ce
    qu'on enleve ici est la seule chose qui compte : la capacite des critiques a refuser.
    """

    def __init__(self, personas: Sequence[Persona] | Sequence[object] = ()) -> None:
        self.critics = tuple(personas)

    def run(
        self, content: str, spec: object, *, verifier: object = None, seed: int = 0
    ) -> tuple[CriticReport, ...]:
        return tuple(
            CriticReport(
                persona=str(getattr(p, "name", f"critique{i}")),
                vote=Vote(
                    agent=str(getattr(p, "name", f"critique{i}")),
                    decision=Verdict.PASS,
                    confidence=1.0,
                    rationale="sans red-team : aucun critique ne cherche de defaut",
                ),
            )
            for i, p in enumerate(self.critics)
        )


class ConsensusPremierAvis:
    """« Sans consensus » : le premier vote decide, et la decision est dite atteinte.

    Il n'y a ni quorum byzantin, ni seuil de supermajorite, ni estimation de faute : un
    avis suffit. Les critiques, eux, restent reels — c'est la REGLE D'AGREGATION qu'on
    enleve, pas les votants, sinon on mesurerait deux leviers a la fois.
    """

    min_panel: int = 1

    def decide(self, votes: Sequence[Vote]) -> ConsensusOutcome:
        liste = tuple(votes)
        if not liste:
            return ConsensusOutcome(
                decision=Verdict.ABSTAIN,
                reached=False,
                agreement=0.0,
                quorum_required=1,
                panel_size=0,
                estimated_faulty=0,
                tally={},
                dissent=(),
                confidence=0.0,
                effective_panel=0,
                reason="sans consensus : aucun vote a agreger",
            )
        premier = liste[0]
        return ConsensusOutcome(
            decision=premier.decision,
            reached=True,
            agreement=1.0,
            quorum_required=1,
            panel_size=len(liste),
            estimated_faulty=0,
            tally={premier.decision.value: len(liste)},
            dissent=(),
            confidence=premier.confidence,
            effective_panel=1,
            reason="sans consensus : le premier avis suffit (aucun quorum exige)",
        )


class PorteOuverte:
    """« Sans porte » : toute confiance est acceptee.

    La porte conforme calibre un seuil `tau` et refuse de livrer sous ce seuil ; sans elle,
    le seul critere de livraison redevient « le panel a approuve ».
    """

    alpha: float = 1.0
    calibrated: bool = False

    def tau(self) -> float:
        return 0.0

    def decide(self, confidence: float) -> tuple[bool, str]:
        return True, "sans porte : toute confiance est acceptee"

    def observe(self, score: float, correct: bool) -> None:  # pragma: no cover - no-op
        return None


class MoniteurPassif:
    """« Sans integrite » : le journal n'est plus rejoue, aucun exploit n'est cherche."""

    def audit(self, journal: object) -> IntegrityReport:
        return IntegrityReport(exploits=(), replay_digest="", steps=0)


# --------------------------------------------------------------------------- #
# Les leviers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Levier:
    """Une brique, ce qu'elle fait, et ce que « sans » veut dire."""

    nom: str
    quoi: str
    sans: str
    appliquer: Callable[[object], None]


def _sans_preuve(moteur: object) -> None:
    moteur.prover = ProverAveugle()  # type: ignore[attr-defined]


def _sans_red_team(moteur: object) -> None:
    panel = getattr(moteur, "panel", None)
    moteur.panel = PanelSansRedTeam(getattr(panel, "critics", ()) or ())  # type: ignore[attr-defined]


def _sans_consensus(moteur: object) -> None:
    moteur.consensus = ConsensusPremierAvis()  # type: ignore[attr-defined]


def _sans_porte(moteur: object) -> None:
    moteur.gate = PorteOuverte()  # type: ignore[attr-defined]


def _sans_integrite(moteur: object) -> None:
    moteur.monitor = MoniteurPassif()  # type: ignore[attr-defined]


def _sans_mutation(moteur: object) -> None:
    moteur.config.mutation_gate = False  # type: ignore[attr-defined]


def _sans_auto_coherence(moteur: object) -> None:
    moteur.config.self_check = False  # type: ignore[attr-defined]


def _sans_differentiel(moteur: object) -> None:
    moteur.config.differential = False  # type: ignore[attr-defined]


def _sans_temoins(moteur: object) -> None:
    moteur.config.temoins = False  # type: ignore[attr-defined]


def _sans_memoire(moteur: object) -> None:
    moteur.memory = None  # type: ignore[attr-defined]


def _sans_bibliotheque(moteur: object) -> None:
    moteur.bibliotheque = None  # type: ignore[attr-defined]


def _sans_routeur(moteur: object) -> None:
    moteur.router = None  # type: ignore[attr-defined]


#: L'ordre est celui de l'affichage. Chaque entree dit ce que la brique fait, puis ce que
#: le code fait a sa place quand on l'enleve — les deux phrases sont verifiees par les
#: tests, parce qu'une ablation qui ne fait pas ce qu'elle annonce mesure autre chose.
LEVIERS: tuple[Levier, ...] = (
    Levier(
        nom="preuve",
        quoi="execute les regles et refuse ce qui echoue",
        sans="tout ce qui est soumis est declare prouve (temoin vide, aucune execution)",
        appliquer=_sans_preuve,
    ),
    Levier(
        nom="red-team",
        quoi="des critiques independants cherchent le defaut d'un candidat",
        sans="le meme nombre de critiques, mais tous complaisants",
        appliquer=_sans_red_team,
    ),
    Levier(
        nom="consensus",
        quoi="agrege les votes avec quorum byzantin n >= 3f+1",
        sans="le premier avis decide, sans quorum ni supermajorite",
        appliquer=_sans_consensus,
    ),
    Levier(
        nom="porte",
        quoi="calibre un seuil conforme et refuse de livrer sous ce seuil",
        sans="toute confiance est acceptee",
        appliquer=_sans_porte,
    ),
    Levier(
        nom="integrite",
        quoi="rejoue le journal et cherche les 6 familles d'exploits",
        sans="aucun exploit n'est cherche",
        appliquer=_sans_integrite,
    ),
    Levier(
        nom="mutation",
        quoi="mute l'artefact pour verifier que ses regles peuvent echouer",
        sans="les regles ne sont jamais mises a l'epreuve d'un mutant",
        appliquer=_sans_mutation,
    ),
    Levier(
        nom="auto-coherence",
        quoi="confronte l'artefact a sa propre documentation",
        sans="la documentation de l'artefact n'est plus lue",
        appliquer=_sans_auto_coherence,
    ),
    Levier(
        nom="differentiel",
        quoi="compare les candidats a egalite de preuves et avoue leurs desaccords",
        sans="les candidats sont departages sans comparaison explicite",
        appliquer=_sans_differentiel,
    ),
    Levier(
        nom="temoins",
        quoi="traduit les regles en temoins executables quand la mission n'en fournit pas",
        sans="aucune traduction : sans oracle, le moteur ne peut plus rien prouver",
        appliquer=_sans_temoins,
    ),
    Levier(
        nom="memoire",
        quoi="rappelle les echecs deja payes",
        sans="le rappel est supprime",
        appliquer=_sans_memoire,
    ),
    Levier(
        nom="bibliotheque",
        quoi="retient les temoins valides par une livraison prouvee",
        sans="rien n'est retenu d'une mission a l'autre",
        appliquer=_sans_bibliotheque,
    ),
    Levier(
        nom="routeur",
        quoi="choisit combien de verification depenser (bandit UCB1)",
        sans="le budget de verification n'est plus adapte",
        appliquer=_sans_routeur,
    ),
)


def levier(nom: str) -> Levier:
    """Le levier porte ce nom — ou une erreur qui dit lesquels existent."""
    for lev in LEVIERS:
        if lev.nom == nom:
            return lev
    connus = ", ".join(lev.nom for lev in LEVIERS)
    raise KeyError(f"levier inconnu : {nom!r} (connus : {connus})")


def appliquer(moteur: object, noms: Iterable[str]) -> object:
    """Neutralise les leviers nommes sur CE moteur, puis le rend.

    On rend le moteur pour que l'appel se lise d'un seul geste a l'endroit ou il compte ;
    on ne construit pas un moteur « sans leviers » ici, parce que la facon d'assembler un
    moteur appartient a l'appelant (simulation, CLI reelle, mode sans oracle).
    """
    for nom in noms:
        levier(nom).appliquer(moteur)
    return moteur


# --------------------------------------------------------------------------- #
# Mesure
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Issue:
    """Ce qu'une mission a donne, en cinq nombres qui ne s'interpretent pas.

    `silencieuse` : livree SANS reserve et fausse. `livree` : le systeme a declare la
    mission livree (avec ou sans reserve). `abstention` : il a refuse de livrer.
    """

    juste: bool
    livree: bool          # livree SANS reserve
    reservee: bool        # livree AVEC reserve : le systeme a signale quelque chose
    silencieuse: bool     # livree sans reserve ET fausse — le seul chiffre qui doit valoir 0
    abstention: bool
    appels: int
    duree_s: float = 0.0
    #: Ce que la mission a FAIT, independamment de son resultat : (cle, compte) tries.
    #:
    #: C'est la reponse a un defaut mesure de ce rapport. Sur 12 leviers, 9 ressortaient
    #: « NON DISTINGUABLE » — meme justesse, memes livraisons, meme nombre d'appels — et le
    #: lecteur ne pouvait pas savoir si la brique n'avait SERVIs a rien ou si le banc ne
    #: l'avait jamais mise a l'epreuve. Les deux phrases appellent des actions opposees :
    #: dans un cas on retire du code, dans l'autre on change de banc. Les confondre, c'est
    #: livrer un instrument qui ne peut pas se tromper, donc qui ne prouve rien.
    #:
    #: Un tuple trie, pas un dict : un dataclass fige doit rester hachable, et l'ordre
    #: d'insertion d'un dict ne doit pas decider si deux bras sont egaux.
    activite: tuple[tuple[str, int], ...] = ()


@dataclass
class Bras:
    """Un bras de mesure : le moteur complet, ou le moteur prive d'un levier."""

    nom: str
    quoi: str = ""
    sans: str = ""
    issues: list[Issue] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.issues)

    @property
    def justes(self) -> int:
        return sum(1 for i in self.issues if i.juste)

    @property
    def livrees(self) -> int:
        return sum(1 for i in self.issues if i.livree)

    @property
    def reservees(self) -> int:
        return sum(1 for i in self.issues if i.reservee)

    @property
    def silencieuses(self) -> int:
        return sum(1 for i in self.issues if i.silencieuse)

    @property
    def abstentions(self) -> int:
        return sum(1 for i in self.issues if i.abstention)

    @property
    def appels(self) -> float:
        if not self.issues:
            return 0.0
        return sum(i.appels for i in self.issues) / len(self.issues)

    @property
    def duree(self) -> float:
        return sum(i.duree_s for i in self.issues)


def mcnemar_exact(b: int, c: int) -> float:
    """Test exact de McNemar sur paires appariees : b contre c, sans approximation.

    `b` = missions ou le moteur complet reussit et ou le levier enleve echoue ; `c` =
    l'inverse. Sous l'hypothese « le levier ne change rien », chaque dissociation est une
    piece jetee deux fois : la loi du nombre de `b` est binomiale(n = b+c, p = 1/2). On
    rend la probablite bilaterale EXACTE (pas de khi-deux : a b+c petit, l'approximation
    serait fausse, et c'est exactement la ou le banc se situe). `b+c = 0` rend 1.0 : zero
    dissociation n'est pas une preuve de nullite, c'est une absence de donnee.
    """
    n = b + c
    if n == 0:
        return 1.0
    extreme = max(b, c)
    queue = sum(math.comb(n, k) for k in range(extreme, n + 1)) / (2**n)
    return min(1.0, 2.0 * queue)


def _wald_apparie(b: int, c: int, n: int) -> tuple[float, float]:
    """IC95 de la difference de taux, pour des paires appariees (formule de Wald).

    Il est rendu meme quand le test ne conclut pas : « non concluant » sans intervalle
    laisserait croire que l'effet est nul, alors qu'il est seulement non mesure.
    """
    if n <= 0:
        return 0.0, 0.0
    delta = (b - c) / n
    variance = (b + c - (b - c) ** 2 / n) / (n * n)
    demi = 1.96 * math.sqrt(max(0.0, variance))
    return delta - demi, delta + demi


@dataclass(frozen=True)
class Comparaison:
    """Un levier, face au moteur complet, sur les memes missions."""

    nom: str
    quoi: str
    sans: str
    n: int
    justes_avec: int
    justes_sans: int
    livrees_avec: int
    livrees_sans: int
    reservees_avec: int
    reservees_sans: int
    silencieuses_avec: int
    silencieuses_sans: int
    abstentions_avec: int
    abstentions_sans: int
    appels_avec: float
    appels_sans: float
    b: int
    c: int
    p_exact: float
    ic_bas: float
    ic_haut: float
    #: Appariement sur la LIVRAISON PROPRE (livree sans reserve). C'est la metrique qui
    #: separe une brique qui rend le resultat JUSTE d'une brique qui le rend LIVRABLE :
    #: mesure faite, retirer le red-team ou le consensus ne rend pas le moteur faux, il le
    #: rend incapable de livrer sans reserve (8/10 -> 0/10). Sans ce second test, ces deux
    #: briques seraient declarees « non distinguees » alors qu'elles decident de tout.
    b_propre: int
    c_propre: int
    p_propre: float
    #: Appariement sur l'ACTIVITE : nombre de missions ou la brique enlevee change AU MOINS
    #: un observable (temoins executes, votes, constats par agent, usage). Zero signifie
    #: « le banc ne la met pas a l'epreuve », pas « la brique ne sert a rien ».
    missions_activite_differente: int = 0
    #: Total des observables comptes dans chaque bras — 0 veut dire NON MESURE, et alors
    #: l'instrument se tait au lieu d'affirmer.
    observations_avec: int = 0
    observations_sans: int = 0
    #: (cle, complet, sans) pour les seules cles qui changent : ce que le retrait coupe.
    ecarts_activite: tuple[tuple[str, int, int], ...] = ()
    verdict: str = ""
    note: str = ""

    @property
    def refus_supplementaires(self) -> int:
        """Missions que le levier retire fait perdre sans qu'un mensonge apparaisse.

        C'est le cas d'une brique REDONDANTE : les autres tiennent la ligne, donc aucune
        erreur silencieuse n'apparait, mais le systeme refuse des missions qu'il livrait.
        Le cout est reel (du travail perdu, pas un mensonge) et il doit etre dit.
        """
        return max(0, self.b - self.c)

    @property
    def livraisons_propres_perdues(self) -> int:
        """Livraisons SANS RESERVE que le retrait fait perdre (ou gagner, si negatif)."""
        return self.b_propre - self.c_propre

    @property
    def delta_points(self) -> float:
        if self.n <= 0:
            return 0.0
        return 100.0 * (self.justes_avec - self.justes_sans) / self.n


def _verdict(comp: Comparaison) -> tuple[str, str]:
    """Le verdict, et sa raison — dans cet ordre d'autorite.

    1. Une erreur silencieuse apparue a l'ablation est une PREUVE D'EXISTENCE : aucune
       statistique ne peut la relativiser, et aucune taille d'echantillon ne l'efface.
    2. Un levier dont le RETRAIT ameliore les livraisons propres est un COUT mesure : le
       rapport ne le cache pas et ne le defend pas — il demande la justification.
    3. Une perte de livraisons PROPRES (livrees sans reserve) est une preuve de
       contribution : la brique ne rend pas le resultat plus juste, elle le rend livrable.
    4. Une perte de justesse est une preuve de contribution sur la metrique de correction.
    5. Sinon, zero dissociation n'autorise PAS a dire « inutile » : on dit ce qui a ete
       mesure, l'intervalle, et ce qu'il faudrait pour trancher.
    """
    if comp.silencieuses_sans > comp.silencieuses_avec:
        return (
            "PREUVE (existence)",
            f"retirer cette brique fait livrer {comp.silencieuses_sans} erreur(s) sans "
            f"reserve (contre {comp.silencieuses_avec}) : preuve d'existence.",
        )
    if comp.p_propre <= 0.05 and comp.c_propre > comp.b_propre:
        return (
            "COUT MESURE",
            f"retirer cette brique rend les livraisons PLUS propres : "
            f"{comp.c_propre} gagnee(s) contre {comp.b_propre} perdue(s) "
            f"(McNemar exact p = {comp.p_propre:.4f}). A justifier, ou a interroger.",
        )
    if comp.p_propre <= 0.05 and comp.b_propre > comp.c_propre:
        return (
            "PREUVE (livraison propre)",
            f"{comp.b_propre} mission(s) ne sont plus livrees SANS reserve contre "
            f"{comp.c_propre} (McNemar exact p = {comp.p_propre:.4f}) : la brique ne rend "
            "pas le resultat plus juste, elle le rend livrable.",
        )
    if comp.p_exact <= 0.05 and comp.b > comp.c:
        return (
            "PREUVE (perte)",
            f"{comp.b} mission(s) perdue(s) contre {comp.c} gagnee(s) "
            f"a l'ablation (McNemar exact p = {comp.p_exact:.4f}).",
        )
    if comp.b == 0 and comp.c == 0 and comp.b_propre == 0 and comp.c_propre == 0:
        return (
            "NON DISTINGUABLE",
            f"aucune dissociation sur {comp.n} mission(s) appariee(s), ni sur la justesse "
            f"ni sur la livraison propre ; effet mesure dans "
            f"[{comp.ic_bas:+.0%} ; {comp.ic_haut:+.0%}].",
        )
    return (
        "NON CONCLUANT",
        f"justesse : {comp.b} dissociation(s) d'un cote, {comp.c} de l'autre ; "
        f"livraison propre : {comp.b_propre} contre {comp.c_propre} "
        f"(p = {comp.p_propre:.3f}).",
    )


def dissociations_requises(seuil: float = 0.05) -> int:
    """Nombre de dissociations UNIDIRECTIONNELLES qu'il faut pour que McNemar conclue.

    C'est le seul budget de mesure qui ait un sens ici, et il est exact : avec `k`
    dissociations toutes dans le meme sens, la probabilite bilaterale vaut `2 / 2^k`.
    Il en faut 6 pour passer sous 5 % (2/64 = 3,1 %), 8 pour passer sous 1 %.

    On ne reutilise PAS `essais_necessaires` du banc : sa formule suppose deux
    echantillons INDEPENDANTS et des proportions intermediaires ; elle rend 0 quand les
    deux taux valent 0 et 1 — c'est-a-dire exactement le cas d'une brique qu'on enleve.
    Un budget de mesure faux vaut moins que pas de budget du tout.
    """
    k = 1
    while 2.0 / (2**k) > seuil:
        k += 1
    return k


def _budget_de_mesure(comp: Comparaison) -> str:
    """Ce qu'il faudrait pour trancher, dit avec les nombres du test reellement employe."""
    if comp.verdict.startswith("PREUVE"):
        return ""
    besoin = dissociations_requises()
    if comp.b + comp.c == 0:
        return (
            f"aucune dissociation observee ; au moins {besoin} dissociations dans le meme "
            "sens seraient necessaires pour que ce test conclue."
        )
    return (
        f"observe : {comp.b} dans un sens, {comp.c} dans l'autre ; il en faudrait au moins "
        f"{besoin} dans le MEME sens pour conclure."
    )


@dataclass
class RapportAblation:
    """Le rapport complet : un bras par levier, et la comparaison appariee."""

    complet: Bras
    leviers: list[Comparaison]
    n_missions: int
    note: str = ""
    taches: int = 0
    graines: int = 0

    @property
    def prouves(self) -> list[Comparaison]:
        return [c for c in self.leviers if c.verdict.startswith("PREUVE")]

    @property
    def non_distingues(self) -> list[Comparaison]:
        return [c for c in self.leviers if c.verdict == "NON DISTINGUABLE"]

    @property
    def couts(self) -> list[Comparaison]:
        """Leviers dont le RETRAIT ameliore les livraisons : leur cout est mesure."""
        return [c for c in self.leviers if c.verdict == "COUT MESURE"]

    @property
    def silencieuses(self) -> int:
        """Erreurs silencieuses du moteur COMPLET. Le seul chiffre qui doit valoir zero."""
        return self.complet.silencieuses

    def en_dict(self) -> dict[str, object]:
        return {
            "n_missions": self.n_missions,
            "taches": self.taches,
            "graines": self.graines,
            "complet": {
                "justes": self.complet.justes,
                # TROIS etats de sortie, pas deux. `livrees` = livree SANS reserve ; `reservees`
                # = livree AVEC reserve nommee (le systeme a dit ce qu'il ne couvrait pas) ;
                # `abstentions` = rien livre. Publier seulement `livrees` faisait lire « le
                # moteur ne livre rien » la ou il livrait 13 artefacts sur 15 en nommant ses
                # reserves — et une mesure qui cache un etat ne se compare pas.
                "livrees": self.complet.livrees,
                "reservees": self.complet.reservees,
                "silencieuses": self.complet.silencieuses,
                "abstentions": self.complet.abstentions,
                "appels": round(self.complet.appels, 2),
            },
            "leviers": [
                {
                    "nom": c.nom,
                    "sans": c.sans,
                    "justes_avec": c.justes_avec,
                    "justes_sans": c.justes_sans,
                    "livrees_avec": c.livrees_avec,
                    "livrees_sans": c.livrees_sans,
                    "reservees_avec": c.reservees_avec,
                    "reservees_sans": c.reservees_sans,
                    "abstentions_sans": c.abstentions_sans,
                    "silencieuses_avec": c.silencieuses_avec,
                    "silencieuses_sans": c.silencieuses_sans,
                    "appels_avec": round(c.appels_avec, 2),
                    "appels_sans": round(c.appels_sans, 2),
                    "b": c.b,
                    "c": c.c,
                    "p_exact": round(c.p_exact, 6),
                    "b_propre": c.b_propre,
                    "c_propre": c.c_propre,
                    "p_propre": round(c.p_propre, 6),
                    "ic95_points": [round(100 * c.ic_bas, 1), round(100 * c.ic_haut, 1)],
                    "missions_activite_differente": c.missions_activite_differente,
                    "observations_avec": c.observations_avec,
                    "observations_sans": c.observations_sans,
                    "ecarts_activite": [
                        {"cle": cle, "complet": avec, "sans": sans}
                        for cle, avec, sans in c.ecarts_activite
                    ],
                    "verdict": c.verdict,
                    "note": c.note,
                }
                for c in self.leviers
            ],
            "note": self.note,
        }


def _somme_activite(issues: Sequence[Issue]) -> dict[str, int]:
    """Le total de chaque observable sur un bras, cle par cle.

    Une cle absente d'un bras et presente dans l'autre est un ecart autant qu'une valeur
    differente : c'est meme le cas le plus parlant (la brique coupee, son constat disparait
    entierement). On n'invente pas de cle a zero : on compare ce qui a ete compte.
    """
    total: dict[str, int] = {}
    for issue in issues:
        for cle, compte in issue.activite:
            total[cle] = total.get(cle, 0) + compte
    return total


#: Les observables qui PORTENT UN SENS : ils disent ce que le systeme a verifie, vote,
#: constate ou subi. Les autres (`usage:*`, `journal`, `sujet_caracteres`) sont des
#: compteurs de VOLUME : ils bougent des qu'un chemin de code differe, y compris quand
#: aucune decision ne change. Mesure a l'origine : sans cette distinction, les douze
#: leviers paraissaient « actifs » sur 10 missions sur 10 — `usage:events` suffisait — et
#: l'instrument restait muet tout en ayant l'air de parler.
#:  * `integrite_etapes` compte les pas de journal REJOUES par le moniteur : retirer le
#:    moniteur ne laisse pas « un peu moins de journal », il n'en rejoue plus un seul
#:    (508 -> 0 mesures). Ce n'est donc pas du volume, c'est le travail de la brique.
_SENS: frozenset[str] = frozenset(
    {"temoins", "temoins_ok", "votes", "exploits", "integrite_etapes"}
)


def _a_du_sens(cle: str) -> bool:
    """Cet observable dit-il quelque chose de la mission, ou seulement de son volume ?"""
    return cle in _SENS or cle.startswith("constat:")


def _activite_de_sens(activite: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    """La part SIGNIFIANTE d'une empreinte d'activite, seule comparable d'un bras a l'autre."""
    return tuple(sorted((c, v) for c, v in activite.items() if _a_du_sens(c)))


def _ecarts(avec: Mapping[str, int], sans: Mapping[str, int]) -> tuple[tuple[str, int, int], ...]:
    """Les cles dont le compte change, triees par ecart decroissant puis par nom.

    Le tri est ce qui rend la note lisible ET stable : un dictionnaire parcouru dans un
    ordre arbitraire ferait varier le texte d'un rapport a l'autre sans qu'une mesure
    change, et un rapport qui bouge tout seul n'est pas une preuve.
    """
    def rang(c: str) -> tuple[int, int, str]:
        return (0 if _a_du_sens(c) else 1, -(avec.get(c, 0) - sans.get(c, 0)), c)

    cles = sorted(
        {c for c in set(avec) | set(sans) if avec.get(c, 0) != sans.get(c, 0)},
        key=rang,
    )
    return tuple((c, avec.get(c, 0), sans.get(c, 0)) for c in cles)


def _phrase_activite(comp: Comparaison) -> str:
    """Ce que l'ablation a CHANGE dans le travail, quand elle ne change pas le verdict.

    Deux cas, et ils ne se valent pas :

    * aucune mission ne differe : le banc ne met pas la brique a l'epreuve. Le dire est
      decisif — `--missions 100` ne changerait rien, il faut un banc qui l'exerce ;
    * des missions different : la brique AGIT, mais son action ne deplace ici ni la
      justesse ni la livraison. C'est une redondance mesuree, pas une absence.

    L'instrument se TAIT quand il n'a rien compte (observations a zero) : « je n'ai pas
    regarde » et « il ne s'est rien passe » ne s'ecrivent pas pareil.
    """
    if comp.observations_avec == 0:
        return ""
    if not comp.missions_activite_differente:
        # Cas a part, mesure sur la porte en regime correle : une brique qui n'agit sur
        # AUCUN observable de mission mais deplace quand meme les DECISIONS (livrees,
        # reservees, abstentions) est un FILTRE DE DECISION. La confondre avec « le banc
        # ne l'exerce pas » conseillerait de changer de banc alors qu'elargir
        # l'echantillon est exactement ce qui peut trancher.
        decisions = comp.b + comp.c + comp.b_propre + comp.c_propre
        if decisions:
            return (
                f"la brique est un FILTRE DE DECISION : elle n'agit sur aucun observable de "
                f"mission, mais son retrait deplace les livraisons ({comp.b} contre {comp.c}, "
                f"livraisons propres {comp.b_propre} contre {comp.c_propre}). C'est son "
                "travail — la decision fait partie de ce qu'elle gouverne. `--missions` peut "
                "trancher : chaque dissociation supplementaire rapproche du seuil."
            )
        volume = ", ".join(
            f"{cle} {avec}->{sans}" for cle, avec, sans in comp.ecarts_activite[:2]
        )
        detail = (
            f" Seuls des compteurs de VOLUME bougent ({volume}), et ils bougeraient pour "
            "n'importe quel changement de chemin de code."
            if volume
            else " Aucun compteur ne bouge non plus."
        )
        return (
            f"ACTIVITE IDENTIQUE sur les {comp.n} mission(s) : retirer cette brique ne "
            "change aucun observable de sens (temoins executes, votes, constats, exploits)."
            + detail
            + " Le banc, tel qu'il est, ne la met donc pas a l'epreuve : elargir `--missions` "
            "(memes taches, autres graines) ne peut rien y changer — il faut des missions ou "
            "la brique ait quelque chose a faire, ou un autre mode."
        )
    apercu = ", ".join(
        f"{cle} {avec}->{sans}" for cle, avec, sans in comp.ecarts_activite if _a_du_sens(cle)
    ) or ", ".join(f"{cle} {avec}->{sans}" for cle, avec, sans in comp.ecarts_activite[:3])
    tete = (
        f"la brique AGIT sur {comp.missions_activite_differente}/{comp.n} mission(s) "
        f"({apercu})."
    )
    pour = comp.b + comp.b_propre
    contre = comp.c + comp.c_propre
    if pour == 0 and contre == 0:
        return (
            tete + " Aucune dissociation ici : sur ces missions elle est REDONDANTE — les "
            "autres briques tenaient deja la ligne — et non absente : retirer du code sur "
            "cette base serait une conclusion tiree d'un banc qui ne l'a pas mise en "
            "difficulte."
        )
    if pour >= contre:
        return (
            tete + f" Les ecarts observes vont dans SON sens ({pour} contre {contre}) : elle "
            "travaille, et ce qui manque est un echantillon plus grand ou des missions plus "
            "dures — pas une brique a retirer."
        )
    return (
        tete + f" Les ecarts vont CONTRE elle ({contre} contre {pour}) : a interroger, car "
        "une brique qui degrade la ou elle agit est un cout, pas une assurance."
    )


def mesurer(
    executer: Callable[[int, int, tuple[str, ...]], Issue],
    *,
    taches: int = 5,
    graines: int = 2,
    leviers: Sequence[str] | None = None,
    avancer: Callable[[str], None] | None = None,
) -> RapportAblation:
    """Compare le moteur complet a chaque levier enleve, sur les MEMES missions.

    `executer(tache, graine, ablations)` recoit l'INDEX de la tache, la graine, et les
    leviers a neutraliser ; il rend l'`Issue` de la mission. L'appariement est garanti par
    la construction : le plan de missions est calcule UNE fois et parcouru a l'identique
    pour tous les bras. Une graine tiree differemment d'un bras a l'autre mesurerait le
    tirage, pas le levier.

    `avancer` est appele apres CHAQUE mission, avec un libelle lisible (« complet 3/10 »). Ce
    module ne sait pas ou ecrire — il ne connait ni le terminal ni le fichier de l'appelant —
    donc il ne fait que SIGNALER. Mesure a l'origine : `jio ablation` tourne plusieurs minutes
    sans rien dire, ce qui le rend indistinguable d'une commande bloquee ; le seul recours
    etait de l'interrompre, c'est-a-dire de ne jamais obtenir la mesure.
    """
    noms = tuple(leviers) if leviers is not None else tuple(lev.nom for lev in LEVIERS)
    for nom in noms:
        levier(nom)  # un nom inconnu doit lever AVANT de faire tourner quoi que ce soit
    plan = [(t, g) for t in range(max(1, taches)) for g in range(max(1, graines))]

    total = len(plan) * (len(noms) + 1)
    fait = 0
    complet = Bras(nom="complet", quoi="le harness tel quel")
    for tache, graine in plan:
        complet.issues.append(executer(tache, graine, ()))
        fait += 1
        if avancer is not None:
            avancer(f"complet {fait}/{total}")

    comparaisons: list[Comparaison] = []
    for nom in noms:
        definition = levier(nom)
        bras = Bras(nom=nom, quoi=definition.quoi, sans=definition.sans)
        for tache, graine in plan:
            bras.issues.append(executer(tache, graine, (nom,)))
            fait += 1
            if avancer is not None:
                avancer(f"sans {nom} {fait}/{total}")

        b = sum(
            1
            for avec, sans in zip(complet.issues, bras.issues)
            if avec.juste and not sans.juste
        )
        c = sum(
            1
            for avec, sans in zip(complet.issues, bras.issues)
            if sans.juste and not avec.juste
        )
        b_propre = sum(
            1
            for avec, sans in zip(complet.issues, bras.issues)
            if avec.livree and not sans.livree
        )
        c_propre = sum(
            1
            for avec, sans in zip(complet.issues, bras.issues)
            if sans.livree and not avec.livree
        )
        p = mcnemar_exact(b, c)
        bas, haut = _wald_apparie(b, c, len(plan))
        activite_avec = _somme_activite(complet.issues)
        activite_sans = _somme_activite(bras.issues)
        # La comparaison porte sur les observables de SENS. Comparer l'empreinte entiere
        # ferait dire « la brique agit » a toute ablation qui deplace un compteur interne,
        # et un instrument qui repond oui a tout ne peut pas se tromper — donc ne prouve rien.
        missions_activite = sum(
            1
            for a, s in zip(complet.issues, bras.issues)
            if _activite_de_sens(dict(a.activite)) != _activite_de_sens(dict(s.activite))
        )
        comparaison = Comparaison(
            nom=nom,
            quoi=definition.quoi,
            sans=definition.sans,
            n=len(plan),
            justes_avec=complet.justes,
            justes_sans=bras.justes,
            livrees_avec=complet.livrees,
            livrees_sans=bras.livrees,
            reservees_avec=complet.reservees,
            reservees_sans=bras.reservees,
            silencieuses_avec=complet.silencieuses,
            silencieuses_sans=bras.silencieuses,
            abstentions_avec=complet.abstentions,
            abstentions_sans=bras.abstentions,
            appels_avec=complet.appels,
            appels_sans=bras.appels,
            b=b,
            c=c,
            p_exact=p,
            ic_bas=bas,
            ic_haut=haut,
            b_propre=b_propre,
            c_propre=c_propre,
            p_propre=mcnemar_exact(b_propre, c_propre),
            missions_activite_differente=missions_activite,
            observations_avec=sum(activite_avec.values()),
            observations_sans=sum(activite_sans.values()),
            ecarts_activite=_ecarts(activite_avec, activite_sans),
            verdict="",
            note="",
        )
        verdict, note = _verdict(comparaison)
        # L'activite ne s'ajoute QU'AUX verdicts qui ne concluent pas : quand une preuve
        # est etablie, la note dit deja quoi ; ailleurs, elle est la seule prise.
        banc_muet = False
        if verdict.startswith("NON"):
            phrase = _phrase_activite(comparaison)
            if phrase:
                banc_muet = phrase.startswith("ACTIVITE IDENTIQUE")
                note = f"{note} {phrase}" if note else phrase
        # Un budget de mesure n'a de sens que si l'echantillon peut trancher. Quand
        # l'activite est identique, elargir ne peut RIEN changer : l'ancienne note
        # conseillait alors `--missions`, c'est-a-dire de payer des heures pour un
        # resultat deja connu. La phrase d'activite remplace le budget, elle ne s'y ajoute pas.
        budget = "" if banc_muet else _budget_de_mesure(comparaison)
        comparaisons.append(
            replace(
                comparaison,
                verdict=verdict,
                note=(note + " " + budget) if budget else note,
            )
        )

    note = ""
    if not plan:
        note = "aucune mission planifiee : il n'y a rien a mesurer."
    return RapportAblation(
        complet=complet,
        leviers=comparaisons,
        n_missions=len(plan),
        note=note,
        taches=max(1, taches),
        graines=max(1, graines),
    )


def _ligne(cellules: Sequence[str], largeurs: Sequence[int]) -> str:
    return "    " + " ".join(
        c.ljust(largeur)[:largeur] for c, largeur in zip(cellules, largeurs)
    )


def formater(rapport: RapportAblation) -> str:
    """Le rapport lisible. Chaque ligne dit ce qui a ete enleve ET avec quoi."""
    lignes: list[str] = []
    complet = rapport.complet
    lignes.append(
        f"  ABLATION DU HARNESS  ·  {rapport.n_missions} mission(s) appariee(s)  ·  "
        f"{len(rapport.leviers)} levier(s)"
    )
    lignes.append(
        f"    moteur complet : {complet.justes}/{complet.n} justes  ·  "
        f"{complet.livrees} livree(s)  ·  {complet.silencieuses} SILENCIEUSE(S)  ·  "
        f"{complet.abstentions} abstention(s)  ·  {complet.appels:.1f} appel(s)/mission"
    )
    lignes.append(
        "    Lecture : une erreur SILENCIEUSE est une mission livree sans reserve et fausse."
    )
    lignes.append("    C'est le seul chiffre qui doit valoir zero ; le reste se lit ensuite.")
    lignes.append("")
    largeurs = (13, 15, 8, 8, 11, 6, 7, 10)
    lignes.append(
        _ligne(
            (
                "levier",
                "justes",
                "livrees",
                "reserve",
                "silencieuses",
                "abst.",
                "appels",
                "activite",
            ),
            largeurs,
        )
    )
    lignes.append(
        _ligne(
            tuple("-" * l for l in largeurs),
            largeurs,
        )
    )
    entete = (
        "(complet)",
        f"{complet.justes}/{complet.n}",
        f"{complet.livrees}",
        f"{complet.reservees}",
        f"{complet.silencieuses}",
        f"{complet.abstentions}",
        f"{complet.appels:.1f}",
        f"{sum(v for i in complet.issues for v in dict(i.activite).values())}",
    )
    lignes.append(_ligne(entete, largeurs))
    for c in rapport.leviers:
        lignes.append(
            _ligne(
                (
                    c.nom,
                    f"{c.justes_sans}/{c.n}",
                    f"{c.livrees_sans}",
                    f"{c.reservees_sans}",
                    f"{c.silencieuses_sans}",
                    f"{c.abstentions_sans}",
                    f"{c.appels_sans:.1f}",
                    (
                        f"{c.missions_activite_differente}/{c.n} m."
                        if c.observations_avec
                        else "-"
                    ),
                ),
                largeurs,
            )
        )
        lignes.append(f"      sans : {c.sans}")
    lignes.append("")
    lignes.append("  VERDICTS")
    besoin = dissociations_requises()
    for c in rapport.leviers:
        lignes.append(f"    {c.nom:<13} {c.verdict:<18} {c.note}")
        if c.verdict == "NON DISTINGUABLE":
            if (
                c.observations_avec
                and not c.missions_activite_differente
                and not (c.b + c.c + c.b_propre + c.c_propre)
            ):
                # Le banc ne l'exerce pas : conseiller `--missions` serait une fausse
                # piste payee en heures. Le calcul de puissance ne s'applique pas, il n'y a
                # rien a echantillonner.
                lignes.append(
                    "                  le banc ne l'exerce pas : aucune puissance "
                    "d'echantillon ne conclura, il faut une mission ou la brique ait "
                    "quelque chose a faire."
                )
            else:
                lignes.append(
                    f"                  aucune dissociation : il en faudrait au moins {besoin} "
                    "dans le meme sens"
                )
                lignes.append(
                    f"                  pour conclure (2/2^{besoin} = "
                    f"{100 * 2.0 / 2**besoin:.1f} %) — l'absence de preuve n'est pas la "
                    "preuve de l'absence."
                )
        elif c.verdict == "NON CONCLUANT":
            lignes.append(
                f"                  l'ecart n'est pas tranche : il faudrait au moins "
                f"{besoin} dissociations dans le MEME sens."
            )
        if c.refus_supplementaires:
            # Mesure faite : le retrait coute des REFUS, pas des mensonges. Les autres
            # briques retiennent la livraison que le levier enleve rendait possible — ce
            # n'est pas une preuve que le levier est inutile, c'est la trace d'une
            # redondance, et elle doit etre ecrite comme telle.
            lignes.append(
                f"                  a l'ablation : {c.refus_supplementaires} mission(s) en "
                "moins, sans qu'un mensonge apparaisse"
            )
            lignes.append(
                "                  -> sur cet echantillon, d'autres briques ont retenu la"
                " livraison."
            )
        if c.livraisons_propres_perdues > 0:
            lignes.append(
                f"                  livraisons sans reserve : {c.b_propre} perdue(s) contre "
                f"{c.c_propre} gagnee(s)"
                + (
                    f" (p = {c.p_propre:.4f})"
                    if c.p_propre <= 0.05
                    else f" (non tranche, p = {c.p_propre:.3f})"
                )
            )
        elif c.livraisons_propres_perdues < 0:
            lignes.append(
                f"                  livraisons sans reserve : {abs(c.c_propre)} GAGNEE(S) en "
                f"moins (p = {c.p_propre:.4f}) — a justifier, ou a interroger"
            )
    lignes.append("")
    lignes.append(
        "    Colonne « activite » : missions ou le retrait change un observable DE SENS"
    )
    lignes.append(
        "    (temoins executes, votes, constats par agent, exploits cherches, journal"
    )
    lignes.append(
        "    rejoue) — plus sensible que le verdict. Les compteurs de VOLUME (jetons,"
    )
    lignes.append(
        "    evenements, taille du sujet) en sont exclus : ils bougent des qu'un chemin de"
    )
    lignes.append(
        "    code differe, meme quand rien ne change. D'ou trois lectures : le banc ne"
    )
    lignes.append(
        "    l'exerce pas · elle agit sans rien deplacer · elle agit et l'ecart penche."
    )
    lignes.append(
        "    Une quatrieme : le FILTRE DE DECISION — aucun observable de mission ne bouge,"
    )
    lignes.append(
        "    mais les livraisons/abstentions si (`--correlee` le montre sur la porte)."
    )
    lignes.append(
        "    Un levier « NON DISTINGUABLE » n'est pas un levier inutile : c'est un levier"
    )
    lignes.append(
        "    dont l'effet n'a pas ete vu a cette taille. `--missions` elargit l'echantillon,"
    )
    lignes.append(
        "    mais SEULEMENT la ou la colonne « activite » montre que la brique agit : la ou"
    )
    lignes.append(
        "    elle est identique, l'echantillon ne peut rien dire, il faut d'autres missions."
    )
    lignes.append("    chaque ligne de verdict dit ce qu'il faudrait pour trancher.")
    if rapport.note:
        lignes.append("")
        lignes.append(f"    {rapport.note}")
    return "\n".join(lignes)
