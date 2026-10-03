"""Travailler SEUL : un plan dont chaque etape doit porter sa preuve.

Le probleme
-----------
« Travaille seul » se traduit presque toujours, dans les outils d'agent, par « enchaine des
actions ». C'est exactement ce qu'il ne faut pas : un plan non verifie enchaine des actions
plausibles, et une action plausible de plus par tour, c'est une derive qui ne se voit qu'a la
fin — quand tout est deja fait, et faux.

Deux regles, et elles viennent de ce depot :

1. **Une etape sans preuve n'existe pas.** Chaque etape du plan doit porter une commande qui
   peut ECHOUER (un test, une verification, un scan). Une etape sans preuve est REFUSEE avec sa
   raison, jamais executee « en attendant ». C'est la meme regle que « une regle sans test ne
   existe pas », appliquee au plan.
2. **On s'arrete, et on le dit.** Un plan s'arrete sur trois issues seulement : toutes les
   etapes sont PROUVEES ; une etape ne peut pas etre prouvee -> `BLOQUE`, avec la question
   essentielle a poser ; le budget est epuise -> `BUDGET`, avec ce qui reste. Aucune quatrieme
   issue, et jamais « je continue pour voir ».

Ce que le module ne fait pas : il ne planifie pas a la place du modele. Le plan vient d'un
fournisseur (reel ou simule), et il est VALIDE avant d'etre execute. Le travail de ce module
est de refuser, de mesurer et de s'arreter — pas d'inventer.

Etat durable
------------
Le plan vit dans `.jio/plan.json`, et il est REPRENABLE : `jio auto --reprendre` continue ou il
s'est arrete. La revision du depot est enregistree a cote : reprendre un plan sur un depot qui a
change est un changement de monde, et ce module le signale au lieu de l'ignorer (arXiv
2608.29381 : une reprise qui restaure un etat hostile tout en gardant une verification faite sur
un autre etat).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    "MAX_ETAPES",
    "Etape",
    "EtapeRefusee",
    "ResultatEtape",
    "ResultatAuto",
    "extraire_etapes",
    "plan_simule",
    "executer",
    "formater",
    "enregistrer",
    "lire_etat",
    "reprendre",
]

#: Au-dela, le plan n'est plus un plan : c'est une liste de souhaits. Une etape coute une
#: mission complete (preuve, panel, consensus) ; 12 etapes est deja un budget serieux.
MAX_ETAPES = 12

#: Longueur maximale d'une commande de preuve. Au-dela, ce n'est plus une preuve c'est un
#: programme — et un programme qu'on n'a pas lu ne prouve rien.
MAX_PREUVE = 300


@dataclass(frozen=True)
class Etape:
    """Une etape du plan : ce qu'on fait, et CE QUI LE PROUVE."""

    id: str
    objectif: str
    preuve: str
    cible: str = ""
    note: str = ""


@dataclass(frozen=True)
class EtapeRefusee:
    """Une etape proposee, et la raison EXACTE de son refus."""

    objectif: str
    raison: str


def _champs_valides(etape: dict[str, object]) -> tuple[Etape | None, EtapeRefusee | None]:
    """Valide UNE etape proposee par le modele. Rend l'etape, ou son refus motive."""
    objectif = str(etape.get("objectif") or etape.get("objective") or "").strip()
    preuve = str(
        etape.get("preuve") or etape.get("proof") or etape.get("check") or etape.get("test") or ""
    ).strip()
    cible = str(etape.get("cible") or etape.get("target") or "").strip()
    if not objectif:
        return None, EtapeRefusee(objectif="(vide)", raison="etape sans objectif")
    if not preuve:
        return None, EtapeRefusee(
            objectif=objectif,
            raison=(
                "aucune preuve fournie : une etape qui ne peut pas ECHOUER ne prouve rien. "
                "Donnez la commande a lancer (test, verification, scan)."
            ),
        )
    if len(preuve) > MAX_PREUVE:
        return None, EtapeRefusee(
            objectif=objectif,
            raison=f"preuve trop longue ({len(preuve)} > {MAX_PREUVE} caracteres) : illisible, "
                   "donc non verifiable",
        )
    return Etape(id="", objectif=objectif, preuve=preuve, cible=cible), None


def extraire_etapes(
    texte: str, *, max_etapes: int = MAX_ETAPES
) -> tuple[tuple[Etape, ...], tuple[EtapeRefusee, ...]]:
    """Lit un plan propose (JSON) et rend `(etapes acceptees, etapes refusees)`.

    Le format attendu est une liste d'objets `{"objectif": ..., "preuve": ..., "cible": ...}`,
    eventuellement entouree de texte. Tout ce qui ne porte pas de preuve est refuse AVEC sa
    raison : un plan dont on retire la moitie en silence n'est plus le plan du modele, et
    personne ne saurait ce qui a ete change.
    """
    brut = _premier_json_liste(texte)
    if brut is None:
        return (), (
            EtapeRefusee(
                objectif="(plan illisible)",
                raison=(
                    "le plan n'est pas une liste JSON exploitable. Attendu : "
                    '[{"objectif": "...", "preuve": "<commande qui peut echouer>", "cible": "..."}]'
                ),
            ),
        )
    acceptees: list[Etape] = []
    refusees: list[EtapeRefusee] = []
    for index, item in enumerate(brut, 1):
        if not isinstance(item, dict):
            refusees.append(EtapeRefusee(objectif=str(item)[:60], raison="etape non structurée"))
            continue
        etape, refus = _champs_valides(item)
        if refus is not None:
            refusees.append(refus)
            continue
        assert etape is not None
        if len(acceptees) >= max_etapes:
            refusees.append(
                EtapeRefusee(
                    objectif=etape.objectif,
                    raison=f"au-dela de {max_etapes} etapes : le plan serait une liste de souhaits",
                )
            )
            continue
        acceptees.append(
            Etape(id=f"E{index:02d}", objectif=etape.objectif, preuve=etape.preuve, cible=etape.cible)
        )
    return tuple(acceptees), tuple(refusees)


def _premier_json_liste(texte: str) -> list[object] | None:
    """Extrait la premiere liste JSON du texte, meme entouree de prose ou de balises."""
    candidat = texte.strip()
    if candidat.startswith("```"):
        candidat = candidat.split("```")[1] if len(candidat.split("```")) > 1 else candidat
        candidat = candidat.removeprefix("json").strip()
    debut = candidat.find("[")
    fin = candidat.rfind("]")
    if debut < 0 or fin <= debut:
        return None
    try:
        charge = json.loads(candidat[debut:fin + 1])
    except ValueError:
        return None
    return charge if isinstance(charge, list) else None


#: Le plan du modele SIMULE : deterministe, declare comme simule, et chaque etape porte une
#: preuve qui existe vraiment dans ce depot. Il sert a mesurer la MACHINERIE (validation des
#: etapes, arret, reprise), pas a faire semblant de planifier.
_PLAN_SIMULE = (
    ("localiser la cible et lire ses regles", "jio scan {cible}"),
    # La preuve de l'etape de correction cite la CIBLE dans l'objectif : une preuve qui ne dit
    # pas sur quoi elle porte ne prouve rien de precis, meme quand elle sort en 0.
    ("corriger la cible et prouver la correction",
     "jio run \"{objectif} — cible {cible}\" --entrypoint {entree}"),
    ("verifier que rien d'autre n'a bouge", "jio scan ."),
    ("verifier les documents qui citent la cible", "jio claims {document}"),
    # La derniere etape porte sur l'ENSEMBLE : un plan peut reussir chacune de ses etapes et
    # laisser le depot incoherent (un artefact qui ne correspond plus a sa doctrine, un chiffre
    # annonce qui n'est plus mesure). C'est la porte qui autorise a dire « fini ».
    ("verifier que l'ensemble tient encore", "jio coherence"),
)


def plan_simule(objectif: str, *, cible: str = ".", entree: str = "") -> list[dict[str, str]]:
    """Un plan deterministe pour le mode SIMULE, qui declare ce qu'il est.

    Il n'essaie pas d'etre intelligent : c'est un plan de reference dont chaque etape porte une
    preuve executable. Le mode reel demande un plan au modele, et le valide avec le meme code.

    Adaptation au projet : l'etape « les documents qui citent la cible » ne porte que sur un
    document QUI EXISTE (README.md, ou la cible elle-meme si c'est un .md). Mesure sur un
    projet etranger : la faire tourner sur un README absent donnait un blocage de plus — un
    blocage sur, mais un blocage qu'on evite en regardant avant de planifier.
    """
    from pathlib import Path

    document = "README.md"
    if not Path(document).is_file():
        document = cible if cible.endswith(".md") and Path(cible).is_file() else ""
    etapes: list[tuple[str, str]] = []
    for texte, preuve in _PLAN_SIMULE:
        if "claims" in preuve and not document:
            continue
        etapes.append((
            texte.format(objectif=objectif, cible=cible, entree=entree or "main"),
            preuve.format(objectif=objectif, cible=cible, entree=entree or "main",
                          document=document or cible),
        ))
    return [
        {"objectif": objectif_etape, "preuve": preuve_etape, "cible": cible}
        for objectif_etape, preuve_etape in etapes
    ]


@dataclass(frozen=True)
class ResultatEtape:
    """Ce qui est arrive a UNE etape, avec sa preuve ou sa raison de ne pas avancer."""

    id: str
    objectif: str
    preuve: str
    etat: str          # prouvee | refusee | bloquee | non_tentee
    motif: str = ""
    appels: int = 0
    duree_s: float = 0.0


@dataclass
class ResultatAuto:
    """Le resultat d'un plan : trois issues, jamais quatre."""

    objectif: str
    etat: str                       # termine | bloque | budget | refuse
    motif: str = ""
    etapes: list[ResultatEtape] = field(default_factory=list)
    refusees: list[EtapeRefusee] = field(default_factory=list)
    duree_s: float = 0.0
    appels: int = 0
    #: Questions a poser a l'humain quand le plan est BLOQUE (porte de clarification).
    questions: tuple[str, ...] = ()
    revision: str = ""
    plan_path: str = ""

    @property
    def prouvees(self) -> int:
        return sum(1 for e in self.etapes if e.etat == "prouvee")

    @property
    def silencieuses(self) -> int:
        """Etapes declarees reussies sans preuve. Doit rester a ZERO, par construction."""
        return sum(1 for e in self.etapes if e.etat in {"prouvee", "termine"} and not e.preuve)

    def as_dict(self) -> dict[str, object]:
        return {
            "objectif": self.objectif,
            "etat": self.etat,
            "motif": self.motif,
            "revision": self.revision,
            "prouvees": self.prouvees,
            "total": len(self.etapes),
            "appels": self.appels,
            "duree_s": self.duree_s,
            "questions": list(self.questions),
            "etapes": [asdict(e) for e in self.etapes],
            "refusees": [asdict(r) for r in self.refusees],
        }


def _revision(racine: Path) -> str:
    """La revision du depot, ou vide. Elle sert a savoir sur QUEL monde on reprend un plan."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(racine), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def executer(
    etapes: Sequence[Etape],
    *,
    objective: str,
    lancer: Callable[[Etape], tuple[bool, str, int]],
    racine: Path,
    budget_etapes: int = MAX_ETAPES,
    refusees: Sequence[EtapeRefusee] = (),
    questions: Sequence[str] = (),
) -> ResultatAuto:
    """Execute les etapes dans l'ordre et s'arrete des la premiere qui ne peut pas etre prouvee.

    `lancer(etape)` rend `(prouvee, motif, appels)`. Ce module ne sait PAS executer une etape :
    il sait decider si elle est prouvee, s'arreter, et le dire. La separation est volontaire :
    c'est ce qui permet de le tester sans lancer une seule mission.

    Deux arrets, et ils ne se confondent pas :

      * l'etape n'a pas pu etre prouvee -> `BLOQUE` : on ne continue PAS. Continuer apres un
        echec non resolu, c'est empiler des etapes sur une base qu'on sait fausse ;
      * le budget d'etapes est epuise -> `BUDGET` : ce qui reste est liste, jamais tu.
    """
    debut = time.monotonic()
    resultat = ResultatAuto(
        objectif=objective,
        etat="termine",
        refusees=list(refusees),
        questions=tuple(questions),
        revision=_revision(racine),
    )
    for index, etape in enumerate(etapes):
        if index >= budget_etapes:
            resultat.etat = "budget"
            restantes = [e.objectif for e in etapes[index:]]
            resultat.motif = (
                f"budget de {budget_etapes} etape(s) epuise : {len(restantes)} etape(s) "
                f"NON TENTEE(S) — {restantes[0][:80]} …"
            )
            resultat.etapes += [
                ResultatEtape(id=e.id, objectif=e.objectif, preuve=e.preuve, etat="non_tentee")
                for e in etapes[index:]
            ]
            break
        depart = time.monotonic()
        try:
            prouvee, motif, appels = lancer(etape)
        except Exception as exc:  # fail-closed : une etape qui plante n'est pas prouvee
            prouvee, motif, appels = False, f"l'etape a leve : {exc}", 0
        resultat.appels += appels
        resultat.etapes.append(
            ResultatEtape(
                id=etape.id, objectif=etape.objectif, preuve=etape.preuve,
                etat="prouvee" if prouvee else "bloquee",
                motif=motif, appels=appels, duree_s=time.monotonic() - depart,
            )
        )
        if not prouvee:
            resultat.etat = "bloque"
            resultat.motif = (
                f"etape {etape.id} non prouvee : {motif} — les {len(etapes) - index - 1} "
                "etape(s) suivantes ne sont PAS tentees"
            )
            # Ce qui n'a PAS ete fait est ecrit noir sur blanc. Un rapport qui s'arrete a
            # l'echec laisse croire que le plan etait court ; il etait long, et il reste du
            # travail — c'est precisement ce que l'humain doit voir avant de reprendre.
            resultat.etapes += [
                ResultatEtape(id=e.id, objectif=e.objectif, preuve=e.preuve, etat="non_tentee")
                for e in etapes[index + 1:]
            ]
            break
    if not etapes:
        # Aucune etape executable : l'etat est `refuse`, JAMAIS `termine`. Defaut trouve par
        # `tests/test_auto.py` : un plan entierement refuse (toutes ses etapes sans preuve)
        # sortait en `termine`, donc un appelant automatise croyait le travail accompli alors
        # que rien n'avait ete execute. C'est le mensonge par omission que ce module existe
        # pour rendre impossible.
        resultat.etat = "refuse"
        resultat.motif = (
            f"aucune etape exploitable : rien n'a ete execute ({len(refusees)} refusee(s))."
            if refusees
            else "aucune etape exploitable : rien n'a ete execute."
        )
    resultat.duree_s = time.monotonic() - debut
    return resultat


def enregistrer(resultat: ResultatAuto, chemin: Path) -> None:
    """Ecrit l'etat du plan sur le disque, pour qu'il soit REPRENABLE.

    On ecrit le resultat, jamais le plan seul : ce qui compte en reprenant, c'est ce qui a ete
    PROUVE. Un plan sans ses preuves se rejoue entierement, et deux executions du meme plan ne
    sont pas la meme chose que deux etapes d'un meme plan.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps(resultat.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@dataclass(frozen=True)
class Reprise:
    """La decision de reprise, et sa raison — jamais un simple booleen.

    Trois cas, et le troisieme est celui qui compte :

      * le fichier d'etat manque ou est illisible -> rien a reprendre, et on le DIT ;
      * la revision a change -> les preuves obtenues decrivent un monde qui n'existe plus
        (arXiv 2608.29381 : une reprise qui restaure un etat hostile tout en conservant une
        verification faite ailleurs est le mecanisme d'attaque documente). On reprend donc a
        ZERO, et on ecrit pourquoi : re-verifier coute une commande par etape, croire coute une
        mission entiere batie sur du vide ;
      * la revision est la meme -> les etapes deja PROUVEES sont sautees, les autres sont
        rejouees.

    `deja_prouvees` est l'ensemble des identifiants a ne PAS relancer. Il n'est jamais devine :
    il vient de l'etat enregistre, et chaque entree doit porter sa preuve.
    """

    etapes: tuple[Etape, ...]
    deja_prouvees: frozenset[str]
    motif: str
    revision_etat: str = ""
    revision_courante: str = ""

    @property
    def utilisable(self) -> bool:
        return bool(self.etapes)

    @property
    def sautees(self) -> int:
        return len(self.deja_prouvees)


def lire_etat(chemin: Path) -> dict:
    """Lit un etat de plan, en refusant de deviner quoi que ce soit.

    On rend le dictionnaire BRUT, et l'appelant decide. Une fonction qui « repare » un fichier
    tronque ferait exactement ce que ce module interdit : inventer un plan que personne n'a
    ecrit.
    """
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError("l'etat n'est pas un objet JSON")
    return donnees


def reprendre(chemin: Path, *_, revision_courante: str = "") -> Reprise:
    """Decide de quoi reprendre un plan interrompu, et pourquoi.

    Regle unique, et elle est stricte : **une reprise ne fait jamais confiance a une preuve
    obtenue dans un autre monde.** Si la revision a bouge, on rejoue tout — et on le dit. Si le
    fichier d'etat ne dit pas sur quelle revision il a ete obtenu, c'est un etat d'avant la
    revision : meme traitement.
    """
    if not chemin.is_file():
        return Reprise((), frozenset(), f"aucun etat a reprendre ({chemin} absent)")

    try:
        donnees = lire_etat(chemin)
    except (OSError, ValueError) as exc:
        return Reprise((), frozenset(), f"etat illisible ({exc}) : reprendre serait deviner")

    brut = donnees.get("etapes") or []
    etapes: list[Etape] = []
    for index, item in enumerate(brut, start=1):
        try:
            etapes.append(Etape(
                id=str(item.get("id") or f"E{index:02d}"),
                objectif=str(item.get("objectif") or ""),
                preuve=str(item.get("preuve") or ""),
            ))
        except AttributeError:
            continue
    if not etapes:
        return Reprise((), frozenset(), "l'etat ne contient aucune etape : rien a reprendre")

    etat = str(donnees.get("etat") or "")
    revision_etat = str(donnees.get("revision") or "")

    if etat == "termine":
        return Reprise(
            tuple(etapes), frozenset(e.id for e in etapes),
            "plan deja TERMINE : rien a reprendre",
            revision_etat, revision_courante,
        )

    if not revision_etat or revision_etat != revision_courante:
        raison = (
            "l'etat n'indique pas la revision du depot"
            if not revision_etat
            else f"revision differente ({revision_etat[:8]} -> {revision_courante[:8]})"
        )
        return Reprise(
            tuple(etapes), frozenset(),
            f"{raison} : les preuves obtenues decrivent un monde qui n'existe plus, "
            "donc le plan est rejoue ENTIER (rien n'est cru sur parole)",
            revision_etat, revision_courante,
        )

    # Même revision : on saute ce qui a ete PROUVE, et rien d'autre. Une etape bloquee ou non
    # tentee est rejouee — c'est le sens d'une reprise.
    prouvees = frozenset(
        str(item.get("id")) for item in brut
        if isinstance(item, dict) and item.get("etat") == "prouvee" and item.get("preuve")
    )
    return Reprise(
        tuple(etapes), prouvees,
        f"revision identique ({revision_courante[:8]}) : {len(prouvees)} etape(s) deja prouvee(s) "
        "sont sautees, le reste est rejoue",
        revision_etat, revision_courante,
    )


def formater(resultat: ResultatAuto, *, largeur: int = 100) -> str:
    """Le rapport, en francais : ce qui est prouve, ce qui est bloque, et quoi faire."""
    icone = {"prouvee": "ok", "bloquee": "BLOQUE", "non_tentee": "--", "refusee": "REFUSE"}
    lignes = [
        "  MISSION AUTONOME  ·  un plan dont chaque etape porte sa preuve",
        f"    objectif : {resultat.objectif[:70]}",
        f"    etat : {resultat.etat.upper()}  ·  {resultat.prouvees}/{len(resultat.etapes)} "
        f"etape(s) prouvee(s)  ·  {resultat.appels} appel(s)  ·  {resultat.duree_s:.1f}s"
        + (f"  ·  revision {resultat.revision[:8]}" if resultat.revision else ""),
        "",
    ]
    for etape in resultat.etapes:
        lignes.append(f"    [{icone.get(etape.etat, etape.etat):<7}] {etape.id} {etape.objectif[:66]}")
        lignes.append(f"              preuve : {etape.preuve[:76]}")
        if etape.motif:
            lignes.append(f"              motif   : {etape.motif[:76]}")
    for refus in resultat.refusees:
        lignes.append(f"    [{icone['refusee']:<7}] {refus.objectif[:66]}")
        lignes.append(f"              raison  : {refus.raison[:76]}")
    if resultat.motif:
        lignes += ["", f"    {resultat.motif[:96]}"]
    if resultat.questions:
        lignes += ["", "    QUESTIONS A POSER (la mission est bloquee dessus) :"]
        lignes += [f"      - {q[:90]}" for q in resultat.questions]
    lignes += [
        "",
        "    Rappel : une etape sans preuve est REFUSEE, et un echec non resolu ARRETE le plan.",
        "    Continuer apres un echec, c'est empiler des etapes sur une base qu'on sait fausse.",
    ]
    return "\n".join(ligne[:largeur] for ligne in lignes)
