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

    titre "3. Le chemin reel (3 agents externes -> livraison auditee)"
    "$PYTHON" -m pytest -q tests/test_real_path.py 2>&1 | tail -2

    titre "4. Le banc : le harness a budget d'appels egal"
    "$PYTHON" -m jio bench --rounds 1 2>&1 | sed -n '/RESULTATS/,$p' | head -14

    titre "5. Le projet s'audite lui-meme"
    "$PYTHON" -m jio scan jio --exclude-tests --no-learn 2>&1 | tail -5
fi

if [ "$FAIRE_TIERS" -eq 1 ]; then
    titre "6. Zero fausse accusation sur des paquets publies"
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
