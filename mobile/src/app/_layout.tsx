import { Geist_400Regular } from '@expo-google-fonts/geist/400Regular';
import { Geist_500Medium } from '@expo-google-fonts/geist/500Medium';
import { Geist_600SemiBold } from '@expo-google-fonts/geist/600SemiBold';
import { Geist_700Bold } from '@expo-google-fonts/geist/700Bold';
import Feather from '@expo/vector-icons/Feather';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { Linking, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { H1, Knopf, Leise, Logo, Seite } from '../ui/bausteine';
import { useFarben } from '../ui/theme';
import { AngebotProvider } from '../zustand/angebot';
import { APP_VERSION, SitzungProvider, useSitzung } from '../zustand/sitzung';

SplashScreen.preventAutoHideAsync().catch(() => {});

function Navigation() {
  const { bereit, rolle, zuAlt, info } = useSitzung();
  const f = useFarben();
  useEffect(() => { if (bereit) SplashScreen.hideAsync().catch(() => {}); }, [bereit]);
  if (!bereit) return <View style={{ flex: 1, backgroundColor: f.bg }} />;
  if (zuAlt) {
    return (
      <Seite>
        <Logo />
        <H1>Bitte aktualisieren Sie die App</H1>
        <Leise>{`Diese Version (${APP_VERSION}) passt nicht mehr zum Angebotsportal. Mindestens erforderlich: ${info?.minAppVersion}. Bitte laden Sie die neue Version aus dem App Store bzw. Google Play.`}</Leise>
        <Knopf titel="Angebot im Browser öffnen" icon="external-link" onPress={() => Linking.openURL('https://angebot-stafl.de/')} />
      </Seite>
    );
  }
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: f.bg } }}>
      <Stack.Protected guard={rolle === 'team'}>
        <Stack.Screen name="(team)" />
        <Stack.Screen name="vorgang/[nr]" />
      </Stack.Protected>
      <Stack.Protected guard={rolle !== 'team'}>
        <Stack.Screen name="(kunde)" />
        <Stack.Screen name="kunde-bestellung/[nr]" />
        <Stack.Screen name="artikel/[id]" options={{ presentation: 'modal' }} />
      </Stack.Protected>
      <Stack.Screen name="anmelden" options={{ presentation: 'modal' }} />
      <Stack.Screen name="mitarbeiter" options={{ presentation: 'modal' }} />
      <Stack.Screen name="server" options={{ presentation: 'modal' }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [geladen, fehler] = useFonts({ Geist_400Regular, Geist_500Medium, Geist_600SemiBold, Geist_700Bold, ...Feather.font, ...Ionicons.font });
  const f = useFarben();
  if (!geladen && !fehler) return null;
  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      <View style={{ flex: 1, backgroundColor: f.bg }}>
        <SitzungProvider>
          <AngebotProvider>
            <Navigation />
          </AngebotProvider>
        </SitzungProvider>
      </View>
    </SafeAreaProvider>
  );
}
