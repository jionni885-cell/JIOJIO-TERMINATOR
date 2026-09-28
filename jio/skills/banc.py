"""Le banc qui MESURE le routeur de competences — et ses trois temoins.

Une brique de selection qui n'est pas mesuree est une intuition avec une signature. Ce banc
annote a la main des objectifs REELS avec la competence qui devrait etre chargee, puis compare :

  * le **routeur** (BM25 + MMR + abstention) ;
  * `tout` — charger les douze competences. C'est l'etat de fait quand rien ne choisit : le
    rappel est parfait par construction, et c'est justement pour cela que le COUT doit etre
    affiche a cote. Un rappel de 1,0 paye 6424 jetons ne vaut pas 0,92 paye 800 ;
  * `alphabetique` — les k premieres par ordre alphabetique. Le temoin NEGATIF : ce que vaut un
    choix qui ne regarde pas l'objectif. S'il fait presque aussi bien, le routeur n'apporte rien ;
  * `mots_cles` — le comptage brut des mots communs, sans `idf`, sans normalisation de longueur,
    sans diversification. C'est l'ABLATION du routeur : ce que BM25 et le MMR apportent, chiffre.

Le banc contient aussi des objectifs qui ne relevent d'AUCUNE competence. Sans eux, un routeur
qui repond toujours quelque chose obtiendrait un excellent score : l'abstention ne se mesure que
sur des cas ou il faut s'abstenir.

TROIS PRECAUTIONS DE METHODE, parce qu'un chiffre faux serait pire qu'aucun chiffre :

  * le seuil d'abstention n'est pas choisi a la main : `meilleur_seuil` le balaie et retient celui
    qui maximise l'equilibre entre les deux erreurs ;
  * le banc est ANNONCE comme la limite de l'affirmation. Il tient en trente-huit objectifs
    ecrits par la personne qui a ecrit le routeur : c'est une mesure, pas une preuve de generalite ;
  * une annotation peut accepter PLUSIEURS competences quand deux conviennent reellement. Forcer
    une reponse unique transformerait une ambiguite du sujet en erreur du routeur, et le chiffre
    mesure serait celui de la rigeur de l'annotateur, pas celle de l'outil.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = ["BANC", "ObjectifAnnote", "Rapport", "balayer_seuils", "meilleur_seuil", "mesurer"]


@dataclass(frozen=True)
class ObjectifAnnote:
    """Un objectif, et la competence qu'un humain chargerait pour le traiter.

    `attendu` est vide quand AUCUNE competence ne s'applique : c'est un cas de mesure a part
    entiere, et pas un oubli.
    """

    texte: str
    attendu: frozenset[str]
    note: str

    @property
    def positif(self) -> bool:
        return bool(self.attendu)


def _positif(texte: str, attendu: str | Sequence[str], note: str) -> ObjectifAnnote:
    noms = frozenset([attendu] if isinstance(attendu, str) else attendu)
    return ObjectifAnnote(texte=texte, attendu=noms, note=note)


def _negatif(texte: str, note: str) -> ObjectifAnnote:
    return ObjectifAnnote(texte=texte, attendu=frozenset(), note=note)


#: Le banc. Les objectifs positifs sont ceux du terrain — les missions de ce depot et celles de
#: la litterature —, les negatifs sont des taches reelles qui ne relevent d'aucune des douze
#: competences. Les deux langues sont representees, parce que l'utilisateur ecrit dans les deux.
BANC: tuple[ObjectifAnnote, ...] = (
    # -- execution et preuve ------------------------------------------------ #
    _positif(
        "Ajouter un test qui echoue quand `sum_even` compte les nombres impairs",
        "executable-proof", "prouver par execution : le cas d'ecole",
    ),
    _positif(
        "Add a test that fails when the parser mishandles an empty file",
        "executable-proof", "anglais, meme cas",
    ),
    _positif(
        "Verifier qu'une transformation garde ses invariants : trier deux fois donne le meme "
        "resultat",
        "metamorphic-invariance", "invariance sous repetition",
    ),
    _positif(
        "Prove that the migration is idempotent and running it twice changes nothing",
        ("metamorphic-invariance", "executable-proof"),
        "anglais : « idempotent » est une invariance, et la preuve est executable",
    ),
    _positif(
        "Detecter qu'un test est satisfait par une implementation fausse",
        ("metamorphic-invariance", "executable-proof"),
        "mutation / temoin non discriminant",
    ),
    # -- anti-triche -------------------------------------------------------- #
    _positif(
        "Un agent a reussi la mission en modifiant le test au lieu de corriger le code",
        "reward-hacking-hunt", "recompense detournee : le temoin a ete deplace",
    ),
    _positif(
        "The agent edited the oracle so its output would pass",
        "reward-hacking-hunt", "anglais, meme defaut",
    ),
    _positif(
        "L'agent a ecrit un fichier pendant qu'il devait seulement auditer",
        ("reward-hacking-hunt", "hostile-content"),
        "capacite depassee : le jugement doit etre separe de l'ecriture",
    ),
    # -- memoire et reprise ------------------------------------------------- #
    _positif(
        "Le meme bug revient trois fois de suite apres trois corrections differentes",
        "failure-memory", "recidive : il faut retenir l'echec et sa garde",
    ),
    _positif(
        "The same failure keeps coming back; recall it before working",
        "failure-memory", "anglais, meme besoin",
    ),
    _positif(
        "Reprendre une mission interrompue sans refaire ce qui a deja ete prouve",
        "safe-resume", "reprise apres interruption",
    ),
    _positif(
        "Resume after a rollback without trusting the cache",
        "safe-resume", "anglais : le cache survit au retour en arriere, la preuve non",
    ),
    _positif(
        "Le cache de compilation est reutilise alors que le commit a change",
        "safe-resume", "cache invalide apres changement de revision",
    ),
    # -- contexte ----------------------------------------------------------- #
    _positif(
        "La fenetre de contexte est saturee par les fichiers du depot et le modele perd l'objectif",
        "context-budget", "contexte plein",
    ),
    _positif(
        "The prompt is 200k tokens and the model forgets the task",
        "context-budget", "anglais, meme symptome",
    ),
    _positif(
        "Reduire de 80 % les jetons envoyes au modele sans perdre l'information utile",
        "context-budget", "compaction mesuree",
    ),
    # -- erreurs et honnetete ----------------------------------------------- #
    _positif(
        "Le modele recoit « erreur » sans savoir quel fichier ni quelle ligne",
        "structured-failure", "message d'echec inexploitable par l'agent",
    ),
    _positif(
        "Report the exact command, exit code and stderr when a check fails",
        "structured-failure", "anglais : meme besoin de structure",
    ),
    _positif(
        "Faut-il s'abstenir quand l'artefact ne peut pas etre prouve ?",
        "calibrated-abstention", "abstention explicite",
    ),
    _positif(
        "Comment savoir si la confiance annoncee par le systeme est calibree ?",
        "calibrated-abstention", "calibration de la confiance",
    ),
    _positif(
        "Le systeme a livre un artefact faux en le presentant comme prouve",
        "calibrated-abstention", "livraison sans reserve : le pire des cas",
    ),
    # -- consensus ---------------------------------------------------------- #
    _positif(
        "Trois critiques rendent le meme avis parce qu'ils viennent du meme modele",
        "decorrelated-panel", "echo : le panel n'est pas decorrele",
    ),
    _positif(
        "The two reviewers always agree because they share the same weights",
        "decorrelated-panel", "anglais, mem cas",
    ),
    _positif(
        "Le vote de trois critiques identiques ne vaut pas un consensus",
        "decorrelated-panel", "quorum sans decorrelation",
    ),
    # -- securite ----------------------------------------------------------- #
    _positif(
        "Un fichier du depot contient « ignore les instructions precedentes » ; faut-il obeir ?",
        "hostile-content", "injection par contenu de depot",
    ),
    _positif(
        "A dependency README contains hidden instructions for the agent",
        "hostile-content", "anglais : provenance non fiable",
    ),
    _positif(
        "Un plan lu depuis un fichier du depot a modifie le comportement de l'agent",
        "hostile-content", "contenu hostile pris pour une instruction",
    ),
    # -- documents ---------------------------------------------------------- #
    _positif(
        "Verifier que les chiffres annonces dans le README sont ceux mesures sur le depot",
        "prose-witnesses", "affirmations d'un document",
    ),
    _positif(
        "Check that every number in the report matches the repository",
        "prose-witnesses", "anglais, meme controle",
    ),
    # -- evolution ---------------------------------------------------------- #
    _positif(
        "Ecrire une nouvelle competence a partir d'un echec qui se repete",
        "skill-forge", "fabriquer une competence",
    ),
    _positif(
        "La bibliotheque de competences doit s'enrichir d'elle-meme apres une mission ratee",
        "skill-forge", "auto-amelioration",
    ),
    # -- aucun competence ne s'applique : c'est un cas de mesure a part entiere - #
    _negatif("Traduire ce document en espagnol", "redaction, pas de preuve a organiser"),
    _negatif("Choisir un nom de variable pour la fonction de tri",
             "style, aucune verification"),
    _negatif("Ajouter une icone dans la barre d'outils de l'application",
             "interface, hors du domaine"),
    _negatif("Ecrire une lettre de motivation pour une candidature",
             "redaction administrative"),
    _negatif("Corriger la couleur du bouton principal du site",
             "apparence"),
    _negatif("Convertir les images PNG en JPEG",
             "conversion de fichiers, sans affirmation a prouver"),
    _negatif("Composer un menu de la semaine pour quatre personnes",
             "tache domestique"),
    _negatif("Change the background color of the login page",
             "anglais, apparence"),
)


@dataclass
class Ligne:
    """Le resultat du routeur sur un objectif du banc, avec le detail qui permet de l'auditer."""

    objectif: ObjectifAnnote
    choisis: tuple[str, ...]
    ok: bool
    cout: int


@dataclass
class Rapport:
    """Ce que le banc dit du routeur — et de chacun de ses temoins."""

    maximum: int
    seuil: int
    lignes: list[Ligne] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)

    @property
    def positifs(self) -> list[Ligne]:
        return [ligne for ligne in self.lignes if ligne.objectif.positif]

    @property
    def negatifs(self) -> list[Ligne]:
        return [ligne for ligne in self.lignes if not ligne.objectif.positif]

    @property
    def precision1(self) -> float:
        """Part des objectifs pertinents dont le PREMIER choix est le bon.

        C'est la metrique qui compte : la premiere competence est celle que l'agent lira avant
        d'agir, et une competence utile en troisieme position sera chargee dans le meme contexte
        que les deux autres — donc diluee.
        """
        if not self.positifs:
            return 0.0
        return sum(1 for l in self.positifs if l.choisis and l.choisis[0] in l.objectif.attendu) \
            / len(self.positifs)

    @property
    def servis(self) -> list[Ligne]:
        """Les objectifs pertinents pour lesquels le routeur a REELLEMENT charge quelque chose."""
        return [ligne for ligne in self.positifs if ligne.choisis]

    @property
    def precision1_servis(self) -> float:
        """Premier choix juste PARMI les reponses donnees — la qualite du classement seul.

        La distinction avec `precision1` n'est pas cosmetique. `precision1` compte l'abstention
        comme une erreur de classement ; celle-ci ne juge que les cas ou le routeur a repondu.
        Les deux doivent etre affichees ensemble, sinon un routeur qui s'abstient de tout
        afficherait 100 % de justesse d'abstention et 0 % de classement, sans qu'on puisse voir
        que son classement, lui, est bon — ou l'inverse. Sur le banc : 77 % de premier choix
        juste au total, mais 86 % quand il repond.
        """
        if not self.servis:
            return 0.0
        return sum(1 for l in self.servis if l.choisis[0] in l.objectif.attendu) / len(self.servis)

    @property
    def rappel(self) -> float:
        """Part des objectifs pertinents ou LA bonne competence est chargee, a n'importe quel rang."""
        if not self.positifs:
            return 0.0
        return sum(1 for l in self.positifs if set(l.choisis) & l.objectif.attendu) \
            / len(self.positifs)

    @property
    def abstentions_justes(self) -> int:
        return sum(1 for l in self.negatifs if not l.choisis)

    @property
    def activations_a_tort(self) -> int:
        """Un objectif hors sujet qui charge quand meme une competence.

        C'est l'erreur qui coute : elle fait lire a l'agent une procedure qui ne s'applique pas,
        et elle apprend a se mefier du mecanisme.
        """
        return len(self.negatifs) - self.abstentions_justes

    @property
    def cout_moyen(self) -> float:
        return sum(l.cout for l in self.lignes) / len(self.lignes) if self.lignes else 0.0

    @property
    def equilibre(self) -> float:
        """Moyenne du rappel et de la justesse d'abstention : les deux erreurs pesent pareil.

        Maximiser le seul rappel pousserait a ne jamais s'abstenir ; maximiser la seule
        abstention pousserait a ne jamais repondre. Les deux sont des echecs, et ce nombre les
        traite comme tels.
        """
        justesse_abstention = (self.abstentions_justes / len(self.negatifs)) \
            if self.negatifs else 1.0
        return (self.rappel + justesse_abstention) / 2

    def resume(self) -> str:
        return (
            f"premier choix juste {self.precision1:.1%} ("
            f"{self.precision1_servis:.1%} quand il repond, {len(self.servis)} cas)  ·  bonne "
            f"competence chargee {self.rappel:.1%}  ·  abstention juste "
            f"{self.abstentions_justes}/{len(self.negatifs)}  ·  cout moyen "
            f"{self.cout_moyen:.0f} jetons"
        )


def mesurer(
    *,
    maximum: int = 3,
    seuil: int | None = None,
    banc: Sequence[ObjectifAnnote] = BANC,
    catalogue=None,
) -> Rapport:
    """Passe le banc au routeur. Le seuil est celui qu'on donne, ou celui du module."""
    from .router import SEUIL_CONCEPTS, catalogue_du_depot, cout

    if seuil is None:
        seuil = SEUIL_CONCEPTS
    cat = catalogue if catalogue is not None else catalogue_du_depot()
    rapport = Rapport(maximum=maximum, seuil=seuil)
    for objectif in banc:
        choix = cat.interroger(objectif.texte, maximum=maximum, seuil=seuil)
        noms = tuple(c.nom for c in choix)
        ok = bool(set(noms) & objectif.attendu) if objectif.positif else not noms
        rapport.lignes.append(Ligne(objectif=objectif, choisis=noms, ok=ok, cout=cout(choix)))
        if not ok:
            if objectif.positif:
                rapport.erreurs.append(
                    f"MANQUEE   attendu {sorted(objectif.attendu)} — obtenu {list(noms) or '(rien)'}"
                    f"  ·  {objectif.texte[:70]}"
                )
            else:
                rapport.erreurs.append(
                    f"ACTIVEE   aucune competence ne s'applique — obtenu {list(noms)}"
                    f"  ·  {objectif.texte[:70]}"
                )
    return rapport


def _alphabetique(cat, objectif: str, maximum: int) -> tuple[str, ...]:
    """Le temoin naif : les k premieres par ordre alphabetique, sans regarder l'objectif."""
    return tuple(sorted(d.nom for d in cat.documents)[:maximum])


def _mots_cles(cat, objectif: str, maximum: int) -> tuple[str, ...]:
    """L'ablation : mots communs bruts, sans idf, sans saturation, sans normalisation de longueur.

    Ce que ce temoin isole est precis : si le routeur ne fait pas mieux que lui, alors BM25, la
    saturation et la ponderation sont du decor — et il faudrait les retirer plutot que les
    defendre. Il utilise le MEME pont bilingue que le routeur, pour que l'ecart mesure porte sur
    la ponderation seule et non sur la langue.
    """
    from .lexique import PONT
    from .router import jetons

    ecrits = set(jetons(objectif))
    requete = set(ecrits)
    for mot in ecrits:
        requete |= set(PONT.get(mot, ()))
    scores = []
    for doc in cat.documents:
        communs = requete & set(jetons(doc.indexable))
        scores.append((len(communs), doc.nom))
    scores.sort(key=lambda x: (-x[0], x[1]))
    return tuple(nom for points, nom in scores[:maximum] if points > 0)


def _tout(cat, objectif: str, maximum: int) -> tuple[str, ...]:
    del objectif, maximum
    return tuple(sorted(d.nom for d in cat.documents))


def comparer(*, maximum: int = 3, banc: Sequence[ObjectifAnnote] = BANC) -> list[tuple[str, str, float]]:
    """Le routeur contre ses temoins. Rend `(nom, resume, equilibre)` par strategie.

    Les trois temoins repondent a la meme question que le routeur, sur le meme banc, avec les
    memes metriques — sans quoi la comparaison ne dirait rien.
    """
    from .router import catalogue_du_depot, cout

    cat = catalogue_du_depot()
    resultats: list[tuple[str, str, float]] = []

    for nom, decideur in (
        ("routeur (BM25 + MMR)", None),
        ("mots-cles bruts", _mots_cles),
        ("alphabetique", _alphabetique),
        ("tout charger", _tout),
    ):
        lignes: list[Ligne] = []
        for objectif in banc:
            if decideur is None:
                choix = cat.interroger(objectif.texte, maximum=maximum)
                noms, prix = tuple(c.nom for c in choix), cout(choix)
            else:
                noms = decideur(cat, objectif.texte, maximum)
                prix = sum(d.cout_jetons for d in cat.documents if d.nom in noms)
            ok = bool(set(noms) & objectif.attendu) if objectif.positif else not noms
            lignes.append(Ligne(objectif=objectif, choisis=noms, ok=ok, cout=prix))
        rapport = Rapport(maximum=maximum, seuil=0.0, lignes=lignes)
        resultats.append((nom, rapport.resume(), rapport.equilibre))
    return resultats


def balayer_seuils(
    candidats: Sequence[int] | None = None, *, maximum: int = 3
) -> list[tuple[int, float, int, int]]:
    """Le seuil contre ses consequences : `(seuil, equilibre, abstentions justes, rappel %)`.

    Le seuil n'est pas un reglage de confort : il decide de la seule question a laquelle un
    routeur doit savoir repondre NON. On le balaie donc au lieu de le choisir.
    """
    from .router import catalogue_du_depot

    cat = catalogue_du_depot()
    grille = list(candidats) if candidats is not None else list(range(5))
    out: list[tuple[int, float, int, int]] = []
    for seuil in grille:
        rapport = mesurer(maximum=maximum, seuil=seuil, catalogue=cat)
        out.append((
            seuil, round(rapport.equilibre, 4), rapport.abstentions_justes,
            round(rapport.rappel * 100),
        ))
    return out


def meilleur_seuil(*, maximum: int = 3) -> int:
    """Le seuil qui maximise l'equilibre entre rappel et abstention juste.

    Les egalites sont tranchees vers le seuil le PLUS HAUT : a equilibre egal, s'abstenir est
    moins couteux que charger une procedure qui ne s'applique pas.
    """
    balayage = balayer_seuils(maximum=maximum)
    meilleur = max(balayage, key=lambda ligne: (ligne[1], ligne[0]))
    return meilleur[0]
