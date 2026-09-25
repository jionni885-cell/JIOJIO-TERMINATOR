#!/bin/sh
# Resynchronise le depot local sur son distant, SANS JAMAIS perdre de travail.
#
# Pourquoi ce script existe
# -------------------------
# Incident reel, vecu par ce projet : entre deux sessions, `.git` a ete restaure a
# son etat INITIAL. Le code etait intact sur le disque, mais le depot ne suivait plus
# rien — `git status` affichait tout comme « non suivi », `git log` revenait au commit
# initial. Rien ne l'annoncait. Un `git commit` ulterieur aurait fabrique un
# historique absurde et perdu toute la tracabilite, qui est la promesse centrale de
# JIO.
#
# Regle de surete, dans cet ordre :
#   1. une copie de travail MODIFIEE n'est jamais touchee (on refuse et on explique);
#   2. un local en RETARD se met a jour en avance rapide (`--ff-only`) : aucun commit
#      local n'est perdu, c'est le seul cas ou l'operation est sure ;
#   3. des historiques DIVERGES ne sont jamais ecrases : on affiche la comparaison et
#      on s'arrete. `--force` existe, mais il doit etre demande explicitement.
#
# Usage : scripts/sync.sh [--force] [--remote NOM] [--branch NOM]

set -eu

FORCE=0
REMOTE=origin
BRANCH=""

while [ $# -gt 0 ]; do
    case "$1" in
        --force)  FORCE=1 ;;
        --remote) shift; REMOTE="${1:-origin}" ;;
        --branch) shift; BRANCH="${1:-}" ;;
        -h|--help)
            sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done

command -v git >/dev/null 2>&1 || { echo "git introuvable" >&2; exit 3; }

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "ce dossier n'est pas un depot git" >&2; exit 3
}
cd "$ROOT"

[ -n "$BRANCH" ] || BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "depot   : $ROOT"
echo "branche : $BRANCH"
echo

# --- 1. travail non valide : on ne touche a RIEN ---------------------------- #
if [ -n "$(git status --porcelain)" ]; then
    echo "REFUS : des modifications ne sont pas validees (commit ou remisage)."
    echo "        Ce script ne detruit JAMAIS du travail non enregistre."
    echo "        Apercu :"
    git status --short | sed 's/^/          /'
    echo
    echo "        Validation possible :  git add -A && git commit -m \"...\""
    echo "        Ou remisage sur :      git stash push -m \"avant sync\""
    exit 1
fi

# --- 2. recuperation -------------------------------------------------------- #
echo "=> recuperation depuis $REMOTE"
git fetch --prune "$REMOTE" "$BRANCH" || {
    # Certains depots distants n'autorisent pas la recuperation d'une branche
    # nommee : on retombe sur un fetch complet plutot que d'echouer.
    git fetch --prune "$REMOTE" || { echo "recuperation impossible" >&2; exit 3; }
}
LOCAL=$(git rev-parse HEAD)
DISTANT=$(git rev-parse FETCH_HEAD 2>/dev/null || echo "")

if [ -z "$DISTANT" ]; then
    echo "aucune reference distante pour '$BRANCH' : rien a synchroniser."
    exit 0
fi

if [ "$LOCAL" = "$DISTANT" ]; then
    echo "deja a jour ($(git rev-parse --short HEAD))."
    exit 0
fi

RETARD=$(git rev-list --count "$LOCAL".."$DISTANT" 2>/dev/null || echo 0)
AVANCE=$(git rev-list --count "$DISTANT".."$LOCAL" 2>/dev/null || echo 0)
echo "local  : $(git rev-parse --short "$LOCAL")"
echo "distant: $(git rev-parse --short "$DISTANT")  (+$RETARD / -$AVANCE)"
echo

if [ "$AVANCE" -eq 0 ]; then
    # --- 3. avance rapide : le seul cas ou rien ne peut etre perdu ---------- #
    echo "=> avance rapide de $RETARD commit(s) (aucun commit local en jeu)"
    git merge --ff-only "$DISTANT" || {
        echo "avance rapide impossible : rien n'a ete modifie." >&2
        exit 1
    }
    echo "a jour : $(git rev-parse --short HEAD)"
    exit 0
fi

# --- 4. historiques diverges ------------------------------------------------ #
echo "Les historiques ont DIVERGE : $AVANCE commit(s) locaux, $RETARD distants."
echo
echo "Commits locaux absents du distant :"
git log --oneline "$DISTANT".."$LOCAL" | sed 's/^/    /' | head -20
echo "Commits distants absents du local :"
git log --oneline "$LOCAL".."$DISTANT" | sed 's/^/    /' | head -20
echo

if [ "$FORCE" -eq 0 ]; then
    echo "REFUS : rien n'a ete modifie. Un ecrasement silencieux detruirait du travail."
    echo "        Pour garder les deux :  git merge $DISTANT   (ou git rebase $DISTANT)"
    echo "        Pour prendre le distant : scripts/sync.sh --force"
    exit 1
fi

# Le travail local reste joignable : on pose une etiquette avant d'ecraser, pour
# qu'aucun commit ne devienne introuvable, meme apres un --force.
TAG="sauvegarde-avant-sync-$(date +%Y%m%d-%H%M%S)"
git tag "$TAG" "$LOCAL"
echo "=> etiquette posee sur l'ancien etat : $TAG (aucun commit ne disparait)"
git reset --hard "$DISTANT"
echo "a jour : $(git rev-parse --short HEAD)"
echo
echo "Pour revenir en arriere :  git reset --hard $TAG"
