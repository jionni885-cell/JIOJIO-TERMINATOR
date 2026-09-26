"""Les etapes de la preuve sont numerotees, et leurs numeros ne se repetent pas.

Ce defaut est arrive deux fois. La premiere, deux etapes portaient « 3 quinquies » ; la
seconde, deux etapes portaient « 7 ». Les deux fois, la cause etait la meme : une etape
ajoutee quelque part dans le script, et un numero choisi a la main, sans regarder ceux qui
existaient deja.

Or une preuve dont les etapes ne se citent pas sans ambiguite ne se cite pas du tout : le
README renvoie a « l'etape 19 », et il faut que ce renvoi designe UNE chose. Ce test rend
l'erreur impossible a commettre — il lit les titres dans l'ordre du fichier et exige :

  * une numerotation **croissante** : le numero suit l'ordre d'affichage reel, qui est
    celui de l'execution, pas l'ordre dans lequel on a ecrit les morceaux ;
  * des numeros **uniques** : un renvoi doit designer une seule etape.

Le piege que ce test evite est connu : `grep -c '^titre "7'` ne compte pas ce qui s'affiche
vraiment (les etapes sont inserees dans un ordre qui n'est pas celui des numeros), et une
mesure qui ne regarde qu'une partie du fichier ne dit rien du tout.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
EVIDENCE = RACINE / "scripts" / "evidence.sh"


def _titres() -> list[str]:
    texte = EVIDENCE.read_text(encoding="utf-8")
    return re.findall(r'^\s*titre\s+"([^"]+)"', texte, re.MULTILINE)


@pytest.mark.skipif(not EVIDENCE.is_file(), reason="scripts/evidence.sh absent")
def test_les_numeros_d_etape_sont_uniques_et_croissants() -> None:
    titres = _titres()
    assert titres, "aucune etape trouvee : le script de preuve a change de forme"

    numeros: list[int] = []
    for titre in titres:
        correspondance = re.match(r"^(\d+)\.\s", titre)
        if not correspondance:
            # Seul le dernier titre (« Termine ») est en dehors de la numerotation.
            assert titre == "Termine", f"titre sans numero : {titre!r}"
            continue
        numeros.append(int(correspondance.group(1)))

    assert numeros == sorted(numeros), (
        "les etapes ne suivent pas leur ordre d'affichage : "
        f"{numeros}\nLes titres s'affichent dans cet ordre :\n  "
        + "\n  ".join(titres)
    )

    doublons = {n for n in numeros if numeros.count(n) > 1}
    assert not doublons, (
        f"numero(s) d'etape utilise(s) deux fois : {sorted(doublons)}. Un renvoi de "
        "documentation (par exemple « etape 19 ») doit designer une seule etape."
    )

    assert numeros == list(range(1, len(numeros) + 1)), (
        f"la numerotation saute des valeurs : {numeros} — numeroter 1..N dans l'ordre "
        "d'affichage, sans trou."
    )


def test_les_renvois_des_documents_designent_une_etape_qui_existe() -> None:
    """Le README renvoie a « l'etape 19 » : la cible doit exister.

    Un renvoi casse ne se voit pas a la lecture (le numero *a l'air* valide) et envoie le
    lecteur chercher une etape qui n'existe plus — c'est exactement ce qui s'est produit
    quand les etapes ont ete renumerotees.
    """
    numeros = {
        int(m.group(1))
        for titre in _titres()
        if (m := re.match(r"^(\d+)\.\s", titre))
    }
    assert numeros, "aucun numero d'etape : le script de preuve a change de forme"

    motif = re.compile(r"\b[ée]tape\s+\*{0,2}(\d+)\*{0,2}")
    documents = [RACINE / "README.md"] + sorted((RACINE / "docs").glob("*.md"))
    vus = 0
    for document in documents:
        if not document.is_file():
            continue
        for indice, ligne in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            for correspondance in motif.finditer(ligne):
                vus += 1
                cible = int(correspondance.group(1))
                assert cible in numeros, (
                    f"{document.relative_to(RACINE)} ligne {indice} renvoie a l'etape "
                    f"{cible}, qui n'existe pas dans scripts/evidence.sh "
                    f"(etapes : {sorted(numeros)})"
                )
    assert vus, (
        "aucun renvoi d'etape trouve : soit les documents ont cesse de citer la preuve, "
        "soit ce controle ne regarde plus rien."
    )
