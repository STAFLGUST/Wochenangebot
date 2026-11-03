<#ftl output_format="plainText">
<#-- STAFL-Plattform: Textfassung der E-Mail „Passwort vergessen“ (zur HTML-Fassung html/password-reset.ftl) -->
Guten Tag<#if user?? && user.firstName?has_content> ${user.firstName}</#if>,

für Ihren Zugang zur STAFL-Plattform wurde auf der Anmeldeseite „Passwort vergessen“ gewählt. Über den folgenden Link legen Sie ein neues Passwort fest.
<#if user?? && user.username?has_content>

Ihr Benutzername: ${user.username}
</#if>

${link}

Der Link ist ${linkExpirationFormatter(linkExpiration)} gültig und kann nur einmal verwendet werden. Haben Sie einen zweiten Faktor eingerichtet (Einmalcode-App oder Passkey), fragt die Anmeldung danach – er bleibt unverändert.

Nicht angefordert? Dann ignorieren Sie diese E-Mail – Ihr Passwort bleibt unverändert. Kommt so eine E-Mail öfter, sagen Sie bitte Ihrem Administrator Bescheid.

-- 
Diese E-Mail wurde über die STAFL-Plattform versendet.
