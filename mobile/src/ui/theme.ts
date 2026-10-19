/* Farben und Maße wie die Website („Klar“, app/assets/app.css), hell und dunkel */
import { useColorScheme } from 'react-native';

export type Farben = {
  bg: string; surface: string; surface2: string; surface3: string; line: string; lineStrong: string;
  text: string; text2: string; muted: string; accent: string; accentInk: string; accentSoft: string; accentLine: string;
  zebra: string; ok: string; okBg: string; warn: string; warnBg: string; danger: string; dangerBg: string; mark: string;
  logoChip: string;
};
export const HELL: Farben = {
  bg: '#f3f3f1', surface: '#ffffff', surface2: '#fafaf9', surface3: '#efefec', line: '#e4e4e0', lineStrong: '#d3d3ce',
  text: '#0b0b0b', text2: '#4f4f4a', muted: '#6f6f6a', accent: '#8c1d2c', accentInk: '#ffffff', accentSoft: '#fbf1f2', accentLine: '#ecc9ce',
  zebra: '#f6f6f4', ok: '#23603f', okBg: '#e8f3ec', warn: '#8a5a1c', warnBg: '#f6eddf', danger: '#a3242f', dangerBg: '#fbecee', mark: '#f9e3a8',
  logoChip: 'transparent',
};
export const DUNKEL: Farben = {
  bg: '#0e0e0d', surface: '#161615', surface2: '#1b1b1a', surface3: '#242422', line: '#2a2a28', lineStrong: '#3a3a37',
  text: '#f0f0ee', text2: '#c4c4be', muted: '#908f89', accent: '#e08190', accentInk: '#1a0b0e', accentSoft: 'rgba(224,129,144,0.12)', accentLine: 'rgba(224,129,144,0.32)',
  zebra: '#1b1b1a', ok: '#7cc39e', okBg: 'rgba(124,195,158,0.12)', warn: '#d9a865', warnBg: 'rgba(217,168,101,0.13)', danger: '#f0a0a8', dangerBg: 'rgba(240,160,168,0.12)', mark: 'rgba(240,196,90,0.35)',
  logoChip: '#ffffff',
};
export function useFarben(): Farben { return useColorScheme() === 'dark' ? DUNKEL : HELL; }

export const SCHRIFT = { normal: 'Geist_400Regular', mittel: 'Geist_500Medium', halbfett: 'Geist_600SemiBold', fett: 'Geist_700Bold' };
export const R = { sm: 8, md: 10, lg: 14 };
