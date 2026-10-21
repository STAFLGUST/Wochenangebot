# Release freigeben

Neue Stände gehen nur live, wenn der Inhaber sie ausdrücklich freigibt. Die Freigabe ist ein Klick in GitHub.

## Ablauf

1. PR mergen (optional vorher in der Testumgebung prüfen, siehe `docs/testumgebung.md`).
2. Die CI läuft auf `main`. Ist sie grün, startet sie den Release-Lauf (Job „Release zur Freigabe vorlegen“).
3. Der Release-Lauf **wartet** in der GitHub-Umgebung `produktion`. Die eingetragenen Prüfer bekommen eine
   E-Mail bzw. eine Meldung in der GitHub-App („Deployment review requested“).
4. Freigeben: Lauf öffnen → **Review deployments** → Haken bei `produktion` → **Approve and deploy**.
   Ablehnen: **Reject**. Wer nichts tut, gibt nichts frei.
5. Nach der Freigabe prüft der Lauf noch einmal, legt dann die Markierung `release-…` an. Der Server übernimmt
   den Stand innerhalb von etwa 2 Minuten (`deploy/freigabe-einspielen.sh`: Sicherung, Healthcheck, Rückfall).

Von Hand starten geht weiterhin: Actions → **Release** → **Run workflow** (Branch `main`, Grund eintragen). Auch
dann wartet der Lauf auf die Freigabe.

**Keine Freigabeanfrage nach dem Merge?** Nur der automatische CI-Lauf nach dem Merge (Ereignis „push“) legt den Release
vor. Wurde die CI auf `main` von Hand gestartet (Actions → CI → Run workflow) oder kam der automatische Lauf nicht,
den Release wie oben von Hand starten – der Release prüft selbst, dass es für genau diesen Commit eine grüne CI gibt.
CI-Läufe auf `main` brechen sich nicht gegenseitig ab, sondern warten aufeinander (`concurrency` in `ci.yml`).

## Was der Lauf nach der Freigabe prüft (`.github/scripts/release-pruefen.sh`)

| Prüfung | Abbruch, wenn … |
| --- | --- |
| Freigabepflicht | die Umgebung `produktion` keine Prüfer verlangt (Schutz gegen versehentliches Abschalten) |
| Aktueller Stand | `main` inzwischen weiter ist – dann wartet bereits ein neuerer Lauf |
| CI | die CI für genau diesen Commit nicht erfolgreich war (läuft sie noch, wartet der Lauf bis 10 Minuten) |

Es wartet immer nur der neueste Lauf: Ein neuer Merge beendet einen älteren, noch nicht freigegebenen Lauf
(Status „abgebrochen“). Das Protokoll (Tag-Beschreibung) nennt, wer freigegeben hat.

Der Server bleibt unverändert: Er übernimmt nur den neuesten erfolgreichen Release-Lauf auf `main` und prüft die
CI selbst noch einmal.

## Einmalige Einrichtung in GitHub (nur Inhaber)

Settings → Environments → **New environment** → Name `produktion` → **Configure environment**:

- **Required reviewers**: anhaken, `STAFLGUST` eintragen. „Prevent self-review“ **nicht** anhaken (der Inhaber
  merged und gibt selbst frei).
- **Deployment branches and tags**: „Selected branches and tags“ → Regel `main`.
- **Save protection rules**.

Fehlt die Umgebung oder der Prüfer, bricht jeder Release-Lauf mit einem Hinweis ab – es wird dann nichts
veröffentlicht.

Benachrichtigungen: GitHub → Settings → Notifications → „Actions“ bzw. „Deployment review“ per E-Mail/App aktiv.
