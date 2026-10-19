/* Artikelzeile und Gruppenkopf der Angebotsliste (Angebot und Merkliste) */
import Ionicons from '@expo/vector-icons/Ionicons';
import React, { memo } from 'react';
import { Pressable, Text, View } from 'react-native';
import { anzeigeName, Artikel, kg as kgText, Preis, preisText } from '../kern/angebot';
import { SCHRIFT, useFarben } from './theme';

function PreisZelle({ p, it, haupt }: { p: Preis; it: Artikel; haupt: boolean }) {
  const f = useFarben();
  const wert = p.status === 'value';
  const sale = haupt && it.sale;
  return (
    <View style={{ alignItems: 'flex-end' }}>
      {p.label ? <Text style={{ color: f.muted, fontFamily: SCHRIFT.normal, fontSize: 11 }}>{p.label}</Text> : null}
      {sale && it.regular != null ? <Text style={{ color: f.muted, fontSize: 12, textDecorationLine: 'line-through', fontFamily: SCHRIFT.normal }}>{preisText({ status: 'value', value: it.regular })}</Text> : null}
      <Text style={{ color: sale ? f.accent : wert ? f.text : f.muted, fontFamily: wert ? SCHRIFT.halbfett : SCHRIFT.normal, fontSize: wert ? 15.5 : 13, fontVariant: ['tabular-nums'] }}>
        {preisText(p)}
      </Text>
    </View>
  );
}

type ZeileProps = { it: Artikel; index: number; gemerkt: boolean; menge?: number; onOpen: (it: Artikel) => void; onMerken: (it: Artikel) => void };
export const ArtikelZeile = memo(function ArtikelZeile({ it, index, gemerkt, menge, onOpen, onMerken }: ZeileProps) {
  const f = useFarben();
  const preise = [...it.altPrices, it.price];
  return (
    <Pressable testID={'artikel-' + it.id} onPress={() => onOpen(it)} accessibilityRole="button"
      accessibilityLabel={`${anzeigeName(it)}, ${it.code ? 'Artikel ' + it.code + ', ' : ''}${preisText(it.price)}${it.price.status === 'value' ? ' Euro je Kilogramm' : ''}`}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', minHeight: 54, paddingLeft: 16, paddingRight: 4, paddingVertical: 8, gap: 10,
        backgroundColor: pressed ? f.surface3 : index % 2 ? f.surface : f.zebra })}>
      <Text style={{ width: 46, color: f.text, fontFamily: SCHRIFT.normal, fontSize: 13, fontVariant: ['tabular-nums'] }}>{it.code}</Text>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={{ color: f.text, fontFamily: SCHRIFT.normal, fontSize: 15, lineHeight: 20 }}>{anzeigeName(it)}</Text>
        {it.sale || menge ? (
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            {it.sale ? <Text style={{ color: f.accent, backgroundColor: f.accentSoft, borderRadius: 4, paddingHorizontal: 6, fontSize: 11.5, fontFamily: SCHRIFT.halbfett, overflow: 'hidden' }}>Sonderposten</Text> : null}
            {menge ? <Text testID={'menge-' + it.id} style={{ color: f.ok, backgroundColor: f.okBg, borderRadius: 4, paddingHorizontal: 6, fontSize: 11.5, fontFamily: SCHRIFT.halbfett, overflow: 'hidden' }}>{kgText(menge)} kg im Bestellwunsch</Text> : null}
          </View>
        ) : null}
      </View>
      <View style={{ flexDirection: preise.length > 1 ? 'column' : 'row', gap: 2, minWidth: 64, alignItems: 'flex-end' }}>
        {preise.map((p, i) => <PreisZelle key={i} p={p} it={it} haupt={p === it.price} />)}
      </View>
      <Pressable testID={'merken-' + it.id} onPress={() => onMerken(it)} hitSlop={8} accessibilityRole="button"
        accessibilityLabel={gemerkt ? 'Von der Merkliste entfernen' : 'Auf die Merkliste'} accessibilityState={{ selected: gemerkt }}
        style={{ width: 40, height: 44, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={gemerkt ? 'star' : 'star-outline'} size={20} color={gemerkt ? f.accent : f.muted} />
      </Pressable>
    </Pressable>
  );
});

/** Gruppenname mit hervorgehobener Marke in Anführungszeichen (wie Druckliste) */
export function GruppenKopf({ name, bereich, zeigeBereich }: { name: string; bereich: string; zeigeBereich: boolean }) {
  const f = useFarben();
  const teile = name.split(/(["„“”][^"„“”]{2,40}["“”])/g);
  return (
    <View style={{ backgroundColor: f.bg }}>
      {zeigeBereich && bereich ? (
        <Text style={{ paddingHorizontal: 16, paddingTop: 18, paddingBottom: 6, color: f.text2, fontFamily: SCHRIFT.halbfett, fontSize: 12.5, letterSpacing: 0.4, textTransform: 'uppercase' }} numberOfLines={2}>{bereich}</Text>
      ) : null}
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: 16, paddingTop: 10, paddingBottom: 6, borderBottomWidth: 1.5, borderBottomColor: f.text, backgroundColor: f.surface, gap: 10 }}>
        <Text style={{ flex: 1, color: f.text, fontFamily: SCHRIFT.halbfett, fontSize: 14.5, lineHeight: 19 }} accessibilityRole="header">
          {teile.map((t, i) => /^["„“”]/.test(t) ? <Text key={i} style={{ color: f.accent, fontStyle: 'italic' }}>{'„' + t.slice(1, -1) + '“'}</Text> : t)}
        </Text>
        <Text style={{ color: f.text2, fontFamily: SCHRIFT.mittel, fontSize: 12, marginRight: 44 }}>€ / kg</Text>
      </View>
    </View>
  );
}
