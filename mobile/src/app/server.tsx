/* Server wählen (versteckt: siebenmal auf die Versionsnummer tippen). Für Tests gegen die Testumgebung.
   Benutzer und Passwort der Testumgebung gibt der Nutzer hier ein; sie liegen nur im sicheren Speicher des Geräts. */
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform } from 'react-native';
import { serverPruefen } from '../kern/api';
import { Chip, Feld, H1, Hinweis, Knopf, Leise, Seite } from '../ui/bausteine';
import { Kopf } from '../ui/kopf';
import { useFarben } from '../ui/theme';
import { SERVER_LIVE, SERVER_TEST, useSitzung } from '../zustand/sitzung';

export default function ServerSeite() {
  const f = useFarben();
  const router = useRouter();
  const { server, serverSetzen } = useSitzung();
  const [base, setBase] = useState(server.base);
  const [user, setUser] = useState(server.basic?.user || '');
  const [pass, setPass] = useState('');
  const [fehler, setFehler] = useState('');
  const speichern = async () => {
    const b = serverPruefen(base);
    if (!b) { setFehler('Bitte eine gültige Adresse mit https:// eingeben.'); return; }
    await serverSetzen({ base: b, basic: b !== SERVER_LIVE && user ? { user, pass: pass || server.basic?.pass || '' } : null });
    router.replace('/');
  };
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Kopf titel="Server" schliessen />
      <Seite kante={['bottom']}>
        <H1>Verbindung</H1>
        <Leise>Nur für Tests. Beim Wechsel wird die Anmeldung beendet.</Leise>
        <Chip titel="Echtbetrieb" aktiv={base === SERVER_LIVE} onPress={() => setBase(SERVER_LIVE)} testID="server-live" />
        <Chip titel="Testumgebung" aktiv={base === SERVER_TEST} onPress={() => setBase(SERVER_TEST)} testID="server-test" />
        <Feld label="Adresse" value={base} onChangeText={setBase} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
        {base !== SERVER_LIVE ? (
          <>
            <Feld label="Benutzer der Testumgebung" value={user} onChangeText={setUser} autoCapitalize="none" autoCorrect={false} />
            <Feld label="Passwort der Testumgebung" value={pass} onChangeText={setPass} secureTextEntry placeholder={server.basic?.pass ? 'gespeichert – leer lassen zum Beibehalten' : ''} />
            <Hinweis>Diese Angaben bleiben nur auf diesem Gerät (Schlüsselbund/Keystore).</Hinweis>
          </>
        ) : null}
        {fehler ? <Hinweis art="fehler">{fehler}</Hinweis> : null}
        <Knopf titel="Speichern und verbinden" art="primaer" onPress={speichern} />
      </Seite>
    </KeyboardAvoidingView>
  );
}
