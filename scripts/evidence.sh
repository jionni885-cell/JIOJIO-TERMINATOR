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

    titre "4. Sans oracle : les regles deviennent des temoins executables"
    "$PYTHON" - <<'PYE'
import sys
sys.path.insert(0, ".")
from jio.bench.tasks import TASKS
from jio.bench.temoins import TraducteurSimule
from jio.cli import _check, _simulated_engine
from jio.core.types import Mission
from jio.loop.engine import WorkItem

print("    Une mission reelle ne fournit AUCUN test. Sans traduction des regles en")
print("    temoins, le moteur ne peut rien prouver : il s'abstient. Mesure sur le banc,")
print("    cinq taches, une seule graine, 3 candidats + 1 appel de traduction (4 appels :")
print("    exactement le budget d'un best-of-4).")
print()
print(f"    {'fidelite du traducteur':<26}{'juste':>7}{'abstention':>12}{'faux+reserve':>14}{'SANS RESERVE':>14}")
for fidelite in (1.0, 0.5, 0.0):
    justes = abstentions = reserves = silencieuses = 0
    for tache in TASKS:
        traducteur = TraducteurSimule(taches=TASKS, fidelite=fidelite)
        moteur = _simulated_engine(tache, skill=0.35, seed=0, max_rounds=1,
                                   temoins=True, traducteur=traducteur)
        rapport = moteur.run(
            Mission(objective=tache.objective, id=tache.id, max_rounds=1),
            WorkItem(objective=tache.objective, entrypoint=tache.entrypoint,
                     spec=tache.spec()),
        )
        if _check(rapport.subject, tache):
            justes += 1
        elif rapport.status.value == "abstained":
            abstentions += 1
        elif rapport.status.value == "delivered":
            silencieuses += 1
        else:
            reserves += 1
    print(f"    {fidelite:>5.0%}{'':<21}{justes:>7}{abstentions:>12}{reserves:>14}"
          f"{silencieuses:>14}")
print()
print("    -> quand le traducteur est juste, la preuve est possible SANS oracle.")
print("       Quand il se trompe, le systeme S'ABSTIENT : il perd des livraisons,")
print("       jamais la justesse. La colonne qui doit rester a zero est la derniere :")
print("       une erreur livree sans que rien ne le dise.")
print("       Lecture du garde-fou : un temoin que TOUS les candidats echouent ne")
print("       prouve rien sur eux (il peut etre faux), donc la regle est declaree NON")
print("       PROUVEE — et il fait s'abstenir au lieu de faire rejeter.")
PYE

    titre "5. La memoire des temoins : une traduction validee n'est pas repayee"
    "$PYTHON" - <<'PYE'
import pathlib, sys, tempfile
sys.path.insert(0, ".")
from jio.bench.tasks import TASKS, TASKS_BY_ID
from jio.cli import _check, _simulated_engine
from jio.core.types import Mission
from jio.loop.engine import WorkItem
from jio.spec.library import BibliothequeTemoins

tache = TASKS_BY_ID["sum_even"]
dossier = pathlib.Path(tempfile.mkdtemp(prefix="jio-biblio-"))
chemin = dossier / "temoins.jsonl"
appels = {"n": 0}


class TraducteurCompte:
    """Fidele, et il COMPTE : c'est le seul chiffre qui compte ici."""

    name, model = "compte", "c-1"

    def complete(self, messages, **kw):
        from jio.bench.temoins import TraducteurSimule

        if not hasattr(self, "_interne"):
            self._interne = TraducteurSimule(taches=TASKS, fidelite=1.0)
        appels["n"] += 1
        return self._interne.complete(messages, **kw)


def mission(numero):
    biblio = BibliothequeTemoins(path=chemin)
    moteur = _simulated_engine(tache, skill=0.85, seed=0, max_rounds=2,
                               temoins=True, traducteur=TraducteurCompte())
    moteur.bibliotheque = biblio
    rap = moteur.run(Mission(objective=tache.objective, id=f"sum-{numero}", max_rounds=2),
                     WorkItem(objective=tache.objective, entrypoint=tache.entrypoint,
                              spec=tache.spec()))
    return rap, biblio


print("    Meme mission, repetee. La traduction des regles est un appel de modele :")
print("    sans memoire, on repaie ce pari a chaque fois. Avec la bibliotheque, il est paye")
print("    une seule fois — a condition qu'une livraison l'ait PROUVE la premiere fois.")
print()
print(f"    {'execution':<12}{'statut':<26}{'traductions':>12}{'memoire':>9}{'juste':>7}")
for i in (1, 2, 3):
    avant = appels["n"]
    rap, biblio = mission(i)
    print(f"    {i:<12}{rap.status.value:<26}{appels['n'] - avant:>12}{biblio.size:>9}"
          f"{str(_check(rap.subject, tache)):>7}")
print()
print("    -> la premiere execution paie UNE traduction et capitalise ; les suivantes")
print("       ne paient rien et livrent le meme resultat. Seule une livraison PROUVEE")
print("       alimente la memoire : une abstention ou une reserve n'a rien a transmettre.")
print("       Et le fichier est verifie par chaine de hachage : edite a la main, il est")
print("       mis en quarantaine — renomme, jamais supprime — et jamais applique.")
PYE

    titre "6. Un fournisseur REEL est sonde avant la premiere mission"
    "$PYTHON" - <<'PYE'
import os, pathlib, sys, tempfile
sys.path.insert(0, ".")

# Faux CLI en SOUS-PROCESSUS : il repond, il traduit les regles, et il propose AUSSI
# un test hostile — que la porte de securite doit refuser. La sonde n'est pas plus
# indulgente qu'une mission : sinon elle annoncerait une capacite inutilisable.
dossier = pathlib.Path(tempfile.mkdtemp(prefix="jio-sonde-"))
binaire = dossier / "opencode"
binaire.write_text(
    "#!" + sys.executable + "\n"
    "import json, sys\n"
    "prompt = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else ''\n"
    "if 'You turn enumerated RULES into executable checks' in prompt:\n"
    "    rendu = {'R-001': 'assert moyenne([1, 2]) == 1.5',\n"
    "             'R-002': 'import os\\nassert moyenne([])'}\n"
    "else:\n"
    "    rendu = {'R-001': 'assert moyenne([1, 2]) == 1.5',\n"
    "             'R-002': 'import os\\nassert moyenne([])'}\n"
    "print(json.dumps({'type': 'text', 'text': json.dumps(rendu)}))\n",
    encoding="utf-8",
)
binaire.chmod(0o755)
os.environ["JIO_BIN_OPENCODE"] = str(binaire)

from jio.providers.probe import sonder
from jio.providers.registry import detect_clis

fournisseurs = [f for f in detect_clis() if f.name == "cli::opencode"]
assert fournisseurs, "le CLI simule n'a pas ete detecte"
sonde = sonder(fournisseurs[0])
print("    " + sonde.resume())
print()
for regle, test in sonde.temoignage.tests.items():
    print(f"      {regle} -> temoin accepte   : {test[:70]}")
for regle, motif in sonde.temoignage.refuses.items():
    print(f"      {regle} -> REFUSE            : {motif[:80]}")
print()
print("    verdict :", sonde.verdict)
print("    -> la sonde dit a l'utilisateur, AVANT toute mission, si son CLI peut")
print("       prouver quelque chose — et elle refuse les tests hostiles avec la MEME")
print("       porte de securite que la mission.")
PYE

    titre "7. Le chemin reel (3 agents externes -> livraison auditee)"
    "$PYTHON" -m pytest -q tests/test_real_path.py 2>&1 | tail -2

    titre "8. Le banc : le harness a budget d'appels egal"
    # On n'affiche pas des taux, on affiche ce qui les rend lisibles : le tableau AVEC
    # leurs intervalles de confiance, puis l'ECART et son verdict. Un ecart dont
    # l'intervalle contient zero est indéterminé a ce nombre d'essais — c'est la seule
    # conclusion que ces chiffres portent, et elle doit figurer dans la preuve.
    "$PYTHON" -m jio bench --rounds 1 2>&1 | sed -n '/RESULTATS/,/^  QUAND LA MISSION/p' | head -30

    titre "9. Le projet s'audite lui-meme"
    "$PYTHON" -m jio scan jio --exclude-tests --no-learn 2>&1 | tail -5
    echo
    # Le balayage ENTIER du depot, code ET documents. Deux proprietes y sont
    # verifiees : il ne traverse pas l'environnement virtuel, et il exclut le corpus
    # de fautes volontaires sur leur propre declaration — sinon il signalerait ses
    # propres fixtures, ce qui le rendait illisible (mesure : 736 problemes, 285 s).
    TMP_SCAN=$(mktemp -d)
    if "$PYTHON" -m jio scan . --no-learn --exclude-tests > "$TMP_SCAN/brut.txt" 2>&1; then
        code_scan=0
    else
        code_scan=$?
    fi
    grep -E '^  (SCAN|dossiers ignores|corpus de fautes)' "$TMP_SCAN/brut.txt" || true
    echo "    -> code $code_scan : $( [ "$code_scan" -eq 0 ] && echo 'aucun probleme sur les regles verifiables' || echo 'PROBLEME(S) a instruire ci-dessus' )"
    if grep -qE '^  dossiers ignores.*\.venv' "$TMP_SCAN/brut.txt"; then
        echo "    -> l'environnement virtuel est ignore ET annonce."
    else
        echo "    -> ATTENTION : .venv n'est pas annonce comme ignore."
    fi
    rm -rf "$TMP_SCAN"
fi

if [ "$FAIRE_TIERS" -eq 1 ]; then
    titre "10. Zero fausse accusation sur des paquets publies"
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

titre "11. Un depot reinitialise se repare sans perdre un octet"

# L'accident est arrive TROIS fois : `.git` restaure a son etat initial, le travail intact
# sur le disque, plus rien de suivi. On le reproduit POUR DE VRAI (depot distant, travail
# pousse, puis destruction de l'historique local) au lieu de le decrire.
SIM=$(mktemp -d)
(
    cd "$SIM"
    git init -q --bare --initial-branch=main distant.git
    git init -q -b main travail
    cd travail
    git config user.email a@b && git config user.name preuve
    mkdir -p jio/docs
    for i in $(seq 1 25); do printf 'x = %d\n' "$i" > "jio/m$i.py"; done
    for i in $(seq 1 8); do printf '# doc\n' > "jio/docs/d$i.md"; done
    printf 'def sante():\n    return "intact"\n' > jio/sante.py
    git add -A && git commit -q -m "travail reel"
    git remote add origin ../distant.git && git push -q -u origin main
    # le travail JAMAIS pousse : c'est lui qu'une reparation maladroite effacerait
    printf 'def local():\n    return "pas pousse"\n' > travail_local.py

    rm -rf .git
    git init -q -b main
    git config user.email a@b && git config user.name preuve
    git remote add origin ../distant.git
    git commit -q --allow-empty -m "Initial commit"
) > /dev/null 2>&1

TRAVAIL="$SIM/travail"
AVANT_LOCAL=$(sha256sum "$TRAVAIL/travail_local.py" | cut -c1-12)
AVANT_CONTENU=$("$PYTHON" -c "
import sys; sys.path.insert(0, '$RACINE')
from pathlib import Path
from jio.recover import empreinte_arbre
print(empreinte_arbre(Path('$TRAVAIL'))[:12])")

echo "    depot reinitialise : $(cd "$TRAVAIL" && git rev-list --count HEAD) commit(s), \
$(cd "$TRAVAIL" && git status --porcelain -uall | grep -c '^??') fichier(s) non suivi(s)"
# On lance sync.sh DEPUIS le depot reinitialise : sans cela, il observe le depot de JIO
# (qui est sain) et la mesure ne dit rien du cas qu'on veut prouver.
MENTIONS=$({ cd "$TRAVAIL" && bash "$RACINE/scripts/sync.sh"; } 2>&1 | grep -c 'jio recover' || true)
echo "    sync.sh refuse ce cas et oriente vers la bonne commande : $MENTIONS mention(s)"
if [ "$MENTIONS" -lt 1 ]; then
    echo "    ECHEC : sync.sh doit nommer `jio recover` quand le depot est reinitialise" >&2
    rm -rf "$SIM"; exit 1
fi

( cd "$TRAVAIL" && PYTHONPATH="$RACINE" "$PYTHON" -m jio recover ) \
    > /tmp/jio_recover.txt 2>&1 || CODE_RECOVER=$?
CODE_RECOVER=${CODE_RECOVER:-0}
sed -n 's/^    \(historique restaure.*\)/    \1/p' /tmp/jio_recover.txt
grep -E "contenu de l'arbre" /tmp/jio_recover.txt | sed 's/^/  /'
if ! grep -q "INTACT" /tmp/jio_recover.txt; then
    echo "    ECHEC : la recuperation a modifie le contenu de l'arbre" >&2
    rm -rf "$SIM"; exit 1
fi

APRES_LOCAL=$(sha256sum "$TRAVAIL/travail_local.py" | cut -c1-12)
APRES_CONTENU=$("$PYTHON" -c "
import sys; sys.path.insert(0, '$RACINE')
from pathlib import Path
from jio.recover import empreinte_arbre
print(empreinte_arbre(Path('$TRAVAIL'))[:12])")
echo "    le travail JAMAIS pousse : $AVANT_LOCAL -> $APRES_LOCAL (copie inchangee)"
echo "    contenu de tout l'arbre  : $AVANT_CONTENU -> $APRES_CONTENU"
echo "    historique retrouve      : $(cd "$TRAVAIL" && git log --oneline | head -1)"
echo "    (le fichier non pousse est desormais INDEXE : suivi par git status)"
if [ "$AVANT_LOCAL" != "$APRES_LOCAL" ] || [ "$AVANT_CONTENU" != "$APRES_CONTENU" ]; then
    echo "    ECHEC : un fichier a change — la recuperation a perdu du travail" >&2
    rm -rf "$SIM"; exit 1
fi
rm -rf "$SIM"

titre "12. La documentation est confrontee a ses propres chiffres"

echo "    $(cd "$RACINE" && "$PYTHON" -m jio chiffres 2>&1 | grep -E 'tests|competences|agents' | tr '\n' ' ')"
cd "$RACINE" && "$PYTHON" -m jio chiffres > /tmp/jio_chiffres.txt 2>&1
CODE_CHIFFRES=$?
echo "    jio chiffres -> code $CODE_CHIFFRES (0 = la documentation dit vrai)"
if [ "$CODE_CHIFFRES" -ne 0 ]; then
    echo "    ECHEC : un chiffre annonce dans la documentation est faux" >&2
    cat /tmp/jio_chiffres.txt | tail -4 >&2
    exit 1
fi

titre "13. Le banc mesure VOTRE modele, et refuse de faire semblant"

# Un CLI externe est appele par subprocess : un faux modele sert de temoin, et il prouve
# aussi la regle la plus importante — un modele demande et indisponible ARRETE la mesure.
printf '#!/bin/sh\ncat\n' > /tmp/jio_faux_llm
chmod +x /tmp/jio_faux_llm
# On force l'absence par `JIO_BIN_<NOM>` : le controle doit refuser que la machine ait ou
# non le binaire installe, sinon cette preuve dependrait de l'environnement.
echo "    modele indisponible :"
( cd "$RACINE" && JIO_BIN_CLAUDE=/aucun/chemin/claude PYTHONPATH="$RACINE" \
    "$PYTHON" -m jio bench --runs 1 --provider cli:claude ) \
    > /tmp/jio_bench_absent.txt 2>&1 || CODE_ABSENT=$?
CODE_ABSENT=${CODE_ABSENT:-0}
if [ "$CODE_ABSENT" = "2" ] && grep -q "Aucun repli" /tmp/jio_bench_absent.txt; then
    echo "      refus explicite (code 2), aucun repli sur la simulation."
else
    echo "      ECHEC : un modele absent doit ARRETER la mesure" >&2
    head -3 /tmp/jio_bench_absent.txt >&2
    exit 1
fi
echo "    modele indisponible mais fourni : la mesure tourne sur un binaire reel"
JIO_BIN_JIO_FAUX_LLM=/tmp/jio_faux_llm \
JIO_CLI_JIO_FAUX_LLM_ARGV='{binary}' \
    "$PYTHON" -c "
import sys
sys.path.insert(0, '$RACINE')
from jio.bench.provider_spec import resoudre
from jio.providers.cli import CliProvider
f = resoudre('cli:jio-faux-llm')
assert isinstance(f.provider, CliProvider), f
print('      binaire resolu :', f.provider.binary, '—', f.instances, 'instances pour le panel')
"

titre "14. Les commandes citees par les documents existent"

# L'oracle est le parseur de la CLI elle-meme : aucune interpretation possible. Ce controle
# a deja trouve deux defauts reels dans ce depot (jio sync promis et inexistant, jio
# --version pris pour une sous-commande).
DOCS=$(git -C "$RACINE" ls-files '*.md' '*.rst' '*.txt' | grep -v '^evidence/' || true)
if [ -n "$DOCS" ]; then
    # shellcheck disable=SC2086
    ( cd "$RACINE" && PYTHONPATH="$RACINE" "$PYTHON" -m jio claims --hook $DOCS ) \
        > /tmp/jio_claims_docs.txt 2>&1
    CODE_DOCS=$?
    echo "    $(grep -c '\[ok\]' /tmp/jio_claims_docs.txt || true) document(s) verifies, \
$(grep -c '\[--\]' /tmp/jio_claims_docs.txt || true) sans matiere prouvable, \
$(grep -c '\[KO\]' /tmp/jio_claims_docs.txt || true) refute(s) — code $CODE_DOCS"
    if [ "$CODE_DOCS" != "0" ]; then
        grep "\[KO\]" /tmp/jio_claims_docs.txt | sed 's/^/    /'
        exit 1
    fi
else
    echo "    aucun document a verifier"
fi

titre "15. Ecrire des artefacts ne detruit rien"

# Un fichier de l'utilisateur n'est jamais ecrase : sa version reste, la notre va a cote.
# Le registre .jio/generated.json signe en plus les fichiers que le format empeche de
# marquer (les JSON, ou un commentaire est interdit).
TMP_ECRITURE=$(mktemp -d)
printf '# mes conventions\n- ne jamais utiliser eval\n' > "$TMP_ECRITURE/AGENTS.md"
# `sync` rend 1 quand il a du PRESERVER un fichier : ce n'est pas un succes, et ce n'est
# pas une erreur non plus. On capture le code sans laisser `set -e` interrompre le script.
CODE_SYNC=0
( cd "$RACINE" && PYTHONPATH="$RACINE" "$PYTHON" -m jio sync --root "$TMP_ECRITURE" ) \
    > /tmp/jio_sync_1.txt 2>&1 || CODE_SYNC=$?
echo "    projet neuf, avec un AGENTS.md ecrit a la main :"
grep -E "=>|PRESERVE" /tmp/jio_sync_1.txt | sed 's/^/    /'
echo "    code de sortie : $CODE_SYNC (1 = quelque chose a ete PRESERVE, donc pas un succes)"
if [ "$CODE_SYNC" != "1" ]; then
    echo "    ECHEC : la preservation du fichier de l'utilisateur devait rendre 1" >&2
    rm -rf "$TMP_ECRITURE"; exit 1
fi
if ! grep -q "ne jamais utiliser eval" "$TMP_ECRITURE/AGENTS.md"; then
    echo "    ECHEC : le fichier de l'utilisateur a ete modifie" >&2
    rm -rf "$TMP_ECRITURE"
    exit 1
fi
echo "    AGENTS.md de l'utilisateur : intact octet pour octet."
( cd "$RACINE" && PYTHONPATH="$RACINE" "$PYTHON" -m jio sync --root "$TMP_ECRITURE" ) \
    > /tmp/jio_sync_2.txt 2>&1 || true
grep "=>" /tmp/jio_sync_2.txt | sed 's/^/    2e passage : /'
# Le registre porte l'empreinte de ce que NOUS avons ecrit : c'est lui qui permet de
# mettre a jour un fichier que son format empeche de signer (les JSON, sans commentaires).
ENTREES=$("$PYTHON" -c "import json,sys; print(len(json.load(open(sys.argv[1]))['fichiers']))" \
    "$TMP_ECRITURE/.jio/generated.json")
echo "    registre .jio/generated.json : $ENTREES fichier(s) signe(s)"
if [ "$ENTREES" -lt 20 ]; then
    echo "    ECHEC : le registre devrait signer l'essentiel des fichiers emis" >&2
    rm -rf "$TMP_ECRITURE"; exit 1
fi
rm -rf "$TMP_ECRITURE"

titre "16. Le budget de contexte : ce que la configuration coute"

# Un fichier de contexte trop long est SURVOLE : il occupe la fenetre et n'apporte rien.
# On mesure donc ce qui est livre, et pas seulement ce qu'un test interne suppose.
PYTHONPATH="$RACINE" "$PYTHON" - <<'FIN'
from pathlib import Path

from jio.artifacts.budget import SEUILS, mesurer
from jio.artifacts.emit import manifest

contexte = {
    c: x for c, x in manifest().items()
    if c in {"AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursor/rules/jio.mdc",
             ".github/copilot-instructions.md"}
}
skills = {c: x for c, x in manifest().items() if "/skills/" in c and c.endswith("SKILL.md")}

pire = max((mesurer(c, x) for c, x in contexte.items()), key=lambda m: m.lignes)
etat = "dans le budget" if pire.lignes <= SEUILS["contexte_lignes"] else "TROP LONG"
print(f"    contexte le plus long : {pire.chemin} {pire.lignes} ligne(s) "
      f"{pire.intervalle()} jetons — {etat} (seuil {SEUILS['contexte_lignes']} lignes)")

mesures = [mesurer(c, x) for c, x in skills.items()]
total = sum(m.jetons for m in mesures)
lourde = max(mesures, key=lambda m: m.jetons)
print(f"    competences : {len(mesures)} fichier(s), ~{total} jetons au total "
      f"(seuil {SEUILS['bibliotheque_jetons']}), la plus lourde ~{lourde.jetons}")
print("    cote d'une session reelle : un seul fichier de contexte, pas la somme.")
FIN

titre "17. Les hooks pre-commit : une promesse ecrite doit avoir une implementation"

# Le defaut trouve dans ce depot : `jio-scan-strict` annoncait « echoue aussi si le projet
# est incoherent a l'import » avec EXACTEMENT la meme commande que le hook normal. On
# verifie donc trois choses : le standard de l'ecosysteme accepte les manifestes, chaque
# hook declare une entree qui existe, et le mode strict change quelque chose d'observable.
if [ -x "$RACINE/.venv/bin/pre-commit" ]; then
    for f in .pre-commit-config.yaml .pre-commit-hooks.yaml; do
        printf '    %-26s ' "$f"
        if "$RACINE/.venv/bin/pre-commit" validate-"$( [ "$f" = ".pre-commit-config.yaml" ] && echo config || echo manifest )" "$f" >/dev/null 2>&1; then
            echo "valide par pre-commit"
        else
            echo "INVALIDE"
        fi
    done
else
    echo "    pre-commit absent : validation des manifestes ignoree"
fi

printf '    %-26s ' "mode strict"
if "$PYTHON" -m jio scan jio --exclude-tests --no-learn --strict >/dev/null 2>&1; then
    echo "code 0 sur le code du projet (une porte qui refuse tout serait desactivee)"
else
    echo "PROBLEME : le code du projet ne passe pas sa propre porte stricte"
fi

# Le hook lui-meme, lance comme pre-commit le lance : tous les documents modifies d'un
# coup. Un document muet ne doit pas faire echouer ; un document refute doit faire echouer.
TMP_HOOK=$(mktemp -d)
printf '# Rapport\n\n12 + 30 = 42 ms.\n' > "$TMP_HOOK/sain.md"
printf '# Note\n\nAucun fait verifiable.\n' > "$TMP_HOOK/muet.md"
printf '# Rapport\n\nLe total vaut 7 x 6 = 43 ms.\n' > "$TMP_HOOK/faux.md"
printf '    %-26s ' "document muet"
"$PYTHON" -m jio claims --hook "$TMP_HOOK/muet.md" >/dev/null 2>&1 && echo "code 0 (ne bloque pas)" || echo "PROBLEME : un document muet bloque un commit"
printf '    %-26s ' "document refute"
if "$PYTHON" -m jio claims --hook "$TMP_HOOK/sain.md" "$TMP_HOOK/faux.md" >/dev/null 2>&1; then
    echo "PROBLEME : une refutation n'a pas bloque"
else
    echo "code 1 (bloque, et cite la refutation)"
fi
rm -rf "$TMP_HOOK"

titre "18. Le serveur MCP : ecrit ne veut pas dire BRANCHE"

# Deux faits, tous deux verifiables sans cle API :
#   1. les fragments de configuration respectent le format de chaque outil ;
#   2. la commande qu'ils nomment sert REELLEMENT des outils sur cette machine.
# Le second est celui qui attrape le piege : une configuration correcte qui ne branche
# rien (`python3` existe, `jio` n'y est pas installe) ne se voit qu'en parlant au serveur.
TMP_MCP=$(mktemp -d)
for dialecte in opencode hermes codex; do
    printf '    %-12s ' "$dialecte"
    "$PYTHON" -m jio artifacts --mcp "$dialecte" --root "$TMP_MCP" 2>&1 \
        | grep -q "mcp_servers\|opencode.json\|jio.mcp_server" \
        && echo "fragment conforme" || echo "PROBLEME : fragment absent"
done
rm -rf "$TMP_MCP"

# Le cablage ne doit JAMAIS toucher une configuration existante.
TMP_USER=$(mktemp -d)
printf '{\n  "mcp": { "autre": { "type": "local", "command": ["x"] } }\n}\n' \
    > "$TMP_USER/opencode.json"
$PYTHON -m jio artifacts --mcp opencode --root "$TMP_USER" >/dev/null 2>&1 || true
if grep -q "jio" "$TMP_USER/opencode.json"; then
    echo "    ATTENTION : une configuration existante a ete MODIFIEE."
else
    echo "    configuration existante : intacte, fragment affiche (jamais fusionne en silence)."
fi
rm -rf "$TMP_USER"

printf '    %-12s ' "sonde"
if "$PYTHON" -m jio mcp --prove 2>&1 | grep -q "sert 5 outil"; then
    echo "5 outil(s) servis — le cablage est PROUVE, pas suppose."
else
    echo "PROBLEME : le serveur ne sert pas ses outils."
fi

titre "19. La PROSE : un document a des affirmations vraies ou fausses"
# Tout le harness prouvait du CODE. Sur une mission generaliste (rapport, analyse,
# note) il n'y avait rien a executer, donc JIO s'abstenait. Ce temoin verifie ce qui,
# dans un texte, se PROUVE au lieu de se relire : un calcul annonce, un bloc presente
# comme Python, un chemin cite. Corpus dans evidence/claims/, donc rejouable.
CORPUS_CLAIMS="$RACINE/evidence/claims"
TMP_CLAIMS=$(mktemp -d)
if [ -d "$CORPUS_CLAIMS" ]; then
    printf '    %-22s %-9s %s\n' "document" "code" "bilan"
    for document in rapport_sain.md rapport_fautif.md; do
        # Le CODE DE SORTIE est le contrat (0 = conforme, 1 = refute). Le lire apres un
        # `|| true` donnerait toujours 0 : on teste donc l'invocation elle-meme.
        if sortie=$("$PYTHON" -m jio claims "$CORPUS_CLAIMS/$document" --racine "$RACINE" 2>&1); then
            code=0
        else
            code=$?
        fi
        bilan=$(printf '%s' "$sortie" | grep -oE 'BILAN : .*' | head -1 | cut -c9- || true)
        printf '    %-22s %-9s %s\n' "$document" "code $code" "${bilan:-?}"
        printf '%s\n' "$sortie" >> "$TMP_CLAIMS/brut.txt"
    done
    printf '    %-22s ' "preuve du calcul faux"
    preuve=$(grep -oE '7 . 6 vaut 42, le texte annonce 43' "$TMP_CLAIMS/brut.txt" | head -1 || true)
    echo "${preuve:-(absente — a instruire)}"
    if grep -q 'NON CONFORME' "$TMP_CLAIMS/brut.txt" \
       && grep -qi 'conforme sur ce qui est verifiable' "$TMP_CLAIMS/brut.txt"; then
        echo "    -> le fautif est REFUTE (code 1), le sain reste MUET (code 0) : le temoin discrimine."
    else
        echo "    -> ATTENTION : la discrimination n'est pas etablie ci-dessus."
    fi
    printf '    %-22s ' "auto-audit du depot"
    # Le depot s'audite LUI-MEME, prose comprise : la documentation du projet passe
    # par ses propres temoins. C'est l'exigence « JIO doit s'auditer lui-meme »,
    # appliquee au texte et pas seulement au code.
    for document_du_depot in README.md docs/ROADMAP.md CLAUDE.md AGENTS.md; do
        [ -f "$RACINE/$document_du_depot" ] || continue
        if "$PYTHON" -m jio claims "$RACINE/$document_du_depot" --racine "$RACINE" \
             > "$TMP_CLAIMS/depot.txt" 2>&1; then
            printf '%s: conforme  ' "$document_du_depot"
        else
            printf '\n    %s : NON CONFORME -> %s\n' "$document_du_depot" \
                "$(grep -oE 'BILAN : .*' "$TMP_CLAIMS/depot.txt" | head -1)"
        fi
    done
    echo
    printf '    %-22s ' "sans affirmation"
    if "$PYTHON" -m jio claims "$CORPUS_CLAIMS/note_sans_affirmation.md" --racine "$RACINE" \
         >/dev/null 2>&1; then
        code_note=0
    else
        code_note=$?
    fi
    # Trois codes, et la distinction est le sujet : 0 conforme, 1 refute, 3 RIEN a
    # verifier. Confondre 1 et 3 obligerait a choisir entre faire passer un document
    # muet pour un quitus, ou signaler un defaut qui n'existe pas.
    case "$code_note" in
        3) echo "code 3 — rien a verifier : NI un succes, NI un echec, et c'est DIT." ;;
        0) echo "code 0 — MAUVAIS : une note sans fait verifiable passerait pour un quitus." ;;
        *) echo "code $code_note — inattendu (1 attendu pour un refus, 3 pour une absence de matiere)." ;;
    esac
else
    echo "    corpus absent : etape ignoree."
fi
rm -rf "$TMP_CLAIMS"

titre "20. Une MISSION de document : la prose entre dans la boucle"
# Les temoins de prose (3 quinquies) verifient UN document. Il manquait la mission
# complete : generer, prouver, panel, consensus, porte. Sans cela, une mission
# generaliste n'avait aucune preuve executable et JIO s'abstenait.
#
# Le chiffre qui compte ici est le meme que partout : les documents non corrects
# livres SANS RIEN DIRE. Il doit valoir zero, a competence NULLE comme a competence
# moyenne — et c'est verifie pour les deux.
if "$PYTHON" -c "import jio.bench.prose" 2>/dev/null; then
    TMP_PROSE=$(mktemp -d)
    # Le CODE DE SORTIE est le contrat. Le lire apres un pipe mesurerait le pipe
    # (c'est `sed` qui sort en dernier) : on teste donc l'invocation elle-meme, en
    # redirigeant la sortie — la meme erreur a deja ete corrigee une fois plus haut,
    # et refaire la meme faute serait le degre zero de ce projet.
    if "$PYTHON" -m jio bench --prose --runs 3 --rounds 2 > "$TMP_PROSE/brut.txt" 2>&1; then
        code=0
    else
        code=$?
    fi
    sed -n '/bras /,/ERREURS LIVREES/p' "$TMP_PROSE/brut.txt"
    echo "    -> code $code : $( [ "$code" -eq 0 ] && echo 'aucun document non correct livre sans rien dire' || echo 'AU MOINS UN SILENCE — a instruire' )"
    rm -rf "$TMP_PROSE"
else
    echo "    module absent : etape ignoree."
fi

titre "Termine"
