/* Bestellwunsch prüfen und senden. Summen und Fracht sind eine Vorschau; der Server rechnet verbindlich. */
import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, Text, TextInput, View } from 'react-native';
import { ApiFehler } from '../../kern/api';
import { anzeigeName, euro, kg, preisText } from '../../kern/angebot';
import { frachtFuer, mengeLesen, mengeText, summen, terminLesen } from '../../kern/bestellung';
import { Feld, H1, H2, Hinweis, Icon, Karte, Knopf, Leer, Leise, Seite, T, Zeile } from '../../ui/bausteine';
import { R, SCHRIFT, useFarben } from '../../ui/theme';
import { Quittung, useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

function MengeFeld({ id, wert, onSetzen }: { id: string; wert: number; onSetzen: (q: number) => void }) {
  const f = useFarben();
  const [t, setT] = useState(mengeText(wert));
  const q = mengeLesen(t);
  return (
    <TextInput testID={'korb-menge-' + id} value={t} onChangeText={setT} onEndEditing={() => { if (!Number.isNaN(q)) onSetzen(q); }} onBlur={() => { if (!Number.isNaN(q)) onSetzen(q); }}
      keyboardType="decimal-pad" inputMode="decimal" accessibilityLabel="Menge in kg"
      style={{ width: 78, height: 40, borderWidth: 1, borderColor: Number.isNaN(q) ? f.danger : f.lineStrong, borderRadius: R.sm, textAlign: 'right', paddingHorizontal: 8, fontSize: 15, color: f.text, backgroundColor: f.surface, fontFamily: SCHRIFT.mittel }} />
  );
}

export default function Bestellwunsch() {
  const f = useFarben();
  const router = useRouter();
  const a = useAngebot();
  const { rolle, bestellung, kunde } = useSitzung();
  const [fehler, setFehler] = useState('');
  const [sendet, setSendet] = useState(false);
  const [quittung, setQuittung] = useState<Quittung | null>(null);
  const [neuLaden, setNeuLaden] = useState(false);
  const s = useMemo(() => (a.angebot ? summen(a.korb, a.angebot.items) : null), [a.korb, a.angebot]);
  const fr = frachtFuer(a.fracht, s ? s.kg : 0);
  const termin = terminLesen(a.kopf.termin);

  if (quittung) {
    const unsicher = quittung.delivery === 'fehler' || quittung.delivery === 'neu';
    return (
      <Seite>
        <Leer icon="check" titel="Vielen Dank!" text={`Bestellwunsch ${quittung.nr}`} />
        <Karte style={{ gap: 4 }} >
          <Zeile links="Positionen" rechts={String(quittung.positions)} />
          <Zeile links="Menge" rechts={kg(quittung.totalQty) + ' kg'} />
          <Zeile links="Warenwert (ca.)" rechts={euro(quittung.total)} />
          {quittung.fracht && quittung.fracht.kosten ? <Zeile links="Frachtanteil" rechts={euro(quittung.fracht.kosten)} /> : null}
        </Karte>
        <Hinweis art={unsicher ? 'warn' : 'ok'} testID="quittung">{unsicher
          ? 'Ihr Bestellwunsch ist gespeichert. Die E-Mail-Zustellung ist noch nicht bestätigt; bitte nicht nochmals als neuen Vorgang senden. Bei Rückfragen nennen Sie uns die Nummer.'
          : `Ihr Bestellwunsch wurde an uns übermittelt. Wir melden uns mit der Bestätigung.${quittung.copy ? ` Eine Kopie ging an ${quittung.copy}.` : ''}`}</Hinweis>
        <Knopf titel="Zu meinen Bestellwünschen" icon="inbox" onPress={() => { setQuittung(null); router.push('/bestellungen'); }} />
        <Knopf titel="Weiter im Angebot" art="leise" onPress={() => { setQuittung(null); router.push('/angebot'); }} />
      </Seite>
    );
  }
  if (rolle !== 'kunde' || !kunde) return <Seite><Leer icon="log-in" titel="Bitte anmelden" text="Bestellwünsche können angemeldete Kunden senden."><Knopf titel="Anmelden" art="primaer" onPress={() => router.push('/anmelden')} /></Leer></Seite>;
  if (!bestellung) return <Seite><Leer icon="slash" titel="Bestellfunktion nicht verfügbar" text="Bestellwünsche über das Portal sind derzeit nicht möglich. Bitte wenden Sie sich direkt an uns." /></Seite>;
  if (!s || !s.zeilen.length) return (
    <Seite><H1>Bestellwunsch</H1>
      <Leer icon="shopping-bag" titel="Noch keine Mengen" text="Tippen Sie im Angebot auf einen Artikel und tragen Sie die gewünschte Menge in kg ein.">
        <Knopf titel="Zum Angebot" art="primaer" icon="list" onPress={() => router.push('/angebot')} />
      </Leer>
      {s && s.fehlend.length ? <Hinweis art="warn">{`${s.fehlend.length} Position(en) aus Ihrem Entwurf sind im aktuellen Angebot nicht mehr enthalten.`}</Hinweis> : null}
    </Seite>
  );

  const senden = async () => {
    setFehler(''); setNeuLaden(false);
    if (termin === null) { setFehler('Bitte das Wunschdatum als TT.MM.JJJJ eingeben oder leer lassen.'); return; }
    setSendet(true);
    try {
      setQuittung(await a.senden());
    } catch (e) {
      const m = e instanceof Error ? e.message : 'Der Bestellwunsch konnte nicht gesendet werden.';
      setFehler(e instanceof ApiFehler && e.offline ? m + ' Ihr Entwurf bleibt gespeichert; beim erneuten Senden entsteht kein doppelter Bestellwunsch.' : m);
      if (e instanceof ApiFehler && e.status === 409 && /aktualisiert|nicht mehr enthalten/.test(m)) setNeuLaden(true);
    } finally { setSendet(false); }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Seite>
        <H1>Bestellwunsch</H1>
        <Leise>{`${kunde.firma} · ${a.angebot?.meta.offerName || 'Wochenangebot'}`}</Leise>
        {a.offline ? <Hinweis art="warn" titel="Offline">Sie sehen einen gespeicherten Stand. Senden ist erst wieder mit Internetverbindung möglich.</Hinweis> : null}
        {s.fehlend.length ? <Hinweis art="warn">{`${s.fehlend.length} Position(en) aus Ihrem Entwurf sind im aktuellen Angebot nicht mehr enthalten und werden nicht gesendet.`}</Hinweis> : null}
        <Karte style={{ padding: 0, overflow: 'hidden' }}>
          {s.zeilen.map((z, i) => (
            <View key={z.it.id} testID={'korb-' + z.it.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: i % 2 ? f.surface : f.zebra }}>
              <View style={{ flex: 1, gap: 2 }}>
                <T style={{ fontSize: 14.5 }}>{anzeigeName(z.it)}</T>
                <T style={{ color: f.text2, fontSize: 12.5 }}>{`${z.it.code ? z.it.code + ' · ' : ''}${preisText(z.it.price)}${z.it.price.status === 'value' ? ' € / kg' : ''}${z.summe !== null ? ' · ' + euro(z.summe) : ''}`}</T>
              </View>
              <MengeFeld key={z.it.id + ':' + z.q} id={z.it.id} wert={z.q} onSetzen={(q) => a.menge(z.it.id, q)} />
              <Text style={{ color: f.text2, fontFamily: SCHRIFT.normal }}>kg</Text>
              <Pressable testID={'korb-entfernen-' + z.it.id} accessibilityLabel="Position entfernen" hitSlop={8} onPress={() => a.menge(z.it.id, 0)}><Icon name="x" size={18} color={f.muted} /></Pressable>
            </View>
          ))}
        </Karte>
        <Karte style={{ gap: 2 }}>
          <Zeile links={fr.kosten ? 'Warenwert (ca.)' : 'Summe (ca.)'} rechts={euro(s.summe)} stark={!fr.kosten} />
          <Zeile links="Menge" rechts={kg(s.kg) + ' kg'} />
          {fr.kosten ? <><Zeile links={`Frachtanteil (unter ${fr.unter} kg)`} rechts={euro(fr.kosten)} /><Zeile links="Gesamt (ca.)" rechts={euro(s.summe + fr.kosten)} stark /></> : null}
          {s.anfrage ? <Leise style={{ marginTop: 4 }}>{`${s.anfrage} Position(en) mit Preis auf Anfrage sind nicht enthalten.`}</Leise> : null}
        </Karte>
        {fr.frei ? (fr.kosten
          ? <Hinweis art="warn" titel="Mindestmenge nicht erreicht" testID="fracht-hinweis">{`Unter ${fr.unter} kg berechnen wir einen Frachtanteil von ${euro(fr.kosten)} pro Sendung – er ist oben bereits aufgeschlagen. Ab ${fr.frei} kg liefern wir frachtfrei (noch ${mengeText(Math.round((fr.frei - s.kg) * 100) / 100)} kg).`}</Hinweis>
          : <Hinweis art="ok" testID="fracht-hinweis">{`Ab ${fr.frei} kg frachtfrei – Ihr Bestellwunsch erfüllt die Mindestmenge.`}</Hinweis>) : null}
        <H2>Angaben</H2>
        <Feld testID="feld-termin" label="Wunschtermin (optional)" placeholder="TT.MM.JJJJ" value={a.kopf.termin} onChangeText={(t) => a.setKopf({ ...a.kopf, termin: t })}
          keyboardType="numbers-and-punctuation" fehler={termin === null ? 'Bitte als TT.MM.JJJJ eingeben.' : undefined} />
        <Feld testID="feld-referenz" label="Ihre Referenz (optional)" value={a.kopf.referenz} maxLength={60} onChangeText={(t) => a.setKopf({ ...a.kopf, referenz: t })} />
        <Feld testID="feld-bemerkung" label="Bemerkung (optional)" value={a.kopf.bemerkung} maxLength={1000} multiline onChangeText={(t) => a.setKopf({ ...a.kopf, bemerkung: t })} />
        <Leise>Ein Bestellwunsch ist noch keine Auftragsbestätigung. Preise und Fracht prüfen wir mit der Bestätigung.</Leise>
        {fehler ? <Hinweis art="fehler" testID="senden-fehler">{fehler}</Hinweis> : null}
        {neuLaden ? <Knopf titel="Aktuelles Angebot laden" icon="refresh-cw" onPress={() => { setFehler(''); setNeuLaden(false); a.laden(); }} /> : null}
        <Knopf testID="senden" titel="Bestellwunsch senden" icon="send" art="primaer" laedt={sendet} deaktiviert={a.offline} onPress={senden} />
      </Seite>
    </KeyboardAvoidingView>
  );
}
