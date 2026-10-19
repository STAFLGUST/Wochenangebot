/* Bearbeitungsstand eines Bestellwunsches (orders.php). „Bestätigt“ ist intern; Kunden sehen dort „In Bearbeitung“. */
export const STATUS_TEXT: Record<string, string> = {
  neu: 'Neu', in_bearbeitung: 'In Bearbeitung', bestaetigt: 'Bestätigt (intern)', erledigt: 'Erledigt', storniert: 'Storniert',
};
export const STATUS_KUNDE: Record<string, string> = {
  neu: 'Eingegangen', in_bearbeitung: 'In Bearbeitung', bestaetigt: 'In Bearbeitung', erledigt: 'Erledigt', storniert: 'Storniert',
};
/** erlaubte Übergänge – gleiche Tabelle wie auf dem Server; der Server prüft trotzdem selbst */
export const UEBERGAENGE: Record<string, string[]> = {
  neu: ['in_bearbeitung', 'storniert'],
  in_bearbeitung: ['neu', 'bestaetigt', 'storniert'],
  bestaetigt: ['in_bearbeitung', 'erledigt', 'storniert'],
  erledigt: [],
  storniert: [],
};
export const STATUS_FILTER = ['', 'neu', 'in_bearbeitung', 'bestaetigt', 'erledigt', 'storniert'];
