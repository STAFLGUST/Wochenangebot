<#import "template.ftl" as layout>
<#import "field.ftl" as field>
<#import "buttons.ftl" as buttons>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('totp'); section>
<!-- template: login-otp.ftl -->
<#-- STAFL: Grundlage keycloak.v2 aus Keycloak 26.8.1; geändert nur das Einmalcode-Feld (bei Keycloak-Updates mit der neuen Fassung vergleichen) -->

    <#if section="header">
        ${msg("doLogIn")}
    <#elseif section="form">
        <form id="kc-otp-login-form" class="${properties.kcFormClass!}" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
            <input id="selectedCredentialId" type="hidden" name="selectedCredentialId" value="${otpLogin.selectedCredentialId!''}">
            <#if otpLogin.userOtpCredentials?size gt 1>
                <div class="${properties.kcFormGroupClass!}">
                    <div class="${properties.kcInputWrapperClass!}">
                        <#list otpLogin.userOtpCredentials as otpCredential>
                            <div id="kc-otp-credential-${otpCredential?index}" class="${properties.kcLoginOTPListClass!}"
                                    onclick="toggleOTP(${otpCredential?index}, '${otpCredential.id}')">
                                <span class="${properties.kcLoginOTPListItemHeaderClass!}">
                                    <span class="${properties.kcLoginOTPListItemIconBodyClass!}">
                                      <i class="${properties.kcLoginOTPListItemIconClass!}" aria-hidden="true"></i>
                                    </span>
                                    <span class="${properties.kcLoginOTPListItemTitleClass!}">${otpCredential.userLabel}</span>
                                </span>
                            </div>
                        </#list>
                    </div>
                </div>
            </#if>

            <#-- STAFL: statt field.input ein eigenes Feld mit pattern und Hinweis (Aufbau wie field.input, Keycloak 26.8.1) -->
            <#assign otpFehler = messagesPerField.get("totp")>
            <@field.group name="otp" label=msg("loginOtpOneTime") error=otpFehler>
                <span class="${properties.kcInputClass} <#if otpFehler?has_content>${properties.kcError}</#if>">
                    <input id="otp" name="otp" value="" type="text" autocomplete="one-time-code" inputmode="numeric"
                           pattern="[0-9]{6}" title="${msg("staflOtpFormat")}" autocapitalize="off" spellcheck="false"
                           data-stafl-otp autofocus aria-describedby="stafl-otp-hinweis"
                           aria-invalid="<#if otpFehler?has_content>true</#if>"/>
                    <@field.errorIcon error=otpFehler/>
                </span>
                <p id="stafl-otp-hinweis" class="stafl-hinweis">${msg("staflOtpHinweis", (realm.displayName!realm.name))}</p>
            </@field.group>

            <@buttons.loginButton />
        </form>
        <script>
            <#outputformat "JavaScript">
            function toggleOTP(index, value) {
                // select the clicked OTP credential
                document.getElementById("selectedCredentialId").value = value;
                // remove selected class from all OTP credentials
                Array.from(document.getElementsByClassName(${properties.kcLoginOTPListSelectedClass!?c})).map(i => i.classList.remove(${properties.kcLoginOTPListSelectedClass!?c}));
                // add selected class to the clicked OTP credential
                document.getElementById("kc-otp-credential-" + index).classList.add(${properties.kcLoginOTPListSelectedClass!?c});
            }
            </#outputformat>
        </script>
    </#if>
</@layout.registrationLayout>