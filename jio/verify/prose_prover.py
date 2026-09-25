"""Le verificateur de prose se presente COMME un prouveur executable.

POURQUOI CE MODULE, et pas une seconde boucle
---------------------------------------------
Tout ce qui fait la valeur du harness — la boucle de reprise, le panel en revue
aveugle, le consensus byzantin, la porte de conformite, le journal chaine, les
garde-fous — est ecrit et prouve pour du code. Une mission generaliste n'a pas besoin
d'une DEUXIEME machinerie : elle a besoin d'un VERIFICATEUR. En donnant a ce module la
meme signature que `ExecutableProver` (`prove(texte, spec, ...) -> ProverResult`), un
document traverse exactement la meme boucle qu'un programme, et la doctrine reste
unique. Un seul endroit a corriger, un seul comportement a expliquer.

CE QUI EST VERIFIE, et rien d'autre : les affirmations d'un document qui sont vraies ou
fausses SANS interpretation — un calcul annonce, un bloc presente comme Python, un
chemin cite (voir `claims.py`, qui porte les regles). Le style, la pertinence et les
opinions sont declares HORS DOMAINE, et cette declaration voyage dans la specification.

LA REGLE `P-000`, et pourquoi elle existe
-----------------------------------------
Un document sans la moindre affirmation verifiable ne doit PAS ressortir « conforme » :
il ressort « rien n'a ete prouve », ce qui n'est pas la meme phrase. Sans cette regle,
un verificateur qui ne trouve rien produirait un succes vide — exactement le silence
que ce projet refuse. `P-000` est donc une REGLE DURE : elle echoue quand le document
n'offre aucune affirmation decisive, et elle echoue aussi quand une affirmation est
refutee. Un document fautif est fausse par une regle nommee, pas par un compteur.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..core.journal import Journal
from ..core.types import Rule, RuleKind, Severity, Spec, Witness
from .claims import Genre, verifier
from .executable import ProverResult

__all__ = ["R_VERIFIABLE", "ProseProver", "spec_prose"]

#: La regle de couverture. Nommee, citee dans les refus, et jamais muette.
R_VERIFIABLE = "P-000"

#: Ce que dit la commande associee a chaque genre. Un temoin porte toujours la
#: description de CE QUI A ETE FAIT : c'est ce qui rend la preuve relisible.
_COMMANDES = {
    Genre.ARITHMETIQUE: "arithmetique : evaluer l'expression et comparer au resultat annonce",
    Genre.BLOC_CODE: "compilation : le bloc presente comme Python doit compiler",
    Genre.CHEMIN: "existence : le chemin cite est-il present sous la racine",
}

#: Ce qu'une mission de prose NE PROUVE PAS. Le declarer fait partie du resultat :
#: l'utilisateur doit voir la frontiere, pas la deviner.
HORS_DOMAINE = (
    (
        "style, pertinence, veracite d'une opinion, exactitude d'une citation dont "
        "la source est absente : hors du domaine prouvable, donc declare et jamais "
        "suppose"
    ),
)


def spec_prose(objectif: str) -> Spec:
    """La specification d'une mission de document : une seule regle, non negociable.

    Elle n'est PAS derivee d'un modele : elle est vraie par construction du
    verificateur, et la confier a un modele reviendrait a lui demander d'autoriser sa
    propre existence.
    """
    return Spec(
        mission=objectif,
        rules=(
            Rule(
                id=R_VERIFIABLE,
                statement=(
                    "Le document offre au moins une affirmation verifiable, et "
                    "aucune de ses affirmations verifiables n'est refutee."
                ),
                kind=RuleKind.PROPERTY,
                check="prose:claims",
            ),
        ),
        under_specified=HORS_DOMAINE,
    )


@dataclass
class ProseProver:
    """Un document est prouve par ses propres affirmations verifiables.

    `racine` : ou chercher les chemins cites. `None` = ne pas juger les chemins
    (aucune accusation sur un fichier qui n'existe pas encore).
    `journal` : le moteur le pose apres construction, comme pour `ExecutableProver` ;
    chaque affirmation verifiee ou refutee y laisse une entree, donc `jio trace`
    fonctionne sur une mission de prose.
    """

    racine: Path | None = None
    journal: Journal | None = field(default=None, repr=False)

    def prove(
        self,
        texte: str,
        spec: Spec,
        *,
        hidden_checks: Mapping[str, str] | None = None,
        entrypoint: str = "",
        stage: object | None = None,
        preamble: str = "",
    ) -> ProverResult:
        """Meme contrat que `ExecutableProver.prove`. Jamais d'exception silencieuse.

        Les parametres propres au code (`hidden_checks`, `entrypoint`, `preamble`)
        sont acceptes et ignores : la boucle les fournit sans savoir quelle famille
        de temoins elle interroge, et c'est precisement ce qu'on veut.
        """
        rapport = verifier(texte or "", racine=self.racine)
        etape = getattr(stage, "value", stage or "prove")

        witnesses: list[Witness] = []
        failures: list[Witness] = []
        codes: dict[str, tuple[int, str]] = {}
        advisory: set[str] = set()

        for index, verification in enumerate(rapport.verifications, 1):
            rule_id = f"P-{index:03d}"
            temoin = Witness(
                rule_id=rule_id,
                command=_COMMANDES.get(verification.affirmation.genre, "affirmation"),
                exit_code=0 if verification.ok else 1,
                ok=verification.ok,
                stdout=verification.message if verification.ok else "",
                stderr="" if verification.ok else verification.message,
            )
            if verification.ok:
                witnesses.append(temoin)
            else:
                failures.append(temoin)
                if not verification.bloquant:
                    # Un chemin introuvable, un bloc non marque : SIGNALES. Une
                    # reserve n'est pas un defaut prouve (voir `ProverResult`).
                    advisory.add(rule_id)
            codes[rule_id] = (temoin.exit_code, temoin.output_hash)
            self._journaliser(rule_id, temoin, etape)

        # -- la regle de couverture ---------------------------------------- #
        decisives = [v for v in rapport.verifications if v.bloquant]
        if not decisives:
            doctrine = Witness(
                rule_id=R_VERIFIABLE,
                command=_COMMANDES[Genre.ARITHMETIQUE],
                exit_code=1,
                ok=False,
                stderr=(
                    "aucune affirmation verifiable dans ce document (aucun calcul, "
                    "aucun bloc presente comme Python). Ce n'est PAS un quitus : "
                    "rien n'a ete prouve, et le reste est declare hors domaine."
                ),
            )
        elif rapport.bloquantes:
            detail = " | ".join(v.message for v in rapport.bloquantes)
            doctrine = Witness(
                rule_id=R_VERIFIABLE,
                command=_COMMANDES[Genre.ARITHMETIQUE],
                exit_code=1,
                ok=False,
                stderr=f"{len(rapport.bloquantes)} affirmation(s) refusee(s) : {detail}",
            )
        else:
            doctrine = Witness(
                rule_id=R_VERIFIABLE,
                command=_COMMANDES[Genre.ARITHMETIQUE],
                exit_code=0,
                ok=True,
                stdout=(
                    f"{rapport.verifiees} affirmation(s) verifiee(s), aucune refutee. "
                    f"{rapport.signalees} signalee(s) non concluante(s)."
                ),
            )

        if doctrine.ok:
            witnesses.append(doctrine)
        else:
            failures.append(doctrine)
        codes[R_VERIFIABLE] = (doctrine.exit_code, doctrine.output_hash)
        self._journaliser(R_VERIFIABLE, doctrine, etape)

        return ProverResult(
            witnesses=tuple(witnesses),
            failures=tuple(failures),
            codes=codes,
            advisory_ids=frozenset(advisory),
        )

    # -- trace -------------------------------------------------------------- #

    def _journaliser(self, rule_id: str, temoin: Witness, etape: object) -> None:
        if self.journal is None:
            return
        self.journal.append(
            "witness",
            {
                "rule": rule_id,
                "command": temoin.command,
                "exit_code": temoin.exit_code,
                "ok": temoin.ok,
                "hash": temoin.output_hash,
                "stage": etape,
                "famille": "prose",
            },
        )

    # -- ce que le moteur peut demander d'autre ----------------------------- #

    def severite(self, temoin: Witness) -> Severity:
        """Les affirmations refutees sont BLOQUANTES ; le reste est une reserve."""
        return Severity.HIGH if temoin.ok is False else Severity.LOW
