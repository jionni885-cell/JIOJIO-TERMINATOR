"""Export HTML autonome et sûr d'un journal de trace JIO.

Le rapport est une vue de lecture, pas une nouvelle preuve : la chaîne complète est vérifiée
sur le journal source, et les valeurs sont échappées avant insertion dans le HTML. Aucun script,
service ni ressource distante n'est nécessaire pour l'ouvrir.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from html import escape

from .audit.integrity import IntegrityMonitor
from .core.journal import Event, Journal
from .core.types import IntegrityReport

_STYLE = """
:root {
  color-scheme: dark;
  --bg: #0b1020;
  --panel: #121a2d;
  --panel-raised: #172239;
  --line: #26334c;
  --text: #edf2ff;
  --muted: #9ba9c2;
  --accent: #77d6c2;
  --good: #86e0b2;
  --bad: #ff8794;
  --warn: #ffd479;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-width: 320px;
  background:
    radial-gradient(ellipse at 80% -15%, #19314a 0, transparent 45%),
    var(--bg);
  line-height: 1.55;
}
main { width: min(1080px, calc(100% - 36px)); margin: 48px auto 64px; }
.eyebrow { color: var(--accent); font-size: .76rem; font-weight: 750; letter-spacing: .16em; text-transform: uppercase; }
h1 { margin: 8px 0 6px; font-size: clamp(2rem, 5vw, 3.25rem); line-height: 1.1; letter-spacing: -.04em; }
h2 { margin: 34px 0 12px; font-size: 1.15rem; }
.lede, .source, .muted { color: var(--muted); }
.lede { max-width: 720px; }
.source { overflow-wrap: anywhere; font: .86rem ui-monospace, SFMono-Regular, Consolas, monospace; }
.status {
  display: flex; align-items: flex-start; gap: 14px; margin: 24px 0 20px; padding: 17px 19px;
  border: 1px solid var(--line); border-radius: 14px; background: var(--panel);
}
.status p { margin: 0; color: var(--muted); }
.status--ok { border-color: #286449; }
.status--bad { border-color: #783b4a; }
.badge {
  display: inline-flex; flex: none; align-items: center; border-radius: 999px; padding: 4px 9px;
  font-size: .72rem; font-weight: 800; letter-spacing: .06em; white-space: nowrap;
}
.badge--ok { color: var(--good); background: #163c31; }
.badge--bad { color: var(--bad); background: #48232e; }
.stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.stat { min-width: 0; padding: 15px; border: 1px solid var(--line); border-radius: 12px; background: #10182a; }
.stat span { display: block; color: var(--muted); font-size: .76rem; }
.stat strong { display: block; margin-top: 5px; font-size: 1.2rem; overflow-wrap: anywhere; }
.stat code { font-size: .8rem; }
.kind-list { display: flex; flex-wrap: wrap; gap: 8px; }
.kind-chip { border: 1px solid var(--line); border-radius: 999px; background: var(--panel); padding: 5px 10px; color: var(--muted); font-size: .82rem; }
.kind-chip strong { color: var(--text); }
.filter-note { border-left: 3px solid var(--warn); padding: 9px 12px; color: var(--muted); background: #211d17; }
.timeline { position: relative; display: grid; gap: 12px; }
.event-card { position: relative; padding: 17px 18px 16px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); }
.event-head { display: flex; align-items: flex-start; gap: 13px; }
.event-seq { min-width: 54px; padding-top: 2px; color: var(--accent); font: 700 .9rem ui-monospace, SFMono-Regular, Consolas, monospace; }
.event-title { flex: 1; min-width: 0; }
.event-title h3 { margin: 0; font-size: 1rem; overflow-wrap: anywhere; }
.event-title p { margin: 3px 0 0; color: var(--muted); font-size: .78rem; }
.trust { border-radius: 999px; padding: 3px 8px; font-size: .69rem; font-weight: 750; text-transform: uppercase; }
.trust--system { color: #b8c5ff; background: #252c51; }
.trust--user { color: #9be6d2; background: #183e39; }
.trust--external { color: var(--warn); background: #49371d; }
.hash { margin: 12px 0 0; color: var(--muted); font-size: .76rem; overflow-wrap: anywhere; }
.hash code { color: #c6d2ed; }
details { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }
summary { color: var(--accent); cursor: pointer; font-size: .84rem; }
pre { margin: 10px 0 0; padding: 14px; max-height: 560px; overflow: auto; border: 1px solid var(--line); border-radius: 9px; background: #090e19; color: #d8e2f6; font: .78rem/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.empty { padding: 22px; border: 1px dashed var(--line); border-radius: 12px; color: var(--muted); }
.audit-list, .world-list { display: grid; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
.audit-item, .world-item { padding: 11px 13px; border: 1px solid var(--line); border-radius: 9px; background: #10182a; }
.audit-item strong, .world-item strong { color: var(--text); }
.audit-item p, .world-item p { margin: 4px 0 0; color: var(--muted); font-size: .82rem; overflow-wrap: anywhere; }
.privacy { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: .78rem; }
@media (max-width: 700px) {
  main { margin-top: 28px; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .status { display: block; }
  .status p { margin-top: 9px; }
}
@media (max-width: 390px) {
  .stats { grid-template-columns: 1fr 1fr; gap: 8px; }
  .stat { padding: 11px; }
  .event-card { padding: 14px 12px; }
  .event-head { gap: 8px; }
  .event-seq { min-width: 42px; }
}
"""


def _echapper(valeur: object) -> str:
    return escape(str(valeur), quote=True)


def _horodatage(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    except (OverflowError, OSError, ValueError):
        return f"{ts!r} (horodatage hors plage)"


def _carte_evenement(position: int, evenement: Event) -> str:
    trust = evenement.trust.value
    donnees = json.dumps(
        evenement.as_dict(), ensure_ascii=False, indent=2, sort_keys=True, default=str
    )
    return f"""<article class="event-card" aria-labelledby="event-title-{position}">
  <div class="event-head">
    <div class="event-seq">#{_echapper(evenement.seq)}</div>
    <div class="event-title">
      <h3 id="event-title-{position}">{_echapper(evenement.kind)}</h3>
      <p>{_echapper(_horodatage(evenement.ts))} · événement {position + 1} sur la trace</p>
    </div>
    <span class="trust trust--{_echapper(trust)}">{_echapper(trust)}</span>
  </div>
  <p class="hash">Empreinte : <code>{_echapper(evenement.digest[:16])}…</code></p>
  <details>
    <summary>Voir l'événement complet, son payload et ses empreintes</summary>
    <pre>{_echapper(donnees)}</pre>
  </details>
</article>"""


def _section_audit(audit: IntegrityReport) -> str:
    if audit.clean:
        return """<section aria-labelledby="audit-title">
  <h2 id="audit-title">Rejeu déterministe</h2>
  <p class="status status--ok"><span class="badge badge--ok">AUCUNE ANOMALIE</span>
    <span>Le moniteur n'a relevé aucun motif d'exploitation dans les événements.</span></p>
</section>"""

    constats = "".join(
        f'<li class="audit-item"><strong>{_echapper(exploit.kind.value)} · étape '
        f'{_echapper(exploit.step)} · confiance {exploit.confidence:.0%}</strong>'
        f'<p>{_echapper(exploit.detail)}</p></li>'
        for exploit in audit.exploits
    )
    return f"""<section aria-labelledby="audit-title">
  <h2 id="audit-title">Rejeu déterministe · {len(audit.exploits)} anomalie(s)</h2>
  <ul class="audit-list">{constats}</ul>
</section>"""


def _section_mondes(mondes: list[dict[str, object]], sceau_courant: str) -> str:
    plusieurs = len(mondes) > 1
    ancien = bool(
        len(mondes) == 1 and sceau_courant and mondes[0].get("sceau") != sceau_courant
    )
    if not plusieurs and not ancien:
        return ""

    titre = (
        "Le monde a changé pendant cette mission."
        if plusieurs
        else "Cette trace porte sur un état antérieur du dépôt."
    )
    detail = (
        "Les observations peuvent provenir de plusieurs états du dépôt ; relisez la conclusion "
        "avant de l'utiliser comme preuve."
        if plusieurs
        else "La chaîne reste vérifiable, mais le contenu du dépôt a changé depuis la trace."
    )
    entrees = []
    for monde in mondes:
        sceau = str(monde.get("sceau", ""))
        revision = str(monde.get("revision", ""))
        evenements = monde.get("evenements", [])
        references = ", ".join(f"#{_echapper(seq)}" for seq in evenements)
        courant = " · état courant" if sceau_courant and sceau == sceau_courant else ""
        empreinte = sceau[:12] or "absent"
        revision_html = f" · révision <code>{_echapper(revision[:12])}</code>" if revision else ""
        entrees.append(
            f'<li class="world-item"><strong>Sceau <code>{_echapper(empreinte)}</code>'
            f'{_echapper(courant)}</strong><p>Événement(s) {references or "non précisés"}'
            f'{revision_html}</p></li>'
        )
    return f"""<section class="status status--bad" aria-label="Avertissement sur le monde">
  <span class="badge badge--bad">MONDE À RELIRE</span>
  <div><strong>{titre}</strong><p>{detail}</p>
    <ul class="world-list">{"".join(entrees)}</ul>
  </div>
</section>"""


def rapport_html(
    journal: Journal,
    *,
    source: str,
    kind: str = "",
    audit: IntegrityReport | None = None,
    sceau_courant: str = "",
) -> str:
    """Rend une vue HTML autonome d'un journal, en vérifiant la chaîne complète.

    Le filtre de type ne masque que les cartes présentées : le statut d'intégrité et le rejeu
    portent toujours sur l'ensemble du journal source. Si aucun audit n'est fourni, il est calculé
    ici de façon déterministe.
    """
    tous = tuple(journal)
    affiches = journal.events(kind) if kind else tous
    integre, mauvais = journal.verify_chain()
    if audit is None:
        audit = IntegrityMonitor().audit(journal)
    mondes = journal.mondes()
    audit_html = _section_audit(audit)
    mondes_html = _section_mondes(mondes, sceau_courant)
    compteurs = Counter(evenement.kind for evenement in tous)
    types_html = "".join(
        f'<span class="kind-chip"><strong>{_echapper(nom)}</strong> · {nombre}</span>'
        for nom, nombre in sorted(compteurs.items())
    ) or '<span class="muted">Aucun événement</span>'
    cartes = "\n".join(
        _carte_evenement(position, evenement) for position, evenement in enumerate(affiches)
    )
    if not cartes:
        cartes = '<p class="empty">Aucun événement ne correspond à ce filtre.</p>'

    classe = "ok" if integre else "bad"
    badge = "CHAÎNE INTACTE" if integre else "CHAÎNE CASSÉE"
    detail = (
        "Tous les événements sont cohérents avec la chaîne de hachage."
        if integre
        else f"Première anomalie à la position {mauvais} (indexation à partir de 0)."
    )
    filtre = (
        f'<p class="filter-note">Filtre actif : type « {_echapper(kind)} ». '
        "L'intégrité a tout de même été vérifiée sur le journal complet.</p>"
        if kind
        else ""
    )
    tete = journal.head
    nb_mondes = len(mondes)
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="no-referrer">
  <title>JIO · Rapport de trace</title>
  <style>{_STYLE}</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">JIO · Observabilité locale</p>
    <h1>Trace de mission</h1>
    <p class="lede">Rapport autonome du journal d'événements. Les cartes suivent l'ordre du journal ; ouvrez un événement pour inspecter son JSON et ses empreintes.</p>
    <p class="source">Source : {_echapper(source)}</p>
  </header>
  <section class="status status--{classe}" role="status" aria-label="État d'intégrité">
    <span class="badge badge--{classe}">{badge}</span>
    <p>{detail}</p>
  </section>
  <section class="stats" aria-label="Synthèse de la trace">
    <div class="stat"><span>Événements dans le journal</span><strong>{len(tous)}</strong></div>
    <div class="stat"><span>Événements affichés</span><strong>{len(affiches)}</strong></div>
    <div class="stat"><span>États du dépôt observés</span><strong>{nb_mondes}</strong></div>
    <div class="stat"><span>Anomalies de rejeu</span><strong>{len(audit.exploits)}</strong></div>
    <div class="stat"><span>Tête de chaîne</span><strong><code>{_echapper(tete[:16])}…</code></strong></div>
  </section>
  {mondes_html}
  {audit_html}
  <section aria-labelledby="types-title">
    <h2 id="types-title">Événements par type</h2>
    <div class="kind-list">{types_html}</div>
  </section>
  {filtre}
  <section aria-labelledby="timeline-title">
    <h2 id="timeline-title">Chronologie · {len(affiches)} événement(s)</h2>
    <div class="timeline">{cartes}</div>
  </section>
  <footer class="privacy">Rapport local autonome : aucun JavaScript ni appel réseau. Les détails affichent le contenu brut du journal (potentiellement prompts, code ou données de projet) ; vérifiez-le avant tout partage.</footer>
</main>
</body>
</html>
"""


__all__ = ["rapport_html"]
