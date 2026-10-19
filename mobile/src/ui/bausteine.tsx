/* Grundbausteine der Oberfläche: Text, Knöpfe, Eingabefelder, Hinweise – im Stil der Website */
import Feather from '@expo/vector-icons/Feather';
import React from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleProp, StyleSheet, Text, TextInput, TextInputProps, TextStyle, View, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Farben, R, SCHRIFT, useFarben } from './theme';

export type IconName = React.ComponentProps<typeof Feather>['name'];
export function Icon({ name, size = 20, color }: { name: IconName; size?: number; color?: string }) {
  const f = useFarben();
  return <Feather name={name} size={size} color={color || f.text} />;
}

type TProps = { children: React.ReactNode; style?: StyleProp<TextStyle>; numberOfLines?: number; testID?: string; selectable?: boolean };
export function T({ children, style, numberOfLines, testID, selectable }: TProps) {
  const f = useFarben();
  return <Text testID={testID} selectable={selectable} numberOfLines={numberOfLines} style={[{ color: f.text, fontFamily: SCHRIFT.normal, fontSize: 15, lineHeight: 21 }, style]}>{children}</Text>;
}
export const H1 = (p: TProps) => <T {...p} style={[{ fontFamily: SCHRIFT.halbfett, fontSize: 22, lineHeight: 28, letterSpacing: -0.2 }, p.style]} />;
export const H2 = (p: TProps) => <T {...p} style={[{ fontFamily: SCHRIFT.halbfett, fontSize: 17, lineHeight: 23 }, p.style]} />;
export function Leise(p: TProps) { const f = useFarben(); return <T {...p} style={[{ color: f.text2, fontSize: 14, lineHeight: 20 }, p.style]} />; }

export function Logo({ hoehe = 30, voll = false }: { hoehe?: number; voll?: boolean }) {
  const f = useFarben();
  const src = voll ? require('../../assets/logo-standard-fleisch.png') : require('../../assets/logo-standard-fleisch-kopf.png');
  const breite = voll ? hoehe * 630 / 200 : hoehe * 428 / 96;
  return (
    <View style={{ backgroundColor: f.logoChip, borderRadius: 6, padding: f.logoChip === 'transparent' ? 0 : 5, alignSelf: 'flex-start' }}>
      <Image source={src} style={{ width: breite, height: hoehe }} resizeMode="contain" accessibilityLabel="Standard-Fleisch" />
    </View>
  );
}

type KnopfArt = 'primaer' | 'normal' | 'leise' | 'gefahr';
export function Knopf({ titel, onPress, art = 'normal', icon, laedt, deaktiviert, testID, style, klein }:
  { titel: string; onPress: () => void; art?: KnopfArt; icon?: IconName; laedt?: boolean; deaktiviert?: boolean; testID?: string; style?: StyleProp<ViewStyle>; klein?: boolean }) {
  const f = useFarben();
  const bg = art === 'primaer' ? f.accent : art === 'gefahr' ? f.dangerBg : art === 'leise' ? 'transparent' : f.surface;
  const fg = art === 'primaer' ? f.accentInk : art === 'gefahr' ? f.danger : art === 'leise' ? f.accent : f.text;
  const aus = deaktiviert || laedt;
  return (
    <Pressable testID={testID} accessibilityRole="button" accessibilityState={{ disabled: !!aus }} disabled={aus} onPress={onPress}
      style={({ pressed }) => [{ minHeight: klein ? 38 : 48, paddingHorizontal: klein ? 12 : 16, borderRadius: R.md, backgroundColor: bg, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
        borderWidth: art === 'normal' ? 1 : 0, borderColor: f.lineStrong, opacity: aus ? 0.55 : pressed ? 0.85 : 1 }, style]}>
      {laedt ? <ActivityIndicator color={fg} /> : icon ? <Icon name={icon} size={klein ? 16 : 18} color={fg} /> : null}
      <Text style={{ color: fg, fontFamily: SCHRIFT.halbfett, fontSize: klein ? 14 : 16 }}>{titel}</Text>
    </Pressable>
  );
}

export function Feld({ label, hinweis, fehler, ...p }: TextInputProps & { label: string; hinweis?: string; fehler?: string }) {
  const f = useFarben();
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: f.text, fontFamily: SCHRIFT.mittel, fontSize: 14 }}>{label}</Text>
      <TextInput placeholderTextColor={f.muted} {...p}
        style={[{ minHeight: 48, borderWidth: 1, borderColor: fehler ? f.danger : f.lineStrong, borderRadius: R.md, paddingHorizontal: 14, fontSize: 16, color: f.text,
          backgroundColor: f.surface, fontFamily: SCHRIFT.normal }, p.multiline ? { minHeight: 88, paddingTop: 12, textAlignVertical: 'top' } : null, p.style]} />
      {fehler ? <Text style={{ color: f.danger, fontSize: 13, fontFamily: SCHRIFT.normal }}>{fehler}</Text> : hinweis ? <Text style={{ color: f.muted, fontSize: 13, fontFamily: SCHRIFT.normal }}>{hinweis}</Text> : null}
    </View>
  );
}

export function Karte({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const f = useFarben();
  return <View style={[{ backgroundColor: f.surface, borderColor: f.line, borderWidth: 1, borderRadius: R.lg, padding: 16 }, style]}>{children}</View>;
}

export function Hinweis({ art = 'info', titel, children, testID }: { art?: 'info' | 'warn' | 'fehler' | 'ok'; titel?: string; children?: React.ReactNode; testID?: string }) {
  const f = useFarben();
  const [bg, fg, icon] = art === 'warn' ? [f.warnBg, f.warn, 'alert-triangle'] : art === 'fehler' ? [f.dangerBg, f.danger, 'alert-circle'] : art === 'ok' ? [f.okBg, f.ok, 'check-circle'] : [f.surface3, f.text2, 'info'];
  return (
    <View testID={testID} accessibilityRole={art === 'fehler' ? 'alert' : undefined} style={{ backgroundColor: bg, borderRadius: R.md, padding: 12, flexDirection: 'row', gap: 10 }}>
      <Icon name={icon as IconName} size={18} color={fg} />
      <View style={{ flex: 1, gap: 2 }}>
        {titel ? <Text style={{ color: fg, fontFamily: SCHRIFT.halbfett, fontSize: 14 }}>{titel}</Text> : null}
        {typeof children === 'string' ? <Text style={{ color: art === 'info' ? f.text2 : fg, fontFamily: SCHRIFT.normal, fontSize: 14, lineHeight: 20 }}>{children}</Text> : children}
      </View>
    </View>
  );
}

export function Seite({ children, scroll = true, style, kante = ['top'] }: { children: React.ReactNode; scroll?: boolean; style?: StyleProp<ViewStyle>; kante?: ('top' | 'bottom')[] }) {
  const f = useFarben();
  return (
    <SafeAreaView edges={kante} style={{ flex: 1, backgroundColor: f.bg }}>
      {scroll
        ? <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[{ padding: 16, gap: 14, maxWidth: 720, width: '100%', alignSelf: 'center' }, style]}>{children}</ScrollView>
        : <View style={[{ flex: 1 }, style]}>{children}</View>}
    </SafeAreaView>
  );
}

export function Chip({ titel, aktiv, onPress, testID }: { titel: string; aktiv: boolean; onPress: () => void; testID?: string }) {
  const f = useFarben();
  return (
    <Pressable testID={testID} accessibilityRole="button" accessibilityState={{ selected: aktiv }} onPress={onPress}
      style={{ paddingHorizontal: 12, height: 34, borderRadius: 17, justifyContent: 'center', borderWidth: 1, borderColor: aktiv ? f.accent : f.lineStrong, backgroundColor: aktiv ? f.accentSoft : f.surface }}>
      <Text numberOfLines={1} style={{ color: aktiv ? f.accent : f.text, fontFamily: aktiv ? SCHRIFT.halbfett : SCHRIFT.mittel, fontSize: 13.5 }}>{titel}</Text>
    </Pressable>
  );
}

export function Leer({ icon, titel, text, children }: { icon: IconName; titel: string; text?: string; children?: React.ReactNode }) {
  const f = useFarben();
  return (
    <View style={{ alignItems: 'center', paddingVertical: 40, paddingHorizontal: 24, gap: 10 }}>
      <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: f.surface3, alignItems: 'center', justifyContent: 'center' }}><Icon name={icon} size={24} color={f.text2} /></View>
      <H2 style={{ textAlign: 'center' }}>{titel}</H2>
      {text ? <Leise style={{ textAlign: 'center' }}>{text}</Leise> : null}
      {children}
    </View>
  );
}

export function Zeile({ links, rechts, stark }: { links: string; rechts: string; stark?: boolean }) {
  const f = useFarben();
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 4 }}>
      <Text style={{ color: stark ? f.text : f.text2, fontFamily: stark ? SCHRIFT.halbfett : SCHRIFT.normal, fontSize: 15, flex: 1 }}>{links}</Text>
      <Text style={{ color: f.text, fontFamily: stark ? SCHRIFT.halbfett : SCHRIFT.mittel, fontSize: 15, fontVariant: ['tabular-nums'] }}>{rechts}</Text>
    </View>
  );
}

export const stil = (f: Farben) => StyleSheet.create({
  trenner: { height: StyleSheet.hairlineWidth, backgroundColor: f.line },
});
