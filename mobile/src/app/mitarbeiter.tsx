/* Mitarbeiter-Anmeldung mit Zwei-Faktor-Code – gleiche Regeln wie der Eingabebereich der Website */
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform } from 'react-native';
import { Feld, H1, Hinweis, Knopf, Leise, Logo, Seite } from '../ui/bausteine';
import { Kopf } from '../ui/kopf';
import { useFarben } from '../ui/theme';
import { useSitzung } from '../zustand/sitzung';

export default function MitarbeiterAnmelden() {
  const f = useFarben();
  const router = useRouter();
  const { teamAnmelden, teamCode } = useSitzung();
  const [schritt, setSchritt] = useState<'pw' | 'code'>('pw');
  const [name, setName] = useState('');
  const [pw, setPw] = useState('');
  const [code, setCode] = useState('');
  const [fehler, setFehler] = useState('');
  const [laedt, setLaedt] = useState(false);
  const fertig = () => router.replace('/vorgaenge');

  const weiter = async () => {
    setFehler(''); setLaedt(true);
    try {
      if (schritt === 'pw') { const r = await teamAnmelden(name, pw); if (r === 'code') { setSchritt('code'); setPw(''); } else fertig(); }
      else { await teamCode(code); fertig(); }
    } catch (e) {
      const m = e instanceof Error ? e.message : 'Anmeldung fehlgeschlagen.';
      setFehler(m);
      if (/Anmeldung ist abgelaufen|erneut anmelden/i.test(m)) { setSchritt('pw'); setCode(''); }
    } finally { setLaedt(false); }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: f.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Kopf titel="Mitarbeiter" schliessen />
      <Seite kante={['bottom']}>
        <Logo hoehe={34} />
        <H1>{schritt === 'pw' ? 'Mitarbeiter-Anmeldung' : 'Bestätigungscode'}</H1>
        {schritt === 'pw' ? (
          <>
            <Leise>Mit Ihrem Zugang zum Eingabebereich. In der App bearbeiten Sie Bestellwünsche; Angebote und Verwaltung bleiben im Browser.</Leise>
            <Feld testID="team-name" label="Benutzername" value={name} onChangeText={setName} autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username" />
            <Feld testID="team-pw" label="Passwort" value={pw} onChangeText={setPw} secureTextEntry autoComplete="current-password" textContentType="password" onSubmitEditing={weiter} />
          </>
        ) : (
          <>
            <Leise>Bitte den sechsstelligen Code aus Ihrer Authenticator-App eingeben (oder einen Wiederherstellungscode).</Leise>
            <Feld testID="team-code" label="Code" value={code} onChangeText={setCode} keyboardType="number-pad" autoComplete="one-time-code" textContentType="oneTimeCode" autoFocus maxLength={11} onSubmitEditing={weiter} />
          </>
        )}
        {fehler ? <Hinweis art="fehler" testID="team-fehler">{fehler}</Hinweis> : null}
        <Knopf testID="team-weiter" titel={schritt === 'pw' ? 'Anmelden' : 'Bestätigen'} art="primaer" laedt={laedt} deaktiviert={schritt === 'pw' ? !name || !pw : code.replace(/\s/g, '').length < 6} onPress={weiter} />
        {schritt === 'code' ? <Knopf titel="Zurück zur Anmeldung" art="leise" onPress={() => { setSchritt('pw'); setCode(''); setFehler(''); }} /> : null}
      </Seite>
    </KeyboardAvoidingView>
  );
}
