#!/bin/bash
# Campagne de preuve du cumul APPARIE — ecrite dans le DEPOT, jamais dans /tmp.
#
# Pourquoi ce fichier existe, et pourquoi il est ici.
#
# Trois campagnes ont ete perdues avant celle-ci : deux par un `kill` de nettoyage, une par un
# redemarrage du bac a sable qui a efface `/tmp` EN ENTIER — le pilote, le cumul deja mesure et
# les sorties. Le depot sait deja ecrire un cycle DES qu'il est mesure (c'est un de ses trois
# garde-fous du cumul) ; ce qui manquait n'etait pas la robustesse du programme, c'etait
# l'EMPLACEMENT de la preuve. Une preuve rangee dans un repertoire temporaire ne survit pas au
# redemarrage : elle n'est donc pas une preuve.
#
# Le script vit dans `scripts/`, le cumul et le rapport vivent dans `evidence/`. Les deux
# persistent avec le depot, et le rapport final peut etre cite tel quel.
#
# Usage :  bash scripts/preuve-cumul.sh          (environ 20 minutes)
set -u
cd "$(dirname "$0")/.." || exit 1

SORTIE=evidence/preuve-cumul.txt
CUMUL=evidence/preuve-cumul.jsonl
rm -f "$SORTIE" "$CUMUL" "$CUMUL.verrou"

# Trois blocs de graines distincts, deux cycles chacun : c'est ce qui separe « l'effet existe »
# de « ce tirage-la a eu de la chance ». Chaque bloc est une execution INDEPENDANTE, et le cumul
# refuse d'en melanger deux si le regime (competence, tours, gain) change.
for i in 1 2 3; do
  echo "=== BLOC $i ===" >> "$SORTIE"
  .venv/bin/python -m jio learn --cycles 2 --runs 8 --rounds 2 --skill 0.4 \
      --plafond-missions 2000 --cumul "$CUMUL" >> "$SORTIE" 2>&1
  echo "=== FIN BLOC $i (code $?) ===" >> "$SORTIE"
done
echo "=== CAMPAGNE TERMINEE ===" >> "$SORTIE"
