/* Kopfzeile von Unterseiten (eigene Kopfzeile statt Systemkopf: gleiche Darstellung auf allen Geräten) */
import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from './bausteine';
import { SCHRIFT, useFarben } from './theme';

export function Kopf({ titel, rechts, schliessen }: { titel: string; rechts?: React.ReactNode; schliessen?: boolean }) {
  const f = useFarben();
  const router = useRouter();
  const ins = useSafeAreaInsets();
  return (
    <View style={{ paddingTop: ins.top + 4, backgroundColor: f.surface, borderBottomWidth: 1, borderBottomColor: f.line }}>
      <View style={{ height: 52, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6, gap: 4 }}>
        <Pressable testID="zurueck" accessibilityRole="button" accessibilityLabel={schliessen ? 'Schließen' : 'Zurück'} hitSlop={6}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
          <Icon name={schliessen ? 'x' : 'chevron-left'} size={24} />
        </Pressable>
        <Text numberOfLines={1} accessibilityRole="header" style={{ flex: 1, color: f.text, fontFamily: SCHRIFT.halbfett, fontSize: 17 }}>{titel}</Text>
        {rechts}
      </View>
    </View>
  );
}
