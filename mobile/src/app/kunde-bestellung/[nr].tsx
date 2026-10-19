import { useLocalSearchParams } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { datumZeit } from '../../kern/angebot';
import { H1, Hinweis, Leise, Seite } from '../../ui/bausteine';
import { Kopf } from '../../ui/kopf';
import { Positionen, StatusMarke, Vorgang } from '../../ui/vorgang';
import { useSitzung } from '../../zustand/sitzung';

export default function KundeBestellung() {
  const { nr } = useLocalSearchParams<{ nr: string }>();
  const { api, abgelaufen } = useSitzung();
  const [o, setO] = useState<Vorgang | null>(null);
  const [fehler, setFehler] = useState('');
  const laden = useCallback(async () => {
    try { setO((await api.call<{ order: Vorgang }>('kunde_bestellung_detail', { query: { nr } })).order); }
    catch (e) { if (!abgelaufen(e)) setFehler(e instanceof Error ? e.message : 'Konnte nicht geladen werden.'); }
  }, [api, nr, abgelaufen]);
  useEffect(() => { laden(); }, [laden]);
  return (
    <View style={{ flex: 1 }}>
      <Kopf titel={'Bestellwunsch ' + (nr || '')} />
      <Seite kante={['bottom']}>
        {fehler ? <Hinweis art="fehler">{fehler}</Hinweis> : null}
        {o ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <H1 testID="detail-nr">{o.nr}</H1>
              <StatusMarke w={o.workflow} kunde />
            </View>
            <Leise>{`${datumZeit(o.t)}${o.angebotName ? ' · ' + o.angebotName : ''}${o.week ? ` · KW ${o.week}/${o.year}` : ''}`}</Leise>
            <Positionen o={o} />
            <Leise>Preise und Positionen sind der Stand beim Senden. Ein Bestellwunsch ist noch keine Auftragsbestätigung.</Leise>
          </>
        ) : null}
      </Seite>
    </View>
  );
}
