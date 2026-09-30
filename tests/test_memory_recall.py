"""Le classement des souvenirs, mesure : BM25 contre le recouvrement de mots.

Pourquoi ce test existe
-----------------------
`FailureMemory.recall()` repond a une seule question : *ce nouvel echec est-il deja
arrive ?* Une reponse fausse coute cher des deux cotes — un souvenir pertinent non
rappele fait repayer l'erreur, un souvenir hors sujet injecte dans le prompt la
fait commettre.

Le corpus est construit ici, pas importe : il faut une verite terrain. Il est
**realiste** (vocabulaire du depot, objectifs en francais, identifiants techniques
au milieu du texte) et **piege** a dessein : chaque requete partage l'essentiel de
ses mots avec des souvenirs SANS RAPPORT, et un seul mot — l'identifiant technique —
dit lequel est le bon. C'est exactement le regime ou le recouvrement de mots se
trompe : il recompense ce que les textes ont en commun, pas ce qui les distingue.

Les chiffres sont IMPRIMES et verifies : un test qui affirme « c'est mieux » sans
donner le nombre ne prouve rien.
"""

from __future__ import annotations

from jio.learn.recall import jaccard, normalized_bm25, terms

# -- le corpus ------------------------------------------------------------------ #
# Deux familles de souvenirs. Les CIBLES portent un identifiant technique unique ;
# les DISTRACTEURS reprennent mot pour mot le vocabulaire des cibles (objective
# generique, symptom generique) et n'ont aucune raison d'etre rappeles.

_GENERIQUES = (
    "corriger un echec de la porte de lint sur le paquet jio pendant une mission",
    "le rapport de coherence signale un compteur faux dans le readme du depot",
    "une mesure de cycle plante quand le fichier de cumul est deja rempli",
    "le verrou de la memoire n'est pas retire apres un echec de la mesure",
    "un souvenir sans remede observe reste en attente dans la memoire des echecs",
)

_CIBLES: tuple[tuple[str, str, str], ...] = (
    ("la porte de lint refuse le paquet jio a cause d'une f-string sans emplacement",
     "le controle F541 signale une f-string sans emplacement",
     "ruff F541 exige de retirer le prefixe f quand aucun emplacement n'est utilise"),
    ("la mesure de cycle ne retrouve pas ses paires apres une reprise sur disque",
     "le cumul JSONL relu n'a plus les dissociations chaud_seul",
     "les compteurs de dissociation doivent etre ecrits dans le JSONL du cumul"),
    ("deux mesures simultanees rejouent les memes graines sur le meme fichier",
     "le second processus ecrit dans le cumul pendant le premier",
     "le verrou O_EXCL du fichier de cumul doit refuser la seconde mesure"),
    ("le test apparie n'est pas fait alors que le plan experimental est apparie",
     "le verdict exige l'intervalle non apparie au lieu de mcnemar_exact",
     "le verdict doit exiger la tranche appariee et non la tranche cumulee"),
    ("une competence installee s'ecrit par dessus un fichier que l'agent a edite",
     "l'installation de la skill PRESERVE ne respecte pas la copie editee",
     "l'installateur doit comparer l'empreinte avant de PRESERVER un fichier"),
    ("une accalmie de la memoire est lue comme une preuve que le levier ne sert pas",
     "le rapport annonce PLATEAU sans dire que la portee etait nulle",
     "le rapport doit dire la portee du levier et la borne de l'effet attendu"),
    ("le compteur de tests du readme n'est relu par personne",
     "le readme annonce un nombre de tests verts qui n'existe plus",
     "jio chiffres doit relire les compteurs et les reecrire par --appliquer"),
    ("le journal de la memoire peut etre reecrit discretement entre deux runs",
     "la chaine de hachage du journal ne detecte pas la reecriture",
     "la memoire doit etre verifiee par chaine de hachage avant chaque lecture"),
    ("un contenu externe fabrique un bloc de memoire en recopiant les marqueurs",
     "un fichier du depot contient PAST FAILURES ON SIMILAR TASKS",
     "les marqueurs reserves doivent etre retires de tout contenu externe"),
    ("le budget de mesure est calcule comme si les deux bras etaient independants",
     "essais_requis surestime le nombre de paires necessaires",
     "le budget doit partir du taux de dissociation observe, pas des deux taux"),
    ("la preuve par coupure ne survit pas a un kill pendant le second cycle",
     "un kill -9 en plein cycle laisse un cumul vide",
     "chaque cycle doit etre ecrit des qu'il est mesure, jamais en fin de run"),
    ("le bail du planificateur autonome ne se libere pas apres une erreur",
     "le bail du plan autonome reste pose pour le run suivant",
     "le bail doit etre rendu dans un finally, meme si le cycle echoue"),
    ("le rappel de memoire classe par recouvrement de mots et se trompe de souvenir",
     "le score de jaccard rappelle un distractor au lieu de la cible",
     "le classement doit ponderer les termes par leur rarete, comme bm25"),
    ("le bras temoin ne mesure pas le meme nombre de missions que le bras chaud",
     "l'artefact froid temoin n'est pas nul et le bruit est compte comme un effet",
     "le bras temoin doit jouer les memes taches avec la meme largeur de tirage"),
    ("un echec est enregistre sans garde, donc il sera repaye",
     "le souvenir ne contient aucun controle qui echoue si l'erreur revient",
     "un enregistrement sans garde doit etre refuse, pas ecrit"),
    ("l'oracle executif valide un patch qui ne change pas la sortie attendue",
     "la verification binaire accepte un patch qui ne corrige rien",
     "l'oracle doit comparer la sortie exacte, pas la presence d'un fichier"),
    ("la largueur de tirage de la generation est confondue avec la competence reelle",
     "l'ecart observe est lu comme la competence du modele",
     "le gain declare se calcule sur la competence, pas sur le taux observe"),
    ("le budget de contexte des artefacts natifs depasse la limite du modele",
     "claude md fait plus de cent cinquante lignes",
     "les artefacts doivent tenir sous la limite de contexte declaree"),
    ("l'audit des competences ne detecte pas un skill qui exploite le rollback",
     "la competence malveillante est installee sans controle",
     "l'audit doit refuser une competence qui touche au rollback de l'agent"),
    ("le cache du routeur sert une reponse d'un autre objectif",
     "la cle de cache du routeur ne contient pas l'objectif",
     "la cle de cache doit inclure l'objectif complet et la version du prompt"),
    ("le rapport de la commande tasks s'arrete sur une exception au lieu d'un code",
     "cmd_tasks leve une erreur quand le registre est vide",
     "une commande sans matiere doit rendre le code indetermine, pas une trace"),
)


def _textes_souvenirs() -> list[str]:
    """Le texte de CHAQUE souvenir, cibles puis distracteurs — source unique du corpus.

    `_corpus()` en derive les jetons, et le test de bout en bout en derive les
    enregistrements reels : les deux mesurent donc exactement les memes textes.
    """
    textes = [f"{objectif} {symptome} {cause}" for objectif, symptome, cause in _CIBLES]
    for i in range(40):
        generique = _GENERIQUES[i % len(_GENERIQUES)]
        # Les distracteurs REPETENT le vocabulaire generique : c'est ce qui les rend
        # dangereux pour un score qui compte les mots plutot que leur rarete.
        textes.append(
            f"{generique} correction du probleme numero {i} dans le depot jio "
            f"memoire mesure cycle rapport porte lint souvenir mission paquet"
        )
    return textes


def _corpus() -> tuple[list[list[str]], list[int], list[str]]:
    """Rend (documents, index de la cible de chaque requete, requetes)."""
    documents = [terms(texte) for texte in _textes_souvenirs()]
    cibles = list(range(len(_CIBLES)))
    requetes = [
        f"corriger l'echec de la porte de lint dans le paquet jio pendant une mission : {symptome}"
        for _, symptome, _ in _CIBLES
    ]
    return documents, cibles, requetes


def _classer_depuis(scores_par_requete, cibles: list[int], k: int) -> list[int | None]:
    """Rang de la cible dans chaque classement ; None si aucun document classe."""
    rangs: list[int | None] = []
    for scores, cible in zip(scores_par_requete, cibles):
        ordre = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        ordre = [i for i in ordre if scores[i] > 0.0]
        rangs.append(ordre.index(cible) + 1 if cible in ordre[:k] else None)
    return rangs


def _metriques(nom: str, classements: list[list[float]], cibles: list[int]) -> dict:
    r1 = _classer_depuis(classements, cibles, 1)
    r3 = _classer_depuis(classements, cibles, 3)
    recall1 = sum(1 for r in r1 if r == 1) / len(cibles)
    recall3 = sum(1 for r in r3 if r is not None) / len(cibles)
    # MRR : moyenne des inverses du rang, 0 quand la cible n'est nulle part.
    mrr = 0.0
    for scores, cible in zip(classements, cibles):
        ordre = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        ordre = [i for i in ordre if scores[i] > 0.0]
        mrr += (1.0 / (ordre.index(cible) + 1)) if cible in ordre else 0.0
    mrr /= len(cibles)
    return {"nom": nom, "recall1": recall1, "recall3": recall3, "mrr": mrr}


def test_bm25_classe_mieux_que_le_recouvrement_de_mots(capsys) -> None:
    """Le constat chiffre : le classement par rarete retrouve le bon souvenir.

    Chaque requete ne differe des distracteurs que par UN identifiant technique
    (`F541`, `mcnemar_exact`, `O_EXCL`) : un score qui compte les mots communs voit
    d'abord les distracteurs, qui partagent tout le reste. Le chiffre est imprime
    pour etre relu, pas affirme.
    """
    documents, cibles, requetes = _corpus()
    temoin = [jaccard(terms(q), documents) for q in requetes]
    candidat = [normalized_bm25(terms(q), documents) for q in requetes]

    mesures = [
        _metriques("recouvrement de mots (Jaccard)", temoin, cibles),
        _metriques("BM25 normalise (rarete + saturation)", candidat, cibles),
    ]
    # Les compteurs sont CALCULES : un libelle en dur redevient faux au premier ajout
    # de cas, et c'est exactement ce que ce depot verifie ailleurs (`jio chiffres`).
    lignes = [
        "",
        f"  CLASSEMENT DES SOUVENIRS — {len(documents)} souvenirs, {len(cibles)} requetes, "
        f"1 cible par requete",
    ]
    for m in mesures:
        lignes.append(
            f"    {m['nom']:<40} recall@1 {m['recall1']:.0%}   recall@3 {m['recall3']:.0%}   "
            f"MRR {m['mrr']:.3f}"
        )
    print("\n".join(lignes))
    with capsys.disabled():
        print("\n".join(lignes))

    jac, bm = mesures
    assert bm["recall1"] > jac["recall1"], (
        f"BM25 doit retrouver la cible au premier rang plus souvent que le recouvrement "
        f"de mots ({bm['recall1']:.0%} contre {jac['recall1']:.0%})"
    )
    assert bm["recall1"] >= 0.85, (
        f"un classement qui retrouve la cible dans {bm['recall1']:.0%} des cas ne merite "
        f"pas de remplacer l'ancien"
    )


def test_le_recall_de_la_MEMOIRE_retrouve_le_bon_souvenir(tmp_path) -> None:
    """Bout en bout : ce n'est pas le score qui compte, c'est le souvenir injecte.

    Le banc precedent mesure un classement ; celui-ci mesure la CONSEQUENCE. Les 60
    souvenirs passent par la vraie `FailureMemory` (donc par `_assainir`, le journal
    chaine et la relecture disque), et chaque requete doit ramener SON souvenir au
    premier rang — c'est ce bloc qui part dans le prompt de generation.

    Mesure avant cablage : **5 %** (le recouvrement de mots ramenait un distractor
    du meme sous-systeme, donc la memoire citait la mauvaise cause et le mauvais
    garde tout en ayant l'air de fonctionner).
    """
    from jio.learn.memory import FailureMemory

    textes = _textes_souvenirs()
    memoire = FailureMemory(path=tmp_path / "m.jsonl")
    for texte in textes:
        # Un souvenir par texte, y compris les 40 distracteurs : c'est la memoire
        # ENCOMBREE qui est le regime reel (plusieurs echecs d'un meme sous-systeme).
        memoire.record(objective=texte, symptom="", root_cause="",
                       correct_fix="remede de test", guard="controle de test")
    assert memoire.size == len(textes)

    _, cibles, requetes = _corpus()
    justes = 0
    for requete, cible in zip(requetes, cibles):
        trouve = memoire.recall(requete, limit=1)
        if trouve and trouve[0].objective == textes[cible]:
            justes += 1
        else:
            rate = trouve[0].objective[:52] if trouve else "rien"
            print(f"    rate : {textes[cible][:52]!r} -> {rate!r}")
    taux = justes / len(cibles)
    print(f"\n  MEMOIRE REELLE — recall@1 sur {len(cibles)} requetes : {taux:.0%}")
    assert taux >= 0.95, (
        f"la memoire doit retrouver le bon souvenir dans 95 % des cas, pas {taux:.0%} : "
        f"le bloc injecte citerait la mauvaise cause"
    )


def test_le_corpus_est_un_CONTROLE_et_non_un_piege(capsys) -> None:
    """Verification anti-triche : le temoin doit gagner quand la tache est facile.

    Un banc ou l'ancien score perd 100 % des cas est un banc suspect — il peut etre
    fabrique pour ca. On mesure donc AUSSI un corpus « jumeau » : chaque cible a un
    sosie qui ne differe QUE par l'identifiant, les deux textes ayant la meme
    longueur et le meme vocabulaire generique. Si le recouvrement de mots y reussit
    (et il doit reussir : un jeton de difference sur trente reste le meilleur score
    de Jaccard), alors l'echec du premier corpus ne vient pas du banc : il vient du
    regime ou plusieurs souvenirs partagent le vocabulaire d'un meme sous-systeme.
    """
    cibles = [terms(f"{o} {s}") for o, s, _ in _CIBLES]
    sosies = [
        terms(f"{o} {s.replace(s.split()[2], 'zzz999')} probleme numero {i} dans le depot jio")
        for i, (o, s, _) in enumerate(_CIBLES)
    ]
    documents = [t for paire in zip(cibles, sosies) for t in paire]
    index = [2 * i for i in range(len(cibles))]
    requetes = [f"{o} {s}" for o, s, _ in _CIBLES]

    temoin = _metriques("Jaccard sur le corpus jumeau",
                        [jaccard(terms(q), documents) for q in requetes], index)
    candidat = _metriques("BM25 sur le corpus jumeau",
                          [normalized_bm25(terms(q), documents) for q in requetes], index)
    lignes = ["", "  CONTROLE — corpus jumeau (le sosie ne differe que par l'identifiant)"]
    for m in (temoin, candidat):
        lignes.append(f"    {m['nom']:<34} recall@1 {m['recall1']:.0%}   "
                      f"recall@3 {m['recall3']:.0%}   MRR {m['mrr']:.3f}")
    print("\n".join(lignes))
    with capsys.disabled():
        print("\n".join(lignes))

    assert temoin["recall1"] >= 0.8, (
        "sur ce corpus-la, l'ancien score DOIT reussir : sinon le premier banc ne mesure "
        f"pas la ponderation par la rarete mais un corpus truque ({temoin['recall1']:.0%})"
    )
    assert candidat["recall1"] >= temoin["recall1"]


def test_le_seuil_de_pertinence_garde_son_sens() -> None:
    """Le score normalise doit valoir ~1 pour la cible et rester bas pour un hors-sujet.

    C'est ce qui autorise `min_score` a rester un seuil unique : un score brut de
    BM25 depend du nombre de termes de la requete et de leurs IDF, donc un seuil
    dessus se deplace en silence d'une requete a l'autre.
    """
    documents = [
        terms("le verrou O_EXCL du fichier de cumul refuse la seconde mesure"),
        terms("corriger un echec de la porte de lint dans le paquet jio pendant une mission"),
    ]
    scores = normalized_bm25(
        terms("le verrou du fichier de cumul refuse la seconde mesure pendant la mission"),
        documents,
    )
    # Le plafond theorique n'est atteint qu'a frequence infinie : un document qui
    # contient tous les termes de la requete UNE fois atteint la moitie du plafond.
    # C'est cette echelle qu'un seuil doit utiliser — d'ou la normalisation.
    assert scores[0] > 0.3, f"la cible doit couvrir la majeure partie de la requete : {scores}"
    assert scores[0] > 3 * scores[1], f"un hors-sujet doit rester loin derriere : {scores}"
    assert all(0.0 <= s <= 1.0 for s in scores), "le score doit rester dans [0, 1]"


def test_un_terme_absent_ne_donne_aucun_score() -> None:
    """Aucun mot commun : aucun souvenir. Un classement qui rend tout le monde
    pertinent est un classement qui injecte du hors-sujet dans le prompt."""
    documents = [terms("le verrou du fichier de cumul refuse la seconde mesure")]
    assert normalized_bm25(terms("traduire ce texte en espagnol"), documents) == [0.0]


def test_la_rarete_pese_plus_que_la_repetition() -> None:
    """Le coeur de BM25, verifie sur un cas ou le recouvrement se trompe.

    Un document qui repete dix fois un mot generique partage moins de points qu'un
    document qui contient UNE fois l'identifiant rare de la requete. Sans l'IDF,
    c'est la repetition qui gagne — et la memoire rappelle le mauvais souvenir.
    """
    bavard = terms(" ".join(["memoire"] * 10))
    precis = terms("memoire f541")
    scores = normalized_bm25(terms("corriger la memoire : le controle f541 refuse le patch"),
                             [bavard, precis])
    assert scores[1] > scores[0], f"la rarete doit battre la repetition : {scores}"
