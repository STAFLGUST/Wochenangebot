"""Kleiner Test-Mailserver für die Keycloak-Prüfungen (nimmt Nachrichten an, hält sie im Speicher).

Keycloak (Jakarta Mail) meldet sich bevorzugt mit AUTH LOGIN an, daher hier LOGIN und PLAIN; ohne TLS, nur 127.0.0.1.
"""
import base64
import email
import email.policy
import socket
import threading


class Postfach:
    def __init__(self, port, user, password):
        self.user, self.password = user, password
        self.nachrichten, self.anmeldungen = [], []
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', port))
        self.sock.listen(8)
        threading.Thread(target=self._annehmen, daemon=True).start()

    def _annehmen(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(c,), daemon=True).start()

    def _sitzung(self, c):
        f = c.makefile('rb')
        senden = lambda s: c.sendall((s + '\r\n').encode())
        zeile = lambda: f.readline().decode().rstrip('\r\n')
        b64 = lambda: base64.b64decode(zeile()).decode()
        try:
            senden('220 postfach ESMTP')
            angemeldet, von, an = False, None, []
            while True:
                roh = f.readline()
                if not roh:                     # Verbindung beendet
                    return
                cmd = roh.decode().rstrip('\r\n')
                up = cmd.upper()
                if up.startswith(('EHLO', 'HELO')):
                    senden('250-postfach\r\n250 AUTH LOGIN PLAIN')
                elif up.startswith('AUTH LOGIN'):
                    senden('334 VXNlcm5hbWU6'); u = b64()
                    senden('334 UGFzc3dvcmQ6'); p = b64()
                    angemeldet = (u, p) == (self.user, self.password); self.anmeldungen.append((u, angemeldet))
                    senden('235 ok' if angemeldet else '535 Authentication failed')
                elif up.startswith('AUTH PLAIN'):
                    teile = (cmd.split(' ', 2)[2:] or [None])[0]
                    if teile is None:
                        senden('334 '); teile = zeile()
                    _, u, p = base64.b64decode(teile).decode().split('\0')
                    angemeldet = (u, p) == (self.user, self.password); self.anmeldungen.append((u, angemeldet))
                    senden('235 ok' if angemeldet else '535 Authentication failed')
                elif up.startswith('MAIL FROM'):
                    if not angemeldet:
                        senden('530 auth required'); continue
                    von, an = cmd[10:].strip('<> '), []; senden('250 ok')
                elif up.startswith('RCPT TO'):
                    an.append(cmd[8:].strip('<> ')); senden('250 ok')
                elif up == 'DATA':
                    senden('354 end with .')
                    daten = b''
                    while True:
                        z = f.readline()
                        if z in (b'.\r\n', b''):
                            break
                        daten += z[1:] if z.startswith(b'..') else z
                    msg = email.message_from_bytes(daten, policy=email.policy.default)
                    teil = msg.get_body(('plain',)) or msg.get_body(('html',))
                    self.nachrichten.append({'von': von, 'an': an, 'betreff': str(msg['subject']), 'text': teil.get_content() if teil else '',
                                             'roh': daten.decode('utf-8', 'replace')})
                    senden('250 queued')
                elif up == 'RSET':
                    von, an = None, []; senden('250 ok')
                elif up == 'QUIT':
                    senden('221 bye'); return
                elif up == 'NOOP':
                    senden('250 ok')
                else:
                    senden('502 unknown')
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass

    def an(self, adresse):
        return [n for n in self.nachrichten if adresse in n['an']]

    def schliessen(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
