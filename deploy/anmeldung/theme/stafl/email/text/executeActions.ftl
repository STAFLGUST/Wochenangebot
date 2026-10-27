<#ftl output_format="plainText">
<#-- STAFL-Plattform: Textfassung der E-Mail „Konto aktualisieren“ (zur HTML-Fassung html/executeActions.ftl) -->
<#assign nurPasswort = requiredActions?? && requiredActions?size == 1 && requiredActions?seq_contains("UPDATE_PASSWORD")>
<#assign aktionen><#if requiredActions??><#list requiredActions as a>${msg("requiredAction.${a}")}<#sep>, </#sep></#list></#if></#assign>
Guten Tag<#if user?? && user.firstName?has_content> ${user.firstName}</#if>,

<#if nurPasswort>
Ihr Zugang zur STAFL-Plattform ist bereit – die gemeinsame Anmeldung für das Dashboard und alle Bereiche, für die Sie freigeschaltet sind. Bitte legen Sie über den folgenden Link Ihr persönliches Passwort fest.
<#else>
Für Ihren Zugang zur STAFL-Plattform ist noch etwas zu erledigen: ${aktionen}. Bitte öffnen Sie dazu den folgenden Link.
</#if>
<#if user?? && user.username?has_content>

Ihr Benutzername: ${user.username}
</#if>

${link}

Der Link ist ${linkExpirationFormatter(linkExpiration)} gültig und kann nur einmal verwendet werden.
<#if nurPasswort>

So geht es weiter:
1. Über den Link ein persönliches Passwort festlegen.
2. Mit Benutzername und Passwort bei der STAFL-Anmeldung anmelden. Wird ein zweiter Faktor verlangt, richten Sie ihn dabei ein (Einmalcode-App oder Passkey).
3. Im Dashboard finden Sie alle Bereiche, für die Sie freigeschaltet sind.
</#if>

-- 
Diese E-Mail wurde über die STAFL-Plattform versendet. Falls Sie keinen Zugang erwartet haben, können Sie sie ignorieren – ohne den Link ändert sich nichts.
