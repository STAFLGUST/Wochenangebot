"""Kleiner Test-Mailserver für die Ende-zu-Ende-Tests (nimmt Nachrichten an und hält sie im Speicher).

Unterstützt EHLO, optional STARTTLS bzw. direktes TLS, AUTH PLAIN/LOGIN, MAIL/RCPT/DATA/RSET/QUIT.
Empfänger, die mit „abgelehnt@“ beginnen, werden mit 550 abgewiesen (Fehlerfall).
"""
import base64
import email
import email.policy
import socket
import ssl
import threading


class TestSmtp:
    def __init__(self, port, user='portal@example.org', password='Test-Postfach-1', mode='none', cert=None, key=None):
        self.port, self.user, self.password, self.mode = port, user, password, mode
        self.messages, self.logins = [], []
        self.ctx = None
        if mode in ('starttls', 'ssl'):
            self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ctx.load_cert_chain(cert, key)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', port))
        self.sock.listen(8)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(c,), daemon=True).start()

    def _session(self, c):
        try:
            if self.mode == 'ssl':
                c = self.ctx.wrap_socket(c, server_side=True)
            f = c.makefile('rb')
            send = lambda s: c.sendall((s + '\r\n').encode())
            send('220 test ESMTP')
            authed, tls = False, self.mode == 'ssl'
            mail_from, rcpts = None, []
            while True:
                line = f.readline()
                if not line:
                    return
                cmd = line.decode().rstrip('\r\n')
                up = cmd.upper()
                if up.startswith('EHLO'):
                    caps = ['250-test']
                    if self.mode == 'starttls' and not tls:
                        caps.append('250-STARTTLS')
                    caps.append('250 AUTH PLAIN LOGIN')
                    send('\r\n'.join(caps))
                elif up == 'STARTTLS':
                    send('220 go ahead')
                    c = self.ctx.wrap_socket(c, server_side=True)
                    f = c.makefile('rb'); tls = True
                    send = lambda s, c=c: c.sendall((s + '\r\n').encode())
                elif up.startswith('AUTH PLAIN'):
                    parts = base64.b64decode(cmd.split(' ', 2)[2]).split(b'\0')
                    authed = parts[1].decode() == self.user and parts[2].decode() == self.password
                    self.logins.append((parts[1].decode(), authed, tls))
                    send('235 ok' if authed else '535 Authentication failed')
                elif up.startswith('MAIL FROM'):
                    if not authed:
                        send('530 auth required'); continue
                    mail_from, rcpts = cmd[10:].strip('<> '), []
                    send('250 ok')
                elif up.startswith('RCPT TO'):
                    addr = cmd[8:].strip('<> ')
                    if addr.startswith('abgelehnt@'):
                        send('550 mailbox unavailable'); continue
                    rcpts.append(addr); send('250 ok')
                elif up == 'DATA':
                    if not rcpts:
                        send('503 no recipients'); continue
                    send('354 end with .')
                    data = b''
                    while True:
                        l = f.readline()
                        if l in (b'.\r\n', b''):
                            break
                        data += l[1:] if l.startswith(b'..') else l
                    msg = email.message_from_bytes(data, policy=email.policy.default)
                    self.messages.append({'from': mail_from, 'to': rcpts, 'msg': msg, 'raw': data, 'tls': tls,
                                          'subject': str(msg['subject']),
                                          'text': msg.get_body(('plain',)).get_content(),
                                          'html': msg.get_body(('html',)).get_content()})
                    if getattr(self, 'drop_after_data', False):
                        return  # Message accepted locally, acknowledgement lost.
                    send('250 queued')
                elif up == 'RSET':
                    mail_from, rcpts = None, []; send('250 ok')
                elif up == 'QUIT':
                    send('221 bye'); return
                else:
                    send('502 unknown')
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)      # weckt den wartenden accept()-Aufruf
        except OSError:
            pass
        self.sock.close()
