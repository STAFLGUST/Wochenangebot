"""Erwartungswerte aus den anonymisierten Testdaten (tests/fixtures) – statt fest eingetragener Zahlen."""
import json
from umgebung import FIX


def de(v):
    """23.3 → '23,30' (deutsches Zahlenformat wie in der Oberfläche)."""
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def angebot(seed='data-seed'):
    raw = open(f'{FIX}/{seed}/angebot.php', encoding='utf-8').read()
    return json.loads(raw[raw.index('\n') + 1:])


def artikel(code, seed='data-seed'):
    return next(i for i in angebot(seed)['items'] if i['code'] == code)


def preis(code, seed='data-seed'):
    return artikel(code, seed)['price']['value']


def preise(seed='data-seed'):
    return [i['price']['value'] for i in angebot(seed)['items'] if i['price']['status'] == 'value']


def bestand_kg(code):
    m = json.load(open(f'{FIX}/bestand/master_stock.json'))
    return next(a[2] for a in m if (a[0].lstrip('0') or '0') == code)


def excel_preis(code, datei='Wochenangebot KW 44 2026.xlsx'):
    """Preis eines Artikels in einer Test-Angebotsliste (Muster: Art.-Nr. | Bezeichnung | Preis)."""
    import openpyxl
    ws = openpyxl.load_workbook(f'{FIX}/angebote/{datei}', data_only=True).worksheets[0]
    for row in ws.iter_rows():
        for i, c in enumerate(row):
            if isinstance(c.value, (int, float)) and str(int(c.value)) == code:
                return next(x.value for x in row[i + 1:i + 7] if isinstance(x.value, (int, float)) or (isinstance(x.value, str) and 'Anfr' in x.value))
    raise KeyError(code)
