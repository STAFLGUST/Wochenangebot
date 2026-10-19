/* Bestellwünsche für Mitarbeiter: Suche, Status, Seitenweise laden */
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { datumZeit, euro, kg } from '../../kern/angebot';
import { STATUS_FILTER, STATUS_TEXT } from '../../kern/status';
import { Chip, H1, Hinweis, Icon, Knopf, Leer, Logo } from '../../ui/bausteine';
import { R, SCHRIFT, useFarben } from '../../ui/theme';
import { KurzVorgang, StatusMarke } from '../../ui/vorgang';
import { useSitzung } from '../../zustand/sitzung';

export default function Vorgaenge() {
  const f = useFarben();
  const router = useRouter();
  const { api, abgelaufen, info } = useSitzung();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [liste, setListe] = useState<KurzVorgang[]>([]);
  const [total, setTotal] = useState(0);
  const [namen, setNamen] = useState<Record<string, string>>({});
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState('');
  const lauf = useRef(0);

  const laden = useCallback(async (offset = 0) => {
    const n = ++lauf.current;
    setLaedt(true); setFehler('');
    try {
      const r = await api.call<{ orders: KurzVorgang[]; total: number; assignees: { id: string; name: string }[] }>('bestellungen', { query: { q: q.trim(), workflow: status, offset, limit: 25 } });
      if (n !== lauf.current) return;
      setListe((alt) => (offset ? [...alt, ...r.orders] : r.orders)); setTotal(r.total);
      setNamen(Object.fromEntries(r.assignees.map((x) => [x.id, x.name])));
    } catch (e) {
      if (n === lauf.current && !abgelaufen(e)) setFehler(e instanceof Error ? e.message : 'Konnte nicht geladen werden.');
    } finally { if (n === lauf.current) setLaedt(false); }
  }, [api, q, status, abgelaufen]);
  const ladenRef = useRef(laden);
  ladenRef.current = laden;
  const erstes = useRef(true);
  useEffect(() => { const t = setTimeout(() => laden(0), q ? 300 : 0); return () => clearTimeout(t); }, [laden, q]);
  // beim Zurückkehren aus dem Detail aktualisieren (nicht beim ersten Anzeigen – das macht der Effekt oben)
  useFocusEffect(useCallback(() => { if (erstes.current) { erstes.current = false; return; } ladenRef.current(0); }, []));

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: f.bg }}>
      <FlatList
        testID="vorgaenge"
        style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
        data={liste}
        keyExtractor={(o) => o.nr}
        contentContainerStyle={{ padding: 16, gap: 10 }}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={laedt} onRefresh={() => laden(0)} tintColor={f.accent} colors={[f.accent]} />}
        ListHeaderComponent={(
          <View style={{ gap: 12, marginBottom: 2 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Logo hoehe={26} />
              {info?.testumgebung ? <Text style={{ color: f.warn, fontFamily: SCHRIFT.halbfett, fontSize: 12 }}>Testumgebung</Text> : null}
            </View>
            <H1>Bestellwünsche</H1>
            <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: f.surface, borderWidth: 1, borderColor: f.lineStrong, borderRadius: R.md, paddingHorizontal: 12, gap: 8 }}>
              <Icon name="search" size={18} color={f.muted} />
              <TextInput testID="vorgang-suche" value={q} onChangeText={setQ} placeholder="Nummer, Firma oder Referenz" placeholderTextColor={f.muted} autoCorrect={false}
                style={{ flex: 1, height: 46, fontSize: 16, color: f.text, fontFamily: SCHRIFT.normal }} />
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              {STATUS_FILTER.map((s) => <Chip key={s || 'alle'} testID={'status-' + (s || 'alle')} titel={s ? STATUS_TEXT[s].replace(' (intern)', '') : 'Alle'} aktiv={status === s} onPress={() => setStatus(s)} />)}
            </ScrollView>
            {fehler ? <Hinweis art="fehler">{fehler}</Hinweis> : null}
            <Text style={{ color: f.muted, fontFamily: SCHRIFT.normal, fontSize: 13 }}>{`${total} ${total === 1 ? 'Bestellwunsch' : 'Bestellwünsche'}`}</Text>
          </View>
        )}
        ListEmptyComponent={laedt ? undefined : <Leer icon="inbox" titel="Keine Bestellwünsche" text={q || status ? 'Für diese Auswahl gibt es keine Treffer.' : 'Neue Bestellwünsche erscheinen hier.'} />}
        renderItem={({ item: o }) => (
          <Pressable testID={'vorgang-' + o.nr} onPress={() => router.push({ pathname: '/vorgang/[nr]', params: { nr: o.nr } })} accessibilityRole="button"
            style={({ pressed }) => ({ backgroundColor: pressed ? f.surface3 : f.surface, borderColor: o.workflow === 'neu' ? f.accentLine : f.line, borderWidth: 1, borderRadius: R.lg, padding: 14, gap: 5 })}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <Text style={{ color: f.text, fontFamily: SCHRIFT.halbfett, fontSize: 16, flex: 1 }} numberOfLines={1}>{o.firma}</Text>
              <StatusMarke w={o.workflow} />
            </View>
            <Text style={{ color: f.text2, fontFamily: SCHRIFT.normal, fontSize: 14 }}>{`${o.nr} · ${datumZeit(o.t)}`}</Text>
            <Text style={{ color: f.text2, fontFamily: SCHRIFT.normal, fontSize: 14 }}>{`${o.positionCount} Pos. · ${kg(o.totalQty)} kg · ca. ${euro(o.total + (o.fracht?.kosten || 0))}${o.assignee && namen[o.assignee] ? ' · ' + namen[o.assignee] : ''}`}</Text>
            {o.delivery === 'fehler' || (o.mailPending ?? 0) > 0 ? <Text style={{ color: f.danger, fontFamily: SCHRIFT.mittel, fontSize: 13 }}>E-Mail-Zustellung offen – im Eingabebereich prüfen</Text> : null}
          </Pressable>
        )}
        ListFooterComponent={liste.length < total ? <Knopf titel="Weitere laden" onPress={() => laden(liste.length)} laedt={laedt} /> : undefined}
      />
    </SafeAreaView>
  );
}
