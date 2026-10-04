#!/usr/bin/env bash
# Mesure de `jio scan` sur du code public.
#
# Pourquoi cette mesure existe
# ----------------------------
# Le README annoncait un chiffre MANQUANT : « de nouvelles regles dans `jio scan` sans mesure
# sur le corpus de paquets publics — qui est ce qui decide si une regle accuse a tort ». Une
# regle qui n'accuse jamais est inutile ; une regle qui accuse a tort detruit la confiance
# dans tout le rapport, y compris ses vraies trouvailles. Le seul juge est du code ecrit par
# d'autres, sur lequel on n'a aucun interet a mentir.
#
# Ce que le script fait
# ---------------------
#   * verifie que les paquets sont deja installes (il n'installe RIEN : pas de reseau) ;
#   * lance `jio scan <paquet> --no-learn` sur chacun ;
#   * affiche, par paquet, le nombre de problemes et le code de sortie ;
#   * recompte les problemes par REGLE, pour voir d'ou ils viennent.
#
# Usage
# -----
#     scripts/mesure-code-public.sh              # la liste par defaut
#     scripts/mesure-code-public.sh rich click   # d'autres paquets installes
#
# Sortie : un tableau, plus un total. Un paquet peut legitimement avoir des problemes — c'est
# meme l'interet : `pyparsing` en a un, verifie a la main, et il est VRAI.
set -uo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${JIO_PYTHON:-$RACINE/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

PAQUETS=("$@")
if [ "${#PAQUETS[@]}" -eq 0 ]; then
    PAQUETS=(click packaging pyparsing attrs)
fi

SITE="$("$PYTHON" - <<'PY'
import sysconfig
print(sysconfig.get_paths()["purelib"])
PY
)"

echo
echo "  MESURE  ·  jio scan sur du code public (aucun reseau, aucun paquet installe ici)"
echo

TOTAL_PROBLEMES=0
MESURES=()
for paquet in "${PAQUETS[@]}"; do
    dossier="$SITE/$paquet"
    if [ ! -d "$dossier" ]; then
        echo "    $paquet : ABSENT de cet environnement (rien n'est installe par ce script)"
        continue
    fi
    sortie="$(cd "$RACINE" && "$PYTHON" -m jio scan "$dossier" --no-learn 2>&1)"
    code=$?
    problemes="$(printf '%s\n' "$sortie" | grep -cE '^        \[' || true)"
    fichiers="$(printf '%s\n' "$sortie" | grep -cE '\.py$' || true)"
    TOTAL_PROBLEMES=$((TOTAL_PROBLEMES + problemes))
    MESURES+=("$(printf '%-12s %3s probleme(s)  code %s' "$paquet" "$problemes" "$code")")
    echo "    $(printf '%-12s' "$paquet") $problemes probleme(s)  ·  code de sortie $code"
    if [ "$problemes" -gt 0 ]; then
        printf '%s\n' "$sortie" | grep -E '^        \[' | sed 's/^/        /' | head -4
    fi
done

echo
echo "    total : $TOTAL_PROBLEMES probleme(s) sur ${#MESURES[@]} paquet(s) mesure(s)"
echo "    Lecture : un probleme n'est ni un succes ni un echec du script. Chacun doit etre"
echo "    INSTRUIT a la main — c'est ainsi qu'ont ete trouves et corriges les faux positifs"
echo "    des huit familles deja rencontrees : fixture pytest, classe a fabriques, traceback,"
echo "    sortie liee a l'import, exemple abrege par \`...\`, import etoile, nom venant d'une"
echo "    etoile chez le voisin, module local masquant un paquet externe."
echo "    Et c'est ainsi qu'a ete trouve un VRAI defaut : \`import tqdm._utils\` echoue."
echo
