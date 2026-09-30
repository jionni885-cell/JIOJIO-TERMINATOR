"""Memoire des echecs — ne jamais repayer deux fois la meme erreur.

Principe
--------
Un echec qui n'est pas enregistre sera repaye. Un echec enregistre mais sans
garde sera repaye aussi : le souvenir sans garde est un journal intime, pas une
memoire. Chaque enregistrement porte donc **obligatoirement** un garde — le test,
le controle ou la regle qui echoue desormais si l'erreur revient.

Pourquoi reutiliser le journal hash-chaine
------------------------------------------
Une memoire de ses propres erreurs est la chose la plus facile a reecrire
discretement. En la stockant dans le meme journal append-only verifie par chaine
de hachage que le reste du systeme, une reecriture devient detectable. La memoire
devient une piece a conviction, pas une narration.

Rappel avant action
-------------------
`recall()` classe les souvenirs par recouvrement de mots-cles (Jaccard pondere),
pas par plongement vectoriel : explicable, hors-ligne, et suffisant a cette
echelle. Un souvenir est un PRIOR, jamais une preuve : si le code a change, on
re-mesure.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.journal import Journal

__all__ = ["FailureRecord", "FailureMemory", "fingerprint"]

_WORD = re.compile(r"[a-z0-9_]{3,}")

#: Les marqueurs que JIO LUI-MEME pose dans les prompts. Un contenu externe qui les
#: contient cherche a fabriquer un bloc de memoire ou un retour d'echec : c'est
#: exactement le vecteur d'injection que l'architecture traite comme HOSTILE.
_MARQUEURS_RESERVES = (
    "PAST FAILURES ON SIMILAR TASKS",
    "PREVIOUS ATTEMPT FAILED",
    "ENUMERATED REQUIREMENTS",
)
#: Formules qui transforment un contenu en instruction. Un message d'erreur utile ne
#: commence pas par « ignore les instructions precedentes ».
_DIRECTIVES = re.compile(
    r"^\s*(system|assistant|instruction|ignore|oublie|disregard|forget)\b",
    re.IGNORECASE,
)


def _assainir(texte: str, limite: int = 200) -> str:
    """Rend un contenu EXTERNE inoffensif avant qu'il entre dans la memoire.

    La memoire n'est pas un fichier de notes : son contenu repart dans les PROMPTS
    (`prompt_block`). Un artefact qui echoue peut donc ecrire dans son message d'erreur une
    fausse memoire — un faux « RIGHT FIX » est une instruction deguisee. On neutralise :

      * les marqueurs reserves a JIO (sinon un contenu peut forger un bloc de memoire) ;
      * les tournures d'instruction en debut de texte ;
      * les sauts de ligne (une memoire tient sur une ligne : elle reste lisible dans un
        rapport et ne peut pas simuler une structure) ;
      * la longueur (un souvenir doit tenir dans un prompt).
    """
    une_ligne = " ".join((texte or "").split())
    for marque in _MARQUEURS_RESERVES:
        une_ligne = une_ligne.replace(marque, "[marqueur retire]")
    if _DIRECTIVES.match(une_ligne):
        une_ligne = "[instruction retiree] " + _DIRECTIVES.sub("", une_ligne)
    return une_ligne[:limite]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def fingerprint(objective: str, symptom: str = "") -> str:
    """Empreinte stable d'un echec : objectif normalise + nature du symptome."""
    basis = " ".join(sorted(_tokens(objective))) + "|" + " ".join(sorted(_tokens(symptom))[:12])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class FailureRecord:
    """Un echec paye, sa cause, et le garde qui l'empeche de revenir."""

    fingerprint: str
    symptom: str            # ce qui a ete observe
    root_cause: str         # la cause REELLE, pas le symptome
    wrong_fix: str          # ce qui a ete tente et n'a pas marche
    correct_fix: str        # ce qui a marche
    guard: str              # le controle qui echoue si l'erreur revient
    objective: str = ""
    mission_id: str = ""
    seq: int = 0

    def as_block(self) -> str:
        """Le bloc injecte. Il NOMME la tache, et ce n'est pas cosmetique.

        DEFAUT MESURE, corrige ici : le bloc ne contenait que le symptome, la cause, le
        remede et le garde — jamais la tache d'origine. Or le simulateur (et, dans la
        vraie mecanique, tout consommateur de ce bloc) n'accorde l'effet d'avertissement
        que si le souvenir concerne CETTE tache precise (`_warns_about`). Mesure sur un
        protocole multi-cycles reel : **28 avertissements examines, 0 declenche**. Le
        levier « memoire » du harness etait donc INATTEIGNABLE, et le « gain attribuable :
        0,0 point » publie jusqu'ici etait en partie l'echo de ce defaut, pas une
        conclusion sur la memoire.

        La ligne dit la tache, et rien de plus : le texte reste un PRIOR, jamais une
        preuve — `re-measure before relying`.
        """
        tete = f"- ON TASK: {self.objective[:160]}\n" if self.objective else "- "
        # Un remede NON OBSERVE est declare comme tel. La version precedente affichait
        # « atteint dans une mission ulterieure », qui se lit comme un remede et n'en est
        # pas un : un modele reel ne peut rien en faire, et un relecteur non plus.
        remede = self.correct_fix or "inconnu (aucun remede observe pour l'instant)"
        return (
            tete
            + f"  SYMPTOM: {self.symptom}\n"
            f"  CAUSE: {self.root_cause}\n"
            f"  WRONG FIX (do not repeat): {self.wrong_fix or 'n/a'}\n"
            f"  RIGHT FIX: {remede}\n"
            f"  GUARD: {self.guard}"
        )


@dataclass
class FailureMemory:
    """Journal append-only des echecs, avec rappel par similarite de mots-cles."""

    path: Path | None = None
    journal: Journal | None = None
    _records: list[FailureRecord] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.journal is None:
            # `Journal(path=...)` OUVRE le fichier en ecriture : il ne relit rien.
            # Sans ce chargement explicite, la memoire ecrivait bien sur disque mais
            # repartait vide a chaque processus — une memoire qui oublie n'est pas
            # une memoire. Bug trouve par le test de rappel, pas par relecture.
            #
            # Et le chargement VERIFIE la chaine de hashes : le contenu de cette
            # memoire repart dans les PROMPTS (voir `prompt_block`). Un fichier edite
            # a la main, ou ecrit par un autre programme, est donc un vecteur
            # d'injection en plus d'etre une memoire fausse. Chaine cassee -> mise en
            # quarantaine (renommage, jamais suppression) et memoire vide, en le disant.
            self.journal = Journal.load_verified(self.path)
        if self._records is None:
            self._records = self._load()

    # -- ecriture ----------------------------------------------------------- #

    def record(
        self,
        *,
        objective: str,
        symptom: str,
        root_cause: str,
        correct_fix: str,
        guard: str,
        wrong_fix: str = "",
        mission_id: str = "",
    ) -> FailureRecord:
        """Enregistre un echec. `guard` est obligatoire : sans garde, pas de memoire."""
        if not guard.strip():
            raise ValueError(
                "un echec sans garde n'est pas une memoire : precisez le controle qui "
                "echouera si l'erreur revient"
            )
        rec = FailureRecord(
            fingerprint=fingerprint(objective, symptom),
            # TOUT contenu qui repartira dans un prompt passe par `_assainir` : ces champs
            # viennent d'un artefact en echec (sa sortie d'erreur), donc d'une source que
            # l'architecture traite comme HOSTILE.
            symptom=_assainir(symptom),
            root_cause=_assainir(root_cause),
            wrong_fix=_assainir(wrong_fix),
            correct_fix=_assainir(correct_fix),
            guard=_assainir(guard, 120),
            objective=objective,
            mission_id=mission_id,
        )
        event = self.journal.append("failure", {
            "fingerprint": rec.fingerprint,
            "symptom": rec.symptom,
            "root_cause": rec.root_cause,
            "wrong_fix": rec.wrong_fix,
            "correct_fix": rec.correct_fix,
            "guard": rec.guard,
            "objective": objective,
            "mission_id": mission_id,
        })
        rec = FailureRecord(**{**rec.__dict__, "seq": event.seq})
        self._records.append(rec)
        return rec

    def resoudre(
        self, *, objective: str, correct_fix: str, mission_id: str = "", symptom: str = ""
    ) -> int:
        """Enregistre le REMEDE qui a fonctionne, sur les echecs encore ouverts.

        POURQUOI CETTE METHODE EXISTE. La version precedente ecrivait, a chaque echec,
        `correct_fix="atteint dans une mission ulterieure"` : un texte VIDE DE SENS, injecte
        ensuite dans chaque prompt comme « RIGHT FIX ». Une memoire qui dit « ce sera
        resolu plus tard » n'apprend rien a personne — ni a un modele, ni a un humain qui
        relit le journal. Un echec se resout ICI : quand une mission ulterieure reussit sur
        le meme objectif, le remede observe remplace le texte creux.

        L'ecriture est un evenement APPEND-ONLY (`resolution`), jamais une reecriture :
        la chaine de hashes reste verifiable, et une memoire qu'on peut reecrire
        discretement est une memoire qu'on peut empoisonner.
        """
        remede = _assainir(correct_fix)
        if not remede:
            return 0
        ouverts = [
            rec for rec in self._records
            if rec.objective == objective and not rec.correct_fix
            and (not symptom or rec.symptom == symptom)
        ]
        if not ouverts:
            return 0
        self.journal.append("resolution", {
            "fingerprint": ouverts[0].fingerprint,
            "correct_fix": remede,
            "objective": objective,
            "mission_id": mission_id,
            "symptom": ouverts[0].symptom,
        })
        from dataclasses import replace as _replace

        for i, rec in enumerate(self._records):
            if rec in ouverts:
                self._records[i] = _replace(rec, correct_fix=remede, mission_id=mission_id)
        return len(ouverts)

    @property
    def en_attente(self) -> int:
        """Echecs enregistres SANS remede observe : la dette de la memoire."""
        return sum(1 for rec in self._records if not rec.correct_fix)

    # -- lecture ------------------------------------------------------------ #

    def recall(self, objective: str, *, limit: int = 3, min_score: float = 0.08) -> list[
        FailureRecord
    ]:
        """Souvenirs pertinents pour un objectif, du plus proche au plus lointain."""
        want = _tokens(objective)
        if not want:
            return []
        scored: list[tuple[float, int, FailureRecord]] = []
        for rec in self._records:
            have = _tokens(f"{rec.objective} {rec.symptom} {rec.root_cause}")
            if not have:
                continue
            inter = len(want & have)
            if not inter:
                continue
            score = inter / len(want | have)
            if score >= min_score:
                scored.append((score, rec.seq, rec))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [rec for _, _, rec in scored[:limit]]

    def prompt_block(self, objective: str, *, limit: int = 3) -> str:
        """Bloc a injecter dans un prompt de generation.

        Un souvenir est un PRIOR, pas une preuve : le bloc le dit explicitement,
        sinon le modele traitera d'anciennes conclusions comme des faits actuels.
        """
        found = self.recall(objective, limit=limit)
        if not found:
            return ""
        lines = [
            "PAST FAILURES ON SIMILAR TASKS (priors, not proofs — re-measure before relying):"
        ]
        lines += [rec.as_block() for rec in found]
        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def head(self) -> str:
        return self.journal.head

    def verify(self) -> tuple[bool, int]:
        """Verifie la chaine d'integrite de la memoire (aucune reecriture discrete).

        `verify_chain()` renvoie `(False, seq)` en cas de rupture et `(True, None)`
        quand tout est sain : convertir `None` en entier levait une TypeError, ce
        qui faisait planter le rapport sur une memoire *valide*.
        """
        ok, bad = self.journal.verify_chain()
        return bool(ok), int(bad) if bad is not None else -1

    def _load(self) -> list[FailureRecord]:
        out: list[FailureRecord] = []
        for event in self.journal:
            if event.kind == "resolution":
                # Une resolution ne cree pas de souvenir : elle REMPLIT un echec ouvert.
                # Rejouee a l'identique au chargement, elle garde la memoire coherente
                # entre deux processus (le defaut « memoire qui oublie » a deja ete paye).
                cible = str(event.payload.get("fingerprint", ""))
                for i, rec in enumerate(out):
                    if rec.fingerprint == cible and not rec.correct_fix:
                        from dataclasses import replace as _replace

                        out[i] = _replace(
                            rec, correct_fix=str(event.payload.get("correct_fix", "")),
                            mission_id=str(event.payload.get("mission_id", "")),
                        )
                        break
                continue
            if event.kind != "failure":
                continue
            payload = dict(event.payload)
            out.append(
                FailureRecord(
                    fingerprint=str(payload.get("fingerprint", "")),
                    symptom=str(payload.get("symptom", "")),
                    root_cause=str(payload.get("root_cause", "")),
                    wrong_fix=str(payload.get("wrong_fix", "")),
                    correct_fix=str(payload.get("correct_fix", "")),
                    guard=str(payload.get("guard", "")),
                    objective=str(payload.get("objective", "")),
                    mission_id=str(payload.get("mission_id", "")),
                    seq=event.seq,
                )
            )
        return out

    def report(self) -> str:
        ok, bad = self.verify()
        resolus = self.size - self.en_attente
        lines = [
            f"memoire : {self.size} echec(s) enregistre(s) "
            f"({resolus} avec un remede OBSERVE, {self.en_attente} en attente)",
            f"integrite : {'chaine valide' if ok else f'CHAINE CASSEE @ {bad}'}",
            f"tete : {self.head}",
        ]
        if self.en_attente:
            lines.append(
                f"  <- {self.en_attente} souvenir(s) sans remede : ils disent ce qui a echoue, "
                "pas ce qui repare. Ils se remplissent quand une mission reussit sur le "
                "meme objectif."
            )
        if self.size:
            lines.append("")
            lines.append("5 derniers echecs retenus :")
            for rec in self._records[-5:]:
                remede = "inconnu" if not rec.correct_fix else rec.correct_fix[:60]
                lines.append(f"  [{rec.seq}] {rec.symptom[:78]}")
                lines.append(f"        garde : {rec.guard[:70]}")
                lines.append(f"        remede : {remede}")
        else:
            lines.append("")
            lines.append(
                "Aucun echec enregistre. Une memoire vide est un etat legitime au debut :"
            )
            lines.append("le systeme n'invente pas de mises en garde qu'il n'a pas payees.")
        return "\n".join(lines)
