"""Réflexion obligatoire et forge de rôles de revue à partir de chaque mission.

Les trois rôles transversaux sont des garde-fous fixes. Les spécialistes, eux, sont
synthétisés à partir du mandat et des règles concrètes de la mission; aucun catalogue
prédéfini de profils spécialisés n'est parcouru. La sélection est déterministe, bornée
et enregistrée sans recopier l'objectif en clair.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AgentRole:
    """Mandat d'un critique forgé pour la mission courante."""

    name: str
    focus: str
    rubric: str
    reason: str
    required_evidence: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ReflectionPlan:
    """Plan de revue lié à une demande précise."""

    objective_sha256: str
    domains: tuple[str, ...]
    risk_flags: tuple[str, ...]
    roles: tuple[AgentRole, ...]
    limits: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "objective_sha256": self.objective_sha256,
            "domains": list(self.domains),
            "risk_flags": list(self.risk_flags),
            "roles": [role.as_dict() for role in self.roles],
            "limits": list(self.limits),
        }

    def trace_summary(self) -> dict[str, object]:
        """Trace les choix et empreintes des mandats, sans copier les prompts."""
        prompt_hashes = {
            role.name: hashlib.sha256(
                f"{role.focus}\n{role.rubric}\n{role.reason}\n{role.required_evidence}".encode(
                    "utf-8"
                )
            ).hexdigest()
            for role in self.roles
        }
        return {
            "reflection_version": 1,
            "objective_sha256": self.objective_sha256,
            "domains": list(self.domains),
            "risk_flags": list(self.risk_flags),
            "agent_roles": [role.name for role in self.roles],
            "role_prompt_sha256": prompt_hashes,
            "role_count": len(self.roles),
            "selection": "mandat et critères de la mission; spécialistes forgés à la demande",
        }


_STOPWORDS = frozenset(
    """
    a an and are as at be been by can could de des du elle en et for from had has have i il ils
    in into is it la le les leur lui me mon ne ni no not of on or our par pas pour que qui sa
    se ses she si son sous sur the then they this to un une uneur unurs us was we were will with
    you your au aux ce ces cette comme dans d de la le les faire fait faire j je l leur leurs ma
    mais mes moi nos notre ou où on ont ou par plus quand que quel quelle quels quelles qui quoi
    sa sans ses son sont sous ta tes ton tout toute toutes tous tu un une vos votre vous y
    creer créer creee créée cree crée produire faire realiser réaliser rendre donner presenter
    présenter demande besoin objectif objectif mission livrable jio terminator duree durée
    duration exactly exactement seconde secondes second seconds minute minutes expliquer
    explique explication parcours pretend pretending agents agent logique logiques models
    model models indépendants independent roster fixe fixed errors erreurs
    quality qualité clarity claire readable lisibilite lisibilité fidelity fidelite
    """.split()
)

# These are risk cues only, not prewritten specialist profiles. They add a dynamic
# risk-review role whose name and scope are built from terms found in this request.
_RISK_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "medical",
        ("medical", "médical", "medicale", "health", "santé", "sante", "diagnostic"),
    ),
    ("legal", ("legal", "juridique", "law", "droit")),
    (
        "security",
        (
            "security",
            "sécurité",
            "securite",
            "secure",
            "securisee",
            "credential",
            "secret",
            "injection",
            "injections",
        ),
    ),
    (
        "financial",
        ("investment", "investissement", "finance", "financial", "financier"),
    ),
    ("emergency", ("urgence", "emergency", "crise")),
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join(
        "".join(c for c in decomposed if not unicodedata.combining(c)).split()
    )


def _keywords(text: str, *, maximum: int = 3) -> tuple[str, ...]:
    """Extrait des étiquettes de mandat; elles ne sont jamais traitées comme des consignes."""
    tokens = re.findall(r"[a-z0-9]+", _normalize(text))
    counts = Counter(
        token
        for token in tokens
        if len(token) >= 4 and token not in _STOPWORDS and not token.isdigit()
    )
    # Fréquence d'abord, puis ordre de première apparition pour un résultat stable.
    first = {token: tokens.index(token) for token in counts}
    ordered = sorted(counts, key=lambda token: (-counts[token], first[token], token))
    return tuple(ordered[:maximum])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize(text)).strip("_")[:48] or "mission"


def _group_requirements(
    requirements: tuple[str, ...], maximum: int
) -> tuple[tuple[str, ...], ...]:
    valid = tuple(
        item.strip() for item in requirements if isinstance(item, str) and item.strip()
    )
    if not valid:
        return ((),)
    count = min(maximum, len(valid))
    groups: list[list[str]] = [[] for _ in range(count)]
    for index, item in enumerate(valid):
        groups[index % count].append(item)
    return tuple(tuple(group) for group in groups)


def reflect_on_task(
    objective: str, requirements: tuple[str, ...] = ()
) -> ReflectionPlan:
    """Réfléchit obligatoirement à la mission et forge ses spécialistes sur mesure.

    Trois revues transversales sont toujours actives. Jusqu'à trois spécialistes supplémentaires
    sont nommés à partir des termes distinctifs du brief et des règles compilées. Les enjeux
    sensibles réservent une de ces places à une revue des risques correspondants.
    """
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("la réflexion exige un objectif non vide")

    context = "\n".join((objective, *requirements))
    objective_digest = hashlib.sha256(objective.strip().encode("utf-8")).hexdigest()
    roles: list[AgentRole] = [
        AgentRole(
            "brief_interpreter",
            "intention utilisateur et couverture des exigences explicites",
            "Compare le livrable au brief et à chaque règle numérotée. Signale toute exigence "
            "omise, déformée ou remplacée par une supposition.",
            "Garde-fou transversal obligatoire.",
            "Table de correspondance entre exigences et éléments observables du livrable.",
        ),
        AgentRole(
            "adversarial_reviewer",
            "contre-exemples, angles morts et échec d'usage réel",
            "Essaie de réfuter le résultat avec un scénario concret. Cherche les cas limites et "
            "hypothèses non vérifiées; une approbation sans motif est invalide.",
            "Garde-fou transversal obligatoire.",
            "Scénario adversarial exécuté ou limite explicitement non vérifiable.",
        ),
        AgentRole(
            "evidence_auditor",
            "preuve, provenance et séparation du vérifié et de l'inconnu",
            "Classe chaque conclusion comme vérifiée, inférée ou inconnue. Refuse qu'un consensus, "
            "une apparence convaincante ou une affirmation de l'artefact tienne lieu de preuve.",
            "Garde-fou transversal obligatoire.",
            "Source, test, commande ou artefact reproductible; limites nommées.",
        ),
    ]

    risk_hits: list[str] = []
    normalized = _normalize(context)
    for risk, cues in _RISK_CUES:
        if any(
            re.search(rf"(?<!\w){re.escape(_normalize(cue))}(?!\w)", normalized)
            for cue in cues
        ):
            risk_hits.append(risk)
    risk_flags = tuple(f"risque potentiel détecté: {risk}" for risk in risk_hits)

    # Spécialistes issus des groupes de critères, pas choisis dans une liste de métiers.
    # Une place est réservée au risque sensible s'il y a lieu, et le plafond reste strict.
    specialist_slots = 2 if risk_hits else 3
    groups = _group_requirements(requirements, specialist_slots)
    objective_terms = _keywords(objective)
    for index, group in enumerate(groups, start=1):
        requirement_text = "\n".join(group)
        terms = _keywords(requirement_text, maximum=3) if requirement_text else ()
        terms = tuple(dict.fromkeys((*terms, *objective_terms)))[:3]
        if not terms:
            terms = (f"mission_{index}",)
        topic = "_".join(terms)
        criterion_ids = tuple(
            match
            for text in group
            for match in re.findall(r"\bR-\d+\b", text, flags=re.I)
        )
        focus_label = ", ".join(terms)
        roles.append(
            AgentRole(
                f"specialist_{_slug(topic)}",
                f"critères de mission associés à : {focus_label}",
                "Examine en profondeur le périmètre nommé dans le brief et les critères attribués. "
                "Vérifie le résultat concret, repère les omissions propres à ce périmètre et cite "
                "les preuves ou les limites. Ne considère pas la finition comme une validation.",
                (
                    "Rôle forgé à partir des critères " + ", ".join(criterion_ids)
                    if criterion_ids
                    else "Rôle forgé à partir des termes distinctifs du mandat."
                ),
                "Vérification élément par élément du périmètre de mission attribué.",
            )
        )

    if risk_hits:
        risk_terms = tuple(
            cue
            for risk, cues in _RISK_CUES
            if risk in risk_hits
            for cue in cues
            if _normalize(cue) in normalized
        )
        risk_scope = (
            "_".join(_keywords(" ".join(risk_terms), maximum=3)) or "enjeu_sensible"
        )
        roles.append(
            AgentRole(
                f"risk_reviewer_{_slug(risk_scope)}",
                "conséquences et limites liées aux signaux de risque présents dans la demande",
                "Vérifie les conséquences possibles d'une erreur, les limites de compétence, les "
                "sources pertinentes et les conditions d'escalade. Ne présente pas un avis non "
                "qualifié comme une décision professionnelle définitive.",
                "Rôle forgé parce que le mandat contient des signaux de risque sensible.",
                "Sources compétentes, limites explicites et orientation sûre si le cas l'exige.",
            )
        )

    # Trois rôles transversaux + au plus trois agents forgés à partir de la mission.
    roles = roles[:6]
    domains = _keywords(objective, maximum=6) or ("general",)
    limits = (
        "Les spécialistes sont forgés à partir des critères de cette mission, pas tirés d'un roster métier fixe.",
        "La segmentation lexicale peut manquer un domaine implicite; l'utilisateur peut corriger le cadrage.",
        "Plusieurs rôles servis par le même modèle peuvent partager un angle mort; un rôle ne constitue pas une preuve.",
    )
    return ReflectionPlan(
        objective_sha256=objective_digest,
        domains=domains,
        risk_flags=risk_flags,
        roles=tuple(roles),
        limits=limits,
    )
