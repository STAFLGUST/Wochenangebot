import { Tabs } from 'expo-router/js-tabs';
import React from 'react';
import { Platform } from 'react-native';
import { Icon } from '../../ui/bausteine';
import { SCHRIFT, useFarben } from '../../ui/theme';

export default function TeamTabs() {
  const f = useFarben();
  return (
    <Tabs screenOptions={{
      headerShown: false, tabBarActiveTintColor: f.accent, tabBarInactiveTintColor: f.muted,
      tabBarStyle: { backgroundColor: f.surface, borderTopColor: f.line, ...(Platform.OS === 'web' ? { height: 60 } : null) }, tabBarLabelStyle: { fontFamily: SCHRIFT.mittel, fontSize: 11.5, lineHeight: 14 },
    }}>
      <Tabs.Screen name="vorgaenge" options={{ title: 'Bestellwünsche', tabBarIcon: ({ color }) => <Icon name="inbox" size={22} color={String(color)} />, tabBarButtonTestID: 'tab-vorgaenge' }} />
      <Tabs.Screen name="profil" options={{ title: 'Konto', tabBarIcon: ({ color }) => <Icon name="user" size={22} color={String(color)} />, tabBarButtonTestID: 'tab-profil' }} />
    </Tabs>
  );
}
