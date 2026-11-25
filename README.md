# OSLO – Open Source Landscape Orchestrator

Ein Werkzeug zur zentralen Verwaltung von SAP-Systemlandschaften. Es spricht mit dem
**SAP Host Agent** (Webservice SAPHostControl, Port 1128/1129) und dem **SAP Start Service**
(`sapstartsrv`, Webservice SAPControl, Port 5NN13/5NN14) auf den verwalteten Hosts.

Dies ist ein unabhängiges Projekt und kein SAP-Produkt.

### Umbenennung von LO in OSLO (2026-11-21)

Das Werkzeug hieß bisher „Landscape Orchestrator“ (LO). Bei einer bestehenden Installation
ändert sich:

- Befehle: `lo-server`, `lo-user`, `lo-db`, `lo-keygen`, `lo-mock` heißen `oslo-…`. Startskripte
  und Dienste anpassen und das Paket neu installieren (`pip install -e .`).
- Umgebungsvariablen: `OSLO_SECRET_KEY`, `OSLO_DATABASE_URL`, `OSLO_TIMEZONE`. Die alten
  `LO_*` werden vorerst weiter gelesen; der Server meldet dann, dass sie umbenannt werden
  sollen. Ist beides gesetzt, gilt `OSLO_*`.
- Das Sitzungs-Cookie heißt `oslo_session`: Alle Benutzer melden sich einmal neu an.
- Eigene Skripte, die die API mit Sitzungs-Cookie aufrufen, senden `X-OSLO-Request: 1` statt
  `X-LO-Request`. Aufrufe mit API-Token sind nicht betroffen.
- Datenbank, gespeicherte Passwörter und API-Tokens bleiben unverändert.

## Stand

| Baustein | Status |
|---|---|
| Projektgerüst, CI | vorhanden |
| Mock-Umgebung (simulierter Host Agent und sapstartsrv) | vorhanden |
| SOAP-Clients für Host Agent und sapstartsrv | vorhanden; Host-Agent-Teil gegen echte Hosts bestätigt |
| Inventar (Hosts, SIDs, Instanzen, Datenbanken) mit Discovery und REST-API | vorhanden; gegen echte Hosts bestätigt |
| Systeme als selbst angelegte Gruppen von Instanzen | vorhanden; gegen ein echtes System bestätigt |
| Operationen (Start/Stopp/Neustart) mit Aktivitäten-Log | vorhanden; gegen ein echtes System bestätigt |
| Abhängigkeiten zwischen Systemen | vorhanden; gegen ein echtes System bestätigt |
| Web-Oberfläche (Deutsch und Englisch) | vorhanden |
| Eigene Operationen (Skripte aus `operations.d` des Host Agents) | vorhanden; Verhalten des Host Agents gegen einen echten Host bestätigt |
| Abbrechen von Aktivitäten | vorhanden |

### Teststand gegen echte Hosts

Bestätigt mit zwei echten SAP Host Agents ohne SAP-Instanz:

- Verbindung zum Endpunkt `/SAPHostControl.cgi` und Anmeldung mit HTTP Basic Auth
- `GetComputerSystem`: Betriebssystem, CPUs und Arbeitsspeicher werden gefunden
- `ListInstances` und `ListDatabases`: leere Listen werden sauber verarbeitet

Bestätigt mit einem echten Host, auf dem ein ABAP-System und eine HANA-Datenbank laufen
(Discovery, nur mit `sapadm` als Zugangsdaten):

- `ListInstances` findet alle Instanzen mit korrekten Instanznummern
- **Lesende Aufrufe am sapstartsrv** (`GetProcessList`, `GetSystemInstanceList`) funktionieren
  mit den Zugangsdaten von `sapadm`; Instanztyp, Startpriorität und Status werden erkannt
- `ListDatabases`: SystemDB und Tenant erscheinen einzeln; die Properties
  `Database/InstanceName` und `Database/Release` sind gefüllt
- Der Datenbankstatus `SAPHostControl-DB-WARNING` kommt in der Praxis vor
- Die HANA-Datenbank hat in der echten Landschaft eine **eigene SID**. Deshalb gibt es die
  Abhängigkeiten zwischen Systemen (siehe „Operationen und Aktivitäten“).
- **`StopSystem` am sapstartsrv mit `sapadm` wird abgelehnt** („Permission denied“). Lesen
  darf `sapadm` am sapstartsrv, administrieren nicht. Deshalb laufen Systemoperationen jetzt
  über den Host Agent (siehe „Operationen und Aktivitäten“).
- **Stopp und Start einer Instanz über den Host Agent mit `sapadm`** funktionieren, das Flag
  `O-INSTANCE` wird akzeptiert. Die Dialoginstanz meldete danach alle Prozesse grau bzw. grün;
  der Stopp dauerte rund 35 Sekunden, der Start rund 15 Sekunden.
- **Ganze Systeme über den Host Agent:** Stopp und Start eines ABAP-Systems mit zentralen
  Diensten und Dialoginstanz in der Reihenfolge der Startpriorität funktionieren, ebenso Start
  und Stopp der HANA-Instanz. Ein vollständiger Neustart mit angelegter Abhängigkeit vom
  Datenbanksystem lief erfolgreich durch.

- **Systeme aus Instanzen mehrerer SIDs:** Ein System aus zentralen Diensten, Dialoginstanz
  und der HANA-Instanz mit eigener SID ließ sich als Ganzes stoppen (rund 56 Sekunden) und
  starten; Neustart und Start einzelner Instanzen dieses Systems funktionieren ebenfalls.
- **Version des Host Agents:** `ExecuteOperation` mit der Operation `versioninfo` funktioniert
  mit `sapadm`. Die Antwort sind Protokollzeilen; das Tool liest daraus `kernel release` und
  `patch number` (angezeigt z. B. als „7.22 PL72“) sowie die Versionszeile von
  `saphostexec`. Achtung: Die Komponentenzeilen nennen einen anderen Patch (Kernel-Patch,
  z. B. 1611) als der Abschnitt „SAPHOSTAGENT information“ (z. B. 72).
- Die Versionsanzeige („7.22 PL72“) und der parallele Start von Datenbank und zentralen
  Diensten funktionieren aus dem Tool heraus.
- **Virtuelle Hostnamen:** Ohne Hostnamen meldete der Host Agent bei `StartInstance` für eine
  Instanz mit virtuellem Hostnamen „SAP Instance not found!“. Er erkennt eine Instanz an SID,
  Instanznummer und SAPLOCALHOST. Das Tool sendet deshalb bei Start und Stopp den Hostnamen
  der Instanz aus der Discovery mit. Damit funktionieren Start, Stopp und Neustart eines
  Systems, dessen Instanzen unter virtuellen Hostnamen auf zwei Hosts laufen.
- **Diagnostics Agents** melden das Feature `SMDAGENT`.
- **Instanz-Agent** (per `saphostctrl` als root): `UnregisterInstanceService` führt
  `sapcontrol -function StopService` und `sapstartsrv -unreg` aus, `RegisterInstanceService`
  `sapstartsrv -reg` und `sapcontrol -function StartService`, beide synchron.
- **Instanz-Agent aus dem Tool** (2026-11-21): Registrieren funktioniert. Neu registrieren lief
  bei laufenden Prozessen trotzdem durch (vermutlich, weil die Prozessliste nicht gelesen werden
  konnte); wird weiter getestet und korrigiert.
- **Operationsvorlagen und Einplanen** (2026-11-21): Eine Vorlage mit festen Zielen (System
  stoppen → eigene Operation auf zwei Hosts als Massenoperation → System starten) lief
  erfolgreich, auch als eingeplante Operation; Zeitplan und Protokoll zeigen die Schritte richtig.
- Zentrale Dienste und Anwendungsserver eines Systems können auf verschiedenen Hosts dieselbe
  Instanznummer haben.
- **Eigene Operationen asynchron** (geprüft mit einem Testskript, das seine Argumente ausgibt,
  Konfiguration mit `Mode: async` und `ResultConverter: hook`):
  - `ExecuteOperation` mit Timeout 0 kehrt sofort mit einer Operation-ID zurück.
  - Argumente kommen als `KEY=value` an. Nicht übergebene Argumente fehlen in der Befehlszeile,
    die folgenden rücken auf.
  - `GetOperationResults` antwortet, solange das Skript läuft, mit dem Fault-Code 255
    („Timeout occurred“) und den bisherigen Zeilen; die letzte lautet
    „saphostcontrol: Executing <Description> hook“. `IsOperationFinished` meldet dann `false`.
  - Erfolgreich endet die Ausgabe mit „saphostcontrol: <Description> hook successfully
    executed“. Bei einem Exit-Code ungleich 0 kommt der Fault-Code 127 („Command execution
    failed.“) mit allen Zeilen, zuletzt „… hook failed (exit code = N)“.
  - Die Antwort von `GetOperationResults` heißt wie in der WSDL `GetOperationResponse`.
  - Jede Zeile kommt als vier Meldungen: `LogMsg/TimeStamp`, `LogMsg/Severity` (`Info`,
    `Warning`, `Error`), `LogMsg/Source` (Beschreibung der Operation oder `saphostcontrol`)
    und `LogMsg/Text`. Das Tool fasst sie zu einer Zeile zusammen und zeigt den Text im
    Protokoll der Aktivität. Zeilen des Skripts mit `[WARNING]:` werden zu `Warning`.
  - Aus dem Tool bestätigt: Eine eigene Host-Operation läuft durch, die Ausgabe des Skripts
    steht vollständig im Protokoll. Noch nicht aus dem Tool geprüft: Fehler mit Exit-Code,
    Abbruch, Operationen auf Instanzen und Systemen.
  - `CancelOperation` beendet das Skript (Exit-Code 15) und antwortet mit Fault-Code 127 und
    den Zeilen bis dahin. Danach kennt der Host Agent die Operation nicht mehr
    (`GetOperationResults`: Fault-Code -20 „Operation ID not found“).

- **HTTPS zum Host Agent** (Port 1129) funktioniert mit abgeschalteter Zertifikatsprüfung
  (selbst signiertes Zertifikat) und mit Zertifikatsprüfung gegen das unter Administration →
  Zertifikate hinterlegte Zertifikat des Host Agents (über die IP-Adresse ohne Hostnamen-Prüfung).
  Die Discovery läuft so ohne Warnungen; den sapstartsrv erreicht OSLO dabei über HTTP.

Noch nicht gegen echte Hosts getestet:

- HTTPS zum sapstartsrv (Port 5NN14)

Nicht Teil der ersten Version: Verschieben von Instanzen (Adaptive Computing) und Hooks.

## Entwicklung

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/pytest
```

```bash
.venv/bin/ruff check .
```

Die Landscape-Seite ist eine React-Anwendung (TypeScript, Vite) in `frontend/`. Gebaut wird
sie nach `src/oslo/web/static/app/`; die gebauten Dateien sind eingecheckt,
damit der Server ohne Node.js läuft. Nach Änderungen in `frontend/` neu bauen und mit
einchecken (braucht Node.js 22):

```bash
npm --prefix frontend ci
```

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run build
```

Alle Bibliotheken und Schriften werden mitgeliefert, nichts wird zur Laufzeit aus dem
Internet geladen. Die Versionen stehen fest in `frontend/package-lock.json`; die Lizenzen der
mitgelieferten Bibliotheken schreibt der Build nach `static/app/THIRD-PARTY-LICENSES.txt`.
Die CI prüft, dass der eingecheckte Build zu den Quellen passt, und meldet Sicherheitslücken
(`npm audit`); Dependabot schlägt Updates vor.

Logo und Favicon liegen in `src/oslo/web/static/` (`oslo-logo.png`, `oslo-logo-dark.png` für
dunkle Farben, `favicon.png`, `apple-touch-icon.png`). Das große Logo steht auf der Anmelde- und der
Einrichtungsseite, das kleine (`oslo-header.png`, `oslo-header-dark.png`) oben links in der
Kopfzeile jeder Seite, das Favicon ebenfalls auf allen Seiten. Anmelde- und Einrichtungsseite
folgen hell oder dunkel der Einstellung des Betriebssystems; angemeldet gilt die Wahl unter
„Mein Konto → Darstellung“ (Standard ebenfalls das Betriebssystem).

## Server starten

Der Server braucht einen Schlüssel aus einer Umgebungsvariable. `oslo-keygen` erzeugt ihn:

```bash
.venv/bin/oslo-keygen
```

| Variable | Bedeutung |
|---|---|
| `OSLO_SECRET_KEY` | Schlüssel, mit dem gespeicherte Passwörter verschlüsselt werden |
| `OSLO_DATABASE_URL` | optional, Standard `sqlite+aiosqlite:///./landscape.db` |
| `OSLO_TIMEZONE` | optional, Standard `Europe/Berlin`: Zeitzone für Uhrzeiten in Einplanungen (IANA-Name) |
| `OSLO_TLS` | optional, `1`: HTTPS mit dem gespeicherten Zertifikat (wie `--tls`) |
| `OSLO_TLS_CERT`, `OSLO_TLS_KEY` | optional: HTTPS mit diesen Dateien (wie `--ssl-certfile`, `--ssl-keyfile`) |

**Den `OSLO_SECRET_KEY` sicher aufbewahren.** Geht er verloren oder wird er geändert, lassen sich
die gespeicherten Passwörter nicht mehr entschlüsseln und müssen neu eingegeben werden.

```bash
.venv/bin/oslo-server
```

Der Server lauscht standardmäßig nur auf `127.0.0.1:8000`. Mit `--mock` spricht er statt echter
Hosts die eingebaute simulierte Landschaft an:

```bash
.venv/bin/oslo-server --mock
```

### HTTPS

OSLO bietet HTTPS selbst an; ohne läuft es mit HTTP. Das Zertifikat wird unter
**Administration → HTTPS** (nur Admins) eingerichtet. Der private Schlüssel entsteht immer auf
dem OSLO-Server und wird nie hochgeladen, denn beim Einrichten läuft OSLO noch mit HTTP:

- **Selbst signiert:** Hostnamen und IP-Adressen von OSLO eintragen, „Zertifikat erzeugen“.
  Das Zertifikat lässt sich herunterladen, z. B. für die Hosts als CA-Datei der
  OSLO-Operationen (`OSLO_CA`).
- **Eigene CA:** „Anforderung erzeugen“, die Zertifikatsanforderung (CSR) herunterladen und
  von der CA signieren lassen, dann das signierte Zertifikat samt Zwischenzertifikaten
  hochladen. OSLO prüft, ob es zum Schlüssel passt. Bis dahin gilt das bisherige Zertifikat.

Schlüssel und Zertifikat stehen in der Datenbank, der Schlüssel verschlüsselt mit
`OSLO_SECRET_KEY`. Danach OSLO neu starten:

```bash
.venv/bin/oslo-server --tls
```

Ohne Browser erzeugt `oslo-tls-cert` ein selbst signiertes Zertifikat in derselben Datenbank
(braucht `OSLO_SECRET_KEY` und `OSLO_DATABASE_URL` wie der Server):

```bash
.venv/bin/oslo-tls-cert --name oslo.example.com --ip 10.0.0.10 --out oslo-ca.pem
```

Schlüssel und Zertifikat, die schon als Dateien vorliegen, gibt man direkt an; das hat Vorrang
vor dem gespeicherten Zertifikat:

```bash
.venv/bin/oslo-server --ssl-certfile /etc/oslo/cert.pem --ssl-keyfile /etc/oslo/key.pem
```

Mit `--tls` schreibt OSLO Schlüssel und Zertifikat kurz in ein privates temporäres Verzeichnis
(nur für den eigenen Prozess lesbar), lädt sie und löscht die Dateien vor der ersten Anfrage.
Über HTTPS setzt OSLO `Strict-Transport-Security`, das Sitzungs-Cookie ist dann `Secure`.
Ohne Zertifikat bricht `--tls` mit einer Meldung ab; ein Zertifikat schaltet HTTPS nie von
selbst ein. Die Regel „HTTPS-Zertifikat von OSLO läuft ab“ unter „Braucht Aufmerksamkeit“
warnt 30 Tage vorher (einstellbar).

### Datenbank und Migrationen

Das Schema wird mit Alembic verwaltet. Beim Start bringt der Server die Datenbank automatisch
auf den neuesten Stand:

| Zustand | Verhalten |
|---|---|
| neue, leere Datenbank | wird angelegt |
| Datenbank einer Version vor den Migrationen (Schema 2) | wird übernommen, die Daten bleiben erhalten |
| ältere Migration | wird migriert |
| Schema 1 oder neuer als der Code | Abbruch mit Meldung |

Bevor bestehende Daten migriert werden, legt der Server eine Kopie der SQLite-Datei daneben an
(`landscape.db.bak-<Zeitstempel>`, UTC). Die letzten 5 Kopien bleiben erhalten, ältere werden
gelöscht. Der Server meldet die Kopie beim Start.

Der Befehl `oslo-db` zeigt und migriert das Schema ohne den Server, für die Datenbank aus
`OSLO_DATABASE_URL`:

```bash
.venv/bin/oslo-db current
```

```bash
.venv/bin/oslo-db upgrade
```

```bash
.venv/bin/oslo-db history
```

`LO_API_TOKEN` gibt es nicht mehr; ist es noch gesetzt, meldet der Server, dass er es
ignoriert. Zugriff auf Oberfläche und API haben jetzt Benutzer (siehe „Benutzer und Rollen“).

## Benutzer und Rollen

**Erster Start:** Solange es keinen Benutzer gibt, gibt der Server beim Start einen einmaligen
Einrichtungscode in der Konsole aus, z. B.

```
No user exists yet. Open /setup and create the first admin with the setup code 3F9A1C-…
```

Unter `http://127.0.0.1:8000/setup` legt man mit diesem Code den ersten Administrator an.
Danach ist die Seite gesperrt. Der Code gilt nur bis zum nächsten Neustart; dann gibt der
Server einen neuen aus.

**Rollen** bauen aufeinander auf:

| Recht | Viewer | Operator | Configurator | Admin |
|---|---|---|---|---|
| Übersicht, Landscape, Activities ansehen, Status aktualisieren | ✓ | ✓ | ✓ | ✓ |
| Start, Stopp, Neustart | | ✓ | ✓ | ✓ |
| Configuration: Hosts, Discovery, Systeme, Pools, Tags, Zugangsdaten | | | ✓ | ✓ |
| Operations: eigene Operationen, Operationsvorlagen | | | | ✓ |
| Administration: Benutzer, Plattform-Einstellungen | | | | ✓ |

Knöpfe ohne Berechtigung werden nicht angezeigt; direkte Aufrufe werden mit HTTP 403
abgelehnt.

- **Benutzer verwalten** (Administration → Benutzer): anlegen mit Startpasswort, das bei der
  ersten Anmeldung geändert werden muss; Rolle ändern, deaktivieren, Passwort zurücksetzen.
  Der letzte aktive Admin lässt sich weder herabstufen noch deaktivieren.
- **Passwörter:** mindestens 12 Zeichen, gespeichert als scrypt-Hash.
- **Anmeldung:** Benutzername und Passwort. Nach 5 Fehlversuchen ist das Konto eine Minute
  gesperrt. Ändern sich Passwort oder Rolle oder wird der Benutzer deaktiviert, enden seine
  Sitzungen.
- **Mein Konto** (Name oben rechts): eigenes Passwort ändern (eigene, servergerenderte Seite,
  auch bei der ersten Anmeldung mit Startpasswort), Darstellung (Sprache: wie im Browser,
  Englisch oder Deutsch; Farbschema: wie im Betriebssystem, hell oder dunkel; Zeitangaben:
  Ortszeit des Browsers oder UTC, dann mit dem Zusatz „UTC“, auch für Eingaben; gilt auf jedem
  Gerät). OSLO speichert und rechnet alle Zeiten in UTC, die API liefert sie mit Zeitzone
  (`+00:00`), persönliche API-Tokens anlegen und löschen. Die gewählte Sprache hat Vorrang vor
  Cookie und Browser. Den Umschalter EN/DE in der Kopfzeile gibt es nur vor der Anmeldung
  (Anmeldung, Einrichtung).
- **Nachvollziehbarkeit:** Jede Aktivität vermerkt, wer sie angefordert hat.
- **Filterauswahl** in der Landscape wird pro Benutzer gespeichert.

Ohne Oberfläche, z. B. wenn kein Admin mehr anmelden kann, hilft `oslo-user` (fragt das Passwort
ab; `passwd` entsperrt und aktiviert das Konto auch):

```bash
.venv/bin/oslo-user add chief --role admin
```

```bash
.venv/bin/oslo-user passwd chief
```

```bash
.venv/bin/oslo-user list
```

## Web-Oberfläche

Nach dem Start ist die Oberfläche unter `http://127.0.0.1:8000/` erreichbar.

Die Oberfläche hat sechs Bereiche. **Landscape** dient zum Beobachten und Bedienen,
**Configuration** und **Operations** zum Einrichten. Diese beiden und **Administration** haben links eine
Seitennavigation mit ihren Unterbereichen; jeder Unterbereich zeigt oben die Überschrift mit
dem Knopf zum Anlegen rechts („Host anlegen“, „System anlegen“, „Pool anlegen“, „Operation
anlegen“, „Vorlage anlegen“) und darunter Reiter, zuerst „Übersicht“. Angelegt wird auf einer
eigenen Seite, danach geht es zur Seite des neuen Eintrags (bei Pools zur Liste).

| Bereich | Inhalt |
|---|---|
| Übersicht | Kennzahlen, Statusmatrix Produkte × Stufen und „Braucht Aufmerksamkeit“ (siehe unten) |
| Landscape | Tabelle der Systeme mit aufklappbaren Instanzen und Tabelle der Hosts, Mehrfachauswahl mit Leiste für Operationen, Filter, Detailleiste rechts für System, Instanz (mit den Prozessen) und Host (Systeminformationen, Instanzen), Befehlspalette (siehe unten). Instanzen ohne System erscheinen hier nicht |
| Activities | Tab „Aktivitäten“ (nur oberste Ebene) mit Filtern (Status, Suche) und Live-Ansicht je Aktivität; Tab „Schritte“ mit allen Aktivitäten, die selbst arbeiten: Zeit, Operation, ID (`O…`), Ziel, Dauer, Aktivität (`A…`). Eine Einzeloperation ist ein Schritt, eine Massenoperation oder Vorlage hat einen je Ziel und Schritt. Nummern: Datenbank-ID + 100000 (`A100002`, `O100002`); Tab „Konfiguration“ mit dem Konfigurationsprotokoll (wer hat wann was angelegt, geändert, gelöscht) mit Filtern nach Objekt, Benutzer und Zeitraum. Die Seiten von Host, System, Pool, eigener Operation, Einplanung und Benutzer zeigen ihre letzten 10 Änderungen |
| Configuration | „Hosts“ (`/configuration/hosts`): anlegen, Verbindung ändern, Discovery, Zugangsdaten, Tags, Instanzen, Datenbanken, löschen. „Systeme“: Reiter „Übersicht“ mit den Systemen, aufklappbar mit ihren Instanzen, und Reiter „Nicht zugeordnete Instanzen“ zum Zuordnen; „System anlegen“ wählt die Instanzen aus allen nicht zugeordneten und schlägt den Namen vor; Seite eines Systems mit Name, Stufe, Beschreibung, Pool, Tags, Abhängigkeiten, Instanzen, Zugangsdaten je SID, Löschen. „Pools“: anlegen und löschen |
| Operations | „Eigene Operationen“ (`/operations/custom`) und „Operationsvorlagen“ (`/operations/templates`) nur für Admins; „Einplanungen“ (`/operations/schedules`) ab Operator, siehe unten. Operatoren und Konfiguratoren sehen in diesem Bereich nur die Einplanungen |
| Administration | „Allgemein“: Version und Einstellungen; „Benutzer“: anlegen, bearbeiten, Passwort zurücksetzen; „Braucht Aufmerksamkeit“: die Regeln der Übersicht; „Zertifikate“: vertrauenswürdige Zertifikate für HTTPS zu den Hosts; „Import/Export“: Konfiguration als JSON-Datei (siehe unten) |

Die Hauptmenüpunkte heißen auf Englisch Overview, Landscape, Activities, Configuration,
Operations und Administration, auf Deutsch Übersicht, Landschaft, Aktivitäten, Konfiguration,
Operationen und Administration. Alte Adressen wie `/configuration?tab=systems` leiten weiter.

**Pools** fassen Systeme zusammen, die zusammengehören, z. B. Entwicklungs-, Test- und
Produktivsystem eines Produkts. Ein System gehört zu höchstens einem Pool. Auf der Seite eines
Pools (Klick auf den Namen in der Liste) lassen sich Name und Beschreibung ändern; die Systeme
ordnet man auf der Seite des Systems zu.

**Mehrere Hosts auf einmal:** Unter „Host anlegen“ nimmt das Feld „Name“ mehrere Namen durch
Kommas getrennt (`sapapp1, sapapp2, sapdb1`). Alle bekommen dieselben Einstellungen und
Zugangsdaten, die Adresse ist jeweils der Name. Angelegt werden alle oder keiner: Existiert
ein Name schon oder steht er doppelt in der Liste, wird nichts angelegt.

### Übersicht

- **Statusmatrix:** Zeilen sind die Produkte (Pools, dazu „ohne Pool“), Spalten die Stufen
  der Systeme: Entwicklung, Qualität und Produktion immer, Sandbox und PreProd nur, wenn ein
  System sie hat, „Ohne Stufe“ bei Bedarf. Die Stufe stellt man auf der Seite eines Systems ein
  (Configuration → Systeme). Jede Instanz ist ein farbiges Kästchen; ein Klick öffnet das System
  in der Landschaft. Darüber Kennzahlen zu Systemen, Instanzen, Hosts und Aktivitäten der
  letzten 24 Stunden.
- **Braucht Aufmerksamkeit:** eine Liste aus Regeln, die Admins für alle festlegen
  (Administration → Braucht Aufmerksamkeit):

  | Regel | Einstellungen (Standard) |
  |---|---|
  | Fehlgeschlagene Aktivitäten | der letzten 24 Stunden; ausblenden: Einplanungen, die mindestens alle 60 Minuten laufen (z. B. stündliche), gewählte Operationen, Fehler, auf die ein erfolgreicher Lauf derselben Operation auf demselben Ziel folgte; nur gewählte Stufen |
  | Systeme mit Fehlern | Status Fehler und im Übergang (nicht während einer Aktivität); nur gewählte Stufen |
  | Gestoppte Systeme | Stufe Produktion |
  | Lang laufende Aktivitäten | länger als 60 Minuten |
  | Nicht erreichbare Hosts | – |
  | Einplanungen ohne Start | letzter Lauf konnte nicht starten |
  | Hosts ohne aktuelle Discovery | seit 7 Tagen (Standard aus) |

  Jeder Benutzer kann unter „Anpassen“ Regeln für sich abschalten und Systeme oder Pools
  ausblenden; an jedem Eintrag gibt es „System für mich ausblenden“ und „Regel für mich
  abschalten“.

### Landscape

Alle Seiten außer Anmeldung, Einrichtung und Passwortwechsel sind React-Seiten auf der
REST-API; ohne JavaScript zeigen sie nur einen Hinweis.

- **Tabellen:** Tab „Systeme“ mit Status, Instanzen (je Instanz ein farbiges Kästchen), Pool,
  „Hängt ab von“, Tags und laufender Aktivität. Systeme sind zunächst zugeklappt;
  aufgeklappt zeigen sie ihre Instanzen in Startreihenfolge mit Typ, Host und Status,
  Diagnostics Agents zuletzt. Welche Systeme offen sind, merkt sich der Browser für diesen
  Tab. Tab „Hosts“ mit Erreichbarkeit, Version des Host Agents, Betriebssystem, Tags und
  letzter Discovery.
- **Auswählen:** Systeme, Instanzen oder Hosts lassen sich ankreuzen, auch alle angezeigten
  auf einmal; gemischt wird nicht (eine Instanz anzukreuzen hebt eine Auswahl von Systemen
  nicht auf, sie wird nur nicht ergänzt). Esc hebt die Auswahl auf.
- **Leiste unten:** Starten, Stoppen und Neu starten (bei Hosts die Discovery) sind Knöpfe;
  alle anderen Operationen stehen in **Menüs nach Kategorie** (z. B. „Instanz-Agent“,
  „OSLO“, eigene wie „Automation“), mit höchstens einer zweiten Ebene, die seitlich
  aufklappt („Automation › Kernel“). Jedes Menü hat ein Suchfeld; bei einer Suche erscheinen
  die Treffer der zweiten Ebene als Gruppen. Operationen ohne Kategorie stehen unter
  „Weitere“. Was zur Auswahl nicht passt (Instanztyp, mehrere Ziele ohne Massenoperation),
  bleibt grau sichtbar, mit dem Grund. Gezeigt werden nur Operationen für den Zieltyp und
  die Rolle des Benutzers. Ein Ziel läuft direkt, mehrere als
  Massenoperation, dann mit Einstellung „gleichzeitig“ (Standard 5) und „bei Fehler
  anhalten“. Stopp und Neustart brauchen einen zweiten Klick auf denselben Eintrag
  („Wirklich: …“). Eigene Operationen mit Parametern öffnen erst ein Formular. Danach
  erscheint eine Meldung mit Link zur Aktivität. Die Detailleiste zeigt dieselben Menüs, die
  Befehlspalette nennt die Kategorie neben dem Namen.
- **Detailleiste rechts:** Ein Klick auf den Namen öffnet sie.
  - **System:** kurze Übersicht. Grob der Status („2 von 2 Instanzen laufen“, grün nur wenn
    alle laufen; Diagnostics Agents zählen nicht), Pool, Abhängigkeiten, Hosts, Tags, die
    Operationen, „Status aktualisieren“, die Instanzen als je eine Zeile und die **letzten 5
    Aktivitäten** des Systems (auch über Abhängigkeiten und Massenoperationen).
  - **Instanz** (Klick auf die Instanz in der Tabelle oder in der Systemübersicht), mit drei
    Reitern: „Allgemein“ (Typ, System, SID, Nummer, Host, Instanz-Hostname, Kernel aus der
    Discovery, Startpriorität, „Hängt ab von“, Operationen), „Status“ (die **Prozesse aus
    `GetProcessList`** mit Farbe, Text, Laufzeit, Startzeit und PID; nur gelesen, solange der
    Reiter offen ist, dann alle 15 Sekunden; aktualisiert den gespeicherten Status) und
    „Aktivitäten“ (die letzten 5 der Instanz und ihres Systems).
  - **Host:** Adresse, Host Agent, Betriebssystem, letzte Discovery, Instanzen darauf und die
    letzten 5 Host-Operationen.
- **Befehlspalette:** Strg+K (Mac: Cmd+K) sucht Systeme, Hosts und Seiten und bietet die
  Operationen der aktuellen Auswahl an; Pfeiltasten wählen, Enter führt aus.
- **Live:** Die Seite bekommt Änderungen über `/api/events` mit und lädt dann neu, ohne die
  Seite neu aufzubauen; Auswahl, Filter und offene Systeme bleiben erhalten.
- **Filter:** Suchfeld (Taste `/`) für System, Beschreibung, SID, Instanz, Host und Tags;
  dazu Listen für Status, Pool, Instanztyp, Tags und Host-Tags (Hosts: Erreichbar, Host
  Agent, Tags). Innerhalb eines Filters reicht ein Treffer (Pool A oder B, Tag `dev` oder
  `sla=2`; `sla` passt zu jedem Wert), alle gesetzten Filter müssen zutreffen. Mit dem Filter
  „Instanztyp“ sind die passenden Systeme aufgeklappt und zeigen nur die passenden Instanzen,
  z. B. um alle ABAP-Anwendungsserver auszuwählen. Die Filter stehen in der Adresse; eine
  gefilterte Ansicht lässt sich als Lesezeichen speichern.
- **Adresse:** `?system=<id>`, `?instance=<id>` oder `?host=<id>` öffnen die Detailleiste;
  die früheren Seiten `/systems/<id>` und `/hosts/<id>` leiten dorthin.

### Aktivität live

Die Seite einer Aktivität (`/activities/<id>`) ist ebenfalls eine React-Seite und folgt der
Aktivität ohne Neuladen:

- **Kopf:** Operation und Ziel, Status, angefordert von und um, laufende Dauer und Zeitlimit,
  bei eigenen Operationen die übergebenen Parameter, bei Teilaktivitäten der Link zur
  Massenoperation. Solange sie läuft, gibt es für Operator und höher „Abbrechen“.
- **Zeitplan:** eine Spur je Instanz mit Stopp (grau) und Start (grün) vom Anfordern bis zum
  Zielzustand, bei eigenen Operationen je Instanz bzw. Host vom Start bis zum Ergebnis des
  Skripts; Fehlgeschlagenes rot, Laufendes gestreift, dazu eine Linie für „jetzt“. Ein Klick
  auf eine Instanz filtert das Protokoll. Bei einer Massenoperation ist jede Teilaktivität
  eine Spur (mit Link), dazu die Tabelle der Teilaktivitäten mit Zählern je Status.
- **Protokoll:** läuft mit (abschaltbar), Filter „Alle / Warnungen / Fehler“ mit Anzahl,
  Auswahl der Instanz und Textsuche.
- Grundlage sind strukturierte Felder der Protokolleinträge (`event`, `subject`, `data`,
  Migration 0006): angefordert (`request_start`, `request_stop`), Status je Instanz
  (`status`) und Start einer eigenen Operation (`op_started`). Ältere Aktivitäten haben diese
  Felder nicht; sie zeigen nur das Protokoll.

### Operationsvorlagen und Einplanen

Eine **Operationsvorlage** besteht aus Schritten, die wie in LaMa einen Graphen bilden: Ein
Schritt startet, wenn alle seine Vorgänger fertig sind; Schritte ohne Weg zwischen ihnen laufen
parallel, und ein Schritt kann mehrere Vorgänger haben (z. B. Kernel vorab kopieren und
parallel einen Scheduler stoppen, beides vor dem Stopp des Systems). Anlegen dürfen nur Admins:
Operations → Operationsvorlagen.

- **Editor:** Reiter „Allgemein“ (Name, Schlüssel, Rolle, Beschreibung), „Schritte“ und
  „Einplanen“. Unter „Schritte“ steht der Graph (von oben nach unten angeordnet, React Flow).
  Ein gewählter Schritt zeigt „+“ (nächster Schritt), „→“ (mit einem folgenden Schritt
  verbinden) und Löschen; verbunden wird auch durch Ziehen vom unteren zum oberen Rand, Entf
  löscht einen gewählten Pfeil. „+ Schritt ohne Vorgänger“ legt einen parallelen Zweig an.
  Rechts stehen für den gewählten Schritt Operation, Zieltyp, Verhalten bei Fehler,
  Parameter, Ziele und Vorgänger. Gelöschte Schritte reichen ihre Vorgänger an ihre
  Nachfolger weiter.
- **Operation wählen:** eine Suche über alle Operationen, die ein Schritt nutzen kann, oben die
  eigenen **Favoriten** (Stern, je Benutzer) und die **5 meistgenutzten** Operationen der
  letzten 90 Tage (über alle Benutzer).
- **Ziele je Schritt:** fest (eine oder mehrere Instanzen, Systeme oder Hosts; mehrere laufen
  als Massenoperation) oder der Platzhalter **„$Auswahl“**. Eine Vorlage darf Schritte auf
  Hosts, Instanzen und Systemen mischen; alle Schritte auf der Auswahl brauchen aber denselben
  Zieltyp.
  - **Dialog-Vorlage** (mit „$Auswahl“): erscheint in der Landschaft bei passender Auswahl
    (Leiste, Detailleiste, Befehlspalette). Mehrere ausgewählte Ziele sind **ein** Lauf mit
    allen Zielen als Auswahl.
  - **Vorlage mit festen Zielen:** läuft, wie sie ist, über „Ausführen“ im Editor oder
    eingeplant; in der Landschaft erscheint sie nicht.
- **Werte:** Jeder Parameter eines Schritts hat einen festen Wert in der Vorlage. Mit „Beim
  Start fragen“ fragt ein Formular ihn beim Start ab (als „<Schritt>.<Name>“, z. B.
  `3.KRNLREL`), vorausgefüllt mit dem Wert der Vorlage; alle anderen Werte lassen sich beim
  Start nicht ändern. Ein Pflichtparameter braucht einen Wert oder „Beim Start fragen“.
- **Verhalten bei Fehler** je Schritt: „Kette anhalten“ (Standard: kein weiterer Schritt
  startet, laufende laufen zu Ende), „weitermachen“ (der Schritt gilt als erledigt, Endstatus
  teilweise fehlgeschlagen) oder „Kette anhalten, System starten“ (danach werden die Systeme
  des Schritts wieder gestartet, nicht bei Hosts).
- **Sperren:** Die Vorlage sperrt beim Start alle Systeme (samt Abhängigkeiten) und Hosts ihrer
  sperrenden Schritte für den ganzen Lauf; nur ihre eigenen Schritte dürfen darin laufen.
  Zwei sperrende Schritte, die gleichzeitig auf denselben Zielen laufen könnten, weist das
  Speichern ab; trifft ein Schritt auf der Auswahl zur Laufzeit auf einen parallelen Schritt
  mit festen Zielen, wartet er. Eigene Operationen, die nichts sperren (siehe unten), dürfen
  parallel laufen.
- **Rolle:** Jede Vorlage hat eine Rolle zum Ausführen, mindestens die höchste ihrer Schritte.
- **Ablauf:** Eine Vorlage läuft als Aktivität, jeder Schritt als Teilaktivität. Endstatus:
  erfolgreich, teilweise fehlgeschlagen oder fehlgeschlagen. Abbrechen bricht die laufenden
  Schritte ab und startet keinen weiteren. Die Live-Ansicht zeigt je Schritt eine Spur.
- Vorlagen von vor Migration 0008 wurden zu Ketten auf der Auswahl mit allen Parametern als
  „Beim Start fragen“; sie verhalten sich wie bisher.
- Eine eigene Operation, die eine Vorlage nutzt, lässt sich nicht löschen; eine eingeplante
  Vorlage auch nicht.

**Einplanen** (im Editor im Reiter „Einplanen“; per API für jede Operation): einmalig zu einem
Zeitpunkt, täglich zu einer Uhrzeit an gewählten Wochentagen oder alle N Minuten (mindestens 5).
Mehrere Ziele laufen als Massenoperation, bei einer Dialog-Vorlage als ein Lauf mit allen
Zielen als Auswahl; eine Vorlage mit festen Zielen wird ohne Ziele eingeplant. Der Lauf geschieht mit den Rechten des Benutzers,
der ihn eingeplant hat; sie werden beim Start erneut geprüft (gesperrter Benutzer oder fehlende
Rolle: kein Lauf, der Grund steht bei der Einplanung). Uhrzeiten gelten in der Zeitzone
`OSLO_TIMEZONE` des Servers. Der Server prüft alle 30 Sekunden, was fällig ist; war er zur
fälligen Zeit aus, läuft ein Lauf beim nächsten Prüfen nach, verpasste Wiederholungen werden
nicht nachgeholt. Die Aktivität nennt als Auftraggeber „<Benutzer> (schedule <Nr.>)“.

### Einplanungen

**Operationen → Einplanungen** (`/operations/schedules`, ab Operator, angelehnt an die
Einplanungen in LaMa) zeigt alle geplanten Läufe aller Operationen und Vorlagen: Name (leer:
Name der Operation), Operation, Ziele, nächster Lauf (oder „pausiert“ bzw. „abgelaufen“, wenn
nichts mehr fällig ist), Status des letzten Laufs mit Link zur Aktivität (bzw. „nicht
gestartet“ mit dem Fehler), Wiederholung und wer eingeplant hat. Darüber stehen die Zeitzone
der Einplanungen und die Serverzeit (`/api/server-time`). Filter: Suche, Operation, letzter
Lauf, nächster Lauf. Mehrere Einplanungen lassen sich auswählen und auf einmal löschen.
„Operation einplanen“ plant jede Operation des Katalogs (eingebaute, eigene und Vorlagen, nicht
die nur für Vorlagen gedachten): Zieltyp und Ziele aus der Landschaft, Werte der Parameter
eigener Operationen, einmalig, täglich zu einer Uhrzeit an gewählten Wochentagen oder alle N
Minuten. Mehrere Ziele laufen als Massenoperation, nur wenn die Operation das erlaubt. Werte,
nach denen eine Vorlage beim Start fragt, plant man weiter im Editor der Vorlage.

### Massenoperationen

Mehrere ausgewählte Systeme, Instanzen oder Hosts laufen als Massenoperation (Leiste unten in
der Landscape oder `POST /api/mass-operations`). Typische Auswahl: alle gefilterten Systeme,
mit dem Filter „Instanztyp“ z. B. alle ABAP-Anwendungsserver, oder Hosts für eine Discovery.

Einstellbar ist, wie viele Ziele gleichzeitig laufen (Standard 5, höchstens 20) und ob bei
einem Fehler weitergemacht (Standard) oder angehalten wird. Daraus entsteht eine
**Sammelaktivität** mit einer Teilaktivität je Ziel:

- Ausgewählte Systeme, die voneinander abhängen, laufen in Reihenfolge: beim Start und Neustart
  zuerst die Abhängigkeiten, beim Stopp zuerst die abhängigen Systeme. Scheitert eine
  Abhängigkeit, werden die Systeme übersprungen, die sie brauchen.
- Brauchen zwei Ziele dasselbe System (z. B. ein gemeinsames Datenbanksystem), wartet das
  zweite, bis das erste fertig ist. Ist ein Ziel durch eine Aktivität außerhalb der
  Massenoperation belegt, wird es übersprungen.
- Die Sammelaktivität zeigt die Teilaktivitäten mit Status und endet als „erfolgreich“,
  „teilweise fehlgeschlagen“ oder „fehlgeschlagen“, mit einer Zusammenfassung wie
  „10 succeeded, 1 failed, 1 skipped“.
- Welche Operationen angeboten werden, steht im **Katalog der Operationen**, zusammen mit
  Zielen und nötiger Rolle. Start, Stopp und Neustart brauchen Operator, die Discovery
  Configurator. Eigene Operationen (siehe unten) erscheinen automatisch in Menüs, in der Leiste
  und in der Befehlspalette; ihre Parameter fragt ein Formular ab.

**Host-Operationen:** Die Discovery und eigene Operationen für Hosts laufen als Aktivität mit
Protokoll (Landscape → Hosts, Hostseite).

### Instanz-Agent registrieren, abmelden, neu registrieren

Drei eingebaute Operationen für Instanzen (Rolle Operator, auch als Massenoperation und als
Schritt einer Vorlage). Sie laufen über den Host Agent (`RegisterInstanceService`,
`UnregisterInstanceService`) und schreiben dessen Ausgabe ins Protokoll.

| Operation | Ablauf |
|---|---|
| Instanz-Agent registrieren | `sapstartsrv -reg`, dann `StartService`; OSLO wartet, bis der sapstartsrv antwortet |
| Instanz-Agent abmelden | `StopService`, dann `sapstartsrv -unreg`; die Instanz selbst wird nicht gestoppt |
| Instanz-Agent neu registrieren | abmelden, dann registrieren |

Abmelden und neu Registrieren werden abgelehnt, solange ein Prozess der Instanz läuft (sie wäre
dann nicht mehr steuerbar). Antwortet der sapstartsrv gar nicht, z. B. bei einem neuen System,
geht es weiter. Annahme: `sapadm` darf beide Methoden aufrufen; geprüft ist bisher nur
`saphostctrl` als root.

### Eigene Operationen

Eigene Operationen führen ein Skript aus, das im Host Agent unter `operations.d` als
Konfigurationsdatei eingerichtet ist (`Name:`, `Command:` mit Platzhaltern wie
`$[SAPSYSTEMNAME]` oder `$[PARAM-KRNLREL]`, `Mode: async`, `ResultConverter: hook`), wie die
kundendefinierten Operationen in LaMa. Das Tool ruft sie über `ExecuteOperation` asynchron
auf und liest die Ausgabe laufend ins Protokoll.

- **Anlegen** dürfen nur Admins: Operations → Eigene Operationen. Je Operation: Name, Schlüssel
  (für URLs und API), Host-Agent-Operation (der `Name:` der Konfigurationsdatei), Ziel
  (Instanz, System oder Host), Instanztypen, Reihenfolge bei Systemen, Rolle zum Ausführen,
  Zeitlimit, ob sie als Massenoperation erlaubt ist, **Kategorie** und zwei Merkmale wie in
  LaMa:
  - **Kategorie** (auch für Operationsvorlagen): ordnet die Operation in die Menüs der
    Landschaft ein, höchstens zwei Ebenen, getrennt durch `/` (`Automation/Kernel`), je Ebene
    bis 40 Zeichen; das Feld schlägt die schon benutzten Kategorien vor. Leer: „Weitere“.
    Namen mit `cat.` am Anfang sind für die eingebauten Kategorien reserviert.
  - **Sperrt Instanz oder Host** (Standard an): Die Operation wartet auf andere Aktivitäten
    ihrer Ziele und hält sie vom Start ab, wie Start und Stopp. Für Skripte, die nur lesen
    (z. B. Protokolle), abschalten; sie laufen dann neben anderen Aktivitäten.
  - **Nicht für Einzelausführung:** nur als Schritt einer Operationsvorlage, nicht in Menüs,
    Landschaft, Massenoperationen oder Einplanungen.
- **Parameter** haben Name, Anzeigename, Typ (Text, Ganzzahl, Ja/Nein), Pflichtfeld,
  Standardwert, Muster und Hilfetext. Sie werden als `PARAM-<Name>` übergeben. Ja/Nein wird
  als `true`/`false` übergeben. Text muss dem Muster entsprechen; ohne eigenes Muster sind
  nur Buchstaben, Ziffern, `.`, `_` und `-` erlaubt, weil der Wert in einer Befehlszeile
  landet, die als root läuft.
- **Leere optionale Parameter** werden wie in LaMa nicht übergeben. Folgende
  Positionsargumente des Skripts rücken dann auf; das muss das Skript berücksichtigen (z. B.
  optionale Parameter zuletzt). Das Formular ist mit den Standardwerten vorausgefüllt; fehlt
  ein Parameter in einem API-Aufruf ganz, gilt sein Standardwert.
- **Kontextparameter** übergibt das Tool immer, mit den Namen aus LaMa: für Instanzen und
  Systeme `SAPSYSTEMNAME`, `SAPSYSTEM`, `SAPLOCALHOST`, `PHYSICAL_HOSTNAME`,
  `SERVICE_CLASS` (`Instance`) und `SERVICE_SUBTYPE`; für Hosts `PHYSICAL_HOSTNAME`,
  `RealHostName`, `OS_TYPE`, `OS_VERSION`, `CPUS`, `MEMAV`.
- **`SERVICE_SUBTYPE`** (Annahme): Der Teil vor dem Schrägstrich kommt aus dem Instanztyp
  (`Instance_Application_Server`, `Instance_SCS`, `Instance_ERS`, `Instance_System_HDB`,
  `Instance_Diag_Agnt/SolMan`), der Teil danach (`ABAP`, `J2EE`, `Shared`) aus den
  Anwendungsservern des Systems.
- **Ausführen:** In der Landschaft (Leiste, Detailleiste, Befehlspalette) fragt ein Dialog die
  Parameter ab. Auf einem System laufen sie auf allen passenden Instanzen: gleichzeitig, nach
  Rollen wie ein Start (Datenbank und zentrale Dienste vor den Anwendungsservern) oder
  nacheinander. Ohne gewählte Instanztypen gilt die Operation für alle Instanzen, bei Systemen
  ohne Diagnostics Agents.
- **Ergebnis:** Die Zeilen des Skripts erscheinen im Protokoll, `Warning` und `Error` als
  Warnung bzw. Fehler. Ein Exit-Code ungleich 0 lässt die Aktivität scheitern; die Meldung
  nennt die letzte Fehlerzeile. Beim Zeitlimit bricht das Tool die Operation auf dem Host ab.

### OSLO-Operationen (eigene Dateien in `operations.d`)

OSLO bringt einige eigene Operationen für den Host Agent mit, als **signiertes Bündel**. Es
enthält `oslo_version` (meldet Version und ob die Dateien unverändert sind), `oslo_update`
(holt und installiert eine neue Version) und den Neustart des Instanz-Agents
(`oslo_restart_service`, `oslo_restart_service_force`, siehe unten).

Der Host Agent nimmt keine Dateien von außen an: `DeployConfiguration` wurde an einem echten
Host abgelehnt („Remote deployment not permitted“, auch lokal als root, ohne erkennbare
Einstellung in `host_profile`). Deshalb holen sich die Hosts das Bündel selbst:

1. **Signaturschlüssel erzeugen**, einmal, auf dem Rechner, der Bündel baut (nicht auf dem
   OSLO-Server):

   ```bash
   .venv/bin/oslo-bundle keygen --out ~/oslo-keys
   ```

2. **Bündel bauen und signieren:**

   ```bash
   .venv/bin/oslo-bundle build --version 1.0.0 --key ~/oslo-keys/oslo-bundle-private.pem
   ```

3. **In OSLO** unter Administration → OSLO-Operationen (nur Admins): den öffentlichen
   Schlüssel (`oslo-bundle-public.pem`) und die Adresse eintragen, unter der die Hosts OSLO
   per HTTPS erreichen (optional eine CA-Datei auf den Hosts), dann die `.oslobundle`-Datei
   hochladen. OSLO prüft die Signatur; das Bündel wird die aktive Version. Frühere Bündel
   lassen sich wieder aktiv setzen.
4. **Erstinstallation**, einmal je Host als root: das „Erstinstallationspaket“ herunterladen,
   auf den Host kopieren (von Hand oder z. B. mit Ansible) und ausführen:

   ```bash
   tar -xzf oslo-bootstrap-1.0.0.tar.gz
   ```

   ```bash
   sh oslo-bootstrap/install.sh
   ```

   Es installiert die Operationen nach `/usr/sap/hostctrl/exe/operations.d` (`oslo_*.conf`
   und das Verzeichnis `oslo/`), dazu den öffentlichen Schlüssel und `oslo.cfg` mit der
   Adresse von OSLO.
5. **Prüfen:** Jede Discovery ruft `oslo_version` auf. Host-Seite und
   Administration → OSLO-Operationen zeigen je Host „aktuell“, „veraltet“, „verändert“ oder
   „nicht installiert“; die Regel „Hosts mit veralteten OSLO-Operationen“ meldet sie unter
   „Braucht Aufmerksamkeit“ (nur, wenn ein Bündel aktiv ist).
6. **Aktualisieren:** die eingebaute Host-Operation „OSLO-Operationen aktualisieren“ (nur
   Admins, auch als Massenoperation, Knopf „Hosts aktualisieren“ auf der Seite). Sie ruft
   `oslo_update` auf: Der Host lädt `/bundle/payload.tar.gz` und `/bundle/payload.sig` von
   OSLO (HTTPS, ohne Anmeldung; das Bündel enthält keine Geheimnisse), prüft die Signatur mit
   dem installierten Schlüssel, prüft Namen und Prüfsummen der Dateien und ersetzt nur
   OSLO-eigene Dateien. Danach liest OSLO die Version und vergleicht sie.

Sicherheit: Wer OSLO übernimmt, kann damit keinen eigenen Code auf die Hosts bringen, weil
die Hosts nur Bündel mit gültiger Signatur installieren und der private Schlüssel nicht auf dem
OSLO-Server liegt. Schlüssel und `oslo.cfg` ändern sich nur durch eine neue Erstinstallation.

**Operationen des Bündels im Katalog:** `oslo/operations.json` im Bündel beschreibt, welche
Operationen OSLO anbietet, ohne dass ein Admin sie als eigene Operation anlegt: Name und
Beschreibung je Sprache, Host-Agent-Operation (`oslo_*`, ihre `.conf` muss im Bündel liegen),
Ziel, Rolle (mindestens Operator), Kategorie, Massenoperation, „gefährlich“ (zweiter Klick),
Sperren, Zeitlimit, Instanztypen, Reihenfolge und Parameter (Texte je Sprache).
`oslo-bundle build` und das Hochladen prüfen die Datei. Im Katalog heißen sie
`oslo.<Schlüssel>` (eigene Operationen können keinen Punkt enthalten, also keine
Überschneidung) und laufen wie eigene Operationen, aber nur auf Hosts, auf denen **genau
diese Version** unverändert installiert ist (Stand der letzten Discovery oder Aktualisierung);
sonst bricht die Aktivität mit einem Hinweis ab, und die Landschaft zeigt den Eintrag grau
mit „OSLO-Operationen auf dem Host nicht aktuell“. Unter Administration → OSLO-Operationen
kann ein Admin sie aus den Menüs nehmen (als Schritt von Vorlagen bleiben sie nutzbar) oder
eine höhere Rolle verlangen, nie eine niedrigere (`platform_settings` `bundle.overrides`).

**Instanz-Agent neu starten** (Menü „Instanz-Agent“, je Instanz, auch als Massenoperation):

- **normal:** `sapcontrol -nr <NR> -function RestartService`, danach wartet das Skript bis zu
  5 Minuten mit `WaitforServiceStarted`. Die Instanz läuft weiter.
- **forciert** (zweiter Klick): für einen sapstartsrv, der nicht mehr antwortet. Das Skript
  beendet den Prozess (TERM, nach 10 Sekunden KILL) und startet ihn mit
  `sapcontrol -nr <NR> -function StartService <SID>`; die Instanz läuft weiter.
- Annahmen, an einem echten Host noch nicht geprüft: Das `sapcontrol` des Host Agents
  (`/usr/sap/hostctrl/exe/sapcontrol`) erreicht den sapstartsrv als root lokal; der Prozess
  ist an seinem Profil `pf=/usr/sap/<SID>/SYS/profile/<SID>_<Name><NR>_<Host>` zu erkennen.

Annahmen und Voraussetzungen: Die Operationen laufen als root (ohne `Username:` in der
`.conf`); auf den Hosts gibt es `curl`, `tar`, `sha256sum` und OpenSSL ab 1.1.1 (Ed25519); nur
UNIX. Der Host Agent liest geänderte `.conf`-Dateien ohne `ReloadConfiguration` (die
Befehlszeilen ändern sich bei Updates nicht, die Skripte schon). Der Name `oslo_*` ist für
OSLO reserviert: eigene Operationen der Kunden dürfen nicht so heißen.

### Import und Export

**Administration → Import/Export** (nur Admins) lädt die Konfiguration als JSON-Datei herunter
und liest sie in dasselbe oder ein anderes OSLO wieder ein.

- **Teile**, einzeln wählbar: Hosts (Verbindung, Tags, Zugangsdaten), Zugangsdaten je SID,
  Pools, Systeme (Stufe, Pool, Tags, Abhängigkeiten, Instanzen), eigene Operationen,
  Operationsvorlagen, Einplanungen, Regeln für „Braucht Aufmerksamkeit“, vertrauenswürdige
  Zertifikate. Aktivitäten, Protokolle und Benutzer sind nie dabei.
- **Bezüge über Namen**, nicht über Ids: ein System über seinen Namen, ein Host über seinen
  Namen, eine Instanz über Host, SID und Nummer. So passt die Datei in ein anderes OSLO.
- **Passwörter** von Hosts und SIDs nur, wenn beim Export ein Export-Passwort (mindestens 8
  Zeichen) vergeben wird; sie stehen dann damit verschlüsselt in der Datei (scrypt und Fernet),
  nie im Klartext. Ohne das Passwort übernimmt der Import alles andere und überspringt die
  Passwörter; ein falsches Passwort lehnt den Import ab.
- **Import:** erst „Vorschau“, die zeigt, was neu angelegt, geändert, übersprungen oder
  abgelehnt würde, ohne etwas zu ändern; dann „Importieren“. Vorhandene Einträge (gleicher
  Name) bleiben unverändert oder werden mit der Datei aktualisiert. Es wird nie etwas gelöscht.
  Ein fehlerhafter Eintrag wird allein abgelehnt, die übrigen laufen weiter.
- **Instanzen** entstehen nur durch eine Discovery, der Import startet keine. Ein System, von
  dessen Instanzen keine bekannt ist, wird abgelehnt (ebenso Vorlagen und Einplanungen mit
  festen Zielen darin); nach einer Discovery der neuen Hosts den Import wiederholen.
- **Einplanungen** laufen nach dem Import mit den Rechten des Admins, der importiert hat.
- Das Dateiformat hat eine Version (`"format": "oslo-export"`, `"version": 1`); eine neuere
  Version lehnt OSLO ab.

### HTTPS und vertrauenswürdige Zertifikate

Je Host gibt es drei Schalter: **HTTPS zum Host Agent** (Port 1129), **Zertifikat prüfen**
und **Hostnamen prüfen**. Sie gelten nur für den Host Agent: Den sapstartsrv (Instanz-Agent)
spricht OSLO immer über HTTP an (Port 5NN13), weil die Instanz-Agents eigene Zertifikate
zeigen. HTTPS zum sapstartsrv ist als ToDo vorgemerkt. Mit „Zertifikat prüfen“ muss der Host ein Zertifikat zeigen, dem das
Betriebssystem des OSLO-Servers oder die Liste unter **Administration → Zertifikate** vertraut.
„Hostnamen prüfen“ verlangt zusätzlich, dass der Name im Zertifikat zur Adresse des Hosts passt;
ausschalten, wenn der Host z. B. über seine IP-Adresse erreicht wird, das Zertifikat aber nur
den Hostnamen nennt.

- **Administration → Zertifikate** (nur Admins): Zertifikate als PEM-Text oder Datei
  hinzufügen, mit Inhaber, Aussteller, Gültigkeit und SHA-256-Fingerabdruck; abgelaufene sind
  markiert. Hinterlegt wird das Zertifikat der ausstellenden CA oder das selbst signierte
  Zertifikat eines Host Agents (ein selbst signiertes Zertifikat ist sein eigener Aussteller).
  Private Schlüssel werden abgewiesen. Änderungen gelten sofort für neue Verbindungen.
- **Zertifikat abrufen** auf der Seite eines Hosts (ab Configurator): liest das Zertifikat, das
  der Host Agent an seinem HTTPS-Port zeigt, ohne es zu prüfen, und sagt, ob es schon
  vertrauenswürdig ist. Admins können ihm dort nach dem Vergleich des Fingerabdrucks direkt
  vertrauen. Gelesen wird nur das Zertifikat des Hosts, nicht der Rest seiner Kette.
- Am echten Host Agent geprüft (2026-11-22): Sein selbst signiertes Zertifikat, über
  „Zertifikat abrufen“ übernommen, wird akzeptiert; über die IP-Adresse nur mit
  ausgeschaltetem „Hostnamen prüfen“. Schlägt die Prüfung fehl, steht der Grund im Fehler der
  Discovery.

### Tags

Hosts und Systeme tragen Tags: ein Schlüssel mit optionalem Wert, z. B. `dev`,
`internetfacing`, `sla=1`. Gepflegt werden sie kommagetrennt auf der Konfigurationsseite des
Hosts bzw. Systems.

- Schlüssel: Kleinbuchstaben, Ziffern, `-` und `_`, höchstens 32 Zeichen; Großbuchstaben
  werden klein geschrieben. Werte: Buchstaben, Ziffern, `.`, `-` und `_`, höchstens 64
  Zeichen. Je Schlüssel ein Wert, höchstens 50 Tags.
- Im Filter passt `sla` auf jeden Wert von `sla`, `sla=1` nur auf diesen Wert.
- Host-Tags gehen nicht auf Systeme über.

### Status aktualisieren

Der Knopf „Status aktualisieren“ (Systemseite und Landscape-Liste) fragt den sapstartsrv aller
Instanzen des Systems parallel ab, Diagnostics Agents eingeschlossen, und liest den Status der
Datenbanken auf den betroffenen Hosts. Das ist keine Aktivität und geht auch, während eine
läuft. Nicht erreichbare Instanzen erscheinen als Warnung und mit Status „unbekannt“.

### Systeme anlegen

Ein **System** ist eine selbst angelegte Gruppe von Instanzen mit frei wählbarem Namen, z. B.
ein ABAP-System mit der HANA-Instanz seiner Datenbank. Die Instanzen dürfen verschiedene SIDs
haben. Die Discovery legt keine Systeme an; neue Instanzen sind zunächst nicht zugeordnet.

1. Configuration → Hosts: Host anlegen und Discovery starten.
2. Configuration → Systeme: Im Reiter „Nicht zugeordnete Instanzen“ die Instanzen anhaken
   und **System anlegen** wählen (oder oben rechts **System anlegen** und dort die Instanzen
   anhaken). Die folgende Seite schlägt als Namen die SID der Anwendungsinstanzen vor (sonst
   die erste SID); Name, Beschreibung und Pool lassen sich dort festlegen.
3. Weitere Instanzen lassen sich mit **Vorhandenem System zuordnen** einem bestehenden System
   zuordnen.

Gehören Instanzen einer SID bereits zu genau einem System, schlägt die Liste für neu
gefundene Instanzen derselben SID dieses System vor. Zugeordnet wird erst per Klick.

Die Spalte „Hängt ab von“ in den aufgeklappten Systemen zeigt bei Anwendungsservern die
anderen SIDs von Datenbank und zentralen Diensten desselben Systems. Zentrale Dienste und
Datenbank hängen von nichts ab. Die Spalte ergibt sich aus den Instanztypen und ist nicht
bearbeitbar.

**Diagnostics Agents** (Feature `SMDAGENT`) gehören zum System, stehen aber in einer eigenen,
zugeklappten Gruppe. Start, Stopp und Neustart des Systems lassen sie aus, und sie zählen
nicht zum Status des Systems. Einzeln lassen sie sich weiter bedienen.

Gibt es dieselbe Kombination aus SID und Instanznummer auf mehreren Hosts, z. B. zentrale
Dienste und Anwendungsserver mit gleicher Nummer, nennt die Bezeichnung zusätzlich den
Hostnamen der Instanz, z. B. `DEV/00 (sapapp2)`. Abhängigkeiten **zwischen** Systemen pflegt man weiterhin auf der Seite eines
Systems.

Wird eine Instanz aus einem System entfernt oder ein System gelöscht, bleiben die Instanzen
im Inventar und sind wieder nicht zugeordnet. Solange für ein System eine Aktivität läuft,
lässt es sich nicht ändern.

- **Sprache:** Deutsch und Englisch, umschaltbar oben rechts. Ohne Auswahl gilt die Sprache
  des Browsers. Protokollmeldungen der Aktivitäten werden auf Englisch aufgezeichnet.
- **Aktualisierung:** Übersicht, Landschaft, Aktivitäten und die Live-Ansicht einer Aktivität
  laden neu, sobald der Server eine Änderung meldet (Server-Sent Events).
- **Keine externen Dateien:** Die Oberfläche lädt nichts aus dem Internet. React und die
  übrigen Bibliotheken werden mitgebaut und vom Server ausgeliefert (Lizenztexte in
  `static/app/THIRD-PARTY-LICENSES.txt`); eine strikte Content-Security-Policy erlaubt nur
  eigene Dateien.
- **Sitzung:** Ein signiertes Sitzungs-Cookie, 8 Stunden gültig, `HttpOnly` und
  `SameSite=Strict`. Wird `OSLO_SECRET_KEY` geändert, sind alle Sitzungen ungültig.
  Formulare von fremden Websites werden abgelehnt.

Einschränkungen:

- Keine Anmeldung über LDAP oder SSO, nur lokale Benutzer.
- Das Konfigurationsprotokoll erfasst nur Änderungen im Namen eines Benutzers (Oberfläche, API, Import), keine An- und Abmeldungen und keine eigenen Einstellungen (Darstellung, Favoriten, API-Tokens). Änderungen an Vorlagenschritten und Parametern eigener Operationen stehen nur als „geändert“ darin, ohne Einzelheiten.
- Das Cookie wird nur mit dem Attribut `Secure` gesetzt, wenn der Server die Anfrage als
  HTTPS sieht. Hinter einem Reverse-Proxy muss dieser das Protokoll weiterreichen.

## Inventar und REST-API

Das Inventar kennt Hosts, SIDs, Instanzen, Datenbanken sowie Systeme und Pools. Ein Host wird
angelegt und danach per Discovery ausgelesen: Der Host Agent liefert Betriebssystemdaten,
Instanzen samt SID und Datenbanken, der sapstartsrv jeder Instanz liefert Status, Instanztyp und
Startpriorität. Systeme legt man selbst aus Instanzen an (siehe „Systeme anlegen“).

Alle Aufrufe unter `/api` verlangen ein persönliches API-Token im Header
`Authorization: Bearer <token>`. Tokens legt man unter „Mein Konto“ an; sie haben die Rechte
der Rolle ihres Benutzers und können ein Ablaufdatum haben. Gespeichert wird nur ein Hash.
Die Oberfläche im Browser ruft die API mit dem Sitzungs-Cookie auf; Aufrufe, die etwas
ändern, brauchen dann zusätzlich den Header `X-OSLO-Request: 1`. Andere Websites können ihn
nicht mitschicken (kein CORS) und so nicht im Namen des angemeldeten Benutzers handeln.
Alle Antworten tragen eine strikte Content-Security-Policy: Skripte, Stile, Schriften und
Verbindungen nur vom Server selbst, keine Inline-Skripte, keine Einbettung in fremde Seiten.
Die interaktive Schnittstellenbeschreibung unter `/api/docs` ist ohne Token lesbar; sie enthält
keine Inventardaten.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Lebenszeichen, ohne Token |
| GET | `/api/me` | eigener Benutzer |
| GET, POST | `/api/me/tokens` | eigene API-Tokens auflisten bzw. anlegen (`{"name": "...", "expires_at": "..."}`; der Wert steht nur in der Antwort) |
| DELETE | `/api/me/tokens/{id}` | eigenes Token löschen |
| GET, PUT | `/api/me/preferences` | eigene Darstellung: `{"language": "" \| "en" \| "de", "theme": "system" \| "light" \| "dark", "time": "browser" \| "utc"}`; PUT ändert nur, was angegeben ist |
| GET, POST | `/api/users` | Benutzer auflisten bzw. anlegen (nur Admin; Startpasswort muss geändert werden) |
| PATCH | `/api/users/{id}` | Anzeigename, Rolle, aktiv ändern (nur Admin) |
| PUT | `/api/users/{id}/password` | Startpasswort setzen (nur Admin) |
| GET | `/api/hosts` | Hosts auflisten; `?tag=` filtert |
| PUT | `/api/hosts/{id}/tags` | Tags eines Hosts ersetzen |
| POST | `/api/hosts` | Host anlegen |
| POST | `/api/hosts/batch` | mehrere Hosts mit denselben Einstellungen anlegen (`names`, sonst wie `/api/hosts` ohne `name` und `address`), alle oder keiner; vorhanden: HTTP 409 |
| GET | `/api/hosts/{id}` | Host mit Instanzen und Datenbanken |
| PATCH | `/api/hosts/{id}` | Verbindungsdaten ändern (Name, Adresse, `hostagent_port`, `https`, `verify_tls`, `verify_hostname`, `sapcontrol_port_offset`); nicht angegebene Felder bleiben, Port 0 heißt Standardport. Während einer Aktivität auf dem Host: HTTP 409 |
| POST | `/api/hosts/{id}/certificate` | Zertifikat lesen, das der Host Agent zeigt (ungeprüft), mit `trusted_id`, falls es schon vertrauenswürdig ist; nicht erreichbar: HTTP 502 |
| GET | `/api/trusted-certificates` | vertrauenswürdige Zertifikate (nur Admin) |
| POST | `/api/trusted-certificates` | Zertifikat hinzufügen (`name`, `pem`; nur Admin); schon vorhanden: HTTP 409 |
| POST | `/api/trusted-certificates/check` | PEM-Text lesen, ohne ihn zu speichern (nur Admin) |
| DELETE | `/api/trusted-certificates/{id}` | Zertifikat entfernen (nur Admin) |
| PUT | `/api/hosts/{id}/credentials` | Zugangsdaten des Hosts setzen |
| DELETE | `/api/hosts/{id}` | Host samt Instanzen und Datenbanken löschen |
| POST | `/api/hosts/{id}/discover` | Host auslesen und Inventar aktualisieren |
| GET | `/api/instances` | alle Instanzen mit SID, System und Zuordnungsvorschlag (`suggested_system_id`); `?unassigned=true` nur nicht zugeordnete |
| GET | `/api/sids` | SIDs mit Angabe, ob Zugangsdaten hinterlegt sind |
| PUT | `/api/sids/{id}/credentials` | Zugangsdaten für den sapstartsrv der Instanzen einer SID setzen |
| GET | `/api/systems` | Systeme mit ihren Instanzen und Abhängigkeiten; `?tag=` filtert (mehrfach möglich, ein Treffer reicht) |
| PUT | `/api/systems/{id}/tags` | Tags eines Systems ersetzen (`{"tags": ["dev", "sla=1"]}`) |
| POST | `/api/systems/{id}/refresh` | Status aller Instanzen einmal neu lesen; liefert System und Warnungen |
| POST | `/api/systems` | System aus nicht zugeordneten Instanzen anlegen (`{"name": "...", "instance_ids": [ids], "pool_id": id, "description": "..."}`) |
| GET | `/api/systems/{id}` | ein System |
| PATCH | `/api/systems/{id}` | Name, Beschreibung und Stufe ändern (`stage`: `sandbox`, `development`, `quality`, `preprod`, `production` oder `null`; weggelassen: unverändert) |
| DELETE | `/api/systems/{id}` | System löschen; seine Instanzen werden wieder nicht zugeordnet |
| POST | `/api/systems/{id}/instances` | nicht zugeordnete Instanzen zuordnen (`{"instance_ids": [ids]}`) |
| DELETE | `/api/systems/{id}/instances/{instance_id}` | Instanz aus dem System entfernen |
| PUT | `/api/systems/{id}/dependencies` | Abhängigkeiten eines Systems setzen (`{"depends_on": [ids]}`) |
| PUT | `/api/systems/{id}/pool` | System einem Pool zuordnen (`{"pool_id": id}`, `null` entfernt) |
| GET | `/api/pools` | Pools mit ihren Systemen |
| POST | `/api/pools` | Pool anlegen (`{"name": "...", "description": "..."}`) |
| GET | `/api/pools/{id}` | ein Pool mit seinen Systemen |
| PATCH | `/api/pools/{id}` | Name und/oder Beschreibung ändern (leere Beschreibung entfernt sie); Name vergeben: HTTP 409 |
| DELETE | `/api/pools/{id}` | Pool löschen; seine Systeme bleiben erhalten |
| POST | `/api/instances/{id}/start`, `/stop`, `/restart` | Operation für eine Instanz anstoßen; nur für Instanzen eines Systems, sonst HTTP 409 |
| POST | `/api/systems/{id}/start`, `/stop`, `/restart` | Operation für ein ganzes System anstoßen |
| GET | `/api/activities` | Aktivitäten, neueste zuerst (`?limit=`); `?system_id=` die eines Systems (auch über Abhängigkeiten), `?instance_id=` die einer Instanz und ihres Systems, `?host_id=` die Host-Operationen eines Hosts |
| GET | `/api/activities/{id}` | Aktivität mit Protokoll (Einträge mit `event`, `subject`, `data` für den Zeitplan) und `options` (Einstellungen der Massenoperation bzw. Beschreibung und Parameter einer eigenen Operation); bei einer Massenoperation mit `children` |
| GET | `/api/operations` | Katalog der Operationen, die der eigene Benutzer ausführen darf, eigene mit Parametern |
| GET | `/api/landscape` | alles, was die Landscape zeigt: Systeme mit Instanzen, Status und laufender Aktivität, Hosts, Pools, die Operationen des Benutzers |
| GET | `/api/overview` | die Übersicht: Kennzahlen, Spalten (Stufen), Pools, Systeme mit Instanzen, „Braucht Aufmerksamkeit“ nach den Regeln und den Ausnahmen des Benutzers |
| GET, PUT | `/api/attention-rules` | Regeln von „Braucht Aufmerksamkeit“ lesen bzw. ändern (nur Admin): `{"rules": {"failed_activities": {"hours": 24, "hide_operations": ["read_logs"]}}}` |
| GET, PUT | `/api/me/attention` | eigene Ausnahmen: `{"disabled_rules": [], "hidden_systems": [], "hidden_pools": []}` |
| GET | `/api/steps?limit=300&activity_id=` | Schritte, neueste zuerst, je mit ihrer obersten Aktivität (`activity_id`); mit `activity_id` nur die Schritte dieser Aktivität |
| GET | `/api/config-changes?limit=300&object_type=&object_id=&username=&days=` | Konfigurationsprotokoll, neueste zuerst; `changes` je Feld `[alt, neu]`, Geheimnisse nur als `"(changed)"`; Einträge zu Benutzern nur für Admins |
| GET, PUT | `/api/config-log-settings` | `{"retention_days": 365}`: wie lange das Konfigurationsprotokoll aufbewahrt wird (PUT nur Admin, 1–3650) |
| GET | `/api/tls` | Zertifikat von OSLO, offene Anforderung, ob diese Verbindung HTTPS ist (nur Admin) |
| POST | `/api/tls/self-signed` | `{"names": [...], "ips": [...], "days": 730}`: Schlüssel und selbst signiertes Zertifikat erzeugen (nur Admin) |
| POST | `/api/tls/request` | `{"names": [...], "ips": [...]}`: Schlüssel und CSR erzeugen (nur Admin) |
| POST | `/api/tls/certificate` | `{"pem": "<Zertifikat und Zwischenzertifikate>"}`: signiertes Zertifikat zur offenen Anforderung (nur Admin) |
| DELETE | `/api/tls/request` | offene Anforderung verwerfen (nur Admin) |
| GET | `/api/bundle-status` | `{"active_version": "1.0.0"}`: Version des aktiven Bündels der OSLO-Operationen |
| GET | `/api/bundles` | Einstellungen (öffentlicher Schlüssel, Adresse, CA-Pfad) und alle Bündel (nur Admin) |
| PUT | `/api/bundles/settings` | `{"public_key": "<PEM>", "base_url": "https://…", "ca_path": ""}` (nur Admin) |
| POST | `/api/bundles` | `{"data": "<base64 der .oslobundle-Datei>"}`: prüfen, speichern, aktiv setzen (nur Admin) |
| POST | `/api/bundles/{id}/activate` | früheres Bündel wieder aktiv setzen (nur Admin) |
| GET | `/api/bundles/bootstrap` | Erstinstallationspaket als `.tar.gz` (nur Admin) |
| GET | `/bundle/payload.tar.gz`, `/bundle/payload.sig` | Download der Hosts, ohne Anmeldung |
| GET | `/api/systems/suggestion?instance_ids=1&instance_ids=2` | Namensvorschlag für ein neues System |
| GET | `/api/platform` | Version und Einstellungen (nur Admin) |
| GET | `/api/instances/{id}/processes` | Prozesse einer Instanz, jetzt gelesen per `GetProcessList`; aktualisiert den gespeicherten Status |
| GET | `/api/events` | Server-Sent Events: `hello`, dann `change`, sobald sich Aktivitäten, Status oder Inventar ändern (Datenbank wird alle 2 Sekunden geprüft) |
| GET | `/api/i18n` | alle Texte der Oberfläche in der Sprache des Benutzers |
| GET, POST | `/api/custom-operations` | eigene Operationen auflisten bzw. anlegen (nur Admin), mit `parameters` |
| GET, PUT, DELETE | `/api/custom-operations/{id}` | eigene Operation lesen, ersetzen (samt Parametern) bzw. löschen (nur Admin) |
| POST | `/api/instances/{id}/operations/{key}`, `/api/systems/{id}/operations/{key}`, `/api/hosts/{id}/operations/{key}` | eigene Operation ausführen (`{"parameters": {"KRNLREL": "793", "ONLYPREPARE": true}}`, `?timeout=` überschreibt das Zeitlimit) |
| GET, POST | `/api/templates` | Operationsvorlagen auflisten bzw. anlegen (nur Admin): `{"key", "name", "role", "steps": [{"position": 1, "operation": "stop", "target_type": "SYSTEM", "targets": [], "after": [], "parameters": {}, "ask": [], "on_error": "stop"}]}`; `targets` leer heißt „$Auswahl“; die Antwort nennt `selection` (Zieltyp der Auswahl oder `null`) |
| GET, PUT, DELETE | `/api/templates/{id}` | Vorlage lesen, ersetzen bzw. löschen (nur Admin); eine Dialog-Vorlage läuft wie eine eigene Operation über `/api/systems/{id}/operations/{key}` bzw. `/api/mass-operations` (ein Lauf mit allen Zielen) |
| POST | `/api/templates/{id}/run` | Vorlage starten (Rolle der Vorlage): `{"target_ids": [], "parameters": {"3.KRNLREL": "793"}}`; `target_ids` nur bei einer Dialog-Vorlage |
| GET | `/api/templates-blocks` | Für den Editor (nur Admin): alle Operationen, die ein Schritt nutzen kann, die 5 meistgenutzten (`top`) und die Favoriten des Benutzers |
| PUT | `/api/me/favorites` | Favoriten des Editors speichern: `{"operations": ["stop", "copy_kernel"]}` |
| GET, POST | `/api/schedules` | Einplanungen (`?operation=`) bzw. einplanen (ab Operator, Rolle der Operation nötig): `{"operation", "target_type", "target_ids", "parameters", "recurrence": "once"|"daily"|"interval", "run_at", "time_of_day", "weekdays", "interval_minutes"}` |
| GET, PUT, DELETE | `/api/schedules/{id}` | eine Einplanung lesen (mit `last_status` des letzten Laufs), ändern (z. B. `enabled`, `name`) bzw. löschen |
| GET | `/api/server-time` | Serverzeit und Zeitzone der Einplanungen |
| POST | `/api/export` | Konfiguration als JSON-Datei (`{"parts": [...], "password": "..."}`, Passwort optional; nur Admin) |
| POST | `/api/import` | Export einlesen (`{"data": {...}, "mode": "add" \| "update", "password": "...", "apply": false}`; ohne `apply` nur Vorschau; Antwort mit `counts` und `items`; nur Admin) |
| POST | `/api/activities/{id}/cancel` | laufende Aktivität abbrechen (Operator); HTTP 409, wenn sie schon beendet ist |
| POST | `/api/mass-operations` | Massenoperation (`{"operation": "stop", "target_type": "SYSTEM", "target_ids": [1, 2], "parallel": 5, "stop_on_error": false}`); `target_type` ist `SYSTEM`, `INSTANCE` oder `HOST`; für eigene Operationen zusätzlich `parameters`; Antwort ist die Sammelaktivität (HTTP 202) |

Beispiel mit der simulierten Landschaft (`OSLO_TOKEN` enthält ein persönliches API-Token):

```bash
curl -H "Authorization: Bearer $OSLO_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "sapapp1", "address": "127.0.0.1", "username": "devadm", "password": "mock"}' \
  http://127.0.0.1:8000/api/hosts
```

```bash
curl -X POST -H "Authorization: Bearer $OSLO_TOKEN" http://127.0.0.1:8000/api/hosts/1/discover
```

Verhalten:

- **Zugangsdaten:** Passwörter werden verschlüsselt gespeichert und von der API nie
  zurückgegeben. Die Zugangsdaten des Hosts gelten für den Host Agent. Für den sapstartsrv
  gelten die Zugangsdaten der SID der Instanz, falls gesetzt, sonst die des Hosts. Für den
  Betrieb reicht `sapadm` am Host: Start und Stopp laufen über den Host Agent, und den
  sapstartsrv liest das Tool nur. Zugangsdaten je SID braucht man nur, wenn ein sapstartsrv
  auch das Lesen mit `sapadm` ablehnt. Gepflegt werden sie auf der Seite eines Systems, das
  Instanzen der SID enthält.
- **Discovery löscht nichts.** Instanzen und Datenbanken, die der Host nicht mehr meldet,
  bleiben im Inventar und werden im Ergebnis als fehlend aufgeführt.
- **Nicht erreichbarer Host Agent:** Die Discovery antwortet mit HTTP 502, der Host wird als
  nicht erreichbar markiert.
- **Nicht erreichbarer sapstartsrv:** Die Instanz wird trotzdem aufgenommen, mit Status
  `UNKNOWN` und einer Warnung im Ergebnis.
- Der gespeicherte Status ist der Stand der letzten Discovery, kein Live-Wert.
- `sapcontrol_port_offset` verschiebt die sapstartsrv-Ports eines Hosts. Das ist nur für
  Testaufbauten gedacht, in denen mehrere simulierte Hosts auf einem Rechner laufen.

Einschränkungen:

- Der Server selbst spricht nur HTTP. Für den Zugriff über ein Netzwerk gehört ein
  Reverse-Proxy mit TLS davor.
- Eine Datenbank aus der Zeit vor dem Systemmodell (Schema 1) ist nicht verwendbar; der
  Server bricht mit einer Meldung ab. Sie muss gelöscht und das Inventar neu eingerichtet
  werden.
- Migrationen gibt es nur vorwärts; zum alten Stand führt die Sicherungskopie zurück.
- Jede SID gibt es nur einmal. Zwei Landschaften mit gleicher SID lassen sich nicht
  unterscheiden.

## Operationen und Aktivitäten

Jede Operation läuft als Aktivität im Hintergrund. Der Aufruf antwortet sofort mit HTTP 202 und
der Aktivität; den Fortschritt liest man über `/api/activities/{id}`.

```bash
curl -X POST -H "Authorization: Bearer $OSLO_TOKEN" http://127.0.0.1:8000/api/systems/1/stop
```

| Ziel | Weg | Fertig, wenn |
|---|---|---|
| Instanz | Host Agent (`StartInstance` / `StopInstance`) | alle Prozesse grün (Start) bzw. grau (Stopp) |
| System | Host Agent, Instanz für Instanz über alle Instanzen des Systems, auch mehrerer SIDs | alle Instanzen grün bzw. grau |

- **Warum alles über den Host Agent:** `StartSystem` und `StopSystem` des sapstartsrv lehnen
  echte Systeme für `sapadm` ab. Über den Host Agent reicht `sapadm`.
- **Reihenfolge im System:** Sie richtet sich nach der Rolle der Instanz, die das Tool aus
  den Features der Discovery ableitet, und gilt über alle SIDs des Systems.

  | Rolle | erkannt an | Start | Stopp |
  |---|---|---|---|
  | Datenbank | `HDB` | Phase 1 | Phase 2 |
  | Zentrale Dienste | `MESSAGESERVER`, `ENQUE`, `ENQREP` | Phase 1, parallel zur Datenbank | Phase 2, parallel zur Datenbank |
  | Anwendungsserver | `ABAP`, `J2EE`, unbekannte Features | Phase 2 | Phase 1 |
  | Diagnostics Agent | `SMDAGENT` | nicht dabei | nicht dabei |

  Innerhalb einer Rolle ordnet die Startpriorität die Instanzen in Gruppen, z. B. ERS vor
  ASCS. Jede Gruppe muss den Zielzustand erreichen, bevor die nächste ihrer Rolle beginnt,
  und jede Phase muss abgeschlossen sein, bevor die nächste beginnt. Instanzen, die schon im
  Zielzustand sind, werden übersprungen; ist das ganze System schon dort, endet die Aktivität
  sofort.
- **Abhängigkeiten zwischen Systemen:** Ist die Datenbank ein eigenes System, z. B. weil
  mehrere Systeme sie nutzen, legt man auf der Seite des ABAP-Systems fest, dass es vom
  Datenbanksystem abhängt (oder per API: `PUT /api/systems/{id}/dependencies` mit
  `{"depends_on": [<id>]}`). Gehört die HANA-Instanz zum selben System, ist keine
  Abhängigkeit nötig.
  - **Start:** erst die Abhängigkeiten, jeweils bis alle Instanzen grün sind, dann das System.
  - **Stopp:** erst das System, dann seine Abhängigkeiten. Eine Abhängigkeit, die ein
    anderes System noch benötigt, bleibt laufen; das Protokoll vermerkt das.
  - **Stopp eines Datenbanksystems** stoppt die Systeme nicht, die es benötigen. Die sollte
    man vorher stoppen.
  - Abhängigkeiten können verkettet sein. Kreise werden abgelehnt.
  - Eine Aktivität sperrt alle beteiligten Systeme; weitere Operationen darauf werden mit
    HTTP 409 abgelehnt.
- **Neustart** ist Stopp und danach Start. Jede der beiden Phasen hat das volle Zeitlimit.
- **Zeitlimit:** Standard 600 Sekunden, einstellbar mit `?timeout=` (10 bis 7200). Wird der
  Zielzustand nicht erreicht, endet die Aktivität mit `FAILED`. Die Operation auf dem Host
  läuft dabei weiter; abgebrochen wird nur das Warten.
- **Eine Aktivität pro System:** Solange eine Aktivität für ein System, eine seiner
  Instanzen oder ein System läuft, das davon abhängt, werden weitere mit HTTP 409 abgelehnt.
- **Status der Aktivität:** `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, bei
  Massenoperationen auch `PARTIAL`. Das Protokoll hält jede Statusänderung fest, und der
  Status im Inventar wird dabei aktualisiert.
- **Abbrechen** (Knopf „Abbrechen“ auf der Seite der Aktivität oder
  `POST /api/activities/{id}/cancel`, ab Operator): Bei Start, Stopp und Neustart hört das
  Tool nur auf zu warten und fordert nichts mehr an; was auf den Hosts schon angefordert ist,
  läuft weiter. Eigene Operationen werden auf dem Host abgebrochen (`CancelOperation`). Eine
  Massenoperation startet keine weiteren Teilaktivitäten und bricht die laufenden ab. Die
  Aktivität endet mit `CANCELLED` und vermerkt, wer abgebrochen hat.
- **Datenbanken:** Am Ende jeder Aktivität wird der Status der Datenbanken auf den
  beteiligten Hosts neu gelesen, damit er zum Zustand der Instanzen passt.
- **Fehlermeldungen:** Lehnt ein Dienst einen Aufruf ab, nennt die Meldung den Aufruf, den
  Dienst, die verwendeten Zugangsdaten und was zu tun ist, z. B. dass für die SID
  Zugangsdaten von `<sid>adm` fehlen.
- **Serverneustart:** Aktivitäten, die beim Beenden des Servers noch liefen, werden als
  `FAILED` mit dem Hinweis „Interrupted“ vermerkt. Der Zustand des Ziels ist dann unbekannt
  und sollte per Discovery geprüft werden.

Einschränkungen:

- Abbrechen hält Start und Stopp auf den Hosts nicht an, es beendet nur das Warten.
- Abhängigkeiten werden nicht automatisch erkannt, sondern von Hand gepflegt.
- Operationen für Datenbanken ohne SAP-Instanz (`StartDatabase` / `StopDatabase`) fehlen noch.
  Eine HANA-Datenbank wird über ihre Instanz gestartet und gestoppt.

## SOAP-Clients

Die Clients sind asynchron und liegen in `oslo.clients`.

```python
from oslo.clients import HostAgentClient, SapControlClient

async with HostAgentClient("sapapp1", auth=("sapadm", "...")) as agent:
    instances = await agent.list_instances()
    databases = await agent.list_databases()
    system = await agent.get_computer_system()

async with SapControlClient("sapapp1", 0, auth=("devadm", "...")) as sap:
    processes = await sap.get_process_list()
    await sap.start()
```

| Client | Methoden |
|---|---|
| `HostAgentClient` | `list_instances`, `list_databases`, `get_database_status`, `get_computer_system`, `execute_operation`, `execute_async`, `is_operation_finished`, `get_operation_results`, `cancel_operation`, `get_version`, `start_instance`, `stop_instance` |
| `SapControlClient` | `get_process_list`, `get_system_instance_list`, `start`, `stop`, `restart_instance`, `start_system`, `stop_system`, `restart_system` |

- Ports: Host Agent 1128 (HTTP) bzw. 1129 (HTTPS), sapstartsrv 5NN13 bzw. 5NN14. Mit `https=True`
  wird HTTPS genutzt, mit `port=` lässt sich der Port überschreiben.
- `verify` steuert die Zertifikatsprüfung bei HTTPS: `True` (Standard), Pfad zu einem CA-Bundle,
  ein `ssl.SSLContext` oder `False`. Für Inventareinträge baut `ClientFactory` den Kontext aus
  den Einstellungen des Hosts und den vertrauenswürdigen Zertifikaten.
- Start und Stopp kehren sofort zurück. Den Fortschritt liest man über `get_process_list` bzw.
  `get_system_instance_list`.
- Umgebungsvariablen für Proxys werden ignoriert, verwaltete Hosts werden direkt angesprochen.

Fehler sind Unterklassen von `SoapError`:

| Fehler | Bedeutung |
|---|---|
| `SoapConnectionError` | Host nicht erreichbar oder Zeitüberschreitung |
| `AuthenticationRequiredError` | geschützte Methode ohne Anmeldedaten (HTTP 401) |
| `InvalidCredentialsError` | Benutzer oder Passwort falsch |
| `PermissionDeniedError` | Benutzer nicht berechtigt |
| `SoapFaultError` | sonstiger Fehler des Dienstes, mit `faultstring` und `detail` |
| `OperationFault` | Fehler einer Operation des Host Agents, mit Fault-Code (`code`) und den Meldungen bis dahin (`result`) |
| `SoapProtocolError` | Antwort ist kein gültiges SOAP oder enthält unbekannte Werte |

`start_instance` und `stop_instance` senden standardmäßig das Flag `O-INSTANCE`; ein echter
Host Agent akzeptiert das. `SapControlClient` kann weiterhin `StartSystem` und `StopSystem`
aufrufen, die Operationen nutzen das aber nicht mehr. Der übrige Teststand steht oben unter
„Teststand gegen echte Hosts“.

## Mock-Umgebung

Die Mock-Umgebung simuliert eine kleine Landschaft, damit ohne echte SAP-Systeme entwickelt
und getestet werden kann. Sie startet pro Host einen Host-Agent-Endpunkt und pro Instanz einen
sapstartsrv-Endpunkt.

```bash
.venv/bin/oslo-mock
```

Die Standardlandschaft enthält das ABAP-System `DEV` und, wie in echten Landschaften, ein
eigenes HANA-System `HDV`:

| Host | Endpunkt | Port |
|---|---|---|
| `sapapp1` | Host Agent | 1128 |
| `sapapp1` | ASCS01 | 50113 |
| `sapapp1` | Dialoginstanz D00 | 50013 |
| `sapdb1` | Host Agent | 11128 |
| `sapdb1` | HANA-Instanz 02 (System `HDV`) | 60213 |

Die HANA-Instanz meldet wie ein echtes Multi-Tenant-System zwei Datenbanken: `SYSTEMDB@HDV`
und `HDV@HDV`. Nach der Discovery sind alle Instanzen nicht zugeordnet; Systeme legt man
selbst an, z. B. ein System `DEV` aus allen drei Instanzen.

Alle Endpunkte lauschen auf `127.0.0.1`. Weil die Mock-Hosts auf demselben Rechner laufen,
verschiebt `port_offset` die Ports des zweiten Hosts um 10000. Benutzer für geschützte
Methoden: `devadm` und `sapadm`, Passwort jeweils `mock`.

Eine eigene Landschaft lässt sich als JSON-Datei übergeben:

```bash
.venv/bin/oslo-mock --config landschaft.json
```

```json
{
  "start_duration": 3,
  "stop_duration": 2,
  "users": {"devadm": "mock"},
  "hosts": [
    {
      "name": "sapapp1",
      "port_offset": 0,
      "instances": [{"sid": "DEV", "nr": 0, "kind": "ABAP", "running": true}],
      "databases": []
    }
  ]
}
```

Mögliche Instanztypen (`kind`): `HDB`, `ERS`, `ASCS`, `SCS`, `ABAP`, `J2EE`, `SMDAGENT`
(Diagnostics Agent; Startpriorität und Prozessnamen sind angenommen).

### Simulierte Webmethoden

| Dienst | Methoden |
|---|---|
| SAPControl | GetProcessList, GetSystemInstanceList, Start, Stop, RestartInstance, StartSystem, StopSystem, RestartSystem |
| SAPHostControl | ListInstances, ListDatabases, GetDatabaseStatus, GetComputerSystem, StartInstance, StopInstance, ExecuteOperation (`versioninfo` und eigene Operationen), IsOperationFinished, GetOperationResults, CancelOperation |

Verhalten:

- Mit `"strict_sapstartsrv_auth": true` erlaubt der simulierte sapstartsrv administrative
  Aufrufe nur `<sid>adm` und antwortet anderen bekannten Benutzern mit „Permission denied“,
  wie ein echtes System. Standard ist `false`.
- Start und Stopp laufen asynchron wie beim echten Dienst: Der Aufruf kehrt sofort zurück,
  die Instanz ist danach `start_duration` bzw. `stop_duration` Sekunden lang gelb.
- `StartSystem` startet nach Instanzpriorität (HDB, dann ASCS, dann Anwendungsserver),
  `StopSystem` in umgekehrter Reihenfolge.
- Eigene Operationen stehen unter `custom_operations` (Name, Beschreibung, Befehl als Liste
  von Argumentnamen). Die Standardlandschaft hat `OSLO_TEST`, das sich wie ein Testskript
  verhält: Es gibt seine Argumente aus, läuft `PARAM-SLEEP` Sekunden (Standard 2) und endet
  mit dem Exit-Code `PARAM-RC`. Faults und Meldungen entsprechen denen eines echten Host Agents.
- Zustandsändernde Methoden verlangen HTTP Basic Auth. Ohne Anmeldedaten kommt HTTP 401,
  mit falschen ein SOAP Fault „Invalid Credentials“.

### Einschränkungen der Mock-Umgebung

- Elementnamen und Enum-Werte beider Dienste sind gegen die WSDLs eines Host Agent 7.22 und
  eines sapstartsrv abgeglichen.
- Inhalte, die die WSDLs offenlassen, orientieren sich an echten `saphostctrl`-Ausgaben: die
  CIM-Klassen von `GetComputerSystem` und die Datenbank-Komponenten. Annahmen bleiben die
  genaue Verschachtelung der CIM-Klassen sowie der Property-Schlüssel für den Vendor.
- Die rohen Antworten echter Hosts sind noch nicht mit denen des Mocks verglichen. Der Client
  findet die Betriebssystemdaten echter Hosts; er sucht die Klassen aber in jeder
  Verschachtelungstiefe, die Struktur selbst ist damit nicht belegt.
- Nur HTTP, kein HTTPS.
- Die Mock-Umgebung ist ein Entwicklungswerkzeug und darf nicht in nicht vertrauenswürdigen
  Netzen erreichbar sein.
