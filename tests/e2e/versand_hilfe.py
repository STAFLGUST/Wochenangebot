"""Hilfe für Tests des Eingabebereichs: veröffentlichen, seit das Veröffentlichen im Modul Versand liegt (13.11.2026).

Viele Gruppen brauchen „veröffentlicht“ nur als Zwischenschritt. veroeffentlichen(pg) macht, was ein Mitarbeiter mit Zugang
im Versand tut: Es wartet, bis der Eingabebereich gespeichert hat, veröffentlicht den gespeicherten Entwurf über die Aktion
des Moduls (versand_veroeffentlichen, mit der Revision aus versand_start) und wartet, bis der offene Eingabebereich den neuen
Stand über seinen Abgleich übernommen hat. Die Oberfläche des Versands selbst prüft die Gruppe „versand“."""

JS = """async () => {
  const hole = async (a, body, csrf) => { const r = await fetch('/api/?action=' + a, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) } : {}); return [r.status, await r.json()]; };
  const [, st] = await hole('status');
  const [c1, d] = await hole('versand_start');
  if (c1 !== 200) return [c1, d];
  return hole('versand_veroeffentlichen', { revision: d.aenderungen.revision }, st.csrf);
}"""


def veroeffentlichen(pg, timeout=20000, warten=True):
    """Entwurf der offenen Seite des Eingabebereichs veröffentlichen; gibt [Status, Antwort] zurück"""
    pg.wait_for_function("!/pending|saving/.test(document.querySelector('#save-state').className)", timeout=timeout)
    ergebnis = pg.evaluate(JS)
    assert ergebnis[0] == 200, ergebnis
    if warten:   # der Eingabebereich holt den veröffentlichten Stand mit seinem Abgleich (alle 8 s bzw. sofort bei der Rückkehr ins Fenster)
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_function("/Keine Änderungen gegenüber der veröffentlichten Fassung/.test(document.querySelector('#save-state').textContent)", timeout=timeout)
    return ergebnis
