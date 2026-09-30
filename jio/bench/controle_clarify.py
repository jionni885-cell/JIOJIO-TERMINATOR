"""Jeu de CONTROLE de la porte de clarification : des objectifs d'un AUTRE projet.

Pourquoi ce jeu existe
----------------------
Le banc du depot (`jio/bench/objectifs.py`, 41 objectifs) cite les chemins de CE depot
(« corriger jio/verify/entropy.py : `_numeric_equal` doit rendre False... »). La porte a donc
ete reglee sur ce vocabulaire, et le banc ne peut pas dire si elle fonctionne sur le projet de
quelqu'un d'autre — c'est-a-dire dans l'usage reel, puisque l'outil se pose sur n'importe quel
depot (`jio start`).

Les objectifs ci-dessous viennent d'un projet IMAGINAIRE mais plausible : application web,
pipeline de donnees, infrastructure, documentation. Aucun ne cite un chemin de ce depot.

Comment l'etiquette est decidee — et la limite
----------------------------------------------
La question posee pour chaque cas est celle qui compte pour l'utilisateur :

    « Un ingenieur competent devrait-il DEMANDER quelque chose avant de commencer ? »

Reponse oui -> la porte doit poser au moins une question (sinon elle laisse partir une IA sur
un perimetre invente). Reponse non -> elle ne doit rien poser (sinon elle interroge au lieu de
travailler). Les cas « non » portent tous une ACTION, une CIBLE et un CRITERE explicites.

La langue est une DONNEE du cas, jamais une deduction. Le premier jet la devinait a la presence
d'accents : or ce depot ecrit le francais sans accents dans le code, le jeu a suivi cette
convention, et onze cas sur vingt-deux se sont retrouves dans la mauvaise langue — la mesure
affichait alors « 0 % en francais », un chiffre faux produit par la mesure elle-meme et non par
la porte mesuree. Un calcul sur une etiquette devinee n'est pas une mesure.

LIMITE DECLAREE : ecrit par la meme personne que la porte, comme le banc. Ce n'est pas une
evaluation independante — c'est un jeu de CONTROLE sur un domaine que le banc ne couvre pas.
"""

from __future__ import annotations

__all__ = ["AMBIGUS", "ACTIONNABLES", "CAS", "mesurer_controle", "resume_controle"]

#: Cas ou une question est NECESSAIRE : (objectif, ce qui manque, langue).
AMBIGUS: tuple[tuple[str, str, str], ...] = (
    ("ameliore la page de connexion",
     "quel critere ? pour qui ? quelle partie ?", "fr"),
    ("rends le service plus rapide",
     "quel service, et mesure en quoi ?", "fr"),
    ("refactorise le module de paiement",
     "vers quoi, et quel critere de reussite ?", "fr"),
    ("mets en place la CI",
     "quelle plateforme, quels controles, bloquante ou non ?", "fr"),
    ("nettoie le depot",
     "quels fichiers, selon quel critere ?", "fr"),
    ("documente l'API",
     "quel format, quelle audience, ou ?", "fr"),
    ("corrige les bugs signales cette semaine",
     "lesquels, et par ordre de priorite ?", "fr"),
    ("ajoute des tests",
     "sur quoi, combien, et a quel seuil de couverture ?", "fr"),
    ("make the dashboard better",
     "better along which axis, judged by what?", "en"),
    ("clean up the data pipeline",
     "which stage, and what counts as clean?", "en"),
    ("improve error handling across the app",
     "where exactly, and to what standard?", "en"),
    ("set up monitoring",
     "for what, with which alerts, at which threshold?", "en"),
)

#: Cas ACTIONNABLES : (objectif, ce qui le rend actionnable, langue). La porte doit laisser
#: partir au travail sans poser une seule question.
ACTIONNABLES: tuple[tuple[str, str, str], ...] = (
    ("corrige `src/parser.py` : `parse_date` doit lever ValueError sur une date vide, "
     "avec un test dans `tests/test_parser.py` qui le prouve",
     "action + cible + critere + preuve demandee", "fr"),
    ("remplace `requests` par `httpx` dans `src/http.py` et mets a jour `requirements.txt` "
     "pour que `pip install -r requirements.txt` installe httpx",
     "action + deux cibles + critere executable", "fr"),
    ("dans `app/models.py`, rends `User.email` unique au niveau de la base et ajoute la "
     "migration correspondante dans `migrations/`",
     "action + cible + critere observable", "fr"),
    ("ajoute dans `tests/test_api.py` un test qui verifie que `/health` repond 200 quand la "
     "base est joignable et 503 sinon",
     "action + cible + critere exact", "fr"),
    ("supprime la dependance `lodash` du fichier `package.json` et remplace ses trois usages "
     "dans `src/utils/format.ts` par des fonctions locales, en gardant les tests verts",
     "action + cible + critere (tests verts)", "fr"),
    ("renomme la colonne `user_id` en `account_id` dans `db/schema.sql`, avec la migration "
     "`migrations/003_rename.sql` et la mise a jour des requetes de `src/queries.py`",
     "action + cible + critere structurel", "fr"),
    ("In `api/routes.py`, return 429 with a `Retry-After: 60` header when the caller exceeds "
     "100 requests per minute, and cover it in `tests/test_limits.py`",
     "action + target + exact criterion", "en"),
    ("Reduce the Docker image size below 200 MB by switching `Dockerfile` from the full "
     "`python:3.11` base to `python:3.11-slim`, keeping `docker compose up` working",
     "action + target + measurable criterion", "en"),
    ("Write `docs/install.md` explaining the three install steps for Ubuntu 22.04, in under "
     "60 lines, with the exact commands",
     "action + target + format + length criterion", "en"),
    ("Add a `--dry-run` flag to `scripts/deploy.py` that prints the commands instead of "
     "running them, and test it in `tests/test_deploy.py`",
     "action + target + criterion", "en"),
)

#: Tout le jeu : (objectif, une question est-elle necessaire, langue).
CAS: tuple[tuple[str, bool, str], ...] = (
    *((texte, True, langue) for texte, _, langue in AMBIGUS),
    *((texte, False, langue) for texte, _, langue in ACTIONNABLES),
)


def _mesurer_langue(langue: str) -> float:
    """Taux de bonnes reponses sur une langue : la porte lit deux tables d'actions."""
    from ..clarify import analyser

    sous_ensemble = [
        (texte, attendu) for texte, attendu, cas_langue in CAS if cas_langue == langue
    ]
    if not sous_ensemble:
        return 0.0
    justes = sum(
        1 for texte, attendu in sous_ensemble if bool(analyser(texte).questions) == attendu
    )
    return justes / len(sous_ensemble)


def mesurer_controle() -> dict[str, object]:
    """Mesure la porte sur ce jeu : les deux sens, langue par langue.

    Le sens qui compte le plus est le SECOND a l'usage : une porte qui pose une question sur un
    objectif actionnable coute du temps a chaque mission, et c'est le defaut qui fait
    desactiver l'outil. Mais un faux NEGATIF est pire en consequence : il laisse partir une IA
    sur un perimetre invente.
    """
    from ..clarify import analyser

    vrais_positifs = faux_negatifs = faux_positifs = vrais_negatifs = 0
    erreurs: list[str] = []
    for texte, question_attendue, _langue in CAS:
        analyse = analyser(texte)
        pose_une_question = bool(analyse.questions)
        if question_attendue and pose_une_question:
            vrais_positifs += 1
        elif question_attendue:
            faux_negatifs += 1
            erreurs.append(f"MANQUEE   {texte[:64]!r} — partie sans demander")
        elif pose_une_question:
            faux_positifs += 1
            premiere = analyse.questions[0].question if analyse.questions else ""
            erreurs.append(
                f"INUTILE   {texte[:64]!r} — a demande : {premiere[:52]!r}"
            )
        else:
            vrais_negatifs += 1

    total = len(CAS)
    return {
        "cas": float(total),
        "exactitude": (vrais_positifs + vrais_negatifs) / total,
        "rappel": vrais_positifs / max(1, vrais_positifs + faux_negatifs),
        "precision": vrais_positifs / max(1, vrais_positifs + faux_positifs),
        "faux_positifs": float(faux_positifs),
        "faux_negatifs": float(faux_negatifs),
        "exactitude_en": _mesurer_langue("en"),
        "exactitude_fr": _mesurer_langue("fr"),
        "erreurs": erreurs,
    }


def resume_controle() -> str:
    """Le rapport du jeu de controle — a lire a cote de `jio clarify --mesure`."""
    m = mesurer_controle()
    erreurs = m["erreurs"]
    lignes = [
        "  JEU DE CONTROLE (objectifs d'un AUTRE projet, aucun chemin de ce depot) :",
        f"    cas {m['cas']:.0f} · exactitude {m['exactitude']:.0%} "
        f"({m['exactitude_en']:.0%} en anglais, {m['exactitude_fr']:.0%} en francais)",
        f"    faux positifs {m['faux_positifs']:.0f} (question posee pour rien — le defaut "
        f"le plus couteux a l'usage) · faux negatifs {m['faux_negatifs']:.0f} (partie sans "
        f"demander)",
    ]
    for erreur in erreurs if isinstance(erreurs, list) else []:
        lignes.append(f"      {erreur}")
    return "\n".join(lignes)
