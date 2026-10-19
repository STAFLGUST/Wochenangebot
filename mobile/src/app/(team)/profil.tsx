import React from 'react';
import { H1, Karte, Knopf, Leise, Logo, Seite, T, Zeile } from '../../ui/bausteine';
import { Rechtliches, VersionZeile } from '../../ui/konto';
import { useSitzung } from '../../zustand/sitzung';

const ROLLE: Record<string, string> = { admin: 'Administrator', editor: 'Bearbeiter', viewer: 'Leser' };

export default function Profil() {
  const { mitarbeiter, abmelden } = useSitzung();
  return (
    <Seite>
      <Logo hoehe={30} />
      <H1>Mitarbeiter</H1>
      {mitarbeiter ? (
        <Karte style={{ gap: 2 }}>
          <T testID="profil-name" style={{ fontSize: 17 }}>{mitarbeiter.name}</T>
          <Zeile links="Benutzername" rechts={mitarbeiter.username} />
          <Zeile links="Rolle" rechts={ROLLE[mitarbeiter.role] || mitarbeiter.role} />
          <Zeile links="Bestellwünsche bearbeiten" rechts={mitarbeiter.perms.includes('bestellungen.bearbeiten') ? 'ja' : 'nur ansehen'} />
        </Karte>
      ) : null}
      <Leise>Angebote, Kunden und Einstellungen pflegen Sie weiter im Eingabebereich der Website.</Leise>
      <Knopf testID="team-abmelden" titel="Abmelden" icon="log-out" art="gefahr" onPress={() => abmelden()} />
      <Rechtliches />
      <VersionZeile />
    </Seite>
  );
}
