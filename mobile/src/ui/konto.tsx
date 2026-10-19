/* Gemeinsame Teile der Kontoseiten: Rechtliches, Versionszeile */
import { useRouter } from 'expo-router';
import React, { useRef } from 'react';
import { Linking, Pressable } from 'react-native';
import { Karte, Knopf, Leise } from './bausteine';
import { useFarben } from './theme';
import { APP_VERSION, SERVER_LIVE, useSitzung } from '../zustand/sitzung';

export function Rechtliches() {
  const { server, info } = useSitzung();
  const links = info?.links || { kontakt: '/kontakt/', impressum: '/impressum/', datenschutz: '/datenschutz/' };
  const auf = (p: string) => Linking.openURL(server.base + p);
  return (
    <Karte style={{ gap: 4 }}>
      <Knopf klein art="leise" titel="Kontakt" icon="phone" onPress={() => auf(links.kontakt)} style={{ justifyContent: 'flex-start' }} />
      <Knopf klein art="leise" titel="Impressum" icon="file-text" onPress={() => auf(links.impressum)} style={{ justifyContent: 'flex-start' }} />
      <Knopf klein art="leise" titel="Datenschutz" icon="shield" onPress={() => auf(links.datenschutz)} style={{ justifyContent: 'flex-start' }} testID="link-datenschutz" />
    </Karte>
  );
}

/** Version; siebenmal tippen öffnet die Servereinstellung (Testumgebung) */
export function VersionZeile() {
  const router = useRouter();
  const { server } = useSitzung();
  const f = useFarben();
  const n = useRef(0);
  return (
    <Pressable testID="version" onPress={() => { n.current += 1; if (n.current >= 7) { n.current = 0; router.push('/server'); } }}>
      <Leise style={{ textAlign: 'center', color: f.muted, fontSize: 12.5 }}>{`Version ${APP_VERSION}${server.base !== SERVER_LIVE ? ' · ' + server.base.replace(/^https?:\/\//, '') : ''}`}</Leise>
    </Pressable>
  );
}

