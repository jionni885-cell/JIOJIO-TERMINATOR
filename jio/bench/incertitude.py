"""L'incertitude d'une mesure, calculee — parce qu'un taux sans barre d'erreur ment.

Un banc qui annonce « +20,0 points » sans dire sur combien d'essais ni avec quelle
dispersion invite a conclure sur du bruit. Sur ce depot, la mesure l'a montre : a
`--runs 1` (5 taches), l'ecart d'isolation vaut +20,0 points, mais son intervalle de
confiance a 95 % contient ZERO. Le chiffre etait exact et la conclusion, fausse.

Deux outils suffisent, tous deux sans dependance et sans hypothese de normalite :

  * `intervalle_wilson` — un intervalle de confiance pour UNE proportion. Le choix de
    Wilson plutot que l'intervalle normal (« p ± 1,96 sqrt(p(1-p)/n) ») n'est pas un
    detail : le normal produit des bornes NEGATIVES et des intervalles de largeur nulle
    quand p vaut 0 ou 1, ce qui arrive tout le temps sur un banc (0 erreur livree, 100 %
    de reussite a haute competence). Wilson reste correct a ces extremes ;
  * `intervalle_difference` — un intervalle pour la DIFFERENCE de deux proportions
    independantes (= methode de Newcombe). C'est ce qui permet de dire « l'ecart est
    significatif » ou « indéterminé a ce nombre d'essais », au lieu de comparer deux
    chiffres et d'esperer.

La fonction ne decide jamais a la place de l'auteur du rapport : elle rend des bornes et
une reponse. L'avertissement affiche est explicite, comme le reste de ce projet.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "intervalle_wilson",
    "intervalle_difference",
    "ecart_a_la_une",
    "essais_necessaires",
]

#: Quantile normal a 95 % — la valeur usuelle, ecrite pour etre lisible.
_Z = 1.959963984540054


def _quantile(seuil: float) -> float:
    """Quantile normal centre-reduit pour un seuil bilateral (Acklam, ~1e-9).

    Ecrit ici plutot qu'importe : une vingtaine de coefficients evitent de dependre de
    scipy pour une seule constante. VERIFIE contre la table connue (1,6449 a 90 %,
    1,9600 a 95 %, 2,5758 a 99 %) : le premier jet de cette fonction rendait 0,24 la ou
    la table dit 1,96 — les intervalles auraient ete cinq fois trop etroits, donc le banc
    aurait declare significatifs des ecarts qui ne le sont pas. Un test compare a la
    table, pas a la fonction elle-meme.
    """
    if not 0.5 < seuil < 1.0:
        raise ValueError("le seuil doit etre strictement entre 0,5 et 1")
    p = 1.0 - (1.0 - seuil) / 2.0
    # Coefficients d'Acklam : `a`/`b` pour le corps, `c`/`d` pour les queues.
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)

    def horner(coefficients, valeur):
        resultat = coefficients[0]
        for coefficient in coefficients[1:]:
            resultat = resultat * valeur + coefficient
        return resultat

    # Queues : la queue BASSE est positive, la queue HAUTE est negative. Inverser ces
    # deux signes rendait -1,96 la ou la table dit +1,96 — un quantile negatif aurait
    # produit des intervalles vides, donc « jamais significatif », sans rien dire.
    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return horner(c, q) / horner((*d, 1.0), q)
    if p > 1.0 - 0.02425:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -horner(c, q) / horner((*d, 1.0), q)
    q = p - 0.5
    r = q * q
    return q * horner(a, r) / horner((*b, 1.0), r)


def intervalle_wilson(succes: int, total: int, _z: float = _Z) -> tuple[float, float]:
    """Intervalle de confiance a 95 % d'une proportion observee `succes / total`.

    Rend `(0.0, 1.0)` quand il n'y a aucun essai : ne rien avoir mesure et ne rien
    pouvoir dire sont la meme chose, et l'intervalle le dit au lieu d'afficher 0 %.

    Le centre de Wilson est decale vers 0,5 par rapport a la proportion observee, et
    l'ecart depend de `total + z^2` : c'est ce qui evite les bornes absurdes
    (negatives, ou de largeur nulle) qui rendraient le banc menteur a ses extremes.
    """
    if total <= 0:
        return 0.0, 1.0
    p = succes / total
    denominateur = 1.0 + _z * _z / total
    centre = (p + _z * _z / (2 * total)) / denominateur
    demi = (
        _z
        * math.sqrt(p * (1.0 - p) / total + _z * _z / (4 * total * total))
        / denominateur
    )
    # Bornes EXACTES aux extremes, ecrites explicitement plutot qu'obtenues par un
    # arrondi : sans cela, 10 succes sur 10 rendait une borne haute de 0,9999999999999999,
    # c'est-a-dire un intervalle qui EXCLUT l'observation qu'il decrit. La formule de
    # Wilson vaut exactement 0 quand x = 0 et exactement 1 quand x = n ; le flottant,
    # non. Un intervalle incoherent avec sa propre mesure serait un drole de debut pour
    # un module dont le sujet est l'honnetete des chiffres.
    bas = 0.0 if succes <= 0 else max(0.0, centre - demi)
    haut = 1.0 if succes >= total else min(1.0, centre + demi)
    return bas, haut


def _succes(echantillon: Sequence[float]) -> tuple[int, int]:
    """Compte les essais et les succes, en refusant les valeurs qui ne sont ni 0 ni 1."""
    total = 0
    succes = 0
    for valeur in echantillon:
        total += 1
        if valeur >= 1.0:
            succes += 1
    return succes, total


def intervalle_difference(
    a: Sequence[float], b: Sequence[float], seuil: float = 0.95
) -> tuple[float, float]:
    """Intervalle a 95 % pour `moyenne(b) - moyenne(a)` (methode de Newcombe).

    Les deux echantillons sont supposes INDEPENDANTS — c'est le cas ici : chaque bras du
    banc rejoue les memes taches avec sa propre graine. L'intervalle ne suppose pas la
    normalite, ce qui compte pour un taux borne entre 0 et 1.
    """
    z = _Z if seuil == 0.95 else _quantile(seuil)
    succes_a, total_a = _succes(a)
    succes_b, total_b = _succes(b)
    bas_a, haut_a = intervalle_wilson(succes_a, total_a, z)
    bas_b, haut_b = intervalle_wilson(succes_b, total_b, z)
    if total_a <= 0 or total_b <= 0:
        return -1.0, 1.0
    p_a, p_b = succes_a / total_a, succes_b / total_b
    difference = p_b - p_a
    bas = difference - math.sqrt((p_a - bas_a) ** 2 + (haut_b - p_b) ** 2)
    haut = difference + math.sqrt((haut_a - p_a) ** 2 + (p_b - bas_b) ** 2)
    return max(-1.0, bas), min(1.0, haut)


def ecart_a_la_une(
    a: Sequence[float], b: Sequence[float], seuil: float = 0.95
) -> tuple[float, tuple[float, float], bool]:
    """Rend `(ecart_en_points, intervalle_en_points, significatif)`.

    `significatif` veut dire : l'intervalle de confiance de l'ecart EXCLUT zero. En
    dessous, la formulation correcte n'est pas « pas d'effet » mais « indéterminé a ce
    nombre d'essais » — et c'est ce que le banc doit afficher, sinon il fait dire a ses
    chiffres plus qu'ils ne portent. `seuil` n'est la que pour rappeler a l'appelant que
    Le seuil est un parametre parce que 95 % est une convention, pas une verite.
    """
    bas, haut = intervalle_difference(a, b, seuil)
    moyenne_a = sum(a) / len(a) if a else 0.0
    moyenne_b = sum(b) / len(b) if b else 0.0
    ecart = (moyenne_b - moyenne_a) * 100.0
    return ecart, (bas * 100.0, haut * 100.0), bas > 0.0 or haut < 0.0



def essais_necessaires(
    p_gauche: float, p_droite: float, puissance: float = 0.80, seuil: float = 0.95
) -> int:
    """Combien d'essais par bras pour demontrer un ecart de cette taille ?

    Rend un nombre a lire comme un BUDGET de mesure, pas comme un verdict. C'est la
    reponse a la seule question utile quand un ecart est indéterminé : « il me faudrait
    combien d'essais ? ».

    Mesure qui a motive cette fonction : l'ecart d'isolation du banc vaut +1,7 point a
    60 essais par bras, intervalle [-13,5 ; +16,9]. Dire « il n'y a pas d'effet » serait
    faux, dire « il y a un effet » aussi : a cette taille d'effet, il faudrait des
    milliers d'essais. Le banc le dit maintenant au lieu de laisser l'utilisateur
    conclure a la place de ses chiffres.

    Formule usuelle pour deux proportions independantes :
        n = (z(1 - seuil/2) + z(puissance))^2 * (p1(1-p1) + p2(1-p2)) / (p2-p1)^2
    Si les deux proportions sont egales, aucun nombre d'essais ne conclura : on rend 0,
    ce qui se lit « effet nul, il n'y a rien a mesurer ».
    """
    difference = p_droite - p_gauche
    if abs(difference) < 1e-12:
        return 0
    z_alpha = _Z if seuil == 0.95 else _quantile(seuil)
    z_beta = _quantile(puissance) if puissance > 0.5 else 0.0
    variance = p_gauche * (1.0 - p_gauche) + p_droite * (1.0 - p_droite)
    return math.ceil((z_alpha + z_beta) ** 2 * variance / difference ** 2)
