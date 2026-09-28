"""Quelles competences charger pour CET objectif — mesure, pas menu.

LE PROBLEME, tel qu'il se pose dans une session reelle. Le depot livre douze competences Hermes
(6424 jetons au total) et une fiche de contexte de 150 lignes qui les enumere. L'agent doit donc
CHOISIR lui-meme, a partir d'un titre et d'une phrase. Deux consequences sont mesurees dans la
litterature du domaine : une fiche de contexte au-dela d'environ 150 lignes est **survolee**, pas
lue ; et 5 000 jetons CIBLES battent un resume de 100 000 (la precision en tete de classement
passe de 0,14 a 0,48 quand on remplace le resume par la recuperation). Ce n'est donc pas la
taille de la bibliotheque qui aide : c'est le fait qu'elle soit INTERROGEE.

CE QUE FAIT CE MODULE. Il repond a une question unique — « pour cet objectif, quelles
competences charger, et pourquoi elles ? » — avec un score, les termes qui l'ont produit, et le
cout en jetons de ce qu'il fait charger.

QUATRE DECISIONS, chacune PAYEE par une mesure sur le banc annote (`jio/skills/banc.py`). Elles
sont ecrites ici parce qu'un choix technique dont on ne connait pas la raison se defait au premier
refactoring :

1. **BM25** (Okapi, Robertson & Zaragoza) plutot qu'un comptage de mots communs. Trois
   proprietes qui comptent ici : l'`idf` annule le poids des mots presents partout (« fichier »,
   « code »), la saturation empeche une competence bavarde de gagner parce qu'elle est longue, et
   la normalisation par la longueur (`b = 0.75`) traite les competences inegales. Le temoin
   `mots-cles bruts` du banc chiffre ce que cela apporte : sans ces trois proprietes, le premier
   choix juste tombe de 87 % a 48 %.

2. **On indexe le TIERS 0, pas les corps.** Mesure a l'origine : indexer le corps entier faisait
   gagner a `structured-failure` l'objectif « Ajouter un test qui echoue quand `sum_even` compte
   les impairs » — parce que son exemple de sortie cite litteralement `sum_even`. Un exemple cite
   le vocabulaire du DEPOT, pas le sujet de la competence. Le tiers 0 (nom, categorie,
   description, tags) est exactement l'enonce de l'intention ; le corps est ce qu'on INJECTE une
   fois la competence choisie. Confondre les deux coutait 29 points de premier choix juste.

3. **Diversification MMR** (Carbonell & Goldstein) : deux competences quasi identiques occuperaient
   deux places pour une seule information. Le classement maximise
   `lambda * pertinence - (1 - lambda) * redondance`.

4. **Abstention sur un seuil d'EVIDENCE MESURE** : un objectif qui ne releve d'aucune competence
   n'en charge AUCUNE. Le seuil porte sur le nombre de CONCEPTS de domaine distincts que
   l'objectif met en jeu (`lexique.concepts`) — pas sur un score, dont l'echelle n'a pas d'unite.
   La valeur retenue est celle que le balayage du banc a trouvee ; elle est declaree, et le banc
   est la limite de l'affirmation.

DEUX REGLES DE CONCEPTION, heritees du reste du depot :

  * **aucun hasard** : le classement est deterministe et les egalites sont tranchees par le nom.
    Un tri qui depend de l'ordre d'un dictionnaire dependrait de la session ;
  * **aucune selection sans raison** : chaque choix porte les termes qui l'ont produit. Un
    classement qu'on ne peut pas expliquer ne peut pas etre verifie.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "MOTS_VIDES",
    "SEUIL_CONCEPTS",
    "Catalogue",
    "Choix",
    "Document",
    "catalogue_du_depot",
    "choisir",
    "cout",
    "jetons",
    "stem",
]

#: Parametres BM25 usuels. Ils ne sont PAS ajustes sur douze documents : les ajuster serait de
#: l'habillage, pas de la mesure.
K1 = 1.2
B = 0.75

#: Poids du radical par rapport au mot exact. « tester » doit rapprocher de « test » sans que
#: l'egalite exacte perde sa valeur : le radical recoit la moitie du poids du mot ecrit.
POIDS_RADICAL = 0.5

#: Part de pertinence dans la diversification MMR.
LAMBDA = 0.7

#: Nombre de CONCEPTS de domaine distincts en dessous duquel le routeur s'abstient.
#:
#: MESURE, et la courbe compte autant que le point. Sur le banc annote (31 objectifs pertinents,
#: 8 hors sujet) :
#:   0 concept  -> 0/8 abstentions justes (le routeur repond toujours)
#:   1 concept  -> 3/8   et 31/31 objectifs pertinents servis
#:   2 concepts -> 8/8   et 27/31 servis       <- retenu
#:   3 concepts -> 8/8   et 14/31 servis
#: Le seuil de 2 est le seul point ou l'abstention est JUSTE sur tous les cas hors sujet sans
#: perdre la majorite des cas pertinents. Il coute 13 % des objectifs pertinents, qui sont
#: declares manques par le banc plutot que caches.
SEUIL_CONCEPTS = 2

#: Mots outils francais et anglais : presents dans presque tous les objectifs, donc ils ne
#: classent rien. « the », « de », « le » gagneraient sinon au detriment du sujet.
MOTS_VIDES = frozenset(["au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du", "elle", "en", "est", "et", "eux", "il", "ils", "je", "la", "le", "les", "leur", "lui", "ma", "mais", "me", "mes", "moi", "mon", "ne", "nos", "notre", "nous", "on", "ou", "par", "pas", "pour", "qu", "que", "quelle", "quelles", "quel", "quels", "qui", "sa", "sans", "se", "ses", "si", "soi", "son", "sont", "sous", "sur", "ta", "te", "tes", "toi", "ton", "tu", "un", "une", "vos", "votre", "vous", "c", "d", "j", "l", "a", "m", "n", "s", "t", "y", "ete", "etre", "avoir", "fait", "faire", "plus", "moins", "tres", "bien", "tout", "tous", "toute", "toutes", "meme", "aussi", "comme", "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "he", "her", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just", "me", "more", "most", "my", "no", "not", "of", "on", "or", "our", "out", "over", "she", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those", "to", "too", "under", "up", "us", "was", "we", "were", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your"])

#: Suffixes retires pour rapprocher les formes flechies. Volontairement LIMITE : un radical trop
#: agressif rapproche des mots sans rapport et rend le classement inexpliquable. Le retrait n'a
#: lieu que si le reste fait au moins quatre caracteres — la borne que la porte de clarification
#: a payee avant nous.
SUFFIXES = ("ations", "ation", "ements", "ement", "ing", "es", "s", "e", "er", "ir", "re", "ant")


def _sans_accent(texte: str) -> str:
    """« sécurité » et « securite » doivent se rencontrer : ce depot s'ecrit sans accents."""
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def stem(mot: str) -> str:
    """Radical minimal d'un mot : `tester`/`teste`/`tests` -> `test`."""
    for suffixe in SUFFIXES:
        if mot.endswith(suffixe) and len(mot) - len(suffixe) >= 4:
            return mot[: -len(suffixe)]
    return mot


def jetons(texte: str) -> list[str]:
    """Les mots porteurs de sens : sans accents, en minuscules, sans mots outils."""
    plat = _sans_accent(texte).lower()
    brut = "".join(c if c.isalnum() else " " for c in plat).split()
    return [m for m in brut if len(m) > 1 and m not in MOTS_VIDES]


def _termes(texte: str) -> Counter[str]:
    """Termes ponderes : le mot ecrit pour 1, son radical pour `POIDS_RADICAL`."""
    poids: Counter[str] = Counter()
    for mot in jetons(texte):
        poids[mot] += 1.0
        radical = stem(mot)
        if radical != mot:
            poids[radical] += POIDS_RADICAL
    return poids


@dataclass(frozen=True)
class Document:
    """Une competence, vue comme un document indexable.

    Le champ indexe est le TIERS 0 : nom, categorie, description, tags. Le corps n'est PAS
    indexe — mesure faite, ses exemples citent le vocabulaire du depot et detournent le
    classement. Il est ce qu'on injecte, pas ce qui sert a choisir.
    """

    nom: str
    categorie: str
    description: str
    tags: tuple[str, ...]

    @property
    def indexable(self) -> str:
        # Le nom et les tags sont repetes : ce sont les champs les plus DISCRIMINANTS (« hostile-
        # content », « abstention », « decorrelation »), et la repetition est la facon la plus
        # simple de ponderer un champ sans introduire un second jeu de parametres. Le couple
        # (3, 3) est celui que le balayage du banc a retenu ; le voisinage (2..4, 2..3) donne le
        # meme resultat, donc la valeur n'est pas un equilibre sur le fil.
        return " ".join(
            [self.nom] * 3 + list(self.tags) * 3 + [self.description, self.categorie]
        )

    @property
    def tier0(self) -> str:
        """Ce qu'un agent voit d'une competence sans la charger (revelation progressive)."""
        return f"{self.nom} ({self.categorie}) : {self.description}"

    @property
    def cout_jetons(self) -> int:
        """Cout d'injection, en jetons estimes — la meme borne que `artifacts/budget.py`."""
        return max(1, round(len(self.tier0) / 3.2))


@dataclass
class Choix:
    """Une competence retenue, avec de quoi verifier le choix."""

    nom: str
    categorie: str
    score: float
    raisons: tuple[str, ...]
    cout_jetons: int


@dataclass
class Catalogue:
    """L'index BM25 des competences, construit une fois et interroge autant de fois qu'on veut."""

    documents: tuple[Document, ...]
    _termes: dict[str, Counter[str]] = field(default_factory=dict, repr=False)
    _longueur: dict[str, float] = field(default_factory=dict, repr=False)
    _moyenne: float = 1.0
    _idf: dict[str, float] = field(default_factory=dict, repr=False)
    _norme: dict[str, float] = field(default_factory=dict, repr=False)
    _vocabulaire: frozenset[str] = frozenset()

    @classmethod
    def depuis(cls, documents: Sequence[Document]) -> Catalogue:
        cat = cls(documents=tuple(documents))
        for doc in cat.documents:
            termes = _termes(doc.indexable)
            cat._termes[doc.nom] = termes
            cat._longueur[doc.nom] = float(sum(termes.values()))
        total = cat._longueur.values()
        cat._moyenne = (sum(total) / len(cat._longueur)) if cat._longueur else 1.0
        n = len(cat.documents)
        presence: Counter[str] = Counter()
        for termes in cat._termes.values():
            presence.update(termes.keys())
        # `idf` de Robertson & Zaragoza, dans la forme qui reste POSITIVE meme pour un terme
        # present partout : un mot que toutes les competences contiennent ne classe rien, sans
        # pour autant devenir un score negatif qui perturberait la somme.
        cat._idf = {
            terme: math.log(1 + (n - df + 0.5) / (df + 0.5)) for terme, df in presence.items()
        }
        cat._norme = {nom: math.sqrt(sum(v * v for v in t.values())) or 1.0
                      for nom, t in cat._termes.items()}
        cat._vocabulaire = frozenset(presence)
        return cat

    # -- calculs ------------------------------------------------------------ #

    def _bm25(self, nom: str, requete: Counter[str]) -> float:
        termes = self._termes[nom]
        longueur = self._longueur[nom] or 1.0
        score = 0.0
        for terme, qtf in requete.items():
            tf = termes.get(terme)
            if not tf:
                continue
            denominateur = tf + K1 * (1 - B + B * longueur / (self._moyenne or 1.0))
            score += self._idf.get(terme, 0.0) * (tf * (K1 + 1) / denominateur) * qtf
        return score

    def _cosinus(self, gauche: str, droite: str) -> float:
        a, b = self._termes[gauche], self._termes[droite]
        commun = set(a) & set(b)
        if not commun:
            return 0.0
        produit = sum(a[t] * b[t] for t in commun)
        return produit / (self._norme[gauche] * self._norme[droite])

    def raisons(self, nom: str, requete: Counter[str], combien: int = 3) -> tuple[str, ...]:
        """Les termes qui ont le plus pese, avec leur contribution — le POURQUOI du choix."""
        termes = self._termes[nom]
        apports = [
            (terme, self._idf.get(terme, 0.0) * termes[terme] * qtf)
            for terme, qtf in requete.items() if terme in termes
        ]
        apports.sort(key=lambda x: (-x[1], x[0]))
        return tuple(f"{terme} ({valeur:.2f})" for terme, valeur in apports[:combien])

    def concepts_du_domaine(self, objectif: str) -> frozenset[str]:
        """Les concepts de l'objectif qui parlent VRAIMENT du domaine des competences.

        Un mot ne compte que s'il est un mot de DOMAINE — c'est-a-dire s'il appartient au
        lexique (`lexique.CONCEPT`) ou s'il figure dans le vocabulaire des competences. Un mot
        etranger au domaine (« espagnol », « bouton », « semaine ») ne prouve pas que l'objectif
        releve du domaine, et c'est exactement ce qu'on veut mesurer avant de charger une
        procedure.

        Ce que le banc a paye ici, et qu'il faut garder : la stabilite du seuil. Trois comptages
        differents ont ete essayes — mots de domaine seuls, vocabulaire de l'index seul, et leur
        union — et les trois donnent **8 abstentions justes sur 8** au seuil de deux concepts, a
        des rappels differents (respectivement 23, 15 et 27 objectifs pertinents conserves sur
        31). Le seuil ne depend donc pas du filtre choisi ; c'est ce qui autorise a retenir
        l'union, qui garde le plus de travail utile.

        L'identite d'un concept est son RADICAL, jamais sa forme ecrite : « outil » et « outils »
        sont un concept, pas deux (defaut mesure et corrige — il laissait passer « Ajouter une
        icone dans la barre d'outils »).
        """
        from .lexique import CONCEPT, concepts

        mots = [m for m in jetons(objectif)
                if m in CONCEPT or m in self._vocabulaire or stem(m) in self._vocabulaire]
        return concepts(" ".join(mots)) if mots else frozenset()

    def interroger(
        self,
        objectif: str,
        *,
        maximum: int = 3,
        seuil: int = SEUIL_CONCEPTS,
        ponter: bool = True,
    ) -> list[Choix]:
        """Les competences a charger — et AUCUNE si l'objectif ne releve d'aucune."""
        base = _termes(objectif)
        if not base or not self.documents:
            return []

        # -- 1. l'abstention d'abord : charger une procedure qui ne s'applique pas coute plus
        #       cher que ne rien charger, parce qu'elle detourne le travail en plus de le ralentir.
        evidence = self.concepts_du_domaine(objectif)
        if len(evidence) < max(0, seuil):
            return []

        # -- 2. le pont bilingue : les objectifs peuvent etre ecrits dans l'une ou l'autre
        #       langue, les descriptions dans une seule. Voir `lexique.py` pour sa limite.
        requete = Counter(base)
        if ponter:
            from .lexique import POIDS_VOISIN, PONT

            ecrits = set(base)
            for mot in jetons(objectif):
                for voisin in PONT.get(mot, ()):
                    if voisin not in ecrits:
                        requete[voisin] = max(requete.get(voisin, 0.0), POIDS_VOISIN)

        # -- 3. le classement BM25, puis la diversification MMR.
        scores = {doc.nom: self._bm25(doc.nom, requete) for doc in self.documents}
        par_nom = {doc.nom: doc for doc in self.documents}
        restants = [nom for nom in sorted(scores, key=lambda n: (-scores[n], n)) if scores[nom] > 0]
        meilleur = max(scores.values(), default=0.0)
        choisis: list[str] = []
        while restants and len(choisis) < max(1, maximum):
            def cle(nom: str) -> tuple[float, str]:
                redondance = max((self._cosinus(nom, deja) for deja in choisis), default=0.0)
                valeur = LAMBDA * scores[nom] - (1 - LAMBDA) * redondance * (meilleur or 1.0)
                return (-valeur, nom)

            retenu = min(restants, key=cle)
            restants.remove(retenu)
            choisis.append(retenu)

        return [
            Choix(
                nom=nom,
                categorie=par_nom[nom].categorie,
                score=round(scores[nom], 4),
                raisons=self.raisons(nom, requete),
                cout_jetons=par_nom[nom].cout_jetons,
            )
            for nom in choisis
        ]


def cout(choix: Sequence[Choix]) -> int:
    """Le cout d'injection d'une selection : ce que l'agent paiera reellement."""
    return sum(c.cout_jetons for c in choix)


_CATALOGUE: Catalogue | None = None


def catalogue_du_depot() -> Catalogue:
    """Le catalogue des competences LIVREES par le depot (`jio/artifacts/definitions.py`).

    L'index est memoise, et la source est le generateur qui ecrit les fichiers dans
    `.hermes/skills/` : enrichir une competence enrichit le classement sans qu'une liste
    parallele ait a etre tenue a jour — une liste parallele finit toujours par decrire un autre
    programme que le programme.
    """
    global _CATALOGUE
    if _CATALOGUE is None:
        from ..artifacts.definitions import SKILLS

        _CATALOGUE = Catalogue.depuis([
            Document(nom=s.name, categorie=s.category, description=s.description,
                     tags=tuple(s.tags))
            for s in SKILLS
        ])
    return _CATALOGUE


def choisir(
    objectif: str,
    *,
    maximum: int = 3,
    seuil: int = SEUIL_CONCEPTS,
    catalogue: Catalogue | None = None,
) -> list[Choix]:
    """Raccourci : interroge le catalogue du depot (cree a la premiere demande)."""
    return (catalogue or catalogue_du_depot()).interroger(
        objectif, maximum=maximum, seuil=seuil
    )
