import { useRouter } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, SectionList, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { abschnitte, Artikel, datum, datumZeit, euro, filtern, kg, titel } from '../../kern/angebot';
import { summen } from '../../kern/bestellung';
import { ArtikelZeile, GruppenKopf } from '../../ui/artikel';
import { Chip, Hinweis, Icon, Knopf, Leer, Logo, T } from '../../ui/bausteine';
import { R, SCHRIFT, useFarben } from '../../ui/theme';
import { useAngebot } from '../../zustand/angebot';
import { useSitzung } from '../../zustand/sitzung';

export default function AngebotSeite() {
  const f = useFarben();
  const router = useRouter();
  const { info, infoFehler, rolle, kunde, bestellung, hinweis } = useSitzung();
  const a = useAngebot();
  const [q, setQ] = useState('');
  const [bereich, setBereich] = useState<string | null>(null);

  const items = useMemo(() => (a.angebot ? filtern(a.angebot.items, { q, bereich, nurMerkliste: false, merkliste: a.merkliste }) : []), [a.angebot, q, bereich, a.merkliste]);
  const sections = useMemo(() => (a.angebot ? abschnitte(a.angebot, items) : []), [a.angebot, items]);
  const s = useMemo(() => (a.angebot ? summen(a.korb, a.angebot.items) : null), [a.korb, a.angebot]);
  const oeffnen = useCallback((it: Artikel) => router.push({ pathname: '/artikel/[id]', params: { id: it.id } }), [router]);
  const merken = useCallback((it: Artikel) => a.merken(it.key), [a]);
  const gesperrt = !a.angebot && info && !info.stdPublic && rolle !== 'kunde';

  const kopf = (
    <View style={{ gap: 12, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Logo hoehe={28} />
        {info?.testumgebung ? <Text style={{ color: f.warn, backgroundColor: f.warnBg, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, fontFamily: SCHRIFT.halbfett, fontSize: 12, overflow: 'hidden' }}>Testumgebung</Text> : null}
      </View>
      {a.angebot ? (
        <View style={{ gap: 2 }}>
          <T testID="angebot-titel" style={{ fontFamily: SCHRIFT.halbfett, fontSize: 19, lineHeight: 25 }}>{titel(a.angebot)}</T>
          <T style={{ color: f.text2, fontSize: 13.5 }}>{`${a.angebot.meta.offerName && a.angebot.meta.offerId !== 'std' ? a.angebot.meta.offerName + ' · ' : ''}Stand ${datum(a.angebot.publishedAt)} · Preise in € je kg`}</T>
        </View>
      ) : null}
      {a.auswahl.length > 1 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {a.auswahl.map((o) => <Chip key={o.id} testID={'angebotwahl-' + o.id} titel={o.name} aktiv={a.angebotId === o.id} onPress={() => a.setAngebotId(o.id)} />)}
        </ScrollView>
      ) : null}
      {hinweis ? <Hinweis art="warn">{hinweis}</Hinweis> : null}
      {info?.wartung ? <Hinweis art="warn" titel="Wartung">{info.wartung.message}</Hinweis> : null}
      {a.offline ? <Hinweis art="warn" titel="Offline" testID="hinweis-offline">{`Keine Verbindung. Angezeigt wird der Stand vom ${datumZeit(a.geladen)} – Preise ohne Gewähr. Bestellwünsche können erst wieder online gesendet werden.`}</Hinweis> : null}
      {a.fehler && !a.angebot && !gesperrt ? <Hinweis art="fehler">{a.fehler}</Hinweis> : null}
      {!a.angebot && infoFehler && !a.fehler ? <Hinweis art="fehler">{infoFehler}</Hinweis> : null}
      {rolle === 'kunde' && kunde && !bestellung && info && !info.bestellfunktion && a.angebot ? <Hinweis>Bestellwünsche über das Portal sind derzeit nicht möglich. Bitte wenden Sie sich direkt an uns.</Hinweis> : null}
      {rolle === 'gast' && a.angebot ? (
        <Pressable onPress={() => router.push('/anmelden')} testID="hinweis-anmelden">
          <Hinweis>Kunden mit Zugang sehen hier ihre Angebote und können Bestellwünsche senden. Zum Anmelden tippen.</Hinweis>
        </Pressable>
      ) : null}
      {a.angebot ? (
        <>
          <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: f.surface, borderWidth: 1, borderColor: f.lineStrong, borderRadius: R.md, paddingHorizontal: 12, gap: 8 }}>
            <Icon name="search" size={18} color={f.muted} />
            <TextInput testID="suche" value={q} onChangeText={setQ} placeholder="Artikel, Nummer oder Merkmal suchen" placeholderTextColor={f.muted}
              autoCorrect={false} returnKeyType="search" clearButtonMode="while-editing"
              style={{ flex: 1, height: 46, fontSize: 16, color: f.text, fontFamily: SCHRIFT.normal }} />
            {q ? <Pressable onPress={() => setQ('')} accessibilityLabel="Suche leeren" hitSlop={8}><Icon name="x" size={18} color={f.muted} /></Pressable> : null}
          </View>
          {a.angebot.sections.length > 1 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              <Chip testID="bereich-alle" titel="Alle Bereiche" aktiv={!bereich} onPress={() => setBereich(null)} />
              {a.angebot.sections.map((b, i) => <Chip key={b} testID={'bereich-' + i} titel={b.length > 38 ? b.slice(0, 36) + '…' : b} aktiv={bereich === b} onPress={() => setBereich(bereich === b ? null : b)} />)}
            </ScrollView>
          ) : null}
          <T style={{ color: f.muted, fontSize: 13 }} testID="trefferzahl">{items.length === a.angebot.items.length ? `${items.length} Artikel` : `${items.length} von ${a.angebot.items.length} Artikeln`}</T>
        </>
      ) : null}
    </View>
  );

  const fuss = a.angebot && a.fracht && a.fracht.hinweis.length ? (
    <View testID="vermerk" style={{ margin: 16, padding: 14, borderRadius: R.md, backgroundColor: f.surface3, gap: 6 }}>
      {a.fracht.hinweis.map((l, i) => <T key={i} style={{ fontSize: 13.5, lineHeight: 19, color: i === 0 ? f.text : f.text2, fontFamily: i === 0 ? SCHRIFT.mittel : SCHRIFT.normal }}>{l}</T>)}
    </View>
  ) : <View style={{ height: 24 }} />;

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: f.bg }}>
      {gesperrt ? (
        <ScrollView>{kopf}
          <Leer icon="lock" titel="Bitte anmelden" text="Das Angebot ist nur für Kunden mit Zugang sichtbar.">
            <Knopf titel="Als Kunde anmelden" art="primaer" icon="log-in" onPress={() => router.push('/anmelden')} />
          </Leer>
        </ScrollView>
      ) : (
        <SectionList
          testID="angebotsliste"
        style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
          sections={sections}
          keyExtractor={(it) => it.id}
          stickySectionHeadersEnabled
          initialNumToRender={24}
          windowSize={11}
          ListHeaderComponent={kopf}
          ListFooterComponent={fuss}
          ListEmptyComponent={a.angebot ? <Leer icon="search" titel="Keine Treffer" text="Andere Suchbegriffe versuchen oder den Bereich zurücksetzen." /> : a.laedt ? undefined : <Leer icon="cloud-off" titel="Kein Angebot geladen" text="Bitte später erneut versuchen."><Knopf titel="Erneut laden" icon="refresh-cw" onPress={a.laden} /></Leer>}
          refreshControl={<RefreshControl refreshing={a.laedt} onRefresh={a.laden} tintColor={f.accent} colors={[f.accent]} />}
          renderSectionHeader={({ section }) => {
            const i = sections.indexOf(section);
            return <GruppenKopf name={section.titel} bereich={section.bereich} zeigeBereich={i === 0 || sections[i - 1].bereich !== section.bereich} />;
          }}
          renderItem={({ item, index }) => <ArtikelZeile it={item} index={index} gemerkt={a.merkliste.has(item.key)} menge={a.korb[item.id]} onOpen={oeffnen} onMerken={merken} />}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={{ paddingBottom: bestellung && s && s.zeilen.length ? 84 : 0 }}
        />
      )}
      {bestellung && s && s.zeilen.length ? (
        <Pressable testID="bestellleiste" onPress={() => router.push('/bestellwunsch')} accessibilityRole="button"
          style={{ position: 'absolute', left: 12, right: 12, bottom: 12, backgroundColor: f.text, borderRadius: R.lg, paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <Icon name="shopping-bag" size={20} color={f.bg} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: f.bg, fontFamily: SCHRIFT.halbfett, fontSize: 15 }}>{`Bestellwunsch · ${s.zeilen.length} ${s.zeilen.length === 1 ? 'Position' : 'Positionen'}`}</Text>
            <Text style={{ color: f.bg, opacity: 0.8, fontFamily: SCHRIFT.normal, fontSize: 13 }}>{`${kg(s.kg)} kg · ca. ${euro(s.summe)}${s.anfrage ? ' + Preise auf Anfrage' : ''}`}</Text>
          </View>
          <Icon name="chevron-right" size={20} color={f.bg} />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}
