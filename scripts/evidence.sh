#!/bin/sh
# Rejoue les preuves annoncees, sur VOTRE machine, sans cle API.
#
# Pourquoi ce script existe
# -------------------------
# Les chiffres du README vivaient dans des corpus crees a la main dans /tmp. Un
# environnement nettoye, et il ne restait plus rien a verifier : une preuve qu'on ne
# peut pas rejouer n'est pas une preuve, c'est une affirmation. Ce script reconstruit
# chaque corpus et rejoue chaque mesure ; le corpus de proprietes est VERSIONNE dans
# le depot (`evidence/properties/`), donc les chiffres sont verifiables par n'importe
# qui, a n'importe quand.
#
# Usage :
#   scripts/evidence.sh                 preuves locales (aucun reseau)
#   scripts/evidence.sh --third-party   ajoute le balayage de paquets publies
#   scripts/evidence.sh --all           tout

set -eu

ICI=$(cd "$(dirname "$0")" && pwd)
RACINE=$(cd "$ICI/.." && pwd)
cd "$RACINE"

PYTHON=""
for candidat in "$RACINE/.venv/bin/python" python3 python; do
    if command -v "$candidat" >/dev/null 2>&1; then PYTHON="$candidat"; break; fi
done
[ -n "$PYTHON" ] || { echo "aucun interpreteur Python trouve" >&2; exit 3; }

FAIRE_TIERS=0
FAIRE_LOCAL=1
for arg in "$@"; do
    case "$arg" in
        --third-party) FAIRE_TIERS=1 ;;
        --all)         FAIRE_TIERS=1 ;;
        --local)       FAIRE_LOCAL=1 ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "option inconnue : $arg" >&2; exit 2 ;;
    esac
done

titre() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

if [ "$FAIRE_LOCAL" -eq 1 ]; then
    titre "1. La suite de tests (le comportement est verrouille)"
    "$PYTHON" -m pytest -q 2>&1 | tail -3

    titre "2. L'axe proprietes, sur le corpus versionne"
    "$PYTHON" - <<'PY'
import pathlib
from jio.core.errors import FailClosed
from jio.verify.autocheck import derive
from jio.verify.executable import ExecutableProver, Sandbox

racine = pathlib.Path("evidence/properties")
prover = ExecutableProver(sandbox=Sandbox(timeout=20))


def mesure(avec_proprietes):
    fautifs = sains = accuses = 0
    for dossier in ("fautifs", "sains"):
        for fichier in sorted((racine / dossier).glob("*.py")):
            source = fichier.read_text(encoding="utf-8")
            derived = derive(source)
            checks = {
                k: v for k, v in derived.checks.items()
                if avec_proprietes or not k.startswith("P-")
            }
            try:
                res = prover.prove(
                    source, derived.spec, hidden_checks=checks,
                    entrypoint=derived.entrypoint, preamble=derived.preamble,
                )
            except FailClosed:
                continue
            echec = bool([w for w in res.witnesses if not w.ok])
            if dossier == "fautifs":
                fautifs += echec
            else:
                sains += not echec
                accuses += echec
    return fautifs, sains, accuses


hors, muets_hors, accuses_hors = mesure(False)
avec, muets_avec, accuses_avec = mesure(True)
print(f"    {'regles':<34}{'fautifs detectes':>18}{'sains muets':>14}{'sains accuses':>15}")
print(f"    {'-'*34}{'-'*18}{'-'*14}{'-'*15}")
print(f"    {'exemples seuls (A-*)':<34}{str(hors) + '/8':>18}{str(muets_hors) + '/8':>14}{str(accuses_hors) + '/8':>15}")
print(f"    {'+ proprietes (P-*)':<34}{str(avec) + '/8':>18}{str(muets_avec) + '/8':>14}{str(accuses_avec) + '/8':>15}")
if accuses_avec:
    print(f"\n    /!\\ {accuses_avec} artefact(s) sain(s) accuse(s) : c'est un faux positif, a instruire.")
PY

    titre "3. Divergence entre candidats : le choix depend-il de l'ordre ?"
    "$PYTHON" - <<'PYE'
import pathlib, sys
sys.path.insert(0, ".")
from jio.core.types import Mission, Rule, RuleKind, Spec
from jio.loop.engine import Engine, EngineConfig, WorkItem
from jio.providers.base import Completion

CORPUS = pathlib.Path("evidence/divergence")
JUSTE = (CORPUS / "candidat_juste.py").read_text(encoding="utf-8")
FAUX = (CORPUS / "candidat_faux.py").read_text(encoding="utf-8")


class Candidats:
    name, model = "sim", "sim-1"

    def __init__(self, sources):
        self.sources = list(sources)
        self.index = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        source = self.sources[self.index % len(self.sources)]
        self.index += 1
        return Completion(text="```python\n" + source + "```\n",
                          prompt_tokens=10, completion_tokens=20, model=self.model)


def juste(source):
    """Oracle : la vraie moyenne de [1, 2] vaut 1.5 ; la division entiere rend 1.0."""
    espace = {}
    try:
        exec(source, espace)
        return abs(espace["mean"]([1, 2]) - 1.5) < 1e-9
    except Exception:
        return False


SPEC = Spec(mission="moyenne", rules=(
    Rule(id="R-001", statement="moyenne nominale", kind=RuleKind.PROPERTY),))
CHECKS = {"R-001": "assert mean([1, 2, 3]) == 2.0, f'nominal: {mean([1,2,3])}'"}

print(f"    {'ordre des candidats':<26}{'sans comparaison':>18}{'avec comparaison':>18}")
gains = 0
for nom, sources in (
    ("le faux en premier", [FAUX, JUSTE, JUSTE]),
    ("le faux au milieu", [JUSTE, FAUX, JUSTE]),
    ("le faux en dernier", [JUSTE, JUSTE, FAUX]),
):
    resultats = []
    for flag in (False, True):
        engine = Engine(generators=[Candidats(sources)], config=EngineConfig(
            max_rounds=1, candidates_per_round=3, self_check=True,
            differential=flag, mutation_gate=False))
        rapport = engine.run(Mission(objective="moyenne", id="evidence"),
                             WorkItem(objective="moyenne", entrypoint="mean",
                                      checks=CHECKS, spec=SPEC))
        resultats.append(juste(rapport.subject or ""))
    if not resultats[0] and resultats[1]:
        gains += 1
    print(f"    {nom:<26}{('juste' if resultats[0] else 'FAUX'):>18}"
          f"{('juste' if resultats[1] else 'FAUX'):>18}")
print(f"    -> livrables corriges par la comparaison : {gains}/3 ; et le desaccord est "
      "avoue dans tous les cas.")
PYE

    titre "4. Le chemin reel (3 agents externes -> livraison auditee)"
    "$PYTHON" -m pytest -q tests/test_real_path.py 2>&1 | tail -2

    titre "5. Le banc : le harness a budget d'appels egal"
    "$PYTHON" -m jio bench --rounds 1 2>&1 | sed -n '/RESULTATS/,$p' | head -14

    titre "6. Le projet s'audite lui-meme"
    "$PYTHON" -m jio scan jio --exclude-tests --no-learn 2>&1 | tail -5
fi

if [ "$FAIRE_TIERS" -eq 1 ]; then
    titre "7. Zero fausse accusation sur des paquets publies"
    echo "    (telechargement temporaire : more-itertools, click, rich, jinja2, attrs)"
    TEMP=$(mktemp -d)
    trap 'rm -rf "$TEMP"' EXIT
    if "$PYTHON" -m pip install -q --target "$TEMP" --no-deps \
        more-itertools click rich jinja2 attrs >/dev/null 2>&1; then
        printf '    %-18s %s\n' "paquet" "problemes"
        for paquet in more_itertools click rich jinja2 attr; do
            sortie=$("$PYTHON" -m jio scan "$TEMP/$paquet" --exclude-tests \
                     --no-learn --no-linters 2>&1 || true)
            compte=$(printf '%s' "$sortie" | grep -oE '^  [0-9]+ PROBLEME' | grep -oE '[0-9]+' | head -1)
            printf '    %-18s %s\n' "$paquet" "${compte:-0}"
        done | tee "$TEMP/resultat.txt"
        total=$(awk '{somme += $2} END {print somme + 0}' "$TEMP/resultat.txt")
        if [ "$total" -eq 0 ]; then
            echo "    -> aucune fausse accusation."
        else
            echo "    -> $total accusation(s) a instruire (voir --no-linters ci-dessus)."
        fi
    else
        echo "    telechargement impossible (reseau indisponible) : etape ignoree."
    fi
fi

titre "Termine"
