/* Web-App (zum Home-Bildschirm hinzugefügt): Angebotsseite und öffentliches Wochenangebot offline lesbar.
   Bewusst eng begrenzt:
   - nur die Startseite, Dateien unter /assets/ und das öffentliche Wochenangebot (action=offer ohne angebot/draft);
   - nie Eingabebereich, Anmeldungen, Kundenangebote, Bestellungen oder andere Aktionen (gehen direkt ans Netz);
   - immer zuerst das Netz; der Zwischenspeicher springt nur ein, wenn keine Verbindung besteht.
   Offline-Antworten des Angebots tragen „X-WA-Offline: <Zeitpunkt>“ – die Seite zeigt dann „Preise ohne Gewähr“. */
'use strict';
const CACHE = 'wa-webapp-1';

self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith('wa-webapp-') && k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

function art(req) {
  if (req.method !== 'GET') return null;
  const u = new URL(req.url);
  if (u.origin !== self.location.origin) return null;
  const base = new URL('./', self.registration.scope).pathname;
  const p = u.pathname.slice(base.length - 1);   // Pfad relativ zum Geltungsbereich, beginnt mit „/“
  if (req.mode === 'navigate') return p === '/' || p === '/index.html' ? 'seite' : null;
  if (p.startsWith('/assets/')) return 'datei';
  if (p === '/manifest.json') return 'datei';
  if (p === '/api/' && u.searchParams.get('action') === 'offer' && !u.searchParams.has('draft')
      && (u.searchParams.get('angebot') || 'std') === 'std' && [...u.searchParams.keys()].every((k) => k === 'action' || k === 'angebot')) return 'angebot';
  return null;
}
/* öffentlich speicherbar: keine privaten Antworten (Kundenangebote sind „private, no-store“) */
function oeffentlich(res) {
  const cc = (res.headers.get('Cache-Control') || '').toLowerCase();
  return res.ok && res.type === 'basic' && !/private|no-store/.test(cc);
}
/* ältere Fassungen derselben Datei (anderes ?v=) entfernen, damit der Speicher nicht wächst */
async function aufraeumen(cache, key) {
  const pfad = new URL(key).pathname;
  for (const r of await cache.keys()) if (r.url !== key && new URL(r.url).pathname === pfad) cache.delete(r).catch(() => {});
}
const schluessel = (req, a) => (a === 'seite' ? new URL('./', self.registration.scope).href : a === 'angebot' ? new URL('api/?action=offer', self.registration.scope).href : req.url);

self.addEventListener('fetch', (e) => {
  const a = art(e.request);
  if (!a) return;   // alles andere unverändert über das Netz
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = schluessel(e.request, a);
    try {
      const res = await fetch(e.request);
      if (oeffentlich(res)) {
        const kopie = res.clone();
        if (a === 'angebot') {
          const h = new Headers(kopie.headers);
          h.set('X-WA-Gespeichert', new Date().toISOString());
          cache.put(key, new Response(await kopie.blob(), { status: 200, headers: h })).catch(() => {});
        } else {
          cache.put(key, kopie).catch(() => {});
          if (a === 'datei') aufraeumen(cache, key);
        }
      } else if (a === 'angebot' && [401, 403, 404].includes(res.status)) {
        cache.delete(key).catch(() => {});   // nicht mehr öffentlich/kein Angebot: alte Offline-Kopie nicht weiter anzeigen
      }
      return res;
    } catch (err) {
      const alt = await cache.match(key);
      if (!alt) throw err;
      if (a !== 'angebot') return alt;
      const h = new Headers(alt.headers);
      h.set('X-WA-Offline', alt.headers.get('X-WA-Gespeichert') || '');
      return new Response(await alt.blob(), { status: 200, headers: h });
    }
  })());
});
