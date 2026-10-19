/* Artikel im Detail: Preise, Merkmale, Merkliste und – für Kunden mit Bestellfunktion – Menge für den Bestellwunsch */
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { anzeigeName, euro, preisText, ZUSTAND } from '../../kern/angebot';
import { frachtFuer, mengeLesen, mengeText, summen, zeilenSumme } from '../../kern/bestellung';
import { Feld, H1, Hinweis, Karte, Knopf, Leer, Leise, Seite, T, Zeile } from '../../ui/bausteine';
import { Kopf } from '../../ui/kopf';
import { SCHRIFT, useFarben } from '../../ui/theme';
import { useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

export default function ArtikelSeite() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const f = useFarben();
  const a = useAngebot();
  const { rolle, bestellung } = useSitzung();
  const it = useMemo(() => a.angebot?.items.find((x) => x.id === id) || null, [a.angebot, id]);
  const [eingabe, setEingabe] = useState('');
  useEffect(() => { if (it) setEingabe(mengeText(a.korb[it.id])); }, [it, a.korb]);

  if (!it) return (<View style={{ flex: 1 }}><Kopf titel="Artikel" schliessen /><Leer icon="alert-circle" titel="Artikel nicht gefunden" text="Das Angebot wurde inzwischen aktualisiert." /></View>);

  const gemerkt = a.merkliste.has(it.key);
  const q = mengeLesen(eingabe);
  const ungueltig = Number.isNaN(q);
  const preise = [it.price, ...it.altPrices];
  const merkmale = [ZUSTAND[it.condition], it.origin, it.category, it.brand, ...it.features].filter((x, i, arr) => x && x !== 'Nicht angegeben' && arr.indexOf(x) === i) as string[];
  const vorher = a.angebot ? summen(a.korb, a.angebot.items) : null;
  const kgNeu = vorher ? vorher.kg - (a.korb[it.id] || 0) + (ungueltig ? 0 : q) : 0;
  const fr = frachtFuer(a.fracht, kgNeu);
  const plus = (n: number) => setEingabe(mengeText(Math.min(99999, (ungueltig ? 0 : q) + n)));

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Kopf titel={it.code ? 'Artikel ' + it.code : 'Artikel'} schliessen />
      <Seite kante={['bottom']}>
        <View style={{ gap: 4 }}>
          <Leise>{it.group}</Leise>
          <H1 testID="artikel-name">{anzeigeName(it)}</H1>
          {merkmale.length ? <Leise>{merkmale.join(' · ')}</Leise> : null}
        </View>
        <Karte style={{ gap: 4 }}>
          {preise.map((p, i) => (
            <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <T style={{ color: f.text2 }}>{p.label || (i === 0 ? (it.sale ? 'Sonderpreis' : 'Preis') : 'Weiterer Preis')}</T>
              <Text style={{ color: it.sale && i === 0 ? f.accent : f.text, fontFamily: SCHRIFT.halbfett, fontSize: 22, fontVariant: ['tabular-nums'] }}>
                {preisText(p)}{p.status === 'value' ? <Text style={{ fontSize: 14, color: f.text2, fontFamily: SCHRIFT.normal }}> € / kg</Text> : null}
              </Text>
            </View>
          ))}
          {it.sale ? <Leise>{`Sonderposten – solange der Vorrat reicht${it.regular != null ? ` (sonst ${preisText({ status: 'value', value: it.regular })} € / kg)` : ''}.`}</Leise> : null}
        </Karte>
        <Knopf testID="artikel-merken" titel={gemerkt ? 'Auf der Merkliste' : 'Auf die Merkliste'} icon="star" art={gemerkt ? 'primaer' : 'normal'} onPress={() => a.merken(it.key)} />
        {rolle === 'kunde' && bestellung ? (
          <Karte style={{ gap: 12 }}>
            <Feld testID="artikel-menge" label="Menge für den Bestellwunsch (kg)" value={eingabe} onChangeText={setEingabe} keyboardType="decimal-pad" inputMode="decimal"
              placeholder="z. B. 25" fehler={ungueltig ? 'Bitte eine Menge zwischen 0,01 und 99.999 kg eingeben (höchstens zwei Nachkommastellen).' : undefined} />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {[5, 10, 25].map((n) => <Knopf key={n} klein titel={'+' + n + ' kg'} onPress={() => plus(n)} style={{ flex: 1 }} />)}
            </View>
            {!ungueltig && q > 0 && it.price.status === 'value' && typeof it.price.value === 'number' ? <Zeile links="Warenwert (ca.)" rechts={euro(zeilenSumme(it.price.value, q))} /> : null}
            {!ungueltig && q > 0 && it.price.status !== 'value' ? <Hinweis>Preis auf Anfrage – wir nennen Ihnen den Preis mit der Bestätigung.</Hinweis> : null}
            {fr.frei && kgNeu > 0 && fr.kosten ? <Hinweis art="warn">{`Mit dieser Menge hat Ihr Bestellwunsch ${mengeText(kgNeu)} kg. Unter ${fr.unter} kg berechnen wir ${euro(fr.kosten)} Frachtanteil; ab ${fr.frei} kg frachtfrei.`}</Hinweis> : null}
            <Knopf testID="artikel-uebernehmen" titel={a.korb[it.id] && q === 0 ? 'Aus dem Bestellwunsch entfernen' : 'In den Bestellwunsch'} art="primaer" icon="shopping-bag" deaktiviert={ungueltig || (q === 0 && !a.korb[it.id])}
              onPress={() => { a.menge(it.id, q); router.back(); }} />
          </Karte>
        ) : rolle !== 'kunde' ? <Hinweis>Bestellwünsche können angemeldete Kunden senden.</Hinweis> : null}
      </Seite>
    </KeyboardAvoidingView>
  );
}
