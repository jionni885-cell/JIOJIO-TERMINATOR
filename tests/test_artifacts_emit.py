"""Les artefacts natifs : ce que les agents des AUTRES outils lisent vraiment.

`jio/artifacts/emit.py` n'etait mentionne par AUCUN test — le score de mutation le
disait noir sur blanc : « aucun test ne mentionne jio/artifacts/emit.py : le mutant est
compte SURVIVANT ». Or c'est exactement le fichier dont le contenu part chez opencode,
Hermes, Claude, Cursor, Copilot et Gemini. Un defaut ici ne casse pas JIO : il casse les
instructions que toutes les autres IA de l'utilisateur lisent.

Chaque test ci-dessous est ecrit pour une raison mesurable, indiquee dans sa docstring.
"""

from __future__ import annotations

import json

import pytest

from jio.artifacts import emit
from jio.artifacts.definitions import AGENTS, PRINCIPLES, SKILLS, AgentSpec

CHEMIN = "jio/artifacts/emit.py"  # trace : le fichier couvert par ce module de tests


def test_la_liste_des_principes_est_NUMEROTEE_a_partir_de_un() -> None:
    """`enumerate(PRINCIPLES, 1)` : les principes sont numerotes 1..N, jamais 2..N+1.

    Mesure a l'origine : `jio mutants` a montre que ce `1` pouvait devenir `2` sans qu'aucun
    test ne bouge. Tous les artefacts (CLAUDE.md, AGENTS.md, GEMINI.md, les 8 competences
    Hermes) auraient commence a « 2. » — une numerotation qui commence a 2 se lit comme une
    liste ampute, et le lecteur cherche ce qui manque au lieu de lire la doctrine.
    """
    lignes = emit._principles_block().splitlines()
    assert lignes[0].startswith("1. ")
    assert lignes[-1].startswith(f"{len(PRINCIPLES)}. ")
    assert len(lignes) == len(PRINCIPLES)
    assert CHEMIN in "jio/artifacts/emit.py"


def test_sans_frontmatter_l_agent_rend_EXACTEMENT_son_prompt() -> None:
    """`frontmatter=False` : le prompt seul, sans en-tete YAML ajoute au passage.

    Mesure a l'origine : `jio mutants` a montre que le `if not frontmatter` de
    `_agent_markdown` pouvait etre vide ET que le defaut `True` pouvait devenir `False`.
    Le premier cas produisait un fichier avec en-tete pour le dialecte « prompt seul »,
    le second retirait l'en-tete YAML a opencode — qui aurait alors ignore le mode,
    la temperature et surtout les PERMISSIONS (le verificateur n'a pas le droit d'ecrire).
    """
    agent = AgentSpec(name="essai", description="d", prompt="Fais ceci.")
    assert emit._agent_markdown(agent, frontmatter=False) == "Fais ceci."
    texte = emit._agent_markdown(agent)
    assert texte.startswith("---\n")
    assert "mode: subagent" in texte and "permission:" in texte
    assert texte.rstrip().endswith("Fais ceci.")


def test_un_agent_sans_outil_n_affiche_pas_de_section_OUTILS_VIDE() -> None:
    """`if tools:` : pas de section « tools: » quand il n'y a aucun outil.

    Mesure a l'origine : `jio mutants` a montre que ce bloc conditionnel pouvait devenir
    vide. Le frontmatter aurait alors contenu « tools: » suivi de rien — un YAML que
    certains parseurs refusent, et dans tous les cas une declaration creuse.
    """
    sans_outil = AgentSpec(name="essai", description="d", prompt="p", tools={})
    assert "tools:" not in emit._agent_markdown(sans_outil)
    avec_outil = AgentSpec(name="essai", description="d", prompt="p", tools={"read": True})
    assert "tools:\n  read: true" in emit._agent_markdown(avec_outil)


def test_les_accents_ne_sont_JAMAIS_echappes_dans_les_artefacts() -> None:
    """`ensure_ascii=False` : un artefact francais reste lisible par un humain.

    Mesure a l'origine : `jio mutants` a montre que ce `False` pouvait devenir `True` a
    trois endroits (frontmatter opencode, `opencode.json`, `.mcp.json`) sans qu'aucun test
    ne bouge. Les fichiers restaient valides — la perte etait invisible : des `\\u00e9`
    partout dans des fichiers que l'utilisateur ouvre pour les lire.
    """
    agent = AgentSpec(name="essai", description="verifie l'intégrité", prompt="p")
    assert "intégrité" in emit._agent_markdown(agent)
    assert "\\u" not in emit._agent_markdown(agent)

    artefacts = emit.manifest(("opencode-mcp", "mcp"))
    for nom in ("opencode.json", ".mcp.json"):
        texte = artefacts[nom]
        assert "\\u" not in texte
        assert json.loads(texte)  # et c'est du JSON valide
        assert "\n  \"" in texte, "indent=2 attendu : sinon le fichier est illisible"


def test_la_borne_de_cent_cinquante_lignes_mord_EXACTEMENT_a_151(monkeypatch) -> None:
    """`len(lines) > 150` : AGENTS.md reste sous la limite, et la limite est REELLE.

    Mesure a l'origine : `jio mutants` a montre que ce `150` pouvait devenir `151` et que
    `>` pouvait devenir `<=`. La garde de qualite (un AGENTS.md trop long est survole par
    les agents) n'aurait plus rien garde du tout — une garde qui ne mord pas est une
    decoration, et une decoration qui valide est pire qu'une absence de garde.
    """
    base = len(emit._target_agents()["AGENTS.md"].splitlines())
    assert base <= 150

    def avec(compensation: int) -> str:
        monkeypatch.setattr(emit, "COMPACT", "\n" * compensation + "extrait")
        return emit._target_agents()["AGENTS.md"]

    # On calcule de combien de lignes il faut depasser pour atteindre EXACTEMENT 151.
    complet = len(avec(0).splitlines())
    manque = 151 - complet
    assert manque >= 0, "le contenu de base doit laisser de la marge"
    monkeypatch.setattr(emit, "COMPACT", "\n" * manque + "extrait")
    with pytest.raises(ValueError, match="151 lignes"):
        emit._target_agents()


def test_une_cible_inconnue_est_REFUSEE_en_nommant_ce_qu_on_a_demande() -> None:
    """`if unknown:` : demander une cible inexistante leve, au lieu d'ecrire un fichier vide.

    Mesure a l'origine : `jio mutants` a montre que ce bloc conditionnel pouvait devenir
    vide. `jio artifacts --target cursorr` aurait alors rendu une liste vide, sans erreur :
    l'utilisateur aurait cru avoir configure son outil et n'aurait rien eu.
    """
    with pytest.raises(ValueError, match="cursorr"):
        emit.manifest(("cursorr",))
    assert set(emit.manifest(("claude",))) == {"CLAUDE.md"}


def test_chaque_competence_Hermes_a_sa_page_et_sa_reference() -> None:
    """Toute competence livree porte sa reference vers la source unique.

    Mesure a l'origine : `jio mutants` a montre que des concatenations de chaines
    (`operateur Add -> Sub`) dans les emetteurs pouvaient changer sans qu'aucun test ne
    bouge. Le symptome typique est un artefact tronque — le pire cas pour une competence,
    qui est une instruction EXECUTEE par l'agent : tronquee, elle devient une instruction
    differente.
    """
    fichiers = emit.manifest(("hermes",))
    assert len([c for c in fichiers if c.endswith("SKILL.md")]) == len(SKILLS)
    for skill in SKILLS:
        texte = fichiers[f".hermes/skills/{skill.category}/{skill.name}/SKILL.md"]
        assert texte.startswith("---\n")
        assert f"name: {skill.name}" in texte
        assert "Doctrine complete : `jio/artifacts/doctrine.py`" in texte
        assert skill.body.rstrip()[:40] in texte


def test_les_dix_cibles_produisent_TOUTES_au_moins_un_fichier() -> None:
    """Chaque dialecte declare livre quelque chose : une cible muette est un cablage mort.

    Mesure a l'origine : `jio mutants` a montre qu'un bloc conditionnel de `manifest`
    pouvait devenir vide. Une cible qui ne produit RIEN en silence est le defaut que tout
    ce module corrige : l'outil croit etre configure et ne voit aucun outil JIO.
    """
    for cible in emit.TARGETS:
        produits = emit.manifest((cible,))
        assert produits, f"la cible {cible} ne produit aucun fichier"
        assert all(nom and contenu for nom, contenu in produits.items())


def test_ecrire_deux_fois_donne_le_meme_octet_et_le_dit(tmp_path) -> None:
    """Idempotence : le deuxieme passage ne touche a rien et rend `inchange`.

    Un generateur qui reecrit ses propres fichiers a chaque passage produit du bruit dans
    git et une date de modification qui fait croire a un changement. La decision est
    RENDUE, pas supposee : `inchange` est une preuve, pas une impression.
    """
    from jio.artifacts.write_guard import ecrire_manifest

    cibles = ("claude", "agents", "mcp", "hermes")
    premier = ecrire_manifest(tmp_path, emit.manifest(cibles))
    assert premier and all(d.action in {"ecrit", "remplace"} for d in premier)
    contenus = {d.chemin: (tmp_path / d.chemin).read_text(encoding="utf-8") for d in premier}

    second = ecrire_manifest(tmp_path, emit.manifest(cibles))
    assert all(d.action == "inchange" for d in second), [d.action for d in second]
    for chemin, texte in contenus.items():
        assert (tmp_path / chemin).read_text(encoding="utf-8") == texte


def test_un_fichier_ecrit_par_l_utilisateur_est_PRESERVE(tmp_path) -> None:
    """`CLAUDE.md` ecrit a la main n'est JAMAIS ecrase : notre version part dans `.jio`.

    Mesure a l'origine : `jio mutants` a montre qu'un bloc conditionnel de `emit.py` pouvait
    devenir vide. Le garde-fou qui PRESERVE un fichier etranger est exactement ce qui se
    serait tu : l'utilisateur aurait perdu ses conventions projet, en silence, et le
    fichier de remplacement aurait eu l'air legitime.
    """
    from jio.artifacts.write_guard import ecrire_manifest

    a_moi = "# Mes conventions a moi\n\nNe jamais ecrire sans preuve.\n"
    (tmp_path / "CLAUDE.md").write_text(a_moi, encoding="utf-8")

    decisions = ecrire_manifest(tmp_path, emit.manifest(("claude",)))
    assert len(decisions) == 1
    assert decisions[0].action == "preserve", decisions[0].detail
    assert decisions[0].ecrit is False
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == a_moi
    assert "jio" in (tmp_path / "CLAUDE.md.jio").read_text(encoding="utf-8")


def test_un_artefact_a_nous_mais_MODIFIE_est_sauvegarde_avant_mise_a_jour(tmp_path) -> None:
    """Quelqu'un a edite un fichier que nous avions genere : sa version est mise de cote.

    La difference entre « preserve » et « sauvegarde » n'est pas cosmetique : le premier
    laisse le fichier en place, le second le remplace en gardant `.avant-jio`. Confondre les
    deux, c'est soit perdre le travail de l'utilisateur, soit ne jamais mettre a jour ses
    propres artefacts.
    """
    from jio.artifacts.write_guard import ecrire_manifest

    ecrire_manifest(tmp_path, emit.manifest(("agents",)))
    edite = (tmp_path / "AGENTS.md").read_text(encoding="utf-8") + "\nNote ajoutee a la main.\n"
    (tmp_path / "AGENTS.md").write_text(edite, encoding="utf-8")

    decisions = ecrire_manifest(tmp_path, emit.manifest(("agents",)))
    assert [d.action for d in decisions] == ["sauvegarde"]
    assert (tmp_path / "AGENTS.md.avant-jio").read_text(encoding="utf-8") == edite
    assert "Note ajoutee a la main." not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert AGENTS and SKILLS  # les sources existent bien : sinon ce fichier teste le vide
