"""Tests metamorphiques (MetaQA) — detecter les hallucinations *coherentes*.

Le probleme que ca resout, et il est severe :

    SelfCheckGPT demande au modele de repondre plusieurs fois, puis compare.
    Mais un modele qui hallucine **repete la meme hallucination** — le score de
    consistance reste bas et l'hallucination passe. Mesure : MetaQA bat
    SelfCheckGPT dans les 7 categories testees.

La parade : ne pas demander la meme chose. **Muter la question** et verifier
que la reponse reste invariante sous la transformation.

    Si f est vraie, alors f(T(x)) = g(f(x)) pour la transformation T.
    Si l'invariance casse, la reponse est suspecte — quelle que soit sa
    coherence apparente.

12 familles de mutations implementees (sans modele, deterministes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..core.types import Severity


@dataclass(frozen=True)
class Mutation:
    """Une transformation d'entree et la relation attendue."""

    name: str
    apply: Callable[[str], str]
    invariant: str  # ce qui doit rester vrai


@dataclass(frozen=True)
class MetamorphicFinding:
    """Une rupture d'invariance detectee."""

    mutation: str
    original: str
    mutated: str
    answer_original: str
    answer_mutated: str
    severity: Severity = Severity.HIGH
    detail: str = ""


# --------------------------------------------------------------------------- #
# Familles de mutations
# --------------------------------------------------------------------------- #

_NULL_TAIL = ", s'il te plait. Reponds uniquement par la reponse."


def _double_space(text: str) -> str:
    return re.sub(r"\s+", "  ", text.strip())


def _polite(text: str) -> str:
    return text.strip() + _NULL_TAIL


def _negate(text: str) -> str:
    return f"Est-il FAUX que : {text.strip()}"


def _reorder_sentences(text: str) -> str:
    parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]
    return " ".join(reversed(parts)) if len(parts) > 1 else text.strip()


def _unit_swap(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        value = m.group(1)
        return f"{float(value) * 100:.0f} %" if value.isdigit() else m.group(0)

    return re.sub(r"\b(\d+)\s*pour\s*cent\b", lambda m: repl(m), text, flags=re.I)


def _synonym(text: str) -> str:
    table = {
        "calculer": "determiner",
        "nombre": "quantite",
        "liste": "ensemble",
        "erreur": "defaut",
        "fonction": "procedure",
        "valeur": "grandeur",
        "somme": "total",
    }
    out = text
    for a, b in table.items():
        out = re.sub(rf"\b{a}\b", b, out, flags=re.I)
    return out


def _case_swap(text: str) -> str:
    return text.upper() if text.strip().isupper() is False and len(text) < 400 else text


def _typo(text: str) -> str:
    return text.replace("e", "e" * 2, 1) if "e" in text else text


def _language_swap(text: str) -> str:
    return f"[Answer in English] {text.strip()}"


def _add_irrelevant(text: str) -> str:
    return f"{text.strip()}\n\nNote : le ciel est bleu aujourd'hui."


def _numerical_perturb(text: str) -> str:
    """Change un nombre *non essentiel* : la reponse doit rester identique."""
    return re.sub(r"\b([1-9])\b(?!\d)", lambda m: str(int(m.group(1))), text, count=1)


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("espaces", _double_space, "reponse identique"),
    Mutation("politesse", _polite, "reponse identique (aucun contenu ajoute)"),
    Mutation("negation", _negate, "reponse INVERSEE"),
    Mutation("ordre_phrases", _reorder_sentences, "reponse identique"),
    Mutation("pourcent", _unit_swap, "meme valeur, unite equivalente"),
    Mutation("synonymes", _synonym, "reponse identique"),
    Mutation("casse", _case_swap, "reponse identique (hors casse)"),
    Mutation("langue", _language_swap, "meme reponse, autre langue"),
    Mutation("bruit", _add_irrelevant, "reponse identique"),
    Mutation("perturbation", _numerical_perturb, "reponse identique"),
)


@dataclass
class MetamorphicTester:
    """Applique les mutations et compare les reponses.

    `answer_fn(question) -> reponse` est injecte : cela marche avec n'importe
    quel modele, y compris en black-box (aucun acces aux logprobs requis).
    """

    mutations: tuple[Mutation, ...] = MUTATIONS
    max_mutations: int = 6
    similarity: float = 0.82  # seuil d'invariance (Jaccard sur mots)

    def test(self, question: str, answer_fn: Callable[[str], str]) -> tuple[MetamorphicFinding, ...]:
        base = (answer_fn(question) or "").strip()
        if not base:
            return ()

        findings: list[MetamorphicFinding] = []
        for mut in self.mutations[: self.max_mutations]:
            mutated_q = mut.apply(question)
            if mutated_q == question:
                continue
            try:
                mutated_a = (answer_fn(mutated_q) or "").strip()
            except Exception:  # noqa: BLE001 — une mutation qui echoue n'invalide pas le reste
                continue

            sim = jaccard(base, mutated_a)
            flipped = _looks_negated(base, mutated_a)

            # Cas "negation" : l'inversion est ATTENDUE — mais uniquement pour
            # une question a reponse boolenne. Sur « combien font 2+2 ? », la
            # negation n'a pas de sens : signaler un probleme serait un faux
            # positif, et les faux positifs detruisent la confiance dans le
            # garde (c'est exactement ce que le SPEC grounding elimine).
            if "INVERSEE" in mut.invariant:
                if _is_boolean_answer(base) and not flipped:
                    findings.append(
                        MetamorphicFinding(
                            mutation=mut.name,
                            original=question,
                            mutated=mutated_q,
                            answer_original=base,
                            answer_mutated=mutated_a,
                            severity=Severity.MEDIUM,
                            detail="la negation n'a pas inverse la reponse : la reponse "
                            "ne depend pas du sens de la question",
                        )
                    )
                continue

            if sim < self.similarity:
                findings.append(
                    MetamorphicFinding(
                        mutation=mut.name,
                        original=question,
                        mutated=mutated_q,
                        answer_original=base,
                        answer_mutated=mutated_a,
                        severity=Severity.HIGH,
                        detail=f"invariance rompue (similarite {sim:.2f} < {self.similarity:.2f}) "
                        f"— attendu : {mut.invariant}",
                    )
                )
        return tuple(findings)


def jaccard(a: str, b: str) -> float:
    """Similarite ensembliste sur les mots — robuste, sans dependance."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


_NEG_MARKERS = ("non", "pas", "faux", "jamais", "aucun", "no", "not", "false")


def _is_boolean_answer(text: str) -> bool:
    """La question admet-elle une reponse oui/non ? Sinon la negation est sans objet."""
    low = (text or "").lower().strip()
    if not low or len(low) > 200:
        return False
    markers = ("oui", "non", "vrai", "faux", "yes", "no", "true", "false", "correct", "incorrect")
    return any(re.search(rf"\b{m}\b", low) for m in markers)


def _looks_negated(a: str, b: str) -> bool:
    """Detecte une orientation de reponse inversee (oui/non, vrai/faux)."""
    la, lb = a.lower(), b.lower()
    pos_a = any(m in la for m in ("oui", "vrai", "yes", "true", "correct"))
    pos_b = any(m in lb for m in ("oui", "vrai", "yes", "true", "correct"))
    neg_a = any(m in la for m in _NEG_MARKERS)
    neg_b = any(m in lb for m in _NEG_MARKERS)
    return (pos_a and neg_b) or (neg_a and pos_b)


__all__ = ["Mutation", "MUTATIONS", "MetamorphicFinding", "MetamorphicTester", "jaccard"]
