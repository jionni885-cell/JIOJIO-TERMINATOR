#!/usr/bin/env bash
# Mesure le harness face a un modele REEL, entraine ici, dont les erreurs n'ont pas ete
# modelisees par nous.
#
# Pourquoi ca change quelque chose : chaque rapport de ce depot portait la meme reserve —
# « le modele est SIMULE ». Une simulation dont on a choisi le taux d'erreur ne peut pas
# repondre a la question qui compte : le harness tient-il quand le modele qui repond n'est
# pas le notre ? Ici les poids sont reels, le calcul est reel, et les erreurs — personne ne
# les a choisies.
#
# Usage :  scripts/modele-local/mesurer.sh [taches] [runs] [port]
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$RACINE/.venv/bin/python"
TACHES="${1:-5}"
RUNS="${2:-3}"
PORT="${3:-8099}"

# JIO_MODELE permet de mesurer un AUTRE modele sans toucher au script : c'est ce qui rend
# deux modeles comparables (v1 contre v2), et une comparaison sans le modele nomme ne vaut rien.
MODELE="${JIO_MODELE:-$RACINE/modele/modele.pt}"
if [ ! -f "$MODELE" ]; then
  echo "modele absent : $MODELE"
  echo "entrainez-le d'abord :"
  echo "  cd $RACINE/scripts/modele-local && python entrainer.py --sortie ../../modele/modele.pt"
  exit 2
fi

echo "  empreinte du modele : $(sha256sum "$MODELE" | cut -c1-16)"
echo "  taches $TACHES  ·  $RUNS tirage(s) par tache  ·  port $PORT"

SERVEUR_LOG="$RACINE/evidence/modele-local-serveur.log"
"$PYTHON" "$RACINE/scripts/modele-local/serveur.py" --modele "$MODELE" --port "$PORT" \
  > "$SERVEUR_LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT

# On attend que le port reponde AVANT de mesurer : un banc qui part trop tot mesurerait
# l'absence de serveur au lieu du modele.
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/statut" > /dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -sf "http://127.0.0.1:$PORT/statut" > /dev/null 2>&1; then
  echo "le serveur n'a pas demarre :"; tail -20 "$SERVEUR_LOG"; exit 1
fi

export JIO_OLLAMA="http://127.0.0.1:$PORT"
export JIO_OPENAI_KEY="${JIO_OPENAI_KEY:-local-sans-cle}"

echo
echo "  ================ MODELE REEL : avec oracle (les regles sont deja des temoins) ================"
"$PYTHON" -m jio bench --provider openai:modele-local-char \
  --taches "$TACHES" --runs "$RUNS" --sans-oracle-reel \
  --rapport "$RACINE/evidence/bench-modele-local-oracle.md" || true

echo
echo "  ================ MODELE REEL : SANS oracle (le cas de toute mission reelle) ================"
"$PYTHON" -m jio bench --provider openai:modele-local-char \
  --taches "$TACHES" --runs "$RUNS" \
  --rapport "$RACINE/evidence/bench-modele-local-sans-oracle.md" || true

echo
echo "  rapports : evidence/bench-modele-local-*.md"
echo "  etat du modele a l'instant de la mesure :"
curl -s "http://127.0.0.1:$PORT/statut" || true
echo
