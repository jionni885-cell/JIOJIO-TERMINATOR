"""Les echecs REELS deviennent des cas de regression, ou ils reviennent en silence.

Le probleme
-----------
Une trace de mission contient des echecs reels : une regle qui a echoue sur un artefact,
un champ sensible qui est entre dans un export. Ces faits sont observes une fois, ranges
dans un journal, puis plus rien ne les utilise. Le meme defaut peut donc revenir a la
version suivante sans qu'aucun controle ne bronche — et rien ne permet de comparer deux
versions sur les MEMES cas, puisque les cas n'existent pas.

La reponse, et sa limite
------------------------
Trois gestes, dans cet ordre, et **le troisieme appartient a un humain** :

  1. `propositions(trace)` lit une trace VERIFIEE et en extrait ce qui a mal tourne :
     une regle qui a echoue, un champ sensible exporte. Chaque proposition porte sa
     provenance (evenement, monde, revision) — jamais une valeur sensible recopiee ;
  2. un humain **gele** une proposition en cas versionne. C'est lui qui apporte ce que la
     trace ne peut PAS contenir : le controle qui a echoue. Ce n'est pas une lacune de
     l'outil, c'est le principe meme des controles caches — un oracle secret ne se
     journalise pas. Le gel est refuse si l'echec ne se reproduit pas ICI, maintenant :
     un cas dont l'attente est fausse des sa creation ne prouverait rien ;
  3. `evaluer(jeu)` rejoue le jeu contre la version courante et publie le **taux de
     silence** : la part de defauts reels que la version courante ne detecte plus.

Ce que le silence veut dire
---------------------------
Un cas qui ne se declenche plus n'est pas « un test qui a bien vieilli » : c'est un
garde qui s'est tu. Le rapport separe donc deux choses qui se ressemblent :

  * `silencieuse` — la version courante ne reproduit plus l'echec enregistre. C'est le
    defaut que ce module existe pour rendre visible ;
  * `durcie` — elle en reproduit davantage (une regle qui n'echouait pas se met a
    echouer). Ce n'est pas une regression, mais cela se dit : un garde qui change de
    comportement sans que personne ne l'ait decide est une surprise, pas une preuve.

Une regression de **securite** est BLOQUANTE : la livraison est refusee. Une regression
de temoin est un defaut, pas un blocage — on peut vouloir livrer en la declarant.

Pourquoi jamais une valeur sensible
-----------------------------------
Un champ sensible observe dans la trace donne son NOM au cas, pas sa valeur. Les valeurs
du cas sont des temoins synthetiques, generes par la forme du champ. Copier la valeur
reelle dans un fichier versionne transformerait le jeu de regression en fuite permanente :
un secret pousse une fois dans un depot y reste, et dans l'historique git aussi.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import FailClosed
from ..core.journal import Journal
from ..core.redaction import is_sensitive_key, redact_data
from ..core.types import Rule, RuleKind, Spec
from ..verify.executable import ExecutableProver, Sandbox

__all__ = [
    "GENRE_SECURITE",
    "GENRE_TEMOIN",
    "Cas",
    "Proposition",
    "RapportEval",
    "ResultatCas",
    "artefact_depuis_trace",
    "charger",
    "ecrire",
    "evaluer",
    "formater",
    "geler_securite",
    "geler_temoin",
    "propositions",
    "rejouer",
    "valeur_temoin",
]

#: Un echec observe dans la trace : des regles DOIVENT encore echouer sur cet artefact.
GENRE_TEMOIN = "temoin"
#: Un champ sensible observe dans la trace : sa valeur temoin ne doit JAMAIS sortir.
GENRE_SECURITE = "securite"

#: Dossier du corpus versionne, par convention.
JEU_PAR_DEFAUT = Path("evidence/regressions")

#: Valeurs temoins, par forme de champ. Elles sont volontairement RECONNAISSABLES : un cas
#: de securite qui passe parce que sa valeur ne ressemble a rien ne mesure rien, il rassure.
#:
#: Le choix des formes n'est pas cosmetique, il vient d'un refus REEL rencontre au premier
#: gel : une valeur temoin libre (`jioTemoin0123456789abcdef`, 26 caracteres alphanumeriques)
#: n'est attrapee par AUCUN motif de la redaction, et le garde de gel a refuse d'archiver le
#: cas — « la redaction laisse passer …, c'est un defaut ACTUEL ». Le garde avait raison : une
#: chaine aleatoire sans prefixe est indiscernable d'un identifiant, d'un hash ou d'une
#: reference. Les valeurs temoins prennent donc la forme des fuites que la redaction sait
#: reconnaitre (prefixe `sk-`, `Bearer`, adresse de courriel, numero de telephone), et c'est
#: cette forme-la qui est verrouillee par le cas.
_VALEURS_TEMOINS: tuple[tuple[str, str], ...] = (
    ("email", "temoin.regression@example.test"),
    ("mail", "temoin.regression@example.test"),
    ("phone", "+33 6 00 00 00 00"),
    ("mobile", "+33 6 00 00 00 00"),
    ("telephone", "+33 6 00 00 00 00"),
    ("authorization", "Bearer sk-jioTemoin0123456789abcdef"),
    ("secret", "sk-jioTemoin0123456789abcdef"),
    ("password", "sk-jioTemoin0123456789abcdef"),
)


def valeur_temoin(champ: str) -> str:
    """La valeur temoin d'un champ, d'apres la forme de son nom.

    Jamais la valeur reelle : on ne mesure pas une fuite en la recopiant.
    """
    minuscule = (champ or "").lower()
    for motif, valeur in _VALEURS_TEMOINS:
        if motif in minuscule:
            return valeur
    # Les champs de jeton (`api_key`, `access_token`, `client_secret`) : forme prefixee,
    # la seule qu'un motif puisse distinguer d'un identifiant ordinaire.
    if is_sensitive_key(champ or "") or any(
        mot in minuscule for mot in ("token", "key", "bearer", "credential")
    ):
        return "sk-jioTemoin0123456789abcdef"
    return "temoin.regression@example.test"


def _apercu(valeur: str, limite: int = 32) -> str:
    """Un apercu sur, avec une marque quand il est tronque.

    Un apercu tronque SANS marque se lit comme la valeur complete : au premier essai, la
    phrase « FUITE : 'contact de test : sk-jio' » laissait croire a une valeur coupee.
    """
    return repr(valeur[:limite]) + ("…" if len(valeur) > limite else "")


def _lire_trace(chemin: Path) -> Journal:
    """Un journal lu SANS verification, puis verifie ICI, pour distinguer trois etats.

    `Journal.load_verified` met en quarantaine un journal a la chaine cassee et rend un
    journal VIDE : l'appelant voit alors « aucun evenement » alors que le fichier est
    plein. Un cas de regression qui dit « la trace est vide » quand elle a ete reecrite se
    trompe de diagnostic — donc de geste a faire.
    """
    try:
        trace = Journal.from_jsonl(chemin.read_text(encoding="utf-8", errors="replace"), path=chemin)
    except (ValueError, KeyError, TypeError) as exc:
        raise FailClosed(f"trace illisible {chemin} : {exc}") from exc
    ok, casse = trace.verify_chain()
    if not ok:
        raise FailClosed(
            f"la chaine de {chemin} est cassee (a l'evenement {casse}) : une trace non "
            "verifiable ne devient pas un cas de regression — la reecrire, ou repartir "
            "d'une trace saine"
        )
    if not trace.events():
        raise FailClosed(f"{chemin} ne contient aucun evenement")
    return trace


def _empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Ce que la trace propose
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Proposition:
    """Un echec REEL, lu dans une trace, candidat a devenir un cas.

    Une proposition n'est pas un cas : elle porte ce que la trace sait (la regle, le
    monde, la revision, l'evenement) et ce qu'il manque pour en faire un cas jouable.
    """

    id: str
    genre: str
    resume: str
    provenance: str
    #: Ce que l'humain doit fournir pour que le cas soit jouable (ecrit noir sur blanc).
    manque: str = ""
    regle: str = ""
    champ: str = ""
    #: Le controle n'est PAS dans la trace (oracle secret) : il vient de l'humain.
    candidats: tuple[str, ...] = ()

    def en_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "genre": self.genre,
            "resume": self.resume,
            "provenance": self.provenance,
            "manque": self.manque,
            "regle": self.regle,
            "champ": self.champ,
            "candidats": list(self.candidats),
        }


def _monde(payload: Mapping[str, Any], evenement: object) -> str:
    monde = payload.get("monde") if isinstance(payload, Mapping) else None
    morceaux: list[str] = []
    if isinstance(monde, Mapping):
        revision = str(monde.get("revision", ""))[:7]
        sceau = str(monde.get("sceau", ""))[:12]
        if revision:
            morceaux.append(f"revision {revision}")
        if sceau:
            morceaux.append(f"monde {sceau}")
    morceaux.append(f"evenement #{getattr(evenement, 'seq', '?')}")
    return ", ".join(morceaux)


def _champs_sensibles(valeur: object, prefixe: str = "") -> list[str]:
    """Les NOMS de champs sensibles d'un payload — les valeurs ne sortent pas d'ici."""
    trouves: list[str] = []
    if isinstance(valeur, Mapping):
        for cle, sous in valeur.items():
            chemin = f"{prefixe}.{cle}" if prefixe else str(cle)
            if isinstance(sous, (str, int, float)) and str(sous) and is_sensitive_key(str(cle)):
                trouves.append(str(cle))
            trouves.extend(_champs_sensibles(sous, chemin))
    elif isinstance(valeur, (list, tuple)):
        for item in valeur:
            trouves.extend(_champs_sensibles(item, prefixe))
    return trouves


def propositions(journal: str | Path) -> tuple[Proposition, ...]:
    """Ce qui a mal tourne dans cette trace, sans recopier une valeur sensible.

    La chaine du journal est VERIFIEE : batir un cas de regression sur une trace dont on
    ne peut pas prouver qu'elle est intacte reviendrait a figer une preuve douteuse.
    """
    chemin = Path(journal)
    if not chemin.exists() or chemin.stat().st_size == 0:
        raise FailClosed(f"aucune trace a lire : {chemin} est absent ou vide")
    evenements = list(_lire_trace(chemin).events())

    candidats = tuple(
        str(e.payload.get("digest", ""))
        for e in evenements
        if e.kind == "candidate" and e.payload.get("digest")
    )
    vues: list[Proposition] = []
    deja: set[tuple[str, str]] = set()

    for evenement in evenements:
        payload = dict(evenement.payload)
        if evenement.kind == "witness" and payload.get("ok") is False:
            regle = str(payload.get("rule", ""))
            cle = (GENRE_TEMOIN, regle)
            if regle and cle not in deja:
                deja.add(cle)
                vues.append(
                    Proposition(
                        id=f"T-{regle}-{evenement.seq}",
                        genre=GENRE_TEMOIN,
                        regle=regle,
                        resume=(
                            f"la regle {regle} a ECHOUE sur un artefact reel "
                            f"(sortie hachee {str(payload.get('hash', ''))[:8]}, "
                            f"code {payload.get('exit_code')})"
                        ),
                        provenance=_monde(payload, evenement),
                        manque=(
                            "l'artefact (--artefact FICHIER, ou --candidat EMPREINTE quand "
                            "il vient de cette trace) et le controle de la regle "
                            "(--controles FICHIER) : l'oracle n'est pas dans la trace"
                        ),
                        candidats=candidats,
                    )
                )
        for champ in _champs_sensibles(payload):
            cle = (GENRE_SECURITE, champ)
            if cle in deja:
                continue
            deja.add(cle)
            vues.append(
                Proposition(
                    id=f"S-{champ}-{evenement.seq}",
                    genre=GENRE_SECURITE,
                    champ=champ,
                    resume=(
                        f"la trace a exporte un champ sensible `{champ}` "
                        f"(valeur NON recopiee : longueur {len(str(payload.get(champ, '')))})"
                    ),
                    provenance=_monde(payload, evenement),
                    manque="rien : les valeurs temoins sont generees, jamais recopiees",
                )
            )
    return tuple(vues)


def formater_propositions(items: Sequence[Proposition]) -> str:
    if not items:
        return "    aucun echec reel propose : cette trace ne contient rien a figer."
    lignes = [f"    {len(items)} proposition(s) issue(s) d'une trace REELLE :"]
    for item in items:
        lignes.append(f"      [{item.genre}] {item.id}  {item.resume}")
        lignes.append(f"        provenance : {item.provenance}")
        if item.manque:
            lignes.append(f"        pour geler : {item.manque}")
    return "\n".join(lignes)


def artefact_depuis_trace(journal: str | Path, digest: str) -> str:
    """Le code d'un candidat de la trace, VERIFIE par son empreinte.

    La trace garde le texte du candidat (`code_tail`) et son empreinte. Rendre le texte
    sans reverifier l'empreinte ferait entrer dans le corpus un artefact qui n'est pas
    celui qui a echoue — un cas de regression qui ne prouve rien, mais qui rassure.
    """
    chemin = Path(journal)
    if not chemin.exists() or chemin.stat().st_size == 0:
        raise FailClosed(f"aucune trace a lire : {chemin} est absent ou vide")
    for evenement in _lire_trace(chemin).events("candidate"):
        contenu = str(evenement.payload.get("code_tail", ""))
        if contenu and _empreinte(contenu) == digest:
            return contenu
    raise FailClosed(
        f"aucun candidat d'empreinte {digest} dans {chemin} : l'artefact doit etre "
        "fourni a la main (--artefact), et son empreinte doit correspondre"
    )


# --------------------------------------------------------------------------- #
# Le cas gele
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Cas:
    """Un echec reel, devenu rejouable.

    `attendues_en_echec` est ce que le cas EXIGE : ces regles doivent encore echouer.
    `artefact_digest` lie le cas a son artefact ; un fichier edite a la main est refuse.
    """

    id: str
    genre: str
    raison: str
    provenance: str
    attendues_en_echec: tuple[str, ...] = ()
    bloquant: bool = False
    #: genre temoin
    artefact: str = ""
    artefact_digest: str = ""
    controles: Mapping[str, str] = field(default_factory=dict)
    #: genre securite
    charge: Mapping[str, Any] = field(default_factory=dict)
    interdits: tuple[str, ...] = ()

    def en_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "genre": self.genre,
            "raison": self.raison,
            "provenance": self.provenance,
            "bloquant": self.bloquant,
            "attendues_en_echec": list(self.attendues_en_echec),
            "artefact": self.artefact,
            "artefact_digest": self.artefact_digest,
            "controles": dict(self.controles),
            "charge": dict(self.charge),
            "interdits": list(self.interdits),
        }

    @classmethod
    def depuis_dict(cls, donnees: Mapping[str, Any]) -> Cas:
        genre = str(donnees.get("genre", ""))
        if genre not in (GENRE_TEMOIN, GENRE_SECURITE):
            raise ValueError(f"genre inconnu : {genre!r}")
        for obligatoire in ("id", "raison", "provenance"):
            if not donnees.get(obligatoire):
                raise ValueError(f"cas {donnees.get('id', '?')} : `{obligatoire}` est obligatoire")
        return cls(
            id=str(donnees["id"]),
            genre=genre,
            raison=str(donnees["raison"]),
            provenance=str(donnees["provenance"]),
            attendues_en_echec=tuple(donnees.get("attendues_en_echec") or ()),
            bloquant=bool(donnees.get("bloquant", genre == GENRE_SECURITE)),
            artefact=str(donnees.get("artefact", "")),
            artefact_digest=str(donnees.get("artefact_digest", "")),
            controles=dict(donnees.get("controles") or {}),
            charge=dict(donnees.get("charge") or {}),
            interdits=tuple(donnees.get("interdits") or ()),
        )


def ecrire(cas: Cas, dossier: str | Path = JEU_PAR_DEFAUT) -> Path:
    """Ecrit un cas dans le corpus, en refusant d'ecraser un cas different."""
    racine = Path(dossier)
    racine.mkdir(parents=True, exist_ok=True)
    chemin = racine / f"{cas.id}.json"
    texte = json.dumps(cas.en_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if chemin.exists() and chemin.read_text(encoding="utf-8") != texte:
        raise FailClosed(
            f"{chemin} existe deja avec un contenu different : un cas de regression se "
            "review, il ne s'ecrase pas en silence. Supprimer l'ancien, ou changer d'id."
        )
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def charger(dossier: str | Path = JEU_PAR_DEFAUT) -> tuple[Cas, ...]:
    """Le corpus versionne, trie par identifiant. Un fichier illisible ARRETE tout."""
    racine = Path(dossier)
    if not racine.is_dir():
        return ()
    cas: list[Cas] = []
    for chemin in sorted(racine.glob("*.json")):
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
            cas.append(Cas.depuis_dict(donnees))
        except (OSError, ValueError, TypeError) as exc:
            raise FailClosed(f"cas illisible {chemin} : {exc}") from exc
    return tuple(cas)


def geler_temoin(
    proposition: Proposition,
    *,
    artefact: str,
    controles: Mapping[str, str],
    provenance_artefact: str = "",
    dossier: str | Path = JEU_PAR_DEFAUT,
    prover: ExecutableProver | None = None,
) -> Cas:
    """Gele un echec observe — a condition qu'il se reproduise MAINTENANT.

    Un cas dont l'attente est fausse des sa creation est pire qu'une absence de cas : il
    occupe la place d'un garde et ne garde rien. L'echec est donc rejoue ici, contre
    l'artefact fourni, et le gel est refuse si la regle observee passe.
    """
    if not proposition.regle:
        raise FailClosed(f"{proposition.id} n'est pas une proposition de temoin")
    if not controles:
        raise FailClosed(
            "aucun controle fourni : la trace ne contient pas l'oracle (il est secret), "
            "donc le cas ne peut pas etre rejoue. Fournir `--controles FICHIER`."
        )
    if proposition.regle not in controles:
        raise FailClosed(
            f"les controles fournis ne couvrent pas la regle {proposition.regle} : "
            f"regles presentes : {', '.join(sorted(controles))}"
        )
    spec = Spec(
        mission=f"regression {proposition.id}",
        rules=tuple(
            Rule(id=regle, statement=regle, kind=RuleKind.TEST) for regle in controles
        ),
    )
    juges = prover or ExecutableProver(sandbox=Sandbox(timeout=30))
    resultat = juges.prove(artefact, spec, hidden_checks=dict(controles))
    obtenues = tuple(sorted({w.rule_id for w in resultat.failures}))
    if proposition.regle not in obtenues:
        raise FailClosed(
            f"l'echec observe n'est PAS reproduit : la regle {proposition.regle} passe sur "
            "cet artefact avec ces controles. Un cas dont l'attente est fausse ne garde "
            "rien — verifier l'artefact et le controle, ou ne pas geler ce cas."
        )
    provenance = f"{proposition.provenance}"
    if provenance_artefact:
        provenance += f" ; artefact : {provenance_artefact}"
    return Cas(
        id=proposition.id,
        genre=GENRE_TEMOIN,
        raison=(
            f"echec reel observe ({proposition.resume}) : ces regles doivent ENCORE "
            f"echouer, sinon le garde s'est tu sans que personne ne le decide"
        ),
        provenance=provenance,
        attendues_en_echec=obtenues,
        bloquant=False,
        artefact=artefact,
        artefact_digest=_empreinte(artefact),
        controles=dict(controles),
    )


def geler_securite(
    proposition: Proposition,
    *,
    champs: Mapping[str, str] | None = None,
    dossier: str | Path = JEU_PAR_DEFAUT,
) -> Cas:
    """Gele une fuite OBSERVEE : la redaction doit continuer de la fermer.

    La charge du cas est construite avec des valeurs temoins — la valeur reelle de la
    trace n'est jamais recopiee, ni dans le cas, ni dans le rapport. Le cas est refuse si
    la valeur fuit DEJA : un cas de regression enregistre un defaut CORRIGE, pas un
    defaut en cours (celui-la doit etre vu maintenant, pas archive).
    """
    champ = proposition.champ
    if not champ:
        raise FailClosed(f"{proposition.id} n'est pas une proposition de securite")
    charge = dict(champs or {})
    if not charge:
        # Le champ observe, plus un champ neutre qui porte une valeur de meme forme : les
        # deux chemins de la redaction (cle sensible, valeur sensible dans un texte) sont
        # couverts, parce que les deux ont ete observes.
        charge = {
            champ: valeur_temoin(champ),
            "note": f"contact de test : {valeur_temoin(champ)}",
        }
    interdits = tuple(
        sorted({str(valeur) for valeur in charge.values() if str(valeur).strip()})
    )
    export = json.dumps(redact_data(charge), ensure_ascii=False)
    fuit = [interdit for interdit in interdits if interdit in export]
    if fuit:
        raise FailClosed(
            "la redaction laisse passer "
            + ", ".join(_apercu(valeur) for valeur in fuit)
            + " : c'est un defaut ACTUEL, pas un cas de regression. Le corriger d'abord ; "
            "un cas gele maintenant figerait la fuite au lieu de la fermer."
        )
    if charge == dict(redact_data(charge)):
        raise FailClosed(
            "aucune valeur du cas n'est masquee : le cas passerait meme si la redaction "
            "disparaissait. Il ne mesure donc rien."
        )
    return Cas(
        id=proposition.id,
        genre=GENRE_SECURITE,
        raison=(
            f"fuite reelle observee ({proposition.resume}) : la redaction doit continuer "
            "de masquer ce champ. Valeurs temoins, jamais les valeurs de la trace."
        ),
        provenance=proposition.provenance,
        bloquant=True,
        charge=charge,
        interdits=interdits,
    )


# --------------------------------------------------------------------------- #
# Le rejeu
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResultatCas:
    """Ce que le rejeu d'un cas dit de la version courante."""

    cas: str
    genre: str
    tenu: bool
    detail: str
    bloquant: bool = False
    #: Vrai quand la version courante detecte PLUS que ce qui etait enregistre. Ce n'est
    #: pas une regression, mais cela se dit.
    durci: bool = False

    def en_dict(self) -> dict[str, Any]:
        return {
            "cas": self.cas,
            "genre": self.genre,
            "tenu": self.tenu,
            "detail": self.detail,
            "bloquant": self.bloquant,
            "durci": self.durci,
        }


def rejouer(cas: Cas, *, prover: ExecutableProver | None = None) -> ResultatCas:
    """Rejoue un cas contre la version courante. Aucune exception ne sort d'ici : un cas
    qui ne peut pas etre rejoue est un cas NON TENU, avec sa raison."""
    if cas.genre == GENRE_TEMOIN:
        return _rejouer_temoin(cas, prover)
    if cas.genre == GENRE_SECURITE:
        return _rejouer_securite(cas)
    return ResultatCas(
        cas=cas.id, genre=cas.genre, tenu=False,
        detail=f"genre inconnu : {cas.genre!r}", bloquant=cas.bloquant,
    )


def _rejouer_temoin(cas: Cas, prover: ExecutableProver | None) -> ResultatCas:
    if not cas.artefact:
        return ResultatCas(cas.id, cas.genre, False, "aucun artefact enregistre", cas.bloquant)
    empreinte = _empreinte(cas.artefact)
    if cas.artefact_digest and empreinte != cas.artefact_digest:
        return ResultatCas(
            cas.id, cas.genre, False,
            f"artefact MODIFIE : empreinte {empreinte}, attendue {cas.artefact_digest} — "
            "un cas de regression decrit un fait passe, il ne se reecrit pas",
            cas.bloquant,
        )
    if not cas.attendues_en_echec:
        return ResultatCas(
            cas.id, cas.genre, False,
            "le cas n'exige AUCUN echec : il passerait meme si tout le harness disparaissait",
            cas.bloquant,
        )
    spec = Spec(
        mission=f"regression {cas.id}",
        rules=tuple(
            Rule(id=regle, statement=regle, kind=RuleKind.TEST) for regle in cas.controles
        ),
    )
    juges = prover or ExecutableProver(sandbox=Sandbox(timeout=30))
    try:
        resultat = juges.prove(cas.artefact, spec, hidden_checks=dict(cas.controles))
    except FailClosed as exc:
        return ResultatCas(
            cas.id, cas.genre, False, f"preuve impossible : {exc}", cas.bloquant
        )
    obtenues = {w.rule_id for w in resultat.failures}
    manquantes = [regle for regle in cas.attendues_en_echec if regle not in obtenues]
    if manquantes:
        return ResultatCas(
            cas.id, cas.genre, False,
            "SILENCE : "
            + ", ".join(manquantes)
            + " n'echoue(nt) plus sur l'artefact enregistre — le garde ne detecte plus "
            "l'echec reel qui l'a fait naitre",
            cas.bloquant,
        )
    durci = bool(obtenues - set(cas.attendues_en_echec))
    detail = (
        f"{len(cas.attendues_en_echec)} echec(s) enregistre(s) reproduit(s)"
        + (f" ; {len(obtenues - set(cas.attendues_en_echec))} en plus (durcissement)" if durci else "")
    )
    return ResultatCas(cas.id, cas.genre, True, detail, cas.bloquant, durci)


def _rejouer_securite(cas: Cas) -> ResultatCas:
    if not cas.charge or not cas.interdits:
        return ResultatCas(
            cas.id, cas.genre, False,
            "aucune charge ou aucune valeur interdite : le cas ne mesure rien", cas.bloquant
        )
    brut = json.dumps(cas.charge, ensure_ascii=False)
    # Une valeur interdite qui n'est PAS dans la charge brute ne mesure rien : le cas
    # passerait meme si la redaction disparaissait. C'est le piege d'un cas edite a la
    # main (« je change la valeur interdite, il passe ») : mesure faite, `jio eval` rendait
    # 0 sur un cas ainsi modifie — un garde qui ne garde plus rien.
    fantomes = [valeur for valeur in cas.interdits if valeur not in brut]
    if fantomes:
        return ResultatCas(
            cas.id, cas.genre, False,
            "cas VIDE : "
            + ", ".join(_apercu(valeur) for valeur in fantomes)
            + " n'est pas dans la charge brute — le cas exigerait l'absence de ce qui n'y est pas",
            cas.bloquant,
        )
    export = json.dumps(redact_data(cas.charge), ensure_ascii=False)
    fuites = [valeur for valeur in cas.interdits if valeur in export]
    if fuites:
        return ResultatCas(
            cas.id, cas.genre, False,
            "FUITE : "
            + ", ".join(_apercu(valeur) for valeur in fuites)
            + " sort(ent) encore d'un export",
            cas.bloquant,
        )
    return ResultatCas(
        cas.id, cas.genre, True,
        f"{len(cas.interdits)} valeur(s) temoin(s) masquee(s)", cas.bloquant
    )


@dataclass
class RapportEval:
    """Le rejeu du corpus entier, avec le chiffre qui decide : le taux de silence."""

    resultats: list[ResultatCas] = field(default_factory=list)
    note: str = ""

    @property
    def tenus(self) -> list[ResultatCas]:
        return [r for r in self.resultats if r.tenu]

    @property
    def silencieux(self) -> list[ResultatCas]:
        """Cas qui ne se declenchent plus : des defauts reels redevenus invisibles."""
        return [r for r in self.resultats if not r.tenu]

    @property
    def bloquants(self) -> list[ResultatCas]:
        """Silences de SECURITE : ceux-la refusent la livraison."""
        return [r for r in self.silencieux if r.bloquant]

    @property
    def durcis(self) -> list[ResultatCas]:
        return [r for r in self.resultats if r.tenu and r.durci]

    @property
    def taux_de_silence(self) -> float:
        """Part des defauts reels que la version courante ne detecte plus."""
        return len(self.silencieux) / len(self.resultats) if self.resultats else 0.0

    @property
    def bloque(self) -> bool:
        return bool(self.bloquants)

    def en_dict(self) -> dict[str, Any]:
        return {
            "cas": len(self.resultats),
            "tenus": len(self.tenus),
            "silencieux": len(self.silencieux),
            "bloquants": len(self.bloquants),
            "taux_de_silence": round(self.taux_de_silence, 4),
            "resultats": [r.en_dict() for r in self.resultats],
            "note": self.note,
        }


def evaluer(
    cas: Iterable[Cas], *, prover: ExecutableProver | None = None, note: str = ""
) -> RapportEval:
    """Rejoue un corpus. Le prouveur est partage : un cas ne coute pas un bac a sable."""
    juges = prover or ExecutableProver(sandbox=Sandbox(timeout=30))
    liste = list(cas)
    rapport = RapportEval(note=note)
    if not liste:
        rapport.note = (
            note or "aucun cas enregistre : rien n'a ete mesure (un taux sur du vide "
            "serait un chiffre sans contenu)"
        )
        return rapport
    for item in liste:
        rapport.resultats.append(rejouer(item, prover=juges))
    return rapport


def formater(rapport: RapportEval) -> str:
    """Le rapport lisible : ce qui a tenu, ce qui s'est tu, et ce que cela bloque."""
    total = len(rapport.resultats)
    lignes = [
        (
            f"    REGRESSIONS  ·  {len(rapport.tenus)}/{total} cas tenu(s)  ·  "
            f"taux de silence : {rapport.taux_de_silence:.0%}"
        ),
        (
            "    Lecture : un cas qui ne se declenche plus est un garde qui s'est TU — "
            "le defaut reel qu'il decrivait redevient invisible."
        ),
    ]
    if rapport.note:
        lignes.append(f"    note : {rapport.note}")
    for resultat in rapport.silencieux:
        marque = "BLOQUANT" if resultat.bloquant else "SILENCE "
        lignes.append(f"    {marque}  {resultat.cas}  [{resultat.genre}]  {resultat.detail}")
    for resultat in rapport.durcis:
        lignes.append(f"    DURCI     {resultat.cas}  [{resultat.genre}]  {resultat.detail}")
    if total and not rapport.silencieux:
        lignes.append("    aucun silence : chaque echec reel enregistre est encore detecte.")
    if rapport.bloque:
        lignes.append(
            "    -> REGRESSION DE SECURITE : la livraison est refusee tant que la fuite "
            "n'est pas refermee."
        )
    return "\n".join(lignes)
