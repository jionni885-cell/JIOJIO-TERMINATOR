#!/usr/bin/env bash
# Installe le corpus public utilise par la mesure, DANS l'environnement courant.
#
# Pourquoi un script : la mesure (`scripts/mesure-code-public.sh`) n'installe RIEN et le dit.
# Mais l'environnement, lui, se perd (environnement virtuel recree, machine neuve), et la
# liste des paquets vivait... dans un historique de commandes. Un corpus qu'on ne peut pas
# reconstruire a l'identique ne mesure rien : il raconte.
#
#   bash scripts/corpus-public.sh            # installe les vingt paquets
#   bash scripts/corpus-public.sh rich httpx # installe seulement ceux-la
#
# Aucun paquet n'est epingle a une version : la mesure porte sur du code ecrit par d'autres,
# et une version figee mesurerait surtout l'age du depot. Le rapport dit quelle version a
# ete mesuree (chemin de `site-packages`).

set -u

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${JIO_PYTHON:-$RACINE/.venv/bin/python}"

#: Les vingt paquets de la mesure. `charset-normalizer` et `markdown-it-py` viennent en plus
#: comme dependances de `requests` et `rich` : sans elles, l'audit les declare « non
#: testables ici », ce qui est honnete mais moins instructif.
CORPUS=(
    click packaging pyparsing attrs jinja2 tqdm tabulate wcwidth idna
    more-itertools filelock platformdirs rich httpx urllib3 requests pygments
    tomlkit anyio sniffio charset-normalizer markdown-it-py
)

if [ "$#" -gt 0 ]; then
    CORPUS=("$@")
fi

if [ ! -x "$PYTHON" ]; then
    echo "python introuvable : $PYTHON" >&2
    echo "  -> creer l'environnement : python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

echo "installation dans : $PYTHON"
"$PYTHON" -m pip install --quiet "${CORPUS[@]}" || exit 1
echo "installe(s) : ${#CORPUS[@]} paquet(s)"
"$PYTHON" - <<'PYEOF'
import importlib.util
corpus = """click packaging pyparsing attrs jinja2 tqdm tabulate wcwidth idna
more-itertools filelock platformdirs rich httpx urllib3 requests pygments
tomlkit anyio sniffio""".split()
absents = [p for p in corpus if importlib.util.find_spec(p.replace("-", "_")) is None]
print("corpus verifiable :", len(corpus) - len(absents), "/", len(corpus))
if absents:
    print("absents :", ", ".join(absents))
PYEOF
echo
echo "mesure : bash scripts/mesure-code-public.sh"
