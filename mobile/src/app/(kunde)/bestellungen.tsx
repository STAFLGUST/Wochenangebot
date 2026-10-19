/* Meine Bestellwünsche (nur eigene; der Server prüft das am einzelnen Vorgang) */
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { datum, euro, kg } from '../../kern/angebot';
import { H1, Hinweis, Icon, Knopf, Leer, Leise } from '../../ui/bausteine';
import { R, SCHRIFT, useFarben } from '../../ui/theme';
import { KurzVorgang, StatusMarke } from '../../ui/vorgang';
import { useSitzung } from '../../zustand/sitzung';

export default function MeineBestellungen() {
  const f = useFarben();
  const router = useRouter();
  const { api, abgelaufen, kunde, hinweis } = useSitzung();
  const [liste, setListe] = useState<KurzVorgang[]>([]);
  const [total, setTotal] = useState(0);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState('');

  const laden = useCallback(async (offset = 0) => {
    setLaedt(true); setFehler('');
    try {
      const r = await api.call<{ orders: KurzVorgang[]; total: number }>('kunde_bestellungen', { query: { offset, limit: 25 } });
      setListe((alt) => (offset ? [...alt, ...r.orders] : r.orders)); setTotal(r.total);
    } catch (e) {
      if (!abgelaufen(e)) setFehler(e instanceof Error ? e.message : 'Konnte nicht geladen werden.');
    } finally { setLaedt(false); }
  }, [api, abgelaufen]);
  useFocusEffect(useCallback(() => { if (kunde) laden(0); }, [laden, kunde]));

  if (!kunde) return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: f.bg, padding: 16, gap: 12 }}>
      {hinweis ? <Hinweis art="warn">{hinweis}</Hinweis> : null}
      <Leer icon="log-in" titel="Bitte anmelden" text="Ihre Bestellwünsche sehen Sie nach der Anmeldung."><Knopf titel="Als Kunde anmelden" art="primaer" onPress={() => router.push('/anmelden')} /></Leer>
    </SafeAreaView>
  );
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: f.bg }}>
      <FlatList
        testID="meine-bestellungen"
        style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
        data={liste}
        keyExtractor={(o) => o.nr}
        contentContainerStyle={{ padding: 16, gap: 10 }}
        refreshControl={<RefreshControl refreshing={laedt} onRefresh={() => laden(0)} tintColor={f.accent} colors={[f.accent]} />}
        ListHeaderComponent={<View style={{ gap: 6, marginBottom: 4 }}><H1>Meine Bestellwünsche</H1><Leise>Bearbeitungsstand Ihrer gesendeten Bestellwünsche.</Leise>{fehler ? <Hinweis art="fehler">{fehler}</Hinweis> : undefined}</View>}
        ListEmptyComponent={laedt ? undefined : <Leer icon="inbox" titel="Noch keine Bestellwünsche" text="Gesendete Bestellwünsche erscheinen hier mit ihrem Bearbeitungsstand." />}
        renderItem={({ item: o }) => (
          <Pressable testID={'vorgang-' + o.nr} onPress={() => router.push({ pathname: '/kunde-bestellung/[nr]', params: { nr: o.nr } })} accessibilityRole="button"
            style={({ pressed }) => ({ backgroundColor: pressed ? f.surface3 : f.surface, borderColor: f.line, borderWidth: 1, borderRadius: R.lg, padding: 14, gap: 6 })}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <Text style={{ color: f.text, fontFamily: SCHRIFT.halbfett, fontSize: 16 }}>{o.nr}</Text>
              <StatusMarke w={o.workflow} kunde />
            </View>
            <Text style={{ color: f.text2, fontFamily: SCHRIFT.normal, fontSize: 14 }}>{`${datum(o.t)} · ${o.positionCount} ${o.positionCount === 1 ? 'Position' : 'Positionen'} · ${kg(o.totalQty)} kg · ca. ${euro(o.total + (o.fracht?.kosten || 0))}`}</Text>
            {o.referenz ? <Text style={{ color: f.muted, fontFamily: SCHRIFT.normal, fontSize: 13 }}>{'Referenz: ' + o.referenz}</Text> : null}
            <View style={{ position: 'absolute', right: 12, bottom: 14 }}><Icon name="chevron-right" size={18} color={f.muted} /></View>
          </Pressable>
        )}
        ListFooterComponent={liste.length < total ? <Knopf titel="Weitere laden" onPress={() => laden(liste.length)} laedt={laedt} /> : undefined}
      />
    </SafeAreaView>
  );
}
