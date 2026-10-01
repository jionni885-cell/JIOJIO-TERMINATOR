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

2. **Deux champs, deux roles : le tiers 0 DECIDE, le corps CLASSE** (BM25F, Robertson &
   Zaragoza). Mesure d'origine, gardee : mettre le corps dans le MEME index que le tiers 0
   faisait gagner a `structured-failure` l'objectif « Ajouter un test qui echoue quand
   `sum_even` compte les impairs », parce que son exemple de sortie cite litteralement
   `sum_even` — un exemple cite le vocabulaire du DEPOT, pas le sujet. Peser les deux champs
   separement repare ce defaut au lieu de renoncer au corps : le corps porte la prose qui dit
   QUAND la competence s'applique (« Any time you are about to assert that something works, is
   fixed, or is correct »), et c'est exactement ce qui manquait aux objectifs formules
   autrement. Le poids est mesure, pas choisi (voir `POIDS_CORPS`).

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
    "POIDS_CORPS",
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

#: Poids du CORPS dans le score : le tiers 0 pese 1, le corps pese cela (BM25F a deux champs).
#:
#: MESURE, et le plateau compte plus que le point. Trois jeux : le banc (celui du reglage), le
#: jeu de controle A (24 objectifs jamais vus) et le jeu B (24 objectifs jamais vus, ecrit avant
#: la retouche). Premier choix juste :
#:
#:   poids 0.00 (tiers 0 seul)  banc 83,9 %   controle A 45,8 %   jeu B 50,0 %
#:   poids 0.25                 banc 87,1 %   controle A 54,2 %   jeu B 50,0 %
#:   poids 0.75                 banc 87,1 %   controle A 58,3 %   jeu B 50,0 %   <- retenu
#:   poids 1.00                 banc 83,9 %   controle A 58,3 %   jeu B 50,0 %
#:
#: Le banc est MIEUX avec le corps que sans (87,1 contre 83,9), ce qui etait la crainte
#: contraire : le piege mesure a l'origine (le corps de `structured-failure` cite `sum_even`)
#: apparait quand les deux champs partagent UN index, pas quand ils sont ponderes separement —
#: l'objectif de reference garde `executable-proof` en tete a 0,25 comme a 1,0. Le corps reste
#: dans le plateau 0,25-1,0 pour le banc et 0,75-1,0 pour le controle ; 0,75 est le point ou
#: les deux courbes sont au mieux, et il n'est PAS un point isole : 0,5 donne les memes chiffres
#: a un cas pres. Les abstentions, elles, ne bougent pas d'un cas (8/8, 4/4, 5/5) : le
#: vocabulaire qui decide de l'abstention est celui du TIERS 0, jamais celui du corps.
POIDS_CORPS = 0.75

#: Nombre de MOTS de domaine distincts en dessous duquel le routeur s'abstient.
#:
#: MESURE, et la courbe compte autant que le point. Sur le banc annote (31 objectifs pertinents,
#: 8 hors sujet) :
#:   0 mot  -> 0/8 abstentions justes (le routeur repond toujours)
#:   1 mot  -> 3/8   et 31/31 objectifs pertinents servis
#:   2 mots -> 8/8   et 31/31 servis       <- retenu
#:   3 mots -> 8/8   et 25/31 servis
#: Le seuil de 2 est le seul point ou l'abstention est JUSTE sur tous les cas hors sujet sans
#: perdre UN SEUL cas pertinent, et il tient encore a 25 sur 31 au cran suivant : la marge
#: existe des deux cotes. Les huit cas hors sujet portent 0 ou 1 mot de domaine (« document »
#: pour une traduction, « outil » pour une barre d'outils, aucun pour un menu de la semaine).
#:
#: VERIFIE sur deux jeux jamais vus (controle A et jeu B, 8 hors sujet de plus) : TOUS portent
#: 0 ou 1 mot de domaine, et le seuil de 2 sert 44 objectifs sur 48. Le seuil de 1 ferait
#: entrer 8 hors sujet sur 17 sans servir un seul objectif de plus : la couverture ne vient pas
#: du seuil, elle vient du vocabulaire. C'est pourquoi une abstention ne laisse pas l'agent
#: sans rien — voir `jio skills` : elle renvoie l'inventaire tier 0.
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
    indexe comme SECOND champ, avec un poids a lui (`POIDS_CORPS`) : sa prose dit quand la
    competence s'applique, et c'est ce qui manquait aux objectifs formules autrement. Ses
    exemples, en revanche, citent le vocabulaire du depot : les melanger au tiers 0 dans un seul
    index detournait le classement, mesure a l'appui.
    """

    nom: str
    categorie: str
    description: str
    tags: tuple[str, ...]
    #: Le corps de la competence. Il n'entre PAS dans `indexable` : il a son propre index, et
    #: surtout il est absent de `_vocabulaire`, donc il ne peut pas faire passer un hors-sujet
    #: pour un objectif du domaine.
    corps: str = ""

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
    """L'index BM25F a DEUX champs des competences, construit une fois et interroge sans limite.

    Champ 1 (`indexable`) : nom, tags, description, categorie. C'est ce qui DECIDE — un objectif
    qui ne partage rien avec lui n'a rien a faire ici, et c'est aussi lui qui definit le
    vocabulaire du domaine (`_vocabulaire`).

    Champ 2 (`corps`) : la procedure elle-meme. C'est ce qui CLASSE : sa prose dit quand la
    competence s'applique. Il ne peut pas contaminer l'abstention, parce que le vocabulaire du
    domaine ne regarde que le champ 1 (invariant verifie par un test : ajouter une competence au
    corps d'une autre ne doit JAMAIS faire charger cette autre).
    """

    documents: tuple[Document, ...]
    _termes: dict[str, Counter[str]] = field(default_factory=dict, repr=False)
    _longueur: dict[str, float] = field(default_factory=dict, repr=False)
    _moyenne: float = 1.0
    _idf: dict[str, float] = field(default_factory=dict, repr=False)
    _norme: dict[str, float] = field(default_factory=dict, repr=False)
    _vocabulaire: frozenset[str] = frozenset()
    _termes_corps: dict[str, Counter[str]] = field(default_factory=dict, repr=False)
    _longueur_corps: dict[str, float] = field(default_factory=dict, repr=False)
    _moyenne_corps: float = 1.0
    _idf_corps: dict[str, float] = field(default_factory=dict, repr=False)

    @classmethod
    def depuis(cls, documents: Sequence[Document]) -> Catalogue:
        cat = cls(documents=tuple(documents))
        for doc in cat.documents:
            termes = _termes(doc.indexable)
            cat._termes[doc.nom] = termes
            cat._longueur[doc.nom] = float(sum(termes.values()))
            if doc.corps:
                termes_corps = _termes(doc.corps)
                cat._termes_corps[doc.nom] = termes_corps
                cat._longueur_corps[doc.nom] = float(sum(termes_corps.values()))
        total = cat._longueur.values()
        cat._moyenne = (sum(total) / len(cat._longueur)) if cat._longueur else 1.0
        total_corps = cat._longueur_corps.values()
        cat._moyenne_corps = (sum(total_corps) / len(total_corps)) if cat._longueur_corps else 1.0
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
        presence_corps: Counter[str] = Counter()
        for termes in cat._termes_corps.values():
            presence_corps.update(termes.keys())
        n_corps = len(cat._termes_corps) or 1
        cat._idf_corps = {
            terme: math.log(1 + (n_corps - df + 0.5) / (df + 0.5))
            for terme, df in presence_corps.items()
        }
        cat._norme = {nom: math.sqrt(sum(v * v for v in t.values())) or 1.0
                      for nom, t in cat._termes.items()}
        # Le vocabulaire du domaine ne vient QUE du champ 1 : c'est la garde qui empeche une
        # prose de competence de transformer un hors-sujet en objectif du domaine.
        cat._vocabulaire = frozenset(presence)
        return cat

    # -- calculs ------------------------------------------------------------ #

    @staticmethod
    def _bm25_champ(
        nom: str,
        requete: Counter[str],
        termes_index: dict[str, Counter[str]],
        longueurs: dict[str, float],
        moyenne: float,
        idf: dict[str, float],
    ) -> float:
        termes = termes_index.get(nom)
        if not termes:
            return 0.0
        longueur = longueurs[nom] or 1.0
        score = 0.0
        for terme, qtf in requete.items():
            tf = termes.get(terme)
            if not tf:
                continue
            denominateur = tf + K1 * (1 - B + B * longueur / (moyenne or 1.0))
            score += idf.get(terme, 0.0) * (tf * (K1 + 1) / denominateur) * qtf
        return score

    def _bm25(self, nom: str, requete: Counter[str]) -> float:
        """Le score des deux champs : le tiers 0 pese 1, le corps pese `POIDS_CORPS`."""
        return self._bm25_champ(
            nom, requete, self._termes, self._longueur, self._moyenne, self._idf
        ) + POIDS_CORPS * self._bm25_champ(
            nom, requete, self._termes_corps, self._longueur_corps, self._moyenne_corps,
            self._idf_corps,
        )

    def _cosinus(self, gauche: str, droite: str) -> float:
        a, b = self._termes[gauche], self._termes[droite]
        commun = set(a) & set(b)
        if not commun:
            return 0.0
        produit = sum(a[t] * b[t] for t in commun)
        return produit / (self._norme[gauche] * self._norme[droite])

    def raisons(self, nom: str, requete: Counter[str], combien: int = 3) -> tuple[str, ...]:
        """Les termes qui ont le plus pese, avec leur contribution — le POURQUOI du choix.

        Les deux champs sont cites, parce que le score vient des deux : un terme du corps est
        annote `corps:` et compte pour `POIDS_CORPS`. Sans cela, un choix dont le score vient du
        corps s'affichait SANS raison (« aucun terme commun ») alors qu'il en avait une — defaut
        trouve par un test, pas par relecture.
        """
        apports: dict[str, float] = {}
        tiers0, corps_champ = self._termes.get(nom, {}), self._termes_corps.get(nom, {})
        for terme, qtf in requete.items():
            apport = self._idf.get(terme, 0.0) * tiers0.get(terme, 0.0) * qtf
            apport += POIDS_CORPS * self._idf_corps.get(terme, 0.0) * corps_champ.get(terme, 0.0) * qtf
            if apport:
                # Le terme est cite UNE fois, avec l'apport des deux champs additionne : deux
                # lignes pour le meme mot feraient lire deux raisons la ou il n'y en a qu'une.
                # Le prefixe `corps:` ne marque donc que ce qui ne vient QUE du corps.
                marque = "" if tiers0.get(terme) else "corps:"
                apports[f"{marque}{terme}"] = apport
        classement = sorted(apports.items(), key=lambda x: (-x[1], x[0]))
        return tuple(f"{terme} ({valeur:.2f})" for terme, valeur in classement[:combien])

    def mots_du_domaine(self, objectif: str) -> frozenset[str]:
        """Les mots de DOMAINE de l'objectif, ramenes a leur RADICAL.

        Un mot est du domaine s'il appartient a une classe du lexique (`lexique.CONCEPT`) ou
        s'il figure dans le vocabulaire du TIERS 0 des competences (nom, tags, description,
        categorie) — jamais dans celui des corps : sinon n'importe quelle prose ferait entrer
        n'importe quel hors-sujet dans le domaine (defaut mesure, garde par un test).
        Un mot etranger (« espagnol », « bouton », « semaine ») ne prouve rien : c'est
        exactement ce qu'on veut mesurer avant de charger une procedure.

        MESURE QUI A FAIT CHANGER CETTE FONCTION, et elle vaut d'etre ecrite. La premiere
        version comptait des CONCEPTS par classe d'equivalence : trois mots du meme champ
        (« vote », « critiques », « consensus ») ne faisaient donc qu'UN concept, et le seuil
        de deux refusait des objectifs qui parlaient clairement du domaine — le banc en
        comptait deux, plus un troisieme sur la forge de competences. Compter les MOTS de
        domaine, par radical, repare cela et ameliore la marge dans les deux sens : sur le banc,
        31 objectifs pertinents sur 31 sont servis au seuil de 2 (contre 28), avec les memes
        8 abstentions justes sur 8, et au seuil de 3 il en reste 25 (contre 14) — le seuil n'est
        donc pas sur le fil.

        L'identite d'un mot est son RADICAL, jamais sa forme ecrite : « outil » et « outils »
        sont un mot, pas deux (defaut mesure et corrige — il laissait passer « Ajouter une icone
        dans la barre d'outils »).
        """
        from .lexique import CONCEPT

        return frozenset(
            stem(m) for m in jetons(objectif)
            if m in CONCEPT or m in self._vocabulaire or stem(m) in self._vocabulaire
        )

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
        evidence = self.mots_du_domaine(objectif)
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
                     tags=tuple(s.tags), corps=s.body)
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
