/* Ablage auf dem Gerät.
   geheim: Sitzungskennung und Zugang zur Testumgebung – im Schlüsselbund (iOS) bzw. Keystore (Android).
   ablage: Angebot für offline, Merkliste, Bestellentwurf, gewählter Server – keine Geheimnisse. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const sicherName = (k: string) => k.replace(/[^A-Za-z0-9._-]/g, '_');
const web = Platform.OS === 'web';

export const geheim = {
  async get(k: string): Promise<string | null> {
    try {
      if (web) return typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('wa.' + k) : null;   // Web nur für Vorschau/Tests
      return await SecureStore.getItemAsync(sicherName(k));
    } catch { return null; }
  },
  async set(k: string, v: string): Promise<void> {
    try {
      if (web) { if (typeof sessionStorage !== 'undefined') sessionStorage.setItem('wa.' + k, v); return; }
      await SecureStore.setItemAsync(sicherName(k), v, { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY });
    } catch { /* Gerät ohne sicheren Speicher: Sitzung gilt dann nur bis zum Schließen */ }
  },
  async del(k: string): Promise<void> {
    try {
      if (web) { if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('wa.' + k); return; }
      await SecureStore.deleteItemAsync(sicherName(k));
    } catch { /* nichts zu tun */ }
  },
};

export const ablage = {
  async get<T>(k: string, fallback: T): Promise<T> {
    try { const v = await AsyncStorage.getItem(k); return v === null ? fallback : (JSON.parse(v) as T); } catch { return fallback; }
  },
  async set(k: string, v: unknown): Promise<void> {
    try { await AsyncStorage.setItem(k, JSON.stringify(v)); } catch { /* Speicher voll/gesperrt */ }
  },
  async del(k: string): Promise<void> {
    try { await AsyncStorage.removeItem(k); } catch { /* nichts zu tun */ }
  },
};
