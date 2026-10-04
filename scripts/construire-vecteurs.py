"""Construire la table de vecteurs embarquee dans `jio/skills/vecteurs/`.

POURQUOI CE SCRIPT EXISTE. Le routeur lexical a un plafond MESURE : sur les 113 cas de controle,
24 objectifs du domaine sont refuses par la porte, et ces 24 ne partagent AUCUN mot avec les
fiches (« prove the fix by running it »). Six portes candidates et douze variantes de classement
ont ete mesurees, toutes au meme niveau : sans similarite SEMANTIQUE, la porte ne peut pas les
reconnaitre, et le classement ne peut pas les ordonner. Ce script construit la seule ressource qui
manquait, a partir d'une source REACHABLE depuis cette machine.

LA SOURCE, et pourquoi celle-la. `wink-embeddings-sg-100d` (npm, MIT) empaquette des vecteurs
derives de **GloVe** (Stanford, licence PDDL — domaine public). Deux raisons de la choisir plutot
qu'un modele de phrase : elle ne demande NI PyTorch NI `sentence-transformers` (le noyau de ce
depot n'a aucune dependance), et son paquet est joignable depuis une machine dont l'acces reseau se
limite a GitHub, PyPI et `registry.npmjs.org` — `huggingface.co` y est injoignable, mesure faite.

CE QUE LE SCRIPT FABRIQUE, et la regle exacte (verifiable, donc) :

  * il lit les entrees de la source dans l'ordre de frequence ;
  * il ne garde que les mots ecrivables en minuscules (`[a-z'-]`, 1 a 30 caracteres) ;
  * il les regroupe par RADICAL (`jio.skills.router.stem`) : la forme « radical » est celle que le
    routeur emploie deja pour rapprocher `tester`/`teste`/`tests`. Un radical prend la moyenne des
    vecteurs des formes qui le partagent, ponderee par la frequence ;
  * il retient les `MAX_MOTS` radicaux les plus FREQUENTS ;
  * il normalise chaque vecteur (seule la DIRECTION compte : la ressemblance est un cosinus) puis
    le quantifie en 8 bits signes, ce qui divise le fichier par quatre sans changer un classement
    (mesure : meme resultat, cf. `evidence/vecteurs-semantiques.*`).

Le fichier produit est lisible par un CHARGEUR MINIMAL, ecrit a la main (`jio/skills/vecteurs.py`) :
magic, en-tete JSON, puis pour chaque mot sa longueur, son texte et ses `dims` octets signes. Pas
de `pickle` — ce depot traite tout fichier comme du contenu NON FIABLE, et `pickle` execute du code.

Usage :
    python scripts/construire-vecteurs.py            # telecharge (118 Mo), construit, verifie
    python scripts/construire-vecteurs.py --verifier  # relit la table versionnee, sans reseau
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import pathlib
import re
import sys
import tarfile
import urllib.request
from array import array

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from jio.skills.router import stem  # noqa: E402

#: URL exacte du paquet (npm est joignable la ou huggingface.co ne l'est pas : mesure faite).
SOURCE = "https://registry.npmjs.org/wink-embeddings-sg-100d/-/wink-embeddings-sg-100d-1.1.0.tgz"
MEMBER = "package/wink-embeddings-sg-100d.json"
#: Empreinte du paquet telecharge : si la source change sous nos pieds, la construction s'arrete.
EMPREINTE_SOURCE = "2d1bea7fa5525661598829da929d628e5c76e6206a4923c6b464f30c1a5d647c"
SORTIE = RACINE / "jio" / "skills" / "vecteurs" / "glove-sg-100d-jio.bin.gz"
MAGIC = b"JIOVEC1\n"
#: Dimension de la source. Le cosinus se calcule sur les deux premiers champs seulement : les
#: positions 100 et 101 de la source portent la norme et un index, pas une coordonnee.
DIMS_SOURCE = 100
#: Nombre de radicaux retenus. Mesure du compromis taille/gain : cf. evidence.
MAX_MOTS = 11000

MOTIF = re.compile(rb'"([^"]{1,60})":\[(-?[\d.,eE+-]+)\]')
MOT_PROPRE = re.compile(r"[a-z][a-z'\-]{0,29}")


def _entrees_source(chemin: pathlib.Path):
    """Rend (mot, vecteur) dans l'ORDRE de la source, sans charger 300 Mo en memoire."""
    with tarfile.open(chemin) as tf:
        flux = tf.extractfile(MEMBER)
        assert flux is not None
        reste = b""
        while True:
            bloc = flux.read(8 << 20)
            if not bloc:
                break
            donnees = reste + bloc
            for m in MOTIF.finditer(donnees):
                mot = m.group(1).decode("utf-8", "replace")
                if not MOT_PROPRE.fullmatch(mot):
                    continue
                valeurs = m.group(2).split(b",")
                if len(valeurs) < DIMS_SOURCE:
                    continue
                yield mot, [float(v) for v in valeurs[:DIMS_SOURCE]]
            reste = donnees[-4000:]


def construire(paquet: pathlib.Path | None = None) -> dict:
    if paquet is None or not paquet.exists():
        paquet = pathlib.Path("/tmp/wink-embeddings-sg-100d-1.1.0.tgz")
        if not paquet.exists():
            print(f"telechargement : {SOURCE}")
            urllib.request.urlretrieve(SOURCE, paquet)  # noqa: S310 (URL constante ci-dessus)

    # La source est verrouillee par son empreinte : si le paquet change sous nos pieds, la
    # construction s'arrete au lieu de produire une table dont personne ne connait l'origine.
    lu = hashlib.sha256(paquet.read_bytes()).hexdigest()
    if lu != EMPREINTE_SOURCE:
        raise SystemExit(f"empreinte de la source differente :\n  attendu {EMPREINTE_SOURCE}\n"
                         f"  lu      {lu}")

    # 1. agreger par RADICAL, en gardant l'ordre de frequence de la source
    sommes: dict[str, list[float]] = {}
    comptes: dict[str, int] = {}
    rangs: dict[str, int] = {}
    for rang, (mot, vecteur) in enumerate(_entrees_source(paquet)):
        cle = stem(mot)
        if cle not in rangs:
            rangs[cle] = rang
            sommes[cle] = [0.0] * DIMS_SOURCE
            comptes[cle] = 0
        if comptes[cle] >= 8:      # borne : une forme tres frequente ne doit pas ecraser son radical
            continue
        for i, x in enumerate(vecteur):
            sommes[cle][i] += x
        comptes[cle] += 1
        if len(rangs) > 4 * MAX_MOTS:
            # on a largement de quoi choisir les plus frequents : inutile de lire les 341 479
            break

    retenus = sorted(rangs, key=lambda c: rangs[c])[:MAX_MOTS]
    table: dict[str, array] = {}
    for cle in retenus:
        moyenne = [x / comptes[cle] for x in sommes[cle]]
        norme = math.sqrt(sum(x * x for x in moyenne))
        if not norme:
            continue
        table[cle] = array("b", [max(-127, min(127, round(127 * x / norme))) for x in moyenne])

    # 2. ecrire le fichier (en-tete lisible + donnees serrees)
    entete = json.dumps(
        {
            "source": "wink-embeddings-sg-100d 1.1.0 (npm, MIT) — vecteurs derives de GloVe (PDDL)",
            "cle": "radical (jio.skills.router.stem), formes flechies moyennees",
            "dims": DIMS_SOURCE,
            "mots": len(table),
            "quantification": "int8 : round(127 * x / norme), vecteurs normalises",
            "construit_par": "scripts/construire-vecteurs.py",
        },
        ensure_ascii=False,
    ).encode()

    brut = bytearray(MAGIC)
    brut += len(entete).to_bytes(4, "little") + entete
    for mot in sorted(table):
        cle = mot.encode()
        brut += len(cle).to_bytes(2, "little") + cle + table[mot].tobytes()

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_bytes(gzip.compress(bytes(brut), 9))
    return {
        "mots": len(table),
        "octets": SORTIE.stat().st_size,
        "empreinte": hashlib.sha256(SORTIE.read_bytes()).hexdigest()[:16],
    }


def verifier() -> int:
    """Relit la table versionnee comme le fera le chargeur, sans reseau. Rend un code de sortie."""
    from jio.skills.vecteurs import charger

    if not SORTIE.exists():
        print(f"ABSENTE : {SORTIE.relative_to(RACINE)}")
        return 1
    table = charger(SORTIE)
    if table is None:
        print("ILLISIBLE : le chargeur a refuse le fichier")
        return 1
    print(f"table lue : {len(table.mots)} radicaux de {table.dims} dimensions, "
          f"{SORTIE.stat().st_size/1e6:.2f} Mo")
    for paire in (("test", "verification"), ("test", "banane"), ("proof", "evidence")):
        a, b = table.mots.get(stem(paire[0])), table.mots.get(stem(paire[1]))
        if a is not None and b is not None:
            print(f"  cos({paire[0]}, {paire[1]}) = {table.cosinus(a, b):+.2f}")
    return 0


def main() -> int:
    global MAX_MOTS
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true", help="relire la table versionnee, sans reseau")
    ap.add_argument("--paquet", type=pathlib.Path, default=None, help="paquet npm deja telecharge")
    ap.add_argument("--mots", type=int, default=MAX_MOTS, help="nombre de radicaux retenus")
    args = ap.parse_args()
    if args.verifier:
        return verifier()
    MAX_MOTS = args.mots
    resultat = construire(args.paquet)
    print(f"ecrit : {SORTIE.relative_to(RACINE)}  {resultat['mots']} mots, "
          f"{resultat['octets']/1e6:.2f} Mo, sha256[:16]={resultat['empreinte']}")
    return verifier()


if __name__ == "__main__":
    raise SystemExit(main())
