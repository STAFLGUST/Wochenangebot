import { useRouter } from 'expo-router';
import React, { useCallback, useMemo } from 'react';
import { Alert, FlatList, Platform, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Artikel } from '../../kern/angebot';
import { ArtikelZeile } from '../../ui/artikel';
import { H1, Hinweis, Knopf, Leer, Leise } from '../../ui/bausteine';
import { useFarben } from '../../ui/theme';
import { useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

export default function Merkliste() {
  const f = useFarben();
  const router = useRouter();
  const a = useAngebot();
  const { rolle } = useSitzung();
  const liste = useMemo(() => (a.angebot ? a.angebot.items.filter((i) => a.merkliste.has(i.key)) : []), [a.angebot, a.merkliste]);
  const fehlend = a.angebot ? [...a.merkliste].filter((k) => !a.angebot!.items.some((i) => i.key === k)).length : 0;
  const oeffnen = useCallback((it: Artikel) => router.push({ pathname: '/artikel/[id]', params: { id: it.id } }), [router]);
  const leeren = () => {
    if (Platform.OS === 'web') { a.merklisteLeeren(); return; }
    Alert.alert('Merkliste leeren?', 'Alle Artikel werden von der Merkliste entfernt.', [{ text: 'Abbrechen', style: 'cancel' }, { text: 'Leeren', style: 'destructive', onPress: a.merklisteLeeren }]);
  };
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: f.bg }}>
      <FlatList
        testID="merkliste"
        style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
        data={liste}
        keyExtractor={(it) => it.id}
        ListHeaderComponent={(
          <View style={{ padding: 16, gap: 8 }}>
            <H1>Merkliste</H1>
            <Leise>{rolle === 'kunde' ? 'Ihre Merkliste ist mit der Website abgeglichen.' : 'Die Merkliste bleibt auf diesem Gerät. Angemeldete Kunden sehen sie auch auf der Website.'}</Leise>
            {fehlend ? <Hinweis>{`${fehlend} gemerkte ${fehlend === 1 ? 'Artikel ist' : 'Artikel sind'} im aktuellen Angebot nicht enthalten.`}</Hinweis> : null}
          </View>
        )}
        ListEmptyComponent={<Leer icon="star" titel="Noch nichts gemerkt" text="Tippen Sie im Angebot auf den Stern, um Artikel hier zu sammeln." />}
        renderItem={({ item, index }) => <ArtikelZeile it={item} index={index} gemerkt menge={a.korb[item.id]} onOpen={oeffnen} onMerken={(it) => a.merken(it.key)} />}
        ListFooterComponent={a.merkliste.size ? <View style={{ padding: 16 }}><Knopf titel="Merkliste leeren" icon="trash-2" art="leise" onPress={leeren} testID="merkliste-leeren" /></View> : undefined}
      />
    </SafeAreaView>
  );
}
