/* Kunden-Anmeldung; danach – falls verlangt – eigenes Passwort festlegen. Auch „Passwort ändern“ aus dem Konto. */
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Linking, Platform, View } from 'react-native';
import { Feld, H1, Hinweis, Knopf, Leise, Logo, Seite } from '../ui/bausteine';
import { Kopf } from '../ui/kopf';
import { useFarben } from '../ui/theme';
import { useSitzung } from '../zustand/sitzung';

export default function Anmelden() {
  const f = useFarben();
  const router = useRouter();
  const { modus } = useLocalSearchParams<{ modus?: string }>();
  const { kundeAnmelden, kundePasswort, kunde, rolle, info, server } = useSitzung();
  const [name, setName] = useState('');
  const [pw, setPw] = useState('');
  const [alt, setAlt] = useState('');
  const [neu, setNeu] = useState('');
  const [neu2, setNeu2] = useState('');
  const [fehler, setFehler] = useState('');
  const [laedt, setLaedt] = useState(false);
  const passwortSchritt = modus === 'passwort' || (rolle === 'kunde' && !!kunde?.mustChange);

  const anmelden = async () => {
    setFehler(''); setLaedt(true);
    try {
      const k = await kundeAnmelden(name, pw);
      if (k.mustChange) { setAlt(pw); setPw(''); } else router.back();
    } catch (e) { setFehler(e instanceof Error ? e.message : 'Anmeldung fehlgeschlagen.'); } finally { setLaedt(false); }
  };
  const aendern = async () => {
    setFehler('');
    if (neu !== neu2) { setFehler('Die beiden neuen Passwörter stimmen nicht überein.'); return; }
    setLaedt(true);
    try { await kundePasswort(alt, neu); router.back(); }
    catch (e) { setFehler(e instanceof Error ? e.message : 'Das Passwort konnte nicht geändert werden.'); } finally { setLaedt(false); }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Kopf titel={passwortSchritt ? 'Passwort' : 'Anmelden'} schliessen />
      <Seite kante={['bottom']}>
        <Logo hoehe={34} />
        {info?.wartung ? <Hinweis art="warn" titel="Wartung">{info.wartung.message}</Hinweis> : null}
        {passwortSchritt ? (
          <>
            <H1>{kunde?.mustChange ? 'Eigenes Passwort festlegen' : 'Passwort ändern'}</H1>
            {kunde?.mustChange ? <Leise>Bitte legen Sie vor der ersten Nutzung ein eigenes Passwort fest.</Leise> : null}
            <Feld testID="pw-alt" label="Aktuelles Passwort" value={alt} onChangeText={setAlt} secureTextEntry autoComplete="current-password" textContentType="password" />
            <Feld testID="pw-neu" label="Neues Passwort" value={neu} onChangeText={setNeu} secureTextEntry autoComplete="new-password" textContentType="newPassword" hinweis="Mindestens 10 Zeichen, nicht leicht zu erraten." />
            <Feld testID="pw-neu2" label="Neues Passwort wiederholen" value={neu2} onChangeText={setNeu2} secureTextEntry autoComplete="new-password" textContentType="newPassword" onSubmitEditing={aendern} />
            {fehler ? <Hinweis art="fehler" testID="anmelden-fehler">{fehler}</Hinweis> : null}
            <Knopf testID="pw-speichern" titel="Passwort speichern" art="primaer" laedt={laedt} deaktiviert={!alt || !neu || !neu2} onPress={aendern} />
          </>
        ) : (
          <>
            <H1>Kunden-Anmeldung</H1>
            <Leise>Melden Sie sich mit den Zugangsdaten aus Ihrer Einladung an.</Leise>
            <Feld testID="kunde-name" label="Benutzername" value={name} onChangeText={setName} autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username" returnKeyType="next" />
            <Feld testID="kunde-pw" label="Passwort" value={pw} onChangeText={setPw} secureTextEntry autoComplete="current-password" textContentType="password" onSubmitEditing={anmelden} returnKeyType="go" />
            {fehler ? <Hinweis art="fehler" testID="anmelden-fehler">{fehler}</Hinweis> : null}
            <Knopf testID="kunde-anmelden" titel="Anmelden" art="primaer" icon="log-in" laedt={laedt} deaktiviert={!name || !pw} onPress={anmelden} />
            <View style={{ height: 4 }} />
            <Knopf titel="Passwort vergessen?" art="leise" onPress={() => Linking.openURL(server.base + (info?.links.kontakt || '/kontakt/'))} />
            <Leise>Ein neues Passwort sendet Ihnen Ihr Ansprechpartner per E-Mail-Link.</Leise>
          </>
        )}
      </Seite>
    </KeyboardAvoidingView>
  );
}
