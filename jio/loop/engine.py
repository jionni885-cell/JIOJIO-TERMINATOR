"""Boucle centrale — generer, prouver, auditer, corriger, re-prouver.

Sept etapes, dans cet ordre exact :

    1. SPECIFICATION   l'objectif devient des regles enumerees (1 test par regle)
    2. GENERATION      N candidats heterogenes, en parallele
    3. PREUVE          execution reelle — fail-closed, pas de temoin pas de vie
    4. AUDIT           critiques a personas divergentes, en revue AVEUGLE
    5. CONSENSUS       quorum byzantin n >= 3f+1, jamais de moyenne silencieuse
    6. GARDE           acceptation calibree + detection d'oscillation
    7. INTEGRITE       rejeu deterministe — l'agent a-t-il triche ?

Chaque etape ecrit dans le journal hash-chaine. Rien n'est cache, tout est
rejouables apres coup.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from ..audit.blame import BlameLedger, FirstErrorLocator
from ..audit.consensus import ConsensusEngine, ConsensusOutcome
from ..audit.integrity import IntegrityMonitor
from ..audit.oscillation import OscillationGuard, ProgressPoint
from ..audit.panel import AuditPanel, CriticReport
from ..core.errors import (
    BudgetExhausted,
    FailClosed,
    IntegrityViolation,
    OscillationDetected,
)
from ..core.journal import Journal
from ..core.types import (
    Artifact,
    Blame,
    FailureFeedback,
    Finding,
    Mission,
    MissionReport,
    MissionStatus,
    RuleKind,
    Severity,
    Spec,
    Stage,
    TrustLevel,
    Verdict,
    Witness,
)
from ..gate.conformal import ConformalGate
from ..providers.base import Completion, Message, Provider
from ..spec.compiler import SpecCompiler
from ..spec.library import empreinte_regle
from ..spec.witness import Temoignage, traduire
from ..verify.executable import ExecutableProver, ProverResult


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass
class EngineConfig:
    """Reglages de la boucle."""

    max_rounds: int = 5
    time_budget_s: float = 600.0
    #: Temperatures successives : diversite forcee entre les tentatives.
    temperatures: tuple[float, ...] = (0.0, 0.35, 0.7, 0.95)
    #: Nombre de candidats par tour (best-of-N adaptatif).
    candidates_per_round: int = 3
    max_tokens: int = 4096
    #: Verifier aussi l'integrite a chaque tour (plus cher, plus sur).
    integrity_every_round: bool = False
    min_decorrelation: float = 0.0
    #: Muter l'artefact pour verifier que les regles peuvent ECHOUER.
    mutation_gate: bool = True
    #: Nombre de mutants executes (cout borne : chaque mutant est une passe entiere).
    mutation_budget: int = 4
    #: Comparer les candidats a EGALITE de preuves et AVOUER leurs desaccords.
    #: Cout : aucun appel de modele (les candidats sont deja payes), seulement des
    #: executions dans le bac a sable.
    differential: bool = True
    #: Confronter l'artefact a SA PROPRE documentation (exemples `>>>`, annotations).
    #: Un artefact qui contredit ce qu'il affirme est suspect, meme quand il satisfait
    #: la specification de la mission — et c'est un signal qu'on peut renvoyer au
    #: modele, precis et executable. Cout : une derivation STATIQUE (aucun reseau) et
    #: une passe de bac a sable par regle trouvee, memorisee par artefact.
    self_check: bool = True
    #: Traduire les regles de la specification en TEMOINS EXECUTABLES quand la mission
    #: n'en fournit aucun (toute mission reelle : le banc, lui, a ses oracles).
    #: Sans cela, la seule preuve executable est l'auto-coherence — l'artefact peut
    #: tenir sa propre documentation et ne rien faire de la mission. Cout : UN appel
    #: de modele, une fois par mission. La traduction est sous garde-fous, et un
    #: temoin que TOUS les candidats echouent est declare NON DISCRIMINANT : il ne
    #: peut jamais, a lui seul, faire rejeter un candidat.
    temoins: bool = True
    #: FAMILLE de temoins : "code" (defaut) ou "prose".
    #:
    #: Le choix ne cree pas une seconde boucle : il change ce que le candidat EST
    #: (un document, pas un module) et la maniere de le demander au modele. La
    #: preuve, le panel, le consensus, la porte, le journal et les garde-fous
    #: restent identiques — un document traverse la meme machinerie qu'un
    #: programme, et une seule doctrine doit etre expliquee.
    #:
    #: En famille "prose", les trois reglages qui n'ont pas de sens sont mis a
    #: False par `Engine.__post_init__` : il n'y a ni documentation executable a
    #: confronter (`self_check`), ni mutant a tuer (`mutation_gate`), ni regle de
    #: code a traduire en test (`temoins`). Les laisser actifs produirait des
    #: abstentions incomprehensibles.
    famille: str = "code"
    #: Graine de la MISSION. Elle entre dans la graine de chaque appel de generation.
    #:
    #: Le defaut (0) rend une mission reproductible, ce qui est voulu. Le bug qu'elle
    #: corrige etait ailleurs, et il etait invisible : la generation utilisait
    #: `1000 * tour + i`, SANS la graine de la mission. Consequences mesurees :
    #:
    #:   * deux executions du banc avec des graines de mission differentes
    #:     produisaient EXACTEMENT les memes candidats — verifie sur trois graines,
    #:     memes empreintes. Les `runs` repetitions des bras S2/S3 etaient donc le
    #:     MEME tirage repete, et l'ecart mesure entre le harness et le modele brut
    #:     n'etait pas une moyenne ;
    #:   * une mission de prose mesuree a competence 0.2 rendait 100 % de reussite,
    #:     non parce que le harness etait bon, mais parce que le tirage etait fige.
    #:
    #: Une mesure dont la variance est nulle par construction ne peut pas etre
    #: presentee comme un resultat.
    seed: int = 0


@dataclass(frozen=True)
class WorkItem:
    """Ce qu'il faut produire, et comment le verifier."""

    objective: str
    entrypoint: str = ""
    checks: Mapping[str, str] = field(default_factory=dict)
    spec: Spec | None = None
    language: str = "python"


# --------------------------------------------------------------------------- #
# Moteur
# --------------------------------------------------------------------------- #


@dataclass
class Engine:
    """Le noyau. Assemble les couches et fait tourner la boucle."""

    generators: Sequence[Provider]
    journal: Journal = field(default_factory=Journal)
    panel: AuditPanel = field(default_factory=AuditPanel.simulated)
    prover: ExecutableProver = field(default_factory=ExecutableProver)
    consensus: ConsensusEngine = field(default_factory=ConsensusEngine)
    monitor: IntegrityMonitor = field(default_factory=IntegrityMonitor)
    gate: ConformalGate = field(default_factory=ConformalGate)
    config: EngineConfig = field(default_factory=EngineConfig)
    spec_compiler: SpecCompiler = field(default_factory=SpecCompiler)
    #: Routeur de confiance : choisit COMBIEN de verification depenser (bandit UCB1).
    router: object | None = None
    #: Memoire des echecs : les erreurs deja payees ne sont pas repayees.
    memory: object | None = None
    #: Bibliotheque de temoins : une traduction VALIDEE par une livraison prouvee
    #: devient une capacite durable, et la prochaine mission identique ne demande
    #: plus rien au modele (cout de traduction ramene a zero).
    bibliotheque: object | None = None
    #: Bras choisi par le routeur pour la mission en cours (interne).
    _arm: object | None = field(default=None, init=False, repr=False)
    #: Memoire du controle d'auto-coherence (interne, voir `__post_init__`).
    _self_check_cache: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.config.famille == "prose":
            # Trois etages n'ont aucun sens sur un document. Les desactiver ICI
            # plutot que dans chaque appelant : un seul endroit decide, et il est
            # impossible d'en oublier un.
            object.__setattr__(self.config, "self_check", False)
            object.__setattr__(self.config, "mutation_gate", False)
            object.__setattr__(self.config, "temoins", False)
        # Tous les temoins sont journalises : une preuve non tracee n'existe pas.
        self.prover.journal = self.journal
        # Memoire du controle d'auto-coherence, par contenu d'artefact : le
        # verificateur est appele par CHAQUE critique du panel, et refaire la meme
        # passe a chaque fois multiplierait le cout sans rien apprendre.
        object.__setattr__(self, "_self_check_cache", {})
        # Motif du dernier rejet par auto-coherence, par contenu d'artefact : la
        # boucle de reprise s'en sert pour que le modele sache QUOI corriger.
        self._motif_auto: dict[str, str] = {}
        #: Temoins traduits depuis la specification, une seule fois par mission :
        #: la traduction est un appel de modele, elle ne se repete pas.
        self._temoignage: Temoignage | None = None
        #: Regles declarees NON PROUVEES : le temoin traduit a echoue sur tous les
        #: candidats, donc il ne prouve rien. Une mission qui en porte une ne peut
        #: pas etre declaree livree sans reserve — c'est la doctrine « un etat se
        #: prouve avant d'etre cru ».
        self._regles_non_prouvees: set[str] = set()
        #: Temoins repris dans la bibliotheque pour la mission en cours (aucune traduction).
        self._temoins_memorises: bool = False

    # -- point d'entree ----------------------------------------------------- #

    def run(self, mission: Mission, work: WorkItem | None = None) -> MissionReport:
        started = time.monotonic()
        work = work or WorkItem(objective=mission.objective)
        self.journal.append("mission", {"id": mission.id, "objective": mission.objective,
                                        "alpha": mission.alpha, "risk": mission.risk.value})

        # --- 1. SPECIFICATION -------------------------------------------- #
        spec = work.spec or self._compile(mission, work)
        self.journal.append(
            "stage", {"name": Stage.SPEC.value, "produced": True, "verified": True,
                      "rules": [r.id for r in spec.rules],
                      "under_specified": list(spec.under_specified)}
        )

        # --- 0. ROUTAGE : combien de verification depenser ? ----------------- #
        # Le routeur (bandit UCB1) choisit la configuration avant de depenser
        # quoi que ce soit. Un harness regle une fois pour toutes est toujours
        # mal regle pour une partie des taches.
        self._arm = None
        if self.router is not None:
            self._arm = self.router.choose(mission.objective)
            self.journal.append(
                "route",
                {
                    "arm": self._arm.name,
                    "candidates": self._arm.candidates,
                    "rounds": self._arm.rounds,
                    "panel_size": self._arm.panel_size,
                    "alpha": self._arm.alpha,
                    "cost": self._arm.cost,
                },
            )
            try:
                self.gate.alpha = float(self._arm.alpha)
            except Exception:  # une porte qui refuse le reglage ne doit pas bloquer
                pass

        # --- 0 bis. FAISABILITE DE LA CONFIGURATION ------------------------- #
        # Mesure d'ablation : avec un panel trop petit, 20 missions sur 20 finissent
        # en reserve apres 13.8 appels, contre 5.4 pour un panel complet — pour le
        # MEME resultat. Reessayer ne peut pas aider : le blocage est dans la
        # configuration, pas dans le candidat. On le calcule une fois, et on
        # s'arrete des que la preuve est complete.
        infeasible = self.infeasibility()
        if infeasible:
            self.journal.append("feasibility", {"blocked": True, "reason": infeasible})

        guard = OscillationGuard()
        ledger = BlameLedger()
        best: tuple[Artifact, ProverResult] | None = None
        reports: tuple[CriticReport, ...] = ()
        outcome: ConsensusOutcome | None = None
        feedback: FailureFeedback | None = None
        warnings: list[Finding] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        rounds = 0

        for rnd in range(mission.max_rounds or self.config.max_rounds):
            rounds = rnd + 1
            self._check_budget(started, mission)

            # --- 2. GENERATION -------------------------------------------- #
            candidates = self._generate(work, spec, rnd, feedback, usage)
            if not candidates:  # pragma: no cover
                break

            # --- 3. PREUVE EXECUTABLE (fail-closed) ----------------------- #
            # Les regles de la mission doivent devenir executables : sans temoin,
            # elles ne sont que des slogans, et l'artefact peut tenir sa propre
            # documentation en ne faisant rien de la mission (voir spec/witness.py).
            temoignage = self._temoins_de_la_spec(spec, work, usage)
            checks: dict[str, str] = dict(self._checks_en_vigueur(work))
            if rnd == 0 and temoignage.appels:
                # PROVENANCE DE LA PREUVE, toujours declaree : le rapport doit dire sur
                # QUOI il s'appuie. Un artefact prouve par des temoins traduits par un
                # modele n'est pas prouve de la meme facon qu'un artefact prouve par
                # les oracles de la mission, et le lecteur a le droit de le savoir.
                warnings.append(self._avertir_sur_les_temoins(temoignage))
            proved: list[tuple[Artifact, ProverResult]] = []
            for art in candidates:
                try:
                    res = self.prover.prove(
                        art.content, spec, hidden_checks=checks,
                        entrypoint=work.entrypoint, stage=Stage.PROVE,
                    )
                except FailClosed as exc:
                    # Fail-closed : aucune preuve disponible. Ce n'est pas un echec
                    # de l'artefact, c'est l'absence de moyen de le prouver. La
                    # bonne sortie est l'abstention, jamais un plantage ni un
                    # « ca a l'air bon ».
                    self.journal.append(
                        "fail-closed", {"round": rnd, "reason": str(exc),
                                        "stage": Stage.PROVE.value}
                    )
                    warnings.append(
                        Finding(agent="prover", severity=Severity.HIGH,
                                message=f"preuve impossible : {exc}")
                    )
                    proved = []
                    break
                proved.append((art, res))
                ledger.steps.append(art.agent)
                ledger.messages.append(self._reason(art, res))

            if not proved:
                abstained_for = (
                    f"aucune preuve executable disponible pour cette mission "
                    f"({len(spec.rules)} regle(s) declaree(s), 0 temoin). "
                    "Fournissez des oracles (banc d'essai) ou des exemples `>>>`."
                )
                self.journal.append("abstention", {"round": rnd, "reason": abstained_for})
                residual = self._finalize(
                    mission=mission, spec=spec, best=best, reports=reports,
                    outcome=outcome, integrity=self.monitor.audit(self.journal),
                    warnings=tuple(warnings), rounds=rounds, usage=usage,
                    started=started, guard=guard, ledger=ledger,
                    force_reason=abstained_for, infeasible=infeasible,
                )
                return residual

            # Un temoin que TOUS les candidats echouent ne prouve RIEN sur eux :
            # soit il est faux, soit il discrimine mal. Il ne peut donc pas, a lui
            # seul, faire rejeter un candidat — il declasse, et il s'AVOUE.
            if temoignage.tests:
                self._signaler_temoins_non_discriminants(
                    proved, temoignage, warnings, rnd, work.objective or spec.mission)

            # Tri par (preuves, MOINS de reserves). Mesure : sur une mission de
            # document ou un candidat cite un chemin inexistant et l'autre non, les
            # deux ont un ratio de 1.0 — le premier etait donc livre au hasard de
            # l'ordre de generation, et 13 livraisons sur 30 citaient un chemin
            # inexistant alors qu'un candidat PROPRE etait disponible. A preuves
            # egales, celui qui laisse le moins de choses en suspens gagne.
            proved.sort(key=_cle_de_preference, reverse=True)
            top_art, top_res = proved[0]

            # --- comparaison differentielle des candidats a EGALITE -------- #
            # Quand plusieurs candidats ont le meme nombre de preuves, le choix
            # entre eux etait ARBITRAIRE (`_better` prend le DERNIER dont le ratio est
            # au moins egal : le livrable dependait de l'ordre de generation). S'ils
            # se contredisent sur une entree non couverte par la specification, le
            # systeme livrait donc l'un des deux sans rien dire. Les comparer ne
            # coute aucun appel de modele : ils sont deja la.
            top_art, top_res = self._arbitrer(proved, spec, work, rnd, warnings)
            best = self._better(best, (top_art, top_res))

            guard.record(
                ProgressPoint(
                    round_index=rnd,
                    score=top_res.ratio,
                    digest=top_art.digest,
                    errors=len(top_res.failures),
                )
            )
            self.journal.append(
                "stage",
                {
                    "name": Stage.GENERATE.value,
                    "round": rnd,
                    "produced": True,
                    "verified": top_res.passed,
                    "depends_on": Stage.SPEC.value,
                    "candidates": len(candidates),
                    "best_digest": top_art.digest,
                    "ratio": round(top_res.ratio, 4),
                },
            )

            # Objectif atteint : on passe a l'audit.
            if top_res.passed:
                reports, outcome = self._audit_and_decide(
                    top_art, spec, work, rnd, usage
                )
                if outcome.reached and outcome.decision is Verdict.PASS:
                    break
                warnings.append(
                    Finding(
                        agent="consensus",
                        severity=Severity.MEDIUM,
                        message=f"audit non concluant: {outcome.reason}",
                    )
                )

            # --- 6. GARDE ANTI-OSCILLATION -------------------------------- #
            # Distinction capitale, et contre-intuitive :
            #
            #   * OSCILLER (alterner, cycler, regresser) = la correction nuit.
            #     On ARRETE : boucler davantage degrade le resultat.
            #
            #   * PLATEAU au sens strict (aucun gain marginal sur la fenetre,
            #     alors que toutes les regles ne sont PAS satisfaites) = il n'y a
            #     simplement rien a corriger pour l'instant. Continuer a
            #     echantillonner AIDE encore, parce que le verificateur sait
            #     SELECTIONNER le bon candidat.
            #
            # Theoreme pratique : best-of-N avec verificateur >= best-of-N aveugle,
            # a budget egal. S'arreter sur un plateau quand il reste des regles
            # non satisfaites casse cette propriete — constate au banc, corrige ici.
            if infeasible and top_res.ratio == 1.0:
                # Toutes les regles sont satisfaites : reessayer ne changerait ni le
                # candidat ni le verdict. On livre avec la reserve expliquee, au lieu
                # de bruler des appels pour arriver exactement au meme point.
                self.journal.append(
                    "stop", {"reason": "configuration infaisable, preuve deja complete",
                             "detail": infeasible}
                )
                if feedback is None:
                    feedback = self._feedback(top_res, spec, repeated=False, artifact=top_art)
                break

            stop, why = guard.should_stop()
            if stop and guard.is_plateau() and not (
                guard.is_flip_flop() or guard.is_cycling() or guard.is_regressing()
            ):
                if top_res.ratio < 1.0 and rnd + 1 < (mission.max_rounds or self.config.max_rounds):
                    self.journal.append(
                        "oscillation",
                        {"stop": False, "reason": why, "action": "continue-echantillonnage",
                         "summary": guard.summary()},
                    )
                    feedback = self._feedback(top_res, spec, repeated=False, artifact=top_art)
                    continue
            # Mesure au banc (competence 0.15) : s'arreter au premier plateau faisait
            # PERDRE 13.3 points face a un tirage aveugle de meme budget. La raison est
            # mathematique : quand un verificateur existe, chaque tirage supplementaire
            # est un tirage que le verificateur peut SELECTIONNER. Un plateau ne dit donc
            # pas « rien a gagner » mais « rien a corriger » — ce qui n'est pas la meme
            # chose. Tant qu'il reste du budget et des regles non satisfaites, on tire.
            # L'arret anticipe est reserve aux vraies pathologies : alternance, cycle,
            # regression (la correction NUIT), et a l'epuisement du budget.
            budget_ok = (
                time.monotonic() - started
                < (mission.deadline_s or self.config.time_budget_s)
            )
            if stop and guard.is_plateau() and top_res.ratio < 1.0 and budget_ok:
                self.journal.append(
                    "oscillation",
                    {"stop": False, "reason": why, "action": "continue-plateau-productif",
                     "summary": guard.summary()},
                )
                feedback = self._feedback(top_res, spec, repeated=False, artifact=top_art)
                guard = OscillationGuard()  # la fenetre repart : le plateau est consomme
                continue

            if stop:
                self.journal.append(
                    "oscillation", {"stop": True, "reason": why, "summary": guard.summary()}
                )
                warnings.append(Finding(agent="oscillation", severity=Severity.MEDIUM,
                                        message=why))
                break

            feedback = self._feedback(
                top_res, spec, repeated=guard.is_plateau(), artifact=top_art
            )

        # --- 4/5. AUDIT SI PAS ENCORE FAIT --------------------------------- #
        if best is not None and not reports:
            reports, outcome = self._audit_and_decide(best[0], spec, work, rounds - 1, usage)

        # --- 7. INTEGRITE -------------------------------------------------- #
        integrity = self.monitor.audit(self.journal)
        self.journal.append(
            "integrity",
            {"clean": integrity.clean, "steps": integrity.steps,
             "exploits": [e.kind.value for e in integrity.exploits]},
        )

        # --- 8. PORTE DE MUTATION ------------------------------------------ #
        # « Les regles passent » ne vaut que si elles POUVENT echouer. On mute
        # l'artefact de facons qui doivent le rendre faux ; un mutant survivant
        # signifie que la specification ne distingue pas le correct du faux.
        mutation = None
        if best is not None and best[1].ratio == 1.0 and self.config.mutation_gate:
            mutation = self._mutation_gate(best[0], spec, work)

        report = self._finalize(
            mission=mission,
            spec=spec,
            best=best,
            reports=reports,
            outcome=outcome,
            integrity=integrity,
            mutation=mutation,
            warnings=tuple(warnings),
            rounds=rounds,
            usage=usage,
            started=started,
            guard=guard,
            ledger=ledger,
            infeasible=infeasible,
        )

        # --- 9. CAPITALISER : une traduction validee devient une capacite ---------- #
        # Seule une livraison PROUVEE alimente la bibliotheque : une abstention ou une
        # reserve ne prouve rien, donc elle n'a rien a transmettre. La prochaine fois,
        # les temoins sont repris sans appeler le modele — cout de traduction : zero.
        gardes = self._conserver_les_temoins(spec, work, report)
        if gardes:
            self.journal.append(
                "temoin-conserve",
                {"mission_id": report.mission_id, "entrees": gardes,
                 "objectif": (work.objective or spec.mission)[:200]},
            )
        self._learn(mission, report)
        return report

    @staticmethod
    def _avertir_sur_les_temoins(temoignage: Temoignage) -> Finding:
        """Ce qui n'a PAS pu devenir un temoin est dit, jamais passe sous silence."""
        if temoignage.motif and not temoignage.utilisable:
            return Finding(
                agent="temoins",
                severity=Severity.MEDIUM,
                message=(
                    f"aucune regle n'a pu etre traduite en temoin executable ({temoignage.motif}) : "
                    "la seule preuve disponible est la coherence de l'artefact avec sa propre "
                    "documentation — ce n'est PAS une preuve contre la mission."
                ),
            )
        if not (temoignage.aveux or temoignage.refuses or temoignage.motif):
            return Finding(
                agent="temoins",
                severity=Severity.MEDIUM,
                message=(
                    f"preuve etablie sur {len(temoignage.tests)} temoin(s) EXECUTABLE(S) "
                    "TRADUIT(S) par le modele : la mission ne fournissait aucun oracle. "
                    "Les regles sont donc prouvees — mais par une traduction, pas par un "
                    "oracle fourni : la traduction passe les garde-fous, elle n'est pas "
                    "pour autant infaillible."
                ),
            )
        details = []
        for rid, raison in list(temoignage.aveux.items())[:3]:
            details.append(f"{rid} declaree non verifiable par le modele ({raison[:120]})")
        for rid, motif in list(temoignage.refuses.items())[:3]:
            details.append(f"{rid} refusee par les garde-fous ({motif[:120]})")
        return Finding(
            agent="temoins",
            severity=Severity.MEDIUM,
            message=(
                f"preuve etablie sur {len(temoignage.tests)} temoin(s) executable(s) "
                "TRADUIT(S) par le modele (aucun oracle fourni par la mission) ; "
                "le reste est declare NON PROUVE : " + " ; ".join(details)
            ),
        )

    def _signaler_temoins_non_discriminants(
        self,
        proved: list[tuple[Artifact, ProverResult]],
        temoignage: Temoignage,
        warnings: list[Finding],
        rnd: int,
        objectif_biblio: str,
    ) -> None:
        """Nomme l'ambiguite : un temoin que TOUS les candidats echouent.

        Deux causes possibles, et le systeme ne peut PAS trancher entre elles :
        le temoin est faux, ou tous les candidats sont faux. Ce que cette methode
        fait — et ce qu'elle ne fait pas — a ete decide par la mesure :

          * elle N'EFFACE PAS l'echec du verdict (la premiere version le faisait,
            et c'etait une faute : « non prouve » devenait « livre ». Le brouillon
            livrait alors un artefact FAUX avec une simple reserve, la ou l'abstention
            etait la bonne sortie) ;
          * elle NE CHANGE PAS le classement : un temoin que personne ne passe ne
            departage personne, donc l'ignorer ne change aucun ordre ;
          * elle DECLARE la regle non prouvee, et interdit la mention « livre sans
            reserve » (voir la post-condition de `_finalize`).

        Le resultat est conservateur dans le bon sens : on s'abstient quand on ne
        peut pas prouver, au lieu de livrer en esperant.
        """
        discriminants = set(temoignage.tests)
        for _art, res in proved:
            discriminants -= {w.rule_id for w in res.witnesses if w.ok}
        if not discriminants:
            return

        # Une regle que personne ne satisfait n'a rien departage : le classement est
        # identique a ce qu'il serait sans elle. On le VERIFIE au lieu de l'affirmer.
        # L'ORDRE, et seulement l'ordre : un temoin que personne ne passe fait
        # baisser tous les ratios de la meme quantite, donc il ne peut pas changer
        # le classement. Comparer les ratios eux-memes ne testerait pas cela.
        ordre_sans = [art.digest for art, _res in proved]
        partielles: list[tuple[str, float]] = []
        for art, res in proved:
            temoins = tuple(w for w in res.witnesses if w.rule_id not in discriminants)
            echecs = tuple(w for w in temoins if not w.ok)
            total = len(temoins) or 1
            partielles.append((art.digest, (total - len(echecs)) / total))
        ordre_sans_eux = [digest for digest, _r in sorted(
            partielles, key=lambda x: x[1], reverse=True)]

        for rid in sorted(discriminants):
            warnings.append(Finding(
                agent="temoins",
                severity=Severity.MEDIUM,
                message=(
                    f"regle {rid} NON PROUVEE : son temoin echoue sur TOUS les candidats. "
                    "Deux causes possibles — le temoin est faux, ou tous les candidats "
                    "sont faux — et rien ici ne permet de trancher. La regle reste "
                    "declaree NON PROUVEE, jamais supposee satisfaite."
                ),
            ))
        # Un temoin REPRIS dans la bibliotheque et qui se met a accuser tout le monde
        # n'est plus un temoin : on le revoque, et la prochaine mission repayera une
        # traduction. C'est le garde-fou qui empeche une memoire de s'auto-entretenir
        # en accumulant des jugements faux.
        if self._temoins_memorises and self.bibliotheque is not None:
            for rid in sorted(discriminants):
                try:
                    self.bibliotheque.retirer(
                        objectif=objectif_biblio, regle=rid,
                        raison="repris dans la bibliotheque, mais echoue sur tous les "
                               "candidats : il accuse tout le monde, il ne discrimine plus",
                    )
                except Exception:  # noqa: BLE001
                    continue
        self._regles_non_prouvees.update(discriminants)
        self.journal.append(
            "temoins-non-discriminants",
            {
                "round": rnd,
                "regles": sorted(discriminants),
                "classement_identique": ordre_sans == ordre_sans_eux,
            },
        )

    def _arbitrer(
        self,
        proved: list[tuple[Artifact, ProverResult]],
        spec: Spec,
        work: WorkItem,
        rnd: int,
        warnings: list[Finding],
    ) -> tuple[Artifact, ProverResult]:
        """Choisit entre candidats a EGALITE de preuves, en comparant leurs resultats.

        Trois comportements, dans cet ordre :
        1. s'il n'y a pas d'egalite (un candidat a strictement plus de preuves), il
           gagne — rien a arbitrer ;
        2. si les candidats a egalite s'accordent sur toutes les entrees derivees, le
           premier est livre (l'ordre reste deterministe) ;
        3. s'ils divergent, un **constat** est enregistre avec l'entree exacte et les
           valeurs obtenues, et un candidat partage par une majorite stricte est
           prefere a un candidat isole.

        Le desaccord n'est JAMAIS bloquant : deux implementations correctes peuvent
        differer sur un comportement non specifie (`mean([])`). L'accuser serait le
        faux positif que tout ce projet refuse. On l'AVOUE, avec la preuve.
        """
        if len(proved) < 2 or not self.config.differential:
            return proved[0]

        meilleur = proved[0][1].ratio
        ex_aequo = [pair for pair in proved if abs(pair[1].ratio - meilleur) < 1e-9]
        # A egalite de preuves, on ecarte d'abord ceux qui traînent le plus de
        # reserves : comparer des candidats dont l'un cite un chemin inexistant
        # reviendrait a arbitrer sur un desaccord qui n'en est pas un.
        if len(ex_aequo) > 1:
            moins_de_reserves = min(len(pair[1].reservations) for pair in ex_aequo)
            ex_aequo = [
                pair for pair in ex_aequo
                if len(pair[1].reservations) == moins_de_reserves
            ]
        if len(ex_aequo) < 2:
            return proved[0]

        from ..verify.divergence import comparer

        etiquette = {pair[0].digest: f"candidat-{i + 1}" for i, pair in enumerate(ex_aequo)}
        try:
            divergences, majoritaire = comparer(
                [(etiquette[pair[0].digest], pair[0].content) for pair in ex_aequo],
                work.entrypoint,
            )
        except Exception as exc:      # observation, jamais une cause d'echec
            self.journal.append("divergence", {"round": rnd, "error": str(exc)[:200]})
            return proved[0]

        if not divergences:
            return proved[0]

        self.journal.append(
            "divergence",
            {
                "round": rnd,
                "candidats": len(ex_aequo),
                "cas": len(divergences),
                "detail": [d.render()[:200] for d in divergences[:3]],
                "majoritaire": etiquette.get(
                    next((p[0].digest for p in ex_aequo if etiquette[p[0].digest] == majoritaire), ""),
                    "",
                ),
            },
        )
        warnings.append(
            Finding(
                agent="divergence",
                severity=Severity.MEDIUM,
                message=(
                    f"{len(divergences)} desaccord(s) entre {len(ex_aequo)} candidats a "
                    "egalite de preuves : la specification ne tranche pas. Le livrable "
                    "est celui du "
                    + (f"candidat majoritaire ({majoritaire})" if majoritaire else
                       "premier candidat (aucune majorite)")
                ),
                evidence=" ; ".join(d.render() for d in divergences[:3])[:400],
                counterexample=divergences[0].entree,
            )
        )

        if majoritaire:
            for pair in ex_aequo:
                if etiquette[pair[0].digest] == majoritaire:
                    return pair
        return proved[0]

    def _contredit_sa_documentation(self, src: str, work: WorkItem) -> tuple[bool, str]:
        """L'artefact tient-il ce qu'il AFFIRME de lui-meme ?

        Idee, et sa justification mesuree : quand la specification de la mission est
        incomplete — le cas normal dans la vraie vie — il reste une source de verite
        qu'on n'exploite pas : ce que l'artefact dit de lui-meme. Ses exemples `>>>`
        et ses annotations sont des affirmations EXECUTABLES, ecrites par son auteur.

        Mesure sur un corpus d'artefacts documentes (`evidence/selfspec/`), regime de
        specification faible : 2 defauts sur 4 rattrapes, et ZERO faux rejet. Les deux
        defauts non rattrapes sont ceux dont la documentation decrit fidelement le
        mauvais comportement — aucune methode locale ne peut les voir.

        Cout : une derivation STATIQUE (aucun modele, aucun reseau) et une passe de bac
        a sable par regle trouvee. Le resultat est memorise par contenu, car le
        verificateur est appele par chaque critique du panel.
        """
        cle = (src, work.entrypoint)
        memo = self._self_check_cache
        if cle in memo:
            return memo[cle]

        try:
            from ..verify.autocheck import derive
            from ..verify.properties import docstring_examples

            derived = derive(src, entrypoint=work.entrypoint or "")
        except Exception:
            memo[cle] = (True, "")
            return memo[cle]

        doc = ""
        try:
            import ast

            for node in ast.walk(ast.parse(src)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node) or ""
                    break
        except Exception:
            doc = ""

        checks = {
            k: v for k, v in derived.checks.items()
            if k == f"A-001:{work.entrypoint}" or k == "A-001" or k == "A-003"
            or k.startswith("A-003:")
        }
        if not checks:
            memo[cle] = (True, "")
            return memo[cle]

        try:
            res = self.prover.prove(
                src, derived.spec, hidden_checks=checks,
                entrypoint=derived.entrypoint, preamble=derived.preamble,
                stage=Stage.PROVE,
            )
        except Exception:
            memo[cle] = (True, "")
            return memo[cle]

        if not res.failures:
            memo[cle] = (True, "")
            return memo[cle]

        premier = res.failures[0]
        detail = (premier.stderr or premier.summary()).strip().splitlines()
        message = detail[-1] if detail else "contradiction avec sa propre documentation"
        if docstring_examples(doc):
            motif = (
                "l'artefact CONTREDIT SES PROPRES EXEMPLES de docstring : "
                f"[{premier.rule_id}] {message[:220]}. Corriger le code, ou corriger "
                "l'exemple s'il est faux — les deux ne peuvent pas etre vrais."
            )
        else:
            motif = (
                "l'artefact ne tient pas ce que sa signature annonce : "
                f"[{premier.rule_id}] {message[:220]}"
            )
        memo[cle] = (False, motif)
        return memo[cle]

    def _mutation_gate(self, artifact: Artifact, spec: Spec, work: WorkItem) -> object | None:
        """Mute l'artefact et verifie que la specification tue chaque mutant.

        Cout borne (MUTATION_BUDGET) : on cherche la faiblesse de specification,
        pas une couverture exhaustive.
        """
        from ..verify.mutation import MutationReport, mutate

        mutants = mutate(artifact.content, budget=self.config.mutation_budget)
        if not mutants:
            return None

        killed = 0
        survived: list[object] = []
        for mutant in mutants:
            try:
                res = self.prover.prove(
                    mutant.source, spec, hidden_checks=self._checks_en_vigueur(work),
                    entrypoint=work.entrypoint, stage=Stage.PROVE,
                )
            except FailClosed:
                # Aucune preuve disponible pour ce mutant : il ne peut pas
                # survivre puisqu'il n'a rien satisfait.
                killed += 1
                continue
            if res.passed:
                survived.append(mutant)
            else:
                killed += 1
        return MutationReport(
            total=len(mutants), killed=killed, survived=tuple(survived)
        )

    # -- apprentissage ------------------------------------------------------ #

    def infeasibility(self) -> str:
        """Dit, AVANT de depenser un seul appel, si la configuration peut livrer.

        Deux blocages arithmetiques, tous deux invisibles pour l'utilisateur :

        * **panel trop petit** : le consensus byzantin exige `n >= 3f+1` ; sous ce
          seuil, aucun consensus n'est atteignable, donc aucune livraison ;
        * **plafond sous le seuil** : la confiance est plafonnee par le nombre
          d'identites de modele distinctes (`0.55 + 0.15 x M`). Avec une seule CLI,
          ce plafond vaut 0.70 ; avec deux, 0.85. Sous un seuil non calibre de 0.90,
          une mission PARFAITE ne peut pas etre acceptee.

        Constate a l'ablation : 13.8 appels brueles contre 5.4 pour un resultat
        identique. Le travail n'etait pas mauvais ; la configuration etait bloquee.
        """
        critics = list(getattr(self.panel, "critics", ()) or ())
        panel = len(critics)
        min_panel = int(getattr(self.consensus, "min_panel", 0) or 0)
        if panel and panel < min_panel:
            return (
                f"panel de {panel} critique(s) alors que le consensus byzantin exige "
                f"au moins {min_panel} (n >= 3f+1) : aucun consensus n'est atteignable, "
                "donc aucune livraison complete. Brancher des agents distincts "
                "(3 suffisent) ou assumer --min-panel plus bas en connaissance de cause."
            )

        identities: set[str] = set()
        for critic in critics:
            provider = getattr(critic, "provider", None)
            if provider is not None:
                ident = getattr(provider, "model", "") or getattr(provider, "name", "")
            else:
                ident = getattr(getattr(critic, "persona", None), "name", "")
            if ident:
                identities.add(str(ident))
        if identities:
            ceiling = min(1.0, 0.55 + 0.15 * len(identities))
            try:
                tau = float(self.gate.tau())
            except Exception:  # une porte sans seuil ne bloque rien
                tau = 0.0
            if ceiling < tau:
                return (
                    f"{len(identities)} identite(s) de modele distincte(s) : une mission "
                    f"PARFAITE plafonne a {ceiling:.3f}, sous le seuil {tau:.3f} — aucune "
                    "livraison ne sera acceptee. Brancher un modele distinct de plus, "
                    "calibrer la porte, ou elargir l'alpha / --min-panel."
                )
        return ""

    def _reachable_ceiling(self, outcome: ConsensusOutcome) -> float:
        """Score maximal atteignable par une mission parfaite, dans cette configuration.

        Sert a distinguer deux refus tres differents :
          * « le travail n'est pas assez bon »  -> il faut ameliorer l'artefact ;
          * « le plafond est sous le seuil »    -> aucun travail ne suffira, il faut
            changer la configuration (plus de modeles distincts, ou une porte calibree).
        Confondre les deux fait perdre des heures a l'utilisateur.
        """
        decorrelation = min(1.0, 0.55 + 0.15 * outcome.effective_panel)
        return round(decorrelation, 4)

    def _learn(self, mission: Mission, report: MissionReport) -> None:
        """Boucle d'auto-amelioration : router + memoire, apres chaque mission.

        Un succes met a jour le bandit. Un echec fait les deux : le bandit
        apprend que ce bras n'etait pas adapte, et la memoire retient la cause
        avec le garde qui l'empechera de revenir.
        """
        delivered = report.status in (
            MissionStatus.DELIVERED,
            MissionStatus.DELIVERED_WITH_RESERVATION,
        )
        if self.router is not None and self._arm is not None:
            self.router.observe(mission.objective, self._arm, success=delivered)

        if self.memory is None or delivered:
            return
        failing = [w for w in report.witnesses if not w.ok]
        if not failing:
            return
        first = failing[0]
        try:
            self.memory.record(
                objective=mission.objective,
                symptom=f"regle {first.rule_id} non satisfaite",
                root_cause=(first.stderr or "").strip().splitlines()[-1][:200]
                if first.stderr
                else "cause inconnue : aucune sortie d'erreur capturee",
                correct_fix="atteint dans une mission ulterieure",
                # Le GARDE est obligatoire : sans controle, la memoire n'est qu'un journal.
                guard=f"regle {first.rule_id} du banc d'essai",
                mission_id=mission.id,
            )
        except Exception:  # une memoire defaillante ne doit jamais faire echouer la mission
            pass

    # -- etapes internes ---------------------------------------------------- #

    def _temoins_de_la_spec(self, spec: Spec, work: WorkItem, usage: dict[str, int]) -> Temoignage:
        """Traduit les regles en temoins executables — UNE fois par mission.

        Rien n'est fait quand la mission FOURNIT deja ses oracles (le banc les
        fournit) : traduire par-dessus un oracle reel serait un gaspillage, et
        surtout une substitution — l'oracle cache est la reference, pas le modele.
        """
        if not self.config.temoins or work.checks:
            return Temoignage()
        if self._temoignage is not None:
            return self._temoignage

        objectif = work.objective or spec.mission

        # -- 1. la bibliotheque d'abord : une traduction deja VALIDEE ne se repaie pas.
        memorises = self._rappeler_les_temoins(spec, objectif)
        provider = self.spec_compiler.provider or (self.generators[0] if self.generators else None)
        manquantes = [r for r in spec.rules
                      if r.kind is not RuleKind.ADVISORY and r.id not in memorises]
        if memorises and not manquantes:
            # Reprise COMPLETE : aucun appel au modele, la memoire suffit.
            self._temoins_memorises = True
            self._temoignage = Temoignage(tests=memorises, modele="bibliotheque")
            self.journal.append(
                "temoins",
                {
                    "regles": len(spec.rules),
                    "traduites": sorted(memorises),
                    "tests": {k: v[:400] for k, v in memorises.items()},
                    "source": "bibliotheque",
                    "appels": 0,
                },
            )
            return self._temoignage

        if memorises:
            # Reprise PARTIELLE : on ne traduit que ce qui manque. La version
            # precedente repartait avec les seuls temoins memorises des qu'il y en
            # avait UN — une regle modifiee (ou nouvelle) n'etait alors jamais
            # traduite, et la mission ne la prouvait plus du tout. Mesure : zero
            # appel de traduction sur une specification dont un enonce avait change.
            partielle = Spec(mission=spec.mission, rules=tuple(manquantes),
                             under_specified=spec.under_specified,
                             acceptance=spec.acceptance)
            frais = traduire(partielle, provider, entrypoint=work.entrypoint,
                             objectif=objectif)
            if frais.tests:
                self._temoins_memorises = False
            temoignage = Temoignage(
                tests={**memorises, **frais.tests},
                aveux=dict(frais.aveux), refuses=dict(frais.refuses),
                motif=frais.motif, appels=frais.appels, modele=frais.modele,
            )
        else:
            temoignage = traduire(
                spec, provider, entrypoint=work.entrypoint, objectif=objectif,
            )
        self._temoignage = temoignage
        usage["calls"] = usage.get("calls", 0) + temoignage.appels
        self.journal.append(
            "temoins",
            {
                "regles": len(spec.rules),
                "traduites": sorted(temoignage.tests),
                # Le TEXTE exact de ce que le modele a eu le droit d'affirmer : sans
                # lui, « jio trace » montrerait un vote sans montrer la question.
                # Borne a 400 caracteres par temoin : c'est un journal, pas un depot.
                "tests": {k: v[:400] for k, v in temoignage.tests.items()},
                "aveux": {k: v[:200] for k, v in temoignage.aveux.items()},
                "refuses": {k: v[:200] for k, v in temoignage.refuses.items()},
                "motif": temoignage.motif,
                "appels": temoignage.appels,
                "modele": temoignage.modele,
            },
        )
        return temoignage

    def _rappeler_les_temoins(self, spec: Spec, objectif: str) -> dict[str, str]:
        """Reprend les temoins deja valides pour cette mission, sans appeler le modele.

        La cle est (empreinte de l'objectif, empreinte de l'enonce de la regle) : une
        specification qui change d'un mot ne retrouve rien, ce qui est le but — une
        memoire qui s'applique a une specification differente serait un faux temoin.
        """
        if self.bibliotheque is None:
            return {}
        empreintes = {
            r.id: empreinte_regle(r.id, r.statement)
            for r in spec.rules
            if r.kind is not RuleKind.ADVISORY
        }
        try:
            rappeles = self.bibliotheque.rappeler(objectif, empreintes)
        except Exception:  # noqa: BLE001 — une memoire defaillante ne bloque pas une mission
            return {}
        return {k: v for k, v in rappeles.items() if k in empreintes}

    def _conserver_les_temoins(self, spec: Spec, work: WorkItem, report: MissionReport) -> int:
        """Alimente la bibliotheque — uniquement sur une livraison PROUVEE.

        La condition est le coeur du module : une abstention ou une reserve ne
        prouve rien, donc elle n'a rien a transmettre. Un temoin FAUX ne peut pas
        entrer par la porte d'une abstention.
        """
        if self.bibliotheque is None or self._temoignage is None:
            return 0
        if self._temoins_memorises or self._temoignage.modele == "bibliotheque":
            return 0
        if report.status is not MissionStatus.DELIVERED or not self._temoignage.tests:
            return 0
        objectif = work.objective or spec.mission
        empreintes = {
            r.id: empreinte_regle(r.id, r.statement)
            for r in spec.rules
            if r.kind is not RuleKind.ADVISORY
        }
        try:
            return int(self.bibliotheque.retenir(
                objectif=objectif,
                empreintes=empreintes,
                correspondance=self._temoignage.tests,
                mission_id=report.mission_id,
            ))
        except Exception:  # noqa: BLE001
            return 0

    def _checks_en_vigueur(self, work: WorkItem) -> Mapping[str, str]:
        """Les temoins valables pour cette mission, en un seul endroit.

        Priorite ABSOLUE aux oracles fournis par la mission : le banc est la
        reference, le modele ne se substitue pas a elle. Les temoins traduits ne
        prennent le relais que lorsque personne d'autre n'a fourni de test — et
        c'est le cas de toute mission reelle.

        Un seul point de verite : la boucle de preuve, le panel et la porte de
        mutation doivent juger sur les MEMES temoins. Sinon le panel voterait sur
        une preuve que la livraison n'utilise pas.
        """
        if work.checks:
            return work.checks
        if self._temoignage is not None:
            return dict(self._temoignage.tests)
        return {}

    def _compile(self, mission: Mission, work: WorkItem) -> Spec:
        compiler = self.spec_compiler
        if compiler.provider is None and self.generators:
            compiler = SpecCompiler(provider=self.generators[0])
        return compiler.compile(mission.objective)

    def _generate(
        self,
        work: WorkItem,
        spec: Spec,
        rnd: int,
        feedback: FailureFeedback | None,
        usage: dict[str, int],
    ) -> list[Artifact]:
        """Produit N candidats avec diversite forcee."""
        n = self._arm.candidates if self._arm is not None else self.config.candidates_per_round
        temps = self.config.temperatures
        prompt = self._prompt(work, spec, feedback)
        out: list[Artifact] = []

        for i in range(n):
            provider = self.generators[i % len(self.generators)]
            temperature = temps[(rnd + i) % len(temps)]
            try:
                comp: Completion = provider.complete(
                    [Message("system", self._system(work), trust=_SYSTEM_TRUST),
                     Message("user", prompt)],
                    temperature=temperature,
                    max_tokens=self.config.max_tokens,
                    seed=1000 * self.config.seed + 100 * rnd + i,
                )
            except Exception as exc:  # noqa: BLE001 — un fournisseur en panne ne bloque pas le panel
                self.journal.append("provider_error", {"provider": getattr(provider, "name", "?"),
                                                       "error": str(exc)[:300]})
                continue

            usage["prompt_tokens"] += comp.prompt_tokens
            usage["completion_tokens"] += comp.completion_tokens
            usage["calls"] += 1

            # En famille "prose", le candidat EST le document : l'extraire comme un
            # bloc de code jetterait le texte (et un document n'a pas d'entree).
            prose = self.config.famille == "prose"
            code = comp.text.strip() if prose else _extract_code(comp.text, work.entrypoint)
            if not code.strip():
                continue

            out.append(
                Artifact(
                    id=f"r{rnd}-c{i}",
                    content=code,
                    kind="prose" if prose else "code",
                    agent=f"gen{i}",
                    model=comp.model,
                    provider=comp.provider,
                    attempt=rnd + 1,
                    metadata={"temperature": temperature, "correct_hint": comp.metadata.get("sim_correct")},
                )
            )
            self.journal.append(
                "candidate",
                {
                    "id": f"r{rnd}-c{i}",
                    "agent": f"gen{i}",
                    "model": comp.model,
                    "digest": out[-1].digest,
                    "temperature": temperature,
                    "sim_correct": comp.metadata.get("sim_correct"),
                    "code_tail": code[-800:],
                },
            )
        return out

    def _audit_and_decide(
        self,
        artifact: Artifact,
        spec: Spec,
        work: WorkItem,
        rnd: int,
        usage: dict[str, int],
    ) -> tuple[tuple[CriticReport, ...], ConsensusOutcome]:
        """Audit en revue aveugle puis consensus. Les votes sont secrets."""

        def verifier(src: str) -> tuple[bool, str]:
            res = self.prover.prove(
                src, spec, hidden_checks=self._checks_en_vigueur(work),
                entrypoint=work.entrypoint, stage=Stage.PROVE,
            )
            if res.failures:
                return False, res.failures[0].stderr[:300] or res.failures[0].summary()
            if self.config.self_check:
                conforme, motif = self._contredit_sa_documentation(src, work)
                if not conforme:
                    # Le message nomme la promesse contredite : c'est ce qui rend la
                    # reprise possible, et c'est aussi la raison d'etre de l'axe. On le
                    # CONSERVE, car la boucle de reprise ne regarde que les echecs de la
                    # specification de mission — qui, ici, sont vides.
                    self._motif_auto[src] = motif
                    return False, motif
            return True, ""

        reports = self.panel.run(artifact.content, spec, verifier=verifier, seed=rnd)

        for rep in reports:
            self.journal.append(
                "vote",
                {
                    "agent": rep.persona,
                    "decision": rep.vote.decision.value,
                    "confidence": rep.vote.confidence,
                    "reason": rep.vote.rationale,
                },
            )

        outcome = self.consensus.decide([r.vote for r in reports])

        decorr = _decorrelation(reports)
        threshold = self.panel and self.config.min_decorrelation
        if threshold and decorr < self.config.min_decorrelation:
            outcome = ConsensusOutcome(
                decision=Verdict.ABSTAIN,
                reached=False,
                agreement=outcome.agreement,
                quorum_required=outcome.quorum_required,
                panel_size=outcome.panel_size,
                estimated_faulty=outcome.estimated_faulty,
                tally=outcome.tally,
                dissent=outcome.dissent + ("decorrelation-insuffisante",),
                confidence=outcome.confidence,
                reason=(
                    f"panel non decorrele ({decorr:.2f} < "
                    f"{self.config.min_decorrelation:.2f}) : un echo n'est pas un consensus"
                ),
            )

        self.journal.append(
            "consensus",
            {
                "reached": outcome.reached,
                "decision": outcome.decision.value,
                "agreement": outcome.agreement,
                "quorum": outcome.quorum_required,
                "panel": outcome.panel_size,
                "decorrelation": decorr,
                "dissent": list(outcome.dissent),
                "reason": outcome.reason,
            },
        )
        return reports, outcome

    def _finalize(
        self,
        *,
        mission: Mission,
        spec: Spec,
        best: tuple[Artifact, ProverResult] | None,
        reports: tuple[CriticReport, ...],
        outcome: ConsensusOutcome | None,
        integrity,
        warnings: tuple[Finding, ...],
        rounds: int,
        usage: dict[str, int],
        started: float,
        guard: OscillationGuard,
        ledger: BlameLedger,
        force_reason: str = "",
        infeasible: str = "",
        mutation: object | None = None,
    ) -> MissionReport:
        if force_reason:
            # Abstention decidee en amont (fail-closed) : on ne construit pas de
            # faux temoignage, on rend un rapport honnete et vide de preuve.
            self.journal.append("verdict", {"status": "abstained", "reason": force_reason})
            return MissionReport(
                mission_id=mission.id,
                objective=mission.objective,
                status=MissionStatus.ABSTAINED,
                subject="",
                spec=spec,
                rounds=rounds,
                witnesses=(),
                findings=tuple(warnings),
                votes=(),
                blames=(),
                integrity=self.monitor.audit(self.journal),
                abstention_reason=force_reason,
                journal_digest=self.journal.head,
                duration_s=time.monotonic() - started,
                usage=dict(usage),
            )

        findings: list[Finding] = list(warnings)
        for rep in reports:
            findings.extend(rep.findings)

        witnesses: tuple[Witness, ...] = best[1].witnesses if best else ()
        ratio = best[1].ratio if best else 0.0
        confidence = round(ratio * (outcome.confidence if outcome else 0.35), 4)

        # --- garde de conformite ------------------------------------------ #
        accepted, gate_reason = self.gate.decide(confidence)
        if not accepted and outcome is not None:
            # Un refus qui n'explique pas son calcul est inutilisable : l'utilisateur
            # ne peut ni le verifier ni agir dessus. Verifie sur un cas reel : avec
            # deux modeles distincts, le score PLAFONNE a 0.85 (decorrelation
            # 0.55 + 0.15*2), donc un seuil non calibre de 0.90 est hors d'atteinte
            # meme pour une mission parfaite. Le motif doit dire lequel des facteurs
            # bloque, et quoi faire.
            floor = self._reachable_ceiling(outcome)
            head = gate_reason
            if infeasible:
                head = f"CONFIGURATION BLOQUEE : {infeasible} Detail : " + head
            if outcome.effective_panel >= 2 and floor < self.gate.tau():
                # L'action d'abord : c'est la seule partie qui sert a quelque chose.
                # Le calcul vient ensuite, pour qui veut le verifier.
                head = (
                    f"PLAFOND INATTEIGNABLE : avec {outcome.effective_panel} modele(s) "
                    f"distinct(s), une mission PARFAITE plafonne a {floor:.3f}, sous le "
                    f"seuil {self.gate.tau():.3f} — aucune livraison ne sera acceptee. "
                    "Solutions : brancher un 3e modele distinct, calibrer la porte "
                    "(`jio learn` fournit des points de calibration), ou elargir "
                    f"l'alpha (actuellement {self.gate.alpha}). Detail : " + gate_reason
                )
            gate_reason = (
                f"{head} | decompte : preuves {ratio:.3f} x accord "
                f"{outcome.agreement:.3f} x decorrelation ({outcome.effective_panel} "
                f"couple(s) modele-verdict distinct(s) sur {outcome.panel_size} voix) x "
                f"confiance {outcome.confidence:.3f} = {confidence:.3f}"
            )
        self.journal.append(
            "gate", {"accepted": accepted, "confidence": confidence, "reason": gate_reason,
                     "tau": self.gate.tau(), "calibrated": self.gate.calibrated}
        )

        all_passed = bool(best) and best[1].passed
        consensus_ok = bool(outcome and outcome.reached
                            and outcome.decision is Verdict.PASS)
        integrity_ok = integrity.clean

        status = MissionStatus.ABSTAINED
        abstention = ""

        # --- porte de mutation : les regles peuvent-elles ECHOUER ? ---------- #
        # Un artefact qui satisfait toutes les regles pour la pire des raisons
        # (les regles ne testent rien) produirait une confiance sans preuve.
        # Un mutant survivant n'accuse pas l'artefact : il accuse la
        # specification. C'est donc une RESERVE, jamais un rejet.
        mutation_weak = bool(mutation is not None and getattr(mutation, "weak", False))
        if mutation is not None and getattr(mutation, "total", 0):
            self.journal.append(
                "mutation",
                {
                    "total": mutation.total,
                    "killed": mutation.killed,
                    "score": round(mutation.score, 4),
                    "survived": [m.label for m in mutation.survived],
                },
            )
            if mutation_weak:
                findings.append(
                    Finding(
                        agent="mutation",
                        severity=Severity.MEDIUM,
                        message=(
                            f"specification faible : {len(mutation.survived)} mutant(s) "
                            "survivant(s) — les regles ne distinguent pas l'artefact "
                            "correct d'un artefact faux"
                        ),
                    )
                )

        if not integrity_ok:
            status = MissionStatus.ABSTAINED
            abstention = "exploits detectes dans le journal — la preuve est compromise"
        elif all_passed and consensus_ok and accepted and mutation_weak:
            status = MissionStatus.DELIVERED_WITH_RESERVATION
            abstention = (
                f"preuve complete, mais specification faible ({mutation.summary()}) : "
                "un mutant survivant signifie que les regles ne peuvent pas echouer"
            )
        elif all_passed and consensus_ok and accepted:
            status = MissionStatus.DELIVERED
        elif all_passed and consensus_ok and not accepted:
            status = MissionStatus.DELIVERED_WITH_RESERVATION
            abstention = f"preuve complete mais confiance sous le seuil : {gate_reason}"
        elif all_passed and integrity_ok:
            status = MissionStatus.DELIVERED_WITH_RESERVATION
            abstention = f"preuve complete mais consensus non atteint : {outcome.reason if outcome else 'aucun panel'}"
        elif ratio > 0.0:
            status = MissionStatus.ABSTAINED
            abstention = (
                f"preuve incomplete : {int(ratio * 100)}% des regles satisfaites. "
                "Aucune erreur ne sera livree en silence — abstention explicite."
            )
        else:
            status = MissionStatus.FAILED
            abstention = "aucune verification n'a pu etre menee a bien"

        # POST-CONDITION, quelle que soit la branche empruntee plus haut : une regle
        # dont le temoin echoue sur TOUS les candidats n'est PAS prouvee. La livrer
        # « sans reserve » laisserait croire que la specification est couverte alors
        # qu'elle ne l'est pas. On ne peut pas non plus la transformer en rejet : un
        # temoin que personne ne satisfait peut etre faux. Donc : reserve, et le nom
        # de la regle dans le rapport.
        if self._regles_non_prouvees and status in (
            MissionStatus.DELIVERED, MissionStatus.DELIVERED_WITH_RESERVATION
        ):
            mention = (
                "regle(s) NON PROUVEE(s) : " + ", ".join(sorted(self._regles_non_prouvees))
                + " — leur temoin traduit echoue sur TOUS les candidats : il ne les "
                "departage pas, donc il ne peut ni accuser ni innocenter."
            )
            status = MissionStatus.DELIVERED_WITH_RESERVATION
            abstention = f"{abstention} · {mention}" if abstention else mention

        # --- blame : localisation du PREMIER pas fautif -------------------- #
        blames: tuple[Blame, ...] = ()
        if best and best[1].failures:
            failing_ids = {w.rule_id for w in best[1].failures}
            order = [r.id for r in spec.rules] or ["R-000"]

            def faulty(prefix_end: int) -> bool:
                return any(rid in failing_ids for rid in order[: prefix_end + 1])

            found = FirstErrorLocator(faulty=faulty, length=len(order)).locate()
            rule_blames = tuple(
                _blame_from_rule(rid, spec, ledger)
                for rid in order[: (found + 1 if found is not None else len(order))]
                if rid in failing_ids
            )
            for b in rule_blames:
                self.journal.append(
                    "blame",
                    {
                        "agent": b.agent,
                        "step": b.step,
                        "message": b.message,
                        "repair_attempt": b.is_repair_attempt,
                    },
                )
            blames = rule_blames

        self.journal.append(
            "verdict",
            {"status": status.value, "ratio": round(ratio, 4),
             "passed": sum(1 for w in witnesses if w.ok), "total": len(witnesses),
             "abstention": abstention, "guard": guard.summary()},
        )

        return MissionReport(
            mission_id=mission.id,
            objective=mission.objective,
            status=status,
            subject=best[0].content if best else "",
            spec=spec,
            rounds=rounds,
            witnesses=witnesses,
            findings=tuple(findings),
            votes=tuple(r.vote for r in reports),
            blames=tuple(blames),
            integrity=integrity,
            abstention_reason=abstention,
            journal_digest=self.journal.head,
            duration_s=time.monotonic() - started,
            usage={
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "calls": usage["calls"],
                "events": len(self.journal),
            },
        )

    # -- utilitaires -------------------------------------------------------- #

    def _better(
        self,
        current: tuple[Artifact, ProverResult] | None,
        candidate: tuple[Artifact, ProverResult],
    ) -> tuple[Artifact, ProverResult]:
        """On ne livre jamais pire que le meilleur etat rencontre.

        L'ordre est lexicographique : d'abord les preuves, ensuite les RESERVES. Une
        reserve est ce qu'on n'a pas pu confirmer ; a preuves egales, un artefact qui
        en laisse moins est strictement preferable. La version precedente comparait le
        seul ratio, donc un artefact propre et un artefact citant un chemin
        inexistant etaient equivalents — et le second pouvait etre livre.
        """
        if current is None:
            return candidate
        return candidate if _cle_de_preference(candidate) >= _cle_de_preference(current) \
            else current

    def _check_budget(self, started: float, mission: Mission) -> None:
        limit = mission.deadline_s or self.config.time_budget_s
        if time.monotonic() - started > limit:
            raise BudgetExhausted(f"budget de temps epuise ({limit}s)")

    @staticmethod
    def _reason(artifact: Artifact, res: ProverResult) -> str:
        if res.failures:
            return f"{artifact.agent}: {res.failures[0].rule_id} non satisfaite"
        return f"{artifact.agent}: {len(res.witnesses)} regles prouvees"

    def _feedback(
        self,
        res: ProverResult,
        spec: Spec,
        *,
        repeated: bool,
        artifact: Artifact | None = None,
    ) -> FailureFeedback:
        """Retour d'echec STRUCTURE — Levier 5 du harness (+5 a 10 pts).

        Le cas `res.failures` vide n'est pas forcement « aucun echec » : l'artefact
        peut satisfaire la specification de MISSION tout en contredisant sa propre
        documentation (exemples `>>>`, annotations). Sans ce transfert, le modele
        recevait « aucun echec » et devait deviner quoi corriger — mesure faite : le
        rejet etait bien prononce, mais aucune reparation guidee n'avait lieu.
        """
        if not res.failures:
            if artifact is not None and artifact.content in self._motif_auto:
                motif = self._motif_auto[artifact.content]
                return FailureFeedback(
                    stage=Stage.PROVE,
                    rule_id="AUTO",
                    assertion=motif[:300],
                    message=motif[:300],
                    repeated=repeated,
                )
            return FailureFeedback(stage=Stage.PROVE, message="aucun echec")
        w = res.failures[0]
        assertion = _extract_assertion(w.stderr) or w.stderr.strip().splitlines()[-1:][0] if w.stderr.strip() else ""
        return FailureFeedback(
            stage=Stage.PROVE,
            rule_id=w.rule_id,
            command=w.command,
            exit_code=w.exit_code,
            assertion=assertion[:300],
            message=w.summary(300),
            repeated=repeated,
        )

    def _system(self, work: WorkItem) -> str:
        if self.config.famille == "prose":
            # Le contrat de prose dit AUSSI ce qui n'est pas demande : un modele
            # pousse a « tout verifier » invente des chiffres plutot que d'ecrire
            # une phrase sans nombre. Un fait verifiable doit rester un choix.
            return (
                "You are a precise technical writer. Return ONLY the finished "
                "document, in Markdown, and nothing else — no preamble, no "
                "meta-commentary about your process.\n"
                "Every factual claim you write must be TRUE and, when it contains "
                "an arithmetic result, exactly computable. Never invent a number: "
                "if you are unsure of a figure, state the fact without it.\n"
                "Fenced code blocks must be valid: any block you label as a "
                "language must at least compile in that language.\n"
                "Cite file paths only if they exist in the project you were given."
            )
        lang = {"python": "Python", "javascript": "JavaScript"}.get(work.language, work.language)
        return (
            f"You are a precise {lang} engineer. Return ONLY the complete implementation "
            f"inside a single fenced code block. No prose, no explanation, no tests.\n"
            f"The code MUST define the function `{work.entrypoint}` exactly.\n"
            "Handle every boundary case explicitly: empty input, zero, negatives, invalid types.\n"
            "Never return a silent wrong value where an error is required — raise instead."
        )

    def _prompt(self, work: WorkItem, spec: Spec, feedback: FailureFeedback | None) -> str:
        rules = "\n".join(f"- [{r.id}] {r.statement}" for r in spec.rules)
        parts = [
            f"OBJECTIVE:\n{work.objective}",
            f"\nENUMERATED REQUIREMENTS (each one is checked independently):\n{rules}",
        ]
        if self.memory is not None:
            # Memoire des echecs : les erreurs deja payees entrent dans le prompt
            # comme PRIORS (le bloc le dit), jamais comme preuves.
            recalled = self.memory.prompt_block(work.objective)
            if recalled:
                parts.append("\n" + recalled)
        if spec.under_specified:
            parts.append("\nNOT SPECIFIED (be conservative and explicit):\n"
                         + "\n".join(f"- {u}" for u in spec.under_specified))
        if feedback is not None:
            parts.append(
                "\nPREVIOUS ATTEMPT FAILED. Structured feedback:\n"
                f"{feedback.render()}\n"
                "Fix the root cause. Do not guess — if the requirement is unclear, "
                "handle the case explicitly."
            )
        if self.config.famille == "prose":
            parts.append(
                "\nReturn the full document in Markdown. Include at least one "
                "verifiable statement (a computed figure or a code block with a "
                "declared language): a document that can be checked is worth more "
                "than one that cannot."
            )
        else:
            parts.append(f"\nReturn the full implementation of `{work.entrypoint}`.")
        return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Aides
# --------------------------------------------------------------------------- #

_SYSTEM_TRUST = TrustLevel.SYSTEM


def _extract_code(text: str, entrypoint: str) -> str:
    """Extrait le bloc de code d'une reponse de modele."""
    import re

    if not text:
        return ""
    blocks = re.findall(r"```(?:python|py|javascript|js)?\s*\n(.*?)```", text, re.S)
    if blocks:
        # Preferer le bloc qui definit l'entree attendue.
        for b in blocks:
            if entrypoint and f"def {entrypoint}" in b:
                return b.strip() + "\n"
        return max(blocks, key=len).strip() + "\n"
    stripped = text.strip()
    if entrypoint and f"def {entrypoint}" in stripped:
        return stripped + "\n"
    return ""


def _extract_assertion(stderr: str) -> str:
    for line in reversed((stderr or "").splitlines()):
        s = line.strip()
        if s.startswith("AssertionError") or "assert" in s.lower():
            return s[:300]
    return ""


def _cle_de_preference(pair: tuple[Artifact, ProverResult]) -> tuple[float, int, int]:
    """Ordre de preference d'un candidat : preuves, puis MOINS de reserves.

    Les reserves sont des echecs NON BLOQUANTS (regles advisory : reproductibilite,
    chemin introuvable). Elles ne condamnent pas l'artefact — mais entre deux artefacts
    egalement prouves, celui qui en porte moins est celui qui laisse le moins de choses
    en suspens. Le troisieme terme departage par le nombre d'echecs bruts, pour que
    l'ordre soit total et donc deterministe.
    """
    resultat = pair[1]
    return (resultat.ratio, -len(resultat.reservations), -len(resultat.failures))


def _decorrelation(reports: Sequence[CriticReport]) -> float:
    """Diversite reelle des verdicts du panel.

    0.0 = echo parfait (inutile) ; 1.0 = totalement independants.
    """
    if len(reports) < 2:
        return 0.0
    decisions = [r.vote.decision.value for r in reports]
    majority = max(set(decisions), key=decisions.count)
    return round(1.0 - decisions.count(majority) / len(decisions), 4)


def _blame_from_rule(rule_id: str, spec: Spec, ledger: BlameLedger) -> Blame:
    order = [r.id for r in spec.rules]
    idx = order.index(rule_id) if rule_id in order else 0
    agent = ledger.steps[idx] if idx < len(ledger.steps) else "generateur"
    return Blame(
        agent=agent,
        step=idx,
        message=f"regle {rule_id} non satisfaite : {spec.rule(rule_id).statement}",
    )


__all__ = ["Engine", "EngineConfig", "WorkItem"]
