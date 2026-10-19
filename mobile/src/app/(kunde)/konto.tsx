import { useRouter } from 'expo-router';
import React from 'react';
import { View } from 'react-native';
import { H1, H2, Hinweis, Karte, Knopf, Leise, Logo, Seite, T, Zeile } from '../../ui/bausteine';
import { Rechtliches, VersionZeile } from '../../ui/konto';
import { useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

export default function Konto() {
  const router = useRouter();
  const { rolle, kunde, abmelden, hinweis } = useSitzung();
  const { auswahl } = useAngebot();
  return (
    <Seite>
      <Logo hoehe={30} />
      {rolle === 'kunde' && kunde ? (
        <>
          <H1>Ihr Zugang</H1>
          <Karte style={{ gap: 2 }}>
            <T testID="konto-firma" style={{ fontSize: 17 }}>{kunde.firma}</T>
            {kunde.ansprechpartner ? <Leise>{kunde.ansprechpartner}</Leise> : null}
            <View style={{ height: 8 }} />
            <Zeile links="Benutzername" rechts={kunde.username} />
            <Zeile links="Angebote" rechts={auswahl.map((o) => o.name).join(', ')} />
          </Karte>
          <Knopf titel="Passwort ändern" icon="key" onPress={() => router.push({ pathname: '/anmelden', params: { modus: 'passwort' } })} />
          <Knopf testID="abmelden" titel="Abmelden" icon="log-out" art="gefahr" onPress={() => abmelden()} />
          <Leise>Nach längerer Inaktivität meldet die App Sie aus Sicherheitsgründen ab – wie die Website.</Leise>
        </>
      ) : (
        <>
          <H1>Anmelden</H1>
          {hinweis ? <Hinweis art="warn">{hinweis}</Hinweis> : null}
          <Karte style={{ gap: 10 }}>
            <H2>Kunden</H2>
            <Leise>Mit Ihrem Kundenzugang sehen Sie Ihre freigeschalteten Angebote und senden Bestellwünsche.</Leise>
            <Knopf testID="anmelden-kunde" titel="Als Kunde anmelden" art="primaer" icon="log-in" onPress={() => router.push('/anmelden')} />
          </Karte>
          <Karte style={{ gap: 10 }}>
            <H2>Mitarbeiter</H2>
            <Leise>Bestellwünsche bearbeiten – mit Ihrem Zugang zum Eingabebereich.</Leise>
            <Knopf testID="anmelden-team" titel="Als Mitarbeiter anmelden" icon="briefcase" onPress={() => router.push('/mitarbeiter')} />
          </Karte>
          <Leise>Noch keinen Zugang? Sprechen Sie Ihren Ansprechpartner bei Standard-Fleisch an.</Leise>
        </>
      )}
      <Rechtliches />
      <VersionZeile />
    </Seite>
  );
}
