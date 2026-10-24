"""Gemeinsame Vorbereitung der Bestell-Testgruppen: Kunde mit Zugang, veröffentlichtes Angebot und Test-Mailserver."""
from kunden_hilfe import Client
from umgebung import SMTP_PORT  # Testserver je Gruppe (parallel)
from smtp_test import TestSmtp

PW = 'Sicheres-Passwort-1'
def setup():
    smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
    a = Client('198.51.100.2'); assert a.call('login', {'username':'admin','password':PW})[0] == 200
    def customer(username, firma):
        rev=a.call('kunden')[1]['rev']
        r=a.call('kunde_save', {'rev':rev,'firma':firma,'nr':username,'email':username+'@example.org','active':True,'angebote':['std'], 'login':{'username':username,'password':'Kantine-Kennwort-5','mustChange':False,'active':True}})
        assert r[0] == 200, r
        c=Client(); assert c.call('kunde_login',{'username':username,'password':'Kantine-Kennwort-5'})[0] == 200
        return c,r[1]['customer']['id']
    k,kid=customer('kantine.test','Kantine <Test>'); other,_=customer('kantine.anders','Andere Firma')
    assert a.call('bestell_settings_save',{'enabled':True,'to':'orders@example.org','copy':False})[0] == 200
    pub=a.call('draft')[1]['published']; item=pub['items'][0]
    payload={'angebot':'std','publishedAt':pub.get('publishedAt',pub.get('savedAt','')),'positions':[{'id':item['id'],'qty':2}],'referenz':'Testreferenz','requestId':'test-request-123456789'}
    r=k.call('kunde_bestellung',payload);assert r[0]==200,r
    return smtp,a,k,other,kid,payload,r[1]['nr']
