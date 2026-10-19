import { Tabs } from 'expo-router/js-tabs';
import React from 'react';
import { Platform } from 'react-native';
import { Icon, IconName } from '../../ui/bausteine';
import { SCHRIFT, useFarben } from '../../ui/theme';
import { useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

export default function KundeTabs() {
  const f = useFarben();
  const { rolle, bestellung } = useSitzung();
  const { korb, merkliste, angebot } = useAngebot();
  const kunde = rolle === 'kunde';
  const nKorb = Object.keys(korb).length;
  const nMerk = angebot ? angebot.items.filter((i) => merkliste.has(i.key)).length : merkliste.size;
  const icon = (n: IconName) => function TabIcon({ color }: { color: unknown }) { return <Icon name={n} size={22} color={String(color)} />; };
  return (
    <Tabs screenOptions={{
      headerShown: false, tabBarActiveTintColor: f.accent, tabBarInactiveTintColor: f.muted,
      tabBarStyle: { backgroundColor: f.surface, borderTopColor: f.line, ...(Platform.OS === 'web' ? { height: 60 } : null) },
      tabBarLabelStyle: { fontFamily: SCHRIFT.mittel, fontSize: 11.5, lineHeight: 14 },
      tabBarBadgeStyle: { backgroundColor: f.accent, color: f.accentInk, fontFamily: SCHRIFT.halbfett, fontSize: 11 },
    }}>
      <Tabs.Screen name="angebot" options={{ title: 'Angebot', tabBarIcon: icon('list'), tabBarButtonTestID: 'tab-angebot' }} />
      <Tabs.Screen name="merkliste" options={{ title: 'Merkliste', tabBarIcon: icon('star'), tabBarBadge: nMerk || undefined, tabBarButtonTestID: 'tab-merkliste' }} />
      <Tabs.Screen name="bestellwunsch" options={{ title: 'Bestellen', tabBarIcon: icon('shopping-bag'), tabBarBadge: nKorb || undefined,
        href: kunde && bestellung ? undefined : null, tabBarButtonTestID: 'tab-bestellwunsch' }} />
      <Tabs.Screen name="bestellungen" options={{ title: 'Meine', tabBarIcon: icon('inbox'), href: kunde ? undefined : null, tabBarButtonTestID: 'tab-bestellungen' }} />
      <Tabs.Screen name="konto" options={{ title: kunde ? 'Konto' : 'Anmelden', tabBarIcon: icon(kunde ? 'user' : 'log-in'), tabBarButtonTestID: 'tab-konto' }} />
    </Tabs>
  );
}
