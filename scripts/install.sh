#!/usr/bin/env sh
# =========================================================================== #
# JIOJIO-TERMINATOR — installation des artefacts dans VOS outils.
#
# Ce script ne copie que des fichiers texte generes par `jio artifacts`.
# Il n'installe rien, ne telecharge rien, et ne modifie aucun paquet.
# Relisez-le avant de l'executer : c'est la regle que JIO applique lui-meme
# a tout contenu de depot, elle s'applique aussi a ce depot.
#
#   ./scripts/install.sh --dry-run     montrer ce qui serait fait (par defaut)
#   ./scripts/install.sh --hermes      installer les competences Hermes
#   ./scripts/install.sh --opencode    installer les agents opencode
#   ./scripts/install.sh --project DIR installer les fichiers de contexte
#   ./scripts/install.sh --all --yes   tout installer
# =========================================================================== #
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
INVOKE_DIR=$(pwd)
DRY=1
DO_HERMES=0
DO_OPENCODE=0
DO_PROJECT=0
PROJECT_DIR=""
BIN="${PYTHON:-python3}"

# Un interpreteur donne en chemin RELATIF ne se resout plus apres un `cd` :
# on le fige en absolu avant tout deplacement. (Erreur constatee a l'execution.)
case "$BIN" in
  /*) : ;;
  */*) BIN="$INVOKE_DIR/$BIN" ;;
esac
if [ ! -x "$BIN" ]; then
  if command -v "$BIN" >/dev/null 2>&1; then :; else
    echo "interpreteur introuvable : $BIN" >&2
    echo "essayez : PYTHON=python3 ./scripts/install.sh" >&2
    exit 2
  fi
fi

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --yes) DRY=0 ;;
    --hermes) DO_HERMES=1 ;;
    --opencode) DO_OPENCODE=1 ;;
    --project) DO_PROJECT=1 ;;
    --all) DO_HERMES=1; DO_OPENCODE=1; DO_PROJECT=1 ;;
    --help|-h) usage ;;
    -*) echo "option inconnue : $arg" >&2; exit 2 ;;
    *) if [ "$DO_PROJECT" = "1" ] && [ -z "$PROJECT_DIR" ]; then PROJECT_DIR="$arg"; fi ;;
  esac
done

if [ "$DO_HERMES" = "0" ] && [ "$DO_OPENCODE" = "0" ] && [ "$DO_PROJECT" = "0" ]; then
  DO_HERMES=1; DO_OPENCODE=1
fi

say() { printf '  %s\n' "$1"; }
run() {
  if [ "$DRY" = "1" ]; then say "[simulation] $*"; else "$@"; fi
}

# --- 0. Generer les artefacts (source unique -> tous les dialectes) --------- #
say "generation des artefacts depuis jio/artifacts/doctrine.py"
(cd "$HERE" && "$BIN" -m jio artifacts --write >/dev/null)

# --- 1. Hermes : competences au format agentskills.io ----------------------- #
if [ "$DO_HERMES" = "1" ]; then
  DEST="${HERMES_HOME:-$HOME/.hermes}/skills"
  say "Hermes -> $DEST"
  run mkdir -p "$DEST"
  for skill in "$HERE"/.hermes/skills/*/*/; do
    [ -d "$skill" ] || continue
    name=$(basename "$skill")
    run cp -R "$skill" "$DEST/$name"
  done
  say "pour verifier : hermes chat -q \"quelles competences sont disponibles ?\""

  # --- 1 bis. Le serveur MCP pour Hermes ---------------------------------- #
  # Hermes lit `~/.hermes/config.yaml`, qui appartient a l'utilisateur : on ne l'ecrit
  # pas. On livre le bloc pret a coller, dans un fichier nomme pour ce qu'il est.
  say "serveur MCP -> fragment a fusionner dans $DEST/../config.yaml"
  say "  (cle mcp_servers ; le fragment est dans .hermes/mcp-fragment.yaml)"
fi

# --- 2. opencode : agents markdown ----------------------------------------- #
if [ "$DO_OPENCODE" = "1" ]; then
  DEST="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/agent"
  say "opencode (global) -> $DEST"
  run mkdir -p "$DEST"
  for agent in "$HERE"/.opencode/agents/*.md; do
    [ -f "$agent" ] || continue
    case "$(basename "$agent")" in README.md) continue ;; esac
    run cp "$agent" "$DEST/"
  done
  say "les agents jio* deviennent disponibles dans opencode"

  # --- 2 bis. Cabler le SERVEUR MCP dans opencode ------------------------- #
  # Les agents ci-dessus n'avaient aucun moyen d'appeler les outils de JIO : `.mcp.json`
  # est le dialecte de Claude Code, opencode lit `opencode.json`. Le serveur etait ecrit,
  # teste, et injoignable. Le cablage ecrit le fichier S'IL N'EXISTE PAS, et affiche le
  # fragment sinon : la configuration de l'utilisateur n'est jamais modifiee.
  CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
  say "serveur MCP -> $CONF_DIR/opencode.json (cree seulement s'il est absent)"
  if [ "$DRY" = "1" ]; then
    say "[simulation] $BIN -m jio artifacts --mcp opencode --root $CONF_DIR"
  else
    run "$BIN" -m jio artifacts --mcp opencode --root "$CONF_DIR"
  fi
fi

# --- 3. Repertoire de projet : fichiers de contexte ------------------------- #
if [ "$DO_PROJECT" = "1" ]; then
  [ -n "$PROJECT_DIR" ] || { echo "--project exige un repertoire" >&2; exit 2; }
  [ -d "$PROJECT_DIR" ] || { echo "repertoire introuvable : $PROJECT_DIR" >&2; exit 2; }
  say "fichiers de contexte -> $PROJECT_DIR"
  for f in AGENTS.md CLAUDE.md GEMINI.md .mcp.json; do
    if [ -e "$PROJECT_DIR/$f" ]; then
      say "ATTENTION : $f existe deja — non ecrase (fusionnez a la main)"
      continue
    fi
    run cp "$HERE/$f" "$PROJECT_DIR/$f"
  done
  run mkdir -p "$PROJECT_DIR/.cursor/rules" "$PROJECT_DIR/.github"
  run cp "$HERE/.cursor/rules/jio.mdc" "$PROJECT_DIR/.cursor/rules/jio.mdc"
  run cp "$HERE/.github/copilot-instructions.md" "$PROJECT_DIR/.github/copilot-instructions.md"
fi

echo
if [ "$DRY" = "1" ]; then
  say "mode simulation : RIEN n'a ete ecrit. Relancez avec --yes pour executer."
else
  say "termine. Verifiez avec : python3 -m jio doctor"
fi
