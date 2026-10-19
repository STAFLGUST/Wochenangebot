/* Bestellwunsch-Anzeige für Kunden und Mitarbeiter: Statusmarke, Positionen, Summen */
import React from 'react';
import { Text, View } from 'react-native';
import { datum, euro, kg, preisZahl } from '../kern/angebot';
import { STATUS_KUNDE } from '../kern/status';
import { Karte, T, Zeile } from './bausteine';
import { SCHRIFT, useFarben } from './theme';

export type KurzVorgang = { nr: string; t: string; firma: string; angebotName?: string; total: number; totalQty: number; workflow: string; positionCount: number; referenz?: string;
  fracht?: { kosten: number; unter?: number | null } | null; assignee?: string; delivery?: string; mailPending?: number; revision: number };
export type Position = { id: string; code: string; name: string; group: string; qty: number; price: number | null; sum: number | null };
export type Vorgang = KurzVorgang & { positions: Position[]; onRequest: number; termin?: string; bemerkung?: string; week?: number; year?: number;
  note?: string; history?: { t: string; by: string; from: string; to: string; assignee: string; note: string }[];
  kunde?: { firma?: string; nr?: string; ansprechpartner?: string; strasse?: string; plz?: string; ort?: string; email?: string; telefon?: string; username?: string } | null;
  deliveryError?: string };

export function StatusMarke({ w, kunde }: { w: string; kunde?: boolean }) {
  const f = useFarben();
  const [bg, fg] = w === 'neu' ? [f.accentSoft, f.accent] : w === 'erledigt' ? [f.okBg, f.ok] : w === 'storniert' ? [f.surface3, f.muted] : [f.warnBg, f.warn];
  const text = kunde ? STATUS_KUNDE[w] : ({ neu: 'Neu', in_bearbeitung: 'In Bearbeitung', bestaetigt: 'Bestätigt', erledigt: 'Erledigt', storniert: 'Storniert' } as Record<string, string>)[w];
  return <Text testID="statusmarke" style={{ backgroundColor: bg, color: fg, fontFamily: SCHRIFT.halbfett, fontSize: 12, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, overflow: 'hidden' }}>{text || w}</Text>;
}

export function Positionen({ o }: { o: Vorgang }) {
  const f = useFarben();
  const fr = o.fracht && o.fracht.kosten ? o.fracht : null;
  return (
    <>
      <Karte style={{ padding: 0, overflow: 'hidden' }}>
        {o.positions.map((p, i) => (
          <View key={p.id + i} style={{ flexDirection: 'row', gap: 10, padding: 12, backgroundColor: i % 2 ? f.surface : f.zebra }}>
            <View style={{ flex: 1, gap: 2 }}>
              <T style={{ fontSize: 14.5 }}>{p.name}</T>
              <T style={{ color: f.text2, fontSize: 12.5 }}>{`${p.code ? p.code + ' · ' : ''}${kg(p.qty)} kg × ${p.price !== null ? preisZahl(p.price) + ' €' : 'Preis auf Anfrage'}`}</T>
            </View>
            <Text style={{ color: f.text, fontFamily: SCHRIFT.mittel, fontSize: 14.5, fontVariant: ['tabular-nums'] }}>{p.sum !== null ? euro(p.sum) : '–'}</Text>
          </View>
        ))}
      </Karte>
      <Karte style={{ gap: 2 }}>
        <Zeile links="Menge" rechts={kg(o.totalQty) + ' kg'} />
        <Zeile links={fr ? 'Warenwert (ca.)' : 'Summe (ca.)'} rechts={euro(o.total)} stark={!fr} />
        {fr ? <><Zeile links={`Frachtanteil${fr.unter ? ` (unter ${fr.unter} kg)` : ''}`} rechts={euro(fr.kosten)} /><Zeile links="Gesamt (ca.)" rechts={euro(o.total + fr.kosten)} stark /></> : null}
        {o.onRequest ? <T style={{ color: f.text2, fontSize: 13, marginTop: 4 }}>{`${o.onRequest} Position(en) mit Preis auf Anfrage nicht enthalten.`}</T> : null}
      </Karte>
      {(o.termin || o.referenz || o.bemerkung) ? (
        <Karte style={{ gap: 4 }}>
          {o.termin ? <Zeile links="Wunschtermin" rechts={datum(o.termin)} /> : null}
          {o.referenz ? <Zeile links="Referenz" rechts={o.referenz} /> : null}
          {o.bemerkung ? <View style={{ gap: 2, paddingTop: 4 }}><T style={{ color: f.text2, fontSize: 14 }}>Bemerkung</T><T selectable>{o.bemerkung}</T></View> : null}
        </Karte>
      ) : null}
    </>
  );
}
