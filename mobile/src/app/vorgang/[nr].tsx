/* Bestellwunsch bearbeiten (Mitarbeiter): Status, Zuständigkeit, interne Notiz. Revision verhindert Überschreiben. */
import { useLocalSearchParams } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Linking, Platform, Text, View } from 'react-native';
import { ApiFehler } from '../../kern/api';
import { datumZeit } from '../../kern/angebot';
import { STATUS_TEXT, UEBERGAENGE } from '../../kern/status';
import { Chip, Feld, H1, H2, Hinweis, Karte, Knopf, Leise, Seite, T } from '../../ui/bausteine';
import { Kopf } from '../../ui/kopf';
import { SCHRIFT, useFarben } from '../../ui/theme';
import { Positionen, StatusMarke, Vorgang } from '../../ui/vorgang';
import { useSitzung } from '../../zustand/sitzung';

export default function VorgangSeite() {
  const { nr } = useLocalSearchParams<{ nr: string }>();
  const f = useFarben();
  const { api, abgelaufen, mitarbeiter } = useSitzung();
  const [o, setO] = useState<Vorgang | null>(null);
  const [bearbeiter, setBearbeiter] = useState<{ id: string; name: string }[]>([]);
  const [status, setStatus] = useState('');
  const [zust, setZust] = useState('');
  const [notiz, setNotiz] = useState('');
  const [fehler, setFehler] = useState('');
  const [ok, setOk] = useState('');
  const [speichert, setSpeichert] = useState(false);
  const darf = !!mitarbeiter && mitarbeiter.perms.includes('bestellungen.bearbeiten');

  const uebernehmen = (x: Vorgang) => { setO(x); setStatus(x.workflow); setZust(x.assignee || ''); setNotiz(x.note || ''); };
  const laden = useCallback(async () => {
    setFehler('');
    try {
      const [d, l] = await Promise.all([
        api.call<{ order: Vorgang }>('bestellung', { query: { nr } }),
        api.call<{ assignees: { id: string; name: string }[] }>('bestellungen', { query: { limit: 1 } }),
      ]);
      uebernehmen(d.order); setBearbeiter(l.assignees);
    } catch (e) { if (!abgelaufen(e)) setFehler(e instanceof Error ? e.message : 'Konnte nicht geladen werden.'); }
  }, [api, nr, abgelaufen]);
  useEffect(() => { laden(); }, [laden]);

  const speichern = async () => {
    if (!o) return;
    setFehler(''); setOk(''); setSpeichert(true);
    try {
      const r = await api.call<{ order: Vorgang }>('bestellung_save', { body: { nr: o.nr, revision: o.revision, workflow: status, assignee: zust, note: notiz } });
      uebernehmen(r.order); setOk('Gespeichert.');
    } catch (e) {
      if (abgelaufen(e)) return;
      setFehler(e instanceof ApiFehler && e.status === 409 ? 'Der Bestellwunsch wurde inzwischen von jemand anderem geändert. Bitte neu laden und erneut ändern.' : e instanceof Error ? e.message : 'Speichern fehlgeschlagen.');
    } finally { setSpeichert(false); }
  };

  const k = o?.kunde;
  const geaendert = !!o && (status !== o.workflow || zust !== (o.assignee || '') || notiz !== (o.note || ''));
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Kopf titel={'Bestellwunsch ' + (nr || '')} />
      <Seite kante={['bottom']}>
        {fehler ? <Hinweis art="fehler" testID="vorgang-fehler">{fehler}</Hinweis> : null}
        {o ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <H1 testID="detail-nr">{o.nr}</H1>
              <StatusMarke w={o.workflow} />
            </View>
            <Leise>{`${datumZeit(o.t)}${o.angebotName ? ' · ' + o.angebotName : ''}${o.week ? ` · KW ${o.week}/${o.year}` : ''}`}</Leise>
            {o.delivery === 'fehler' || o.deliveryError ? <Hinweis art="warn" titel="E-Mail nicht zugestellt">Der Bestellwunsch ist gespeichert. Den erneuten Versand bitte im Eingabebereich prüfen.</Hinweis> : null}
            {k ? (
              <Karte style={{ gap: 4 }}>
                <H2>{k.firma || o.firma}</H2>
                {k.nr ? <Leise>{'Kundennummer ' + k.nr}</Leise> : null}
                {k.ansprechpartner ? <T>{k.ansprechpartner}</T> : null}
                {k.strasse || k.ort ? <T selectable>{[k.strasse, [k.plz, k.ort].filter(Boolean).join(' ')].filter(Boolean).join(', ')}</T> : null}
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                  {k.telefon ? <Knopf klein titel={k.telefon} icon="phone" onPress={() => Linking.openURL('tel:' + k.telefon!.replace(/[^\d+]/g, ''))} /> : null}
                  {k.email ? <Knopf klein titel="E-Mail" icon="mail" onPress={() => Linking.openURL('mailto:' + k.email + '?subject=' + encodeURIComponent('Ihr Bestellwunsch ' + o.nr))} /> : null}
                </View>
              </Karte>
            ) : null}
            <Positionen o={o} />
            <H2>Bearbeitung</H2>
            {darf ? (
              <Karte style={{ gap: 12 }}>
                <View style={{ gap: 8 }}>
                  <Text style={{ color: f.text, fontFamily: SCHRIFT.mittel, fontSize: 14 }}>Status</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {[o.workflow, ...(UEBERGAENGE[o.workflow] || [])].map((s) => <Chip key={s} testID={'setze-' + s} titel={STATUS_TEXT[s]} aktiv={status === s} onPress={() => setStatus(s)} />)}
                  </View>
                  {status === 'bestaetigt' ? <Leise>„Bestätigt“ ist eine interne Kennzeichnung; der Kunde sieht weiter „In Bearbeitung“. Es wird keine E-Mail versendet.</Leise> : null}
                </View>
                <View style={{ gap: 8 }}>
                  <Text style={{ color: f.text, fontFamily: SCHRIFT.mittel, fontSize: 14 }}>Zuständig</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    <Chip titel="Niemand" aktiv={!zust} onPress={() => setZust('')} testID="zust-niemand" />
                    {bearbeiter.map((b) => <Chip key={b.id} testID={'zust-' + b.id} titel={b.id === mitarbeiter?.id ? b.name + ' (ich)' : b.name} aktiv={zust === b.id} onPress={() => setZust(b.id)} />)}
                  </View>
                </View>
                <Feld testID="vorgang-notiz" label="Interne Notiz (sieht der Kunde nicht)" value={notiz} onChangeText={setNotiz} multiline maxLength={2000} />
                {ok && !geaendert ? <Hinweis art="ok" testID="vorgang-ok">{ok}</Hinweis> : null}
                <Knopf testID="vorgang-speichern" titel="Speichern" art="primaer" icon="check" laedt={speichert} deaktiviert={!geaendert} onPress={speichern} />
                {fehler && /geändert/.test(fehler) ? <Knopf titel="Neu laden" icon="refresh-cw" onPress={laden} /> : null}
              </Karte>
            ) : <Hinweis>Sie können Bestellwünsche ansehen, aber nicht bearbeiten.</Hinweis>}
            {o.history && o.history.length ? (
              <Karte style={{ gap: 10 }}>
                <H2>Verlauf</H2>
                {[...o.history].reverse().map((h, i) => (
                  <View key={i} style={{ gap: 2 }}>
                    <T style={{ fontSize: 14 }}>{`${STATUS_TEXT[h.from] || h.from} → ${STATUS_TEXT[h.to] || h.to}`}</T>
                    <Leise style={{ fontSize: 13 }}>{`${datumZeit(h.t)} · ${h.by}`}</Leise>
                    {h.note ? <Leise style={{ fontSize: 13 }} >{h.note}</Leise> : null}
                  </View>
                ))}
              </Karte>
            ) : null}
          </>
        ) : null}
      </Seite>
    </KeyboardAvoidingView>
  );
}
