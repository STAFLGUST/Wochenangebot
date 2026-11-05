<#-- STAFL-Plattform: E-Mail „Passwort vergessen“ (Link von der Anmeldeseite, konten.sh passwort-vergessen an) im Stil der
     Plattform-Mails (wie executeActions.ftl). Nur Tabellen und Inline-Stile, keine Bilder. Werte maskiert FreeMarker. -->
<#assign gueltig = linkExpirationFormatter(linkExpiration)>
<#assign ueberschrift = "Neues Passwort festlegen">
<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>${ueberschrift}</title></head>
<body style="margin:0;padding:0;background:#f4f1ec;font-family:Arial,Helvetica,sans-serif;color:#1d1a17;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Sie haben ein neues Passwort für die STAFL-Plattform angefordert.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;padding:28px 12px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;border:1px solid #e6e0d8;overflow:hidden;">
<tr><td style="background:#1d1a17;padding:18px 28px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#ffffff;font-weight:bold;">${realmName}</td>
<td align="right" style="font-size:12px;color:#c9bfb4;">Mitarbeiterzugang</td></tr></table></td></tr>
<tr><td style="height:4px;background:#7b1e2b;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:30px 28px 8px;"><h1 style="margin:0;font-size:24px;line-height:1.25;font-weight:bold;color:#1d1a17;">${ueberschrift}</h1></td></tr>
<tr><td style="padding:14px 28px 6px;font-size:15px;line-height:1.6;">
<p style="margin:0 0 12px;">Guten Tag<#if user?? && user.firstName?has_content> ${user.firstName}</#if>,</p>
<p style="margin:0;">für Ihren Zugang zur STAFL-Plattform wurde auf der Anmeldeseite „Passwort vergessen“ gewählt. Über den Knopf legen Sie ein neues Passwort fest.</p>
<#if user?? && user.username?has_content>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 4px;"><tr><td style="background:#f6f3ef;border:1px solid #eee7df;border-radius:10px;padding:12px 16px;">
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#857c72;margin-bottom:4px;">Ihr Benutzername</div>
<div style="font-family:Menlo,Consolas,'Courier New',monospace;font-size:17px;font-weight:bold;color:#1d1a17;">${user.username}</div></td></tr></table>
</#if>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 10px;"><tr><td style="border-radius:10px;background:#7b1e2b;">
<a href="${link}" style="display:inline-block;padding:14px 28px;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;letter-spacing:.01em;">Neues Passwort festlegen &rarr;</a></td></tr></table>
<p style="margin:0 0 6px;font-size:13px;color:#4a443e;">Der Link ist ${gueltig} gültig und kann nur einmal verwendet werden. Haben Sie einen zweiten Faktor eingerichtet (Einmalcode-App oder Passkey), fragt die Anmeldung danach – er bleibt unverändert.</p>
<p style="margin:0;font-size:12px;color:#857c72;">Falls der Knopf nicht funktioniert: <a href="${link}" style="color:#7b1e2b;">Link zum Passwort-Festlegen öffnen</a> (die Textfassung dieser E-Mail enthält ihn ebenfalls).</p>
</td></tr>
<tr><td style="padding:10px 28px 4px;"><div style="border-top:1px solid #eee7df;padding-top:18px;font-size:14px;line-height:1.5;color:#4a443e;"><strong style="color:#1d1a17;">Nicht angefordert?</strong> Dann ignorieren Sie diese E-Mail – Ihr Passwort bleibt unverändert. Kommt so eine E-Mail öfter, sagen Sie bitte Ihrem Administrator Bescheid.</div></td></tr>
<tr><td style="height:20px;"></td></tr>
</table>
<p style="max-width:560px;margin:16px auto 0;font-size:12px;line-height:1.5;color:#857c72;">Diese E-Mail wurde über die STAFL-Plattform versendet.</p>
</td></tr></table>
</body>
</html>
