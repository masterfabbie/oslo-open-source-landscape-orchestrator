# OSLO – Hinweise für Claude

OSLO (Open Source Landscape Orchestrator, bis 2026-11-21 „Landscape Orchestrator“, kurz LO)
ist ein Werkzeug zur zentralen Verwaltung von SAP-Systemlandschaften, angelehnt an den
Funktionsumfang von SAP Landscape Management. Es ist ein unabhängiges Projekt. Verwende im
Code und in der Oberfläche keine SAP-Produktnamen als Namen dieses Werkzeugs; deshalb steht
„SAP“ auch nicht im Namen (Entscheidung des Eigentümers). Paket `oslo`, Befehle `oslo-*`,
Umgebungsvariablen `OSLO_*` (die alten `LO_*` werden mit Warnung noch gelesen,
`settings.env_value`), Header `X-OSLO-Request`, CSS-Klassen `oslo-*`.

Das README beschreibt Bedienung, API und Einschränkungen. Diese Datei beschreibt, wie hier
gearbeitet wird und was offen ist.

## Arbeitsweise

- **Änderungen am Code erst vorschlagen und freigeben lassen.** Der Eigentümer möchte keine
  Codeänderungen ohne Zustimmung.
- **Keine echten Daten ins Repository:** keine echten Hostnamen, IP-Adressen, SIDs realer
  Systeme, Passwörter, Tokens oder rohen Antworten echter Hosts. Beispiele und Tests nutzen
  die Namen der simulierten Landschaft (`sapapp1`, `sapdb1`, System `DEV`).
- **Annahmen kennzeichnen.** Was nicht aus einer WSDL oder einer echten Antwort belegt ist,
  wird im Code als Annahme kommentiert und im README unter den Einschränkungen genannt.
- Code, Kommentare und Protokollmeldungen sind englisch. README und diese Datei sind deutsch.
  Die Oberfläche ist zweisprachig; jeder Text braucht beide Sprachen
  (`src/oslo/web/i18n.py`, ein Test prüft das).

## Befehle

```bash
.venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/pytest
```

```bash
.venv/bin/ruff check .
```

Server gegen die simulierte Landschaft, braucht `OSLO_SECRET_KEY` (erzeugen mit
`.venv/bin/oslo-keygen`). Ohne Benutzer gibt er einen Einrichtungscode für `/setup` aus:

```bash
.venv/bin/oslo-server --mock
```

Benutzer ohne Oberfläche anlegen (fragt das Passwort ab):

```bash
.venv/bin/oslo-user add chief --role admin
```

Frontend (React, TypeScript, Vite in `frontend/`): Tests und Build; der Build schreibt nach
`src/oslo/web/static/app/` und wird mit eingecheckt (der Server braucht kein
Node.js). Nach jeder Änderung in `frontend/` neu bauen, sonst schlägt die CI fehl:

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run build
```

Schema der Datenbank aus `OSLO_DATABASE_URL` anzeigen bzw. migrieren (macht der Server beim Start
auch selbst):

```bash
.venv/bin/oslo-db current
```

Vor jedem Commit müssen Tests und Lint grün sein. Die CI prüft beides auf Python 3.11 und 3.13,
dazu im Job `frontend` Vitest, TypeScript, den Build (eingecheckter Build muss gleich sein) und
`npm audit`.

## Aufbau

Alles liegt unter `src/oslo/`.

| Modul | Aufgabe |
|---|---|
| `soapxml.py` | SOAP-Envelopes bauen und lesen, gemeinsam für Clients und Mock |
| `clients/` | asynchrone SOAP-Clients: `HostAgentClient` (SAPHostControl, Port 1128/1129), `SapControlClient` (sapstartsrv, Port 5NN13/5NN14), gemeinsame Fehlerklassen in `base.py` |
| `models.py`, `db.py` | Datenmodell (SQLAlchemy, asynchron): Host, Sid, Instance, System, Pool, Database, Activity, ActivityLogEntry; Migration beim Start, Sicherungskopie, Befehl `oslo-db` |
| `migrations/` | Alembic-Migrationen (`env.py`, `versions/`) |
| `hosts.py` | Verbindungsdaten eines Hosts ändern |
| `transfer.py` | Export und Import der Konfiguration als JSON (`export_configuration`, `import_configuration`, Bericht je Eintrag) |
| `tls.py` | vertrauenswürdige Zertifikate lesen und prüfen (`parse_pem`), TLS-Kontext für Hosts (`client_context`), Zertifikat eines Hosts abrufen (`fetch_certificate`) |
| `users.py` | Benutzer, Rollen, Passwörter (scrypt), Sperre nach Fehlversuchen, Sitzungs-Cookies, persönliche API-Tokens, Einstellungen pro Benutzer |
| `permissions.py` | welche Rolle eine Route braucht, gemeinsam für API und Oberfläche |
| `usercli.py` | Befehl `oslo-user` |
| `crypto.py`, `settings.py` | Verschlüsselung gespeicherter Passwörter (Fernet), Konfiguration aus Umgebungsvariablen |
| `connections.py` | baut Clients für Inventareinträge samt Zugangsdaten |
| `discovery.py` | liest einen Host aus und aktualisiert das Inventar |
| `dependencies.py` | Abhängigkeiten zwischen Systemen, Reihenfolge von Start und Stopp |
| `roles.py` | Rolle einer Instanz aus ihren Features: Datenbank, zentrale Dienste, Anwendungsserver, Diagnostics Agent; Instanztyp für Filter (`instance_type_key`) |
| `tags.py` | Tags von Hosts und Systemen (Schlüssel mit optionalem Wert): prüfen, ersetzen, vergleichen |
| `filters.py` | Werte der Landscape-Filter; gefiltert wird im Browser (`frontend/src/landscape/filter.ts`) |
| `landscape.py` | Daten der Landscape-Seite (`landscape_snapshot`), Gesamtstatus eines Systems, laufende Aktivitäten je System und Host, Prozesse einer Instanz live (`read_processes`) |
| `events.py` | Änderungen als Server-Sent Events (`/api/events`): Fingerabdruck der Datenbank, alle 2 Sekunden geprüft |
| `status.py` | Status lesen ohne Aktivität: Instanzen eines Systems (Knopf „Status aktualisieren“) und Datenbanken |
| `systems.py` | Systeme als Gruppen von Instanzen: anlegen, zuordnen, entfernen, löschen, Namens- und Zuordnungsvorschläge, abgeleitete „Hängt ab von“-SIDs |
| `pools.py` | Zuordnung von Systemen zu Pools |
| `operations.py` | Start, Stopp, Neustart, Discovery als Hintergrund-Aktivitäten, Massenoperationen (`OperationRunner`) |
| `catalog.py` | Katalog der Operationen: eingebaute und eigene (`Catalog`, je App eine Instanz, neu geladen nach Änderungen), Ziele, nötige Rolle, als Massenoperation erlaubt |
| `customspec.py` | Beschreibung einer eigenen Operation (`CustomSpec`, als JSON in der Aktivität), Kontextparameter, `SERVICE_SUBTYPE` |
| `templatespec.py`, `templates.py` | Operationsvorlagen: Beschreibung (`TemplateSpec`, `StepSpec`, als JSON in der Aktivität), anlegen und prüfen (`save_template`), Werte eines Laufs je Schritt (`template_values`) |
| `schedules.py` | Einplanungen (einmalig, täglich, Intervall), nächster Lauf (`next_run`), Start einer Katalog-Operation (`start_operation`), `Scheduler` |
| `customops.py` | eigene Operationen und Parameter anlegen und prüfen, Parameterwerte prüfen (`parameter_values`) |
| `api/` | REST-API unter `/api`, geschützt durch persönliche API-Tokens; `create_app` baut die Anwendung |
| `web/` | Anmeldung, Einrichtung und Passwortwechsel (Jinja2), Hüllen der React-Seiten (`app_page.html`, `routes.app_page`), Seitennavigation der Bereiche, Übersetzungen |
| `bundle.py` | Bündel der OSLO-Operationen: bauen, signieren (Ed25519), prüfen, Erstinstallationspaket, Ausgabe von `oslo_version`; Befehl `oslo-bundle`; Quellen der Host-Dateien in `bundle_files/` |
| `bundles.py` | Bündel auf dem Server: hochladen, aktives Bündel (`BundleStore`), Einstellungen, `oslo_version` am Host lesen, Zustand je Host (`host_state`) |
| `config_log.py` | Konfigurationsprotokoll: Änderungen beim Speichern erfassen (`before_flush`, `SPECS`), Benutzer der Anfrage (`set_actor`), Änderungen ohne ORM (`record`), Aufbewahrung (`purge`) |
| `attention.py` | Regeln für „Braucht Aufmerksamkeit“ (global in `platform_settings`, Ausnahmen je Benutzer), Spalten der Statusmatrix |
| `mock/` | simulierter Host Agent und sapstartsrv für Entwicklung und Tests |

Außerhalb des Pakets: `frontend/` mit den React-Seiten. `src/landscape/`: `Landscape.tsx`
Seite und Zustand, `SystemsTable`, `HostsTable`, `FilterBar`, `ActionBar`, `Drawer`
(Detailleiste: System, Instanz mit Reitern, Host, letzte Aktivitäten), `CommandPalette`,
`ParameterDialog`; `filter.ts` und `selection.ts` reine Logik mit Tests. `src/activity/`:
`ActivityPage.tsx` (Live-Ansicht einer Aktivität), `timeline.ts` (Zeitplan aus den
strukturierten Protokolleinträgen, mit Tests). `src/templates/`: `TemplatesPage.tsx` (Liste
und Graph-Editor unter `/operations/templates`), `graph.ts` (Anordnung, Vorgänger, mit Tests),
`OperationPicker.tsx`, `Schedules.tsx` (Einplanen). `src/overview/` (Übersicht),
`src/activities/` (Aktivitäten und Schritte), `src/configuration/` (Hosts, Systeme, Pools),
`src/operations/` (eigene Operationen), `src/administration/` (Allgemein, Benutzer, Regeln),
`src/account/` (Mein Konto mit Darstellung). `src/lib/` API-Aufrufe, Texte, Typen, `mount.tsx` (Start einer
Seite), `forms.tsx` und `forms.css` (Seitenkopf, Formulare, Tags, Zugangsdaten). Ein Stylesheet
für alle Seiten (`app.css`), gemeinsamer Code in `shared-*.js`.

Wichtige Entwurfsentscheidungen:

- **Alle Starts und Stopps laufen über den Host Agent** (`StartInstance`, `StopInstance`) und
  brauchen nur `sapadm`. Ganze Systeme orchestriert das Tool selbst nach Rollen
  (`roles.py`): Datenbank und zentrale Dienste starten parallel, Anwendungsserver erst danach;
  Stopp umgekehrt. Innerhalb einer Rolle ordnet die Startpriorität. Diagnostics Agents
  (`SMDAGENT`) gehören zum System, sind aber nicht Teil von Systemoperationen und zählen nicht
  zum Systemstatus; einzeln bleiben sie bedienbar. In der Landschaft, der Systemliste und auf
  der Seite eines Systems stehen sie zuletzt in einer eigenen, zunächst zugeklappten Gruppe
  „Diagnostics-Agents“ (beim Umstieg auf React verloren gegangen, 2026-11-23 wiederhergestellt;
  in der Landschaft offen, solange der Filter „Instanztyp“ aktiv ist). Wunsch des Eigentümers, angelehnt an LaMa.
  `StartSystem` und `StopSystem` des sapstartsrv werden nicht genutzt, weil echte Systeme sie
  für `sapadm` ablehnen. Den sapstartsrv liest das Tool
  nur (`GetProcessList`, `GetSystemInstanceList`).
- **Systeme sind selbst angelegte Gruppen von Instanzen** mit frei wählbarem Namen; die
  Instanzen dürfen verschiedene SIDs haben (z. B. ABAP-System samt HANA-Instanz mit eigener
  SID). Die Discovery legt nur SIDs (Tabelle `sids`) und nicht zugeordnete Instanzen an
  (`instances.system_id` ist dann NULL), nie Systeme. Nur Instanzen eines Systems lassen sich
  bedienen und erscheinen in der Landscape. Vorschläge (Name aus der SID der
  Anwendungsinstanzen, Zuordnung zu dem einen System, das die SID schon enthält) werden nie
  automatisch übernommen. „Hängt ab von“ je Instanz wird aus den Rollen abgeleitet (nur
  Anwendungsserver hängen ab, von Datenbank und zentralen Diensten) und nur angezeigt.
- **Bezeichnung einer Instanz** ist `SID/NR`; gibt es SID/NR auf mehreren Hosts, kommt der
  Instanz-Hostname dazu (`Instance.label`, Zählung per `column_property`).
- **Version des Host Agents** kommt aus `ExecuteOperation` `versioninfo` (synchron,
  Timeout -1) und steht in der eigenen Tabelle `host_agent_info`. Geparst werden nur die
  Texte der Meldungen, nicht ihre Schlüssel.
- **Zugangsdaten** gibt es auf zwei Ebenen: Die des Hosts gelten für den Host Agent, die der
  SID für den sapstartsrv. Fehlen die der SID, gelten die des Hosts.
- **Abhängigkeiten zwischen Systemen** werden von Hand gepflegt, z. B. wenn ein
  Datenbanksystem von mehreren Systemen genutzt wird. Start geht erst über die
  Abhängigkeiten, Stopp umgekehrt, und eine Abhängigkeit, die ein anderes System noch braucht,
  bleibt laufen. Innerhalb eines Systems ordnen Rollen und Startprioritäten über alle SIDs.
- **Nur eine aktive Aktivität pro System.** Eine Aktivität sperrt alle beteiligten Systeme
  (Tabelle `activity_systems`); weitere werden abgelehnt. Solange sie läuft, lässt sich das
  System auch nicht ändern (Instanzen zuordnen oder entfernen, löschen).
- **Schema und Migrationen:** Das Schema wird mit Alembic verwaltet (`migrations/`).
  `upgrade_database` läuft beim Start (Server und `create_app`): leere Datenbank anlegen,
  Datenbank von vor den Migrationen (Tabelle `schema_info` mit Version 2) übernehmen
  (fehlende Tabellen per `create_all`, dann `stamp 0001`, dann `upgrade`), sonst migrieren.
  Vor dem Migrieren bestehender Daten wird die SQLite-Datei kopiert; die letzten 5 Kopien
  bleiben (Wunsch des Eigentümers: automatisch, mit Sicherung). Schema 1 und unbekannte
  Revisionen werden abgewiesen. `create_all` wird sonst nicht mehr benutzt.
- **Neue Migration anlegen:** Modell ändern, dann gegen eine Datenbank auf neuestem Stand
  automatisch erzeugen, z. B. mit `alembic_config()` aus `db.py` und
  `command.revision(config, message=..., autogenerate=True, rev_id="000N")` (die Verbindung
  über `config.attributes["connection"]`). Die erzeugte Datei prüfen und kürzen. Revisionen
  sind fortlaufend nummeriert (`0001`, `0002`, …). `render_as_batch` ist an, weil SQLite
  Spalten nur durch Neuaufbau der Tabelle ändern kann; bei solchen Migrationen auf die
  Fremdschlüssel achten (`PRAGMA foreign_keys` ist an). Der Test
  `test_models_match_migrations` schlägt fehl, wenn eine Migration fehlt. Autogenerate schlägt
  dabei jedes Mal vor, die Fremdschlüssel von `activities` aus Migration 0004 neu aufzubauen;
  das ist nur die Lücke beim Zurücklesen (siehe Migration 0004) und muss aus der erzeugten
  Datei entfernt werden.
- **HTTPS und vertrauenswürdige Zertifikate** (Wunsch des Eigentümers, 2026-11-21): Tabelle
  `trusted_certificates` (Migration 0010, Administration → Zertifikate, nur Admins), dazu
  `hosts.verify_hostname`. `ClientFactory` hält die PEM-Texte (`load_trusted` beim Start und
  nach jeder Änderung) und je Einstellung von `verify_hostname` einen gecachten
  `ssl.SSLContext` (Speicher des Betriebssystems plus Liste); ohne HTTPS oder ohne
  `verify_tls` ist `verify` False. Ein selbst signiertes Zertifikat ohne CA-Merkmal wird von
  OpenSSL direkt als Vertrauensanker angenommen (in den Tests mit echten TLS-Servern auf
  127.0.0.1 geprüft). `POST /api/hosts/{id}/certificate` liest das Zertifikat ungeprüft
  (`app.state.fetch_certificate`), nur das Blatt, nicht die Kette (Python 3.11). Mit dem
  selbst signierten Zertifikat eines echten Host Agents geprüft (2026-11-22).
  Die Liste unter Administration → Zertifikate zeigt nur Name, Gültigkeit und Herkunft; Inhaber,
  Aussteller und Fingerabdruck klappt „Details“ unter der Zeile auf (Wunsch des Eigentümers:
  lange Namen verbreiterten die Tabelle, bis „Entfernen“ nur mit Scrollen erreichbar war).
- **HTTPS am Host gilt nur für den Host Agent** (Entscheidung des Eigentümers, 2026-11-22):
  `ClientFactory.sapcontrol` nutzt immer HTTP und Port 5NN13 (plus Verschiebung), weil die
  Instanz-Agents eigene Zertifikate zeigen; am Host scheiterte die Prüfung dort mit
  „self-signed certificate“ bzw. „unable to get local issuer certificate“. HTTPS zum
  sapstartsrv soll später eine eigene Einstellung je System oder Instanz bekommen (ToDo 13).
- **Seite eines Hosts:** zwei Spalten (`oslo-columns`), links Systeminformationen,
  Zugangsdaten, Tags, rechts Verbindung und Zertifikat; darunter Instanzen und Datenbanken.
- **Verbindungsdaten eines Hosts** lassen sich ändern (`hosts.update_connection`), nicht aber
  während einer Aktivität, die eine Instanz oder ein System auf dem Host betrifft. Geprüft wird
  die neue Verbindung erst durch die nächste Discovery.
- **Tags** sind Schlüssel mit optionalem Wert (`dev`, `sla=1`), je Schlüssel ein Wert, in den
  Tabellen `host_tags` und `system_tags`. Beim Ersetzen werden vorhandene Schlüssel
  aktualisiert statt gelöscht und neu angelegt (sonst Primärschlüssel-Konflikt im selben
  Flush).
- **Filter** der Landscape: innerhalb eines Filters reicht ein Treffer, alle Filter müssen
  passen; gefiltert wird in Python über die geladenen Listen. Welche Filter sichtbar sind,
  steht pro Benutzer in `user_settings` (Schlüssel `filters.<tab>`, Namen durch Punkte
  getrennt).
- **Benutzer und Rollen** (Wunsch des Eigentümers: vier Rollen wie in LaMa, kein gemeinsames
  Token mehr): viewer < operator < configurator < admin. Welche Rolle eine Route braucht,
  steht zentral in `permissions.required_role` (nach Methode und Routen-Vorlage); API
  (`require_user`) und Oberfläche (`require_login`) prüfen dort. Neue Routen dort einordnen;
  ohne Sonderfall gilt: GET → viewer, sonst configurator. Vorlagen blenden Knöpfe mit
  `can("operator")` usw. aus (Makros mit `import … with context`).
- **Anmeldung:** Sitzungs-Cookie mit Benutzer-ID, `session_epoch` und Ablauf, signiert mit
  einem aus `OSLO_SECRET_KEY` abgeleiteten Schlüssel. Passwort- oder Rollenänderung und
  Deaktivieren erhöhen `session_epoch` und beenden so alle Sitzungen. Startpasswörter
  (`must_change_password`) erzwingen den Wechsel vor jeder anderen Seite.
- **Erster Admin:** Ohne Benutzer erzeugt `create_app` beim Start einen einmaligen
  Einrichtungscode (`app.state.setup_code`) und gibt ihn auf stderr aus; `/setup` legt damit
  den ersten Admin an. `LO_API_TOKEN` wird nicht mehr verwendet.
- **API-Tokens** sind persönlich, haben die Rechte ihres Benutzers, optional ein Ablaufdatum;
  gespeichert wird nur der SHA-256-Hash. Aktivitäten speichern `requested_by`.
- **Discovery löscht nichts**, sie meldet fehlende Einträge nur.
- **JavaScript ist erlaubt** (Entscheidung des Eigentümers, 2026-11-20), auch ein Framework wie
  React, wo es echten Nutzen bringt: Mehrfachauswahl mit Aktionsleiste, Live-Ansichten,
  Drag-and-drop. Seit Phase 5 sind alle Seiten außer Anmeldung, Einrichtung und
  Passwortwechsel React-Seiten auf der REST-API. Größere Umbauten erst vorschlagen.
- **Bibliotheken und Schriften werden mitgeliefert** (Entscheidung des Eigentümers,
  2026-11-20): gebaut und vom OSLO-Server ausgeliefert, nie von einem CDN oder aus dem
  Internet geladen. Gründe: OSLO muss in abgeschotteten Admin-Netzen und im Störfall laufen; ein
  Werkzeug, das Produktivsysteme steuert und Skripte als root startet, lädt keinen fremden
  Code zur Laufzeit (strikte Content-Security-Policy nur mit `'self'` möglich); keine
  Aufrufe an Dritte (Datenschutz); getestete, feste Versionen. Dafür nötig: Build-Schritt
  (geplant: React mit Vite in `frontend/`, gebaut nach `web/static/app/`), die CI baut und
  testet beides, Versionen fest im Lockfile, Updates und Sicherheitspatches der Bibliotheken
  pflegen (z. B. Dependabot, `npm audit`), Lizenztexte mitliefern.
- **Gestaltungsrichtung** (Rückmeldung des Eigentümers zu fünf Entwürfen, 2026-11-20):
  - Landscape als dichte Tabelle mit Mehrfachauswahl von Systemen und Instanzen und einer
    Leiste unten mit den möglichen Operationen (Massenoperationen); Befehlspalette (Strg K).
  - Rechts aufklappende Detailleiste eines Systems; darin der Status je Instanz aus
    `GetProcessList` des sapstartsrv (Prozesse mit Farbe). Ein Abhängigkeitsgraph als
    Hauptansicht bringt keinen Mehrwert.
  - Aktivität als Live-Ansicht: Zeitplan je Instanz und mitlaufendes Protokoll mit Filtern.
  - Übersicht als Statusmatrix Produkte × Stufen mit „Braucht Aufmerksamkeit“; was dort
    erscheint, muss konfigurierbar sein (z. B. stündlich geplante Operationen ausblenden).
  - Operationsvorlagen als Kette von Bausteinen mit Parametern je Schritt, Verhalten bei
    Fehler und Einplanen: genau so umsetzen. Später (2026-11-20) ersetzt durch einen Graphen
    wie in LaMa, siehe „Operationsvorlagen“ unten.
- **Landscape als React-Seite** (Phase 1 des Umstiegs, ersetzt die alte Seite direkt;
  Wunsch des Eigentümers): `/landscape` liefert nur eine Hülle (`app_page.html` mit
  `base.html`, Startdaten als `<script type="application/json" id="oslo-boot">`: Sprache, alle
  Texte, Benutzer) und lädt `static/app/landscape.js`; die Daten kommen aus `/api/landscape`.
  Dateinamen ohne Hash, `asset_url()` hängt `?v=<Inhalts-Hash>` an. Filter, Auswahl und
  welche Operation passt, rechnet der Browser (`filter.ts`, `selection.ts`). Ein Ziel läuft
  über die einzelnen Endpunkte, mehrere und Host-Operationen über `/api/mass-operations`.
  Stopp und Neustart brauchen in der Leiste einen zweiten Klick (für Massenoperationen keine
  weitere Rückfrage, Wunsch des Eigentümers). Systeme sind zu Beginn zugeklappt; der Filter
  „Instanztyp“ klappt auf und zeigt nur passende Instanzen. Live über `/api/events`
  (React Query lädt neu). Die alte Seite `/mass` und `/landscape/filters` (sichtbare Filter
  pro Benutzer) gibt es nicht mehr. `?system=`, `?instance=` und `?host=` öffnen die
  Detailleiste; sie ersetzt die früheren Seiten `/systems/<id>` und `/hosts/<id>`, die dorthin
  weiterleiten.
- **Detailleiste** (Wunsch des Eigentümers): Ein System zeigt nur eine Übersicht (Status
  grob, Instanzen als Zeilen, letzte 5 Aktivitäten über `/api/activities?system_id=`), erst
  eine Instanz zeigt Details in Reitern (Allgemein, Status mit `GetProcessList`, Aktivitäten).
  Prozesse werden nur gelesen, solange der Reiter „Status“ offen ist. Kein
  Validierungsstatus wie in LaMa (gibt es in OSLO nicht).
- **Aktivität live** (Phase 2): `/activities/<id>` ist eine React-Hülle (`app_page.html`,
  Startdaten mit `activity_id`), Daten aus `/api/activities/<id>`, neu geladen bei Ereignissen
  aus `/api/events`. Der Zeitplan rechnet nicht mit Protokolltexten, sondern mit den Feldern
  `event`, `subject`, `data` der Einträge (Migration 0006): `_log(..., event=, subject=,
  data=)` im Runner. Neue Wartezustände, die im Zeitplan erscheinen sollen, brauchen dort ein
  Ereignis. Abbrechen über `POST /api/activities/<id>/cancel`; die alte Web-Route dafür gibt
  es nicht mehr.
- **Schritte** (Wunsch des Eigentümers, 2026-11-23, ersetzen den Reiter mit allen
  Protokolleinträgen und `/api/activity-log`): Schritte sind Aktivitäten, die selbst arbeiten,
  also nicht Sammelaktivitäten (`target_type` MASS oder TEMPLATE, `kind` TEMPLATE);
  `/api/steps` nennt zu jedem die oberste Aktivität (über `parent_id`). Spalten nach Vorgabe
  des Eigentümers: Zeit, Operation, ID, Ziel, Dauer, Aktivitätsnummer; der Status erscheint nur
  als Marke neben der Dauer, wenn er nicht „erfolgreich“ ist. Nummern auf allen Seiten
  `A`/`O` + ID + 100000 (`frontend/src/lib/numbers.ts`, nur Anzeige); die Liste der
  Aktivitäten zeigt nur die oberste Ebene. `/activities?tab=logs` zeigt die Schritte.
- **Operationsvorlagen** (Phase 3, Wunsch des Eigentümers; seit Migration 0008 als Graph nach
  dem Vorbild LaMa): Tabellen `operation_templates`, `template_steps`, nur Admins legen sie an.
  Schlüssel teilen sich den Raum mit eigenen Operationen. Jeder Schritt hat `position`
  (Nummer), eine eingebaute oder eigene Operation, `target_type`, `targets` (feste Ids, leer:
  „$Auswahl“ des Laufs), `after` (Vorgänger), `parameters` (feste Werte), `ask` (beim Start
  gefragt) und `on_error` (`stop`: kein neuer Schritt, laufende enden; `continue`;
  `stop_and_start`: danach die Systeme des Schritts starten). `operation_templates.target`
  ist der Zieltyp der Auswahl ("" ohne Auswahl; aus den Schritten abgeleitet, alle Schritte auf
  der Auswahl brauchen denselben Typ); `mass` ist seit 0008 unbenutzt. `save_template` prüft
  Kreise, Ziele und parallele sperrende Schritte auf denselben Zielen (`lock_scope`,
  `templatespec.parallel_pairs`). Rolle der Vorlage ≥ höchste Rolle der Schritte. Im Katalog
  als `OperationDef(kind=TEMPLATE)` mit `targets` = {Auswahltyp} (Dialog-Vorlage) oder leer
  (feste Ziele: nicht in der Landschaft, Start über `POST /api/templates/{id}/run` oder
  Einplanen). Mehrere ausgewählte Ziele sind ein Lauf (`submit_template(spec, selection, …)`,
  auch aus `/api/mass-operations`). Der Runner (`_execute_template`) startet jeden Schritt,
  sobald seine Vorgänger fertig sind, als Kind-Aktivität (mehrere Ziele: eine
  Massenoperation mit `parent_id`); zwei sperrende Schritte mit überschneidenden Zielen warten
  aufeinander. Die Vorlage sperrt beim Start alle Systeme und Hosts ihrer sperrenden Schritte
  (`activity_systems`, neu `activity_hosts`); `_submit` lässt Kinder durch, deren Vorfahr die
  Sperre hält (`_ancestors`). Das Ereignis `step` im Protokoll nennt das Kind
  (`data.activity`) für den Zeitplan. Teilweise gescheitert → PARTIAL. Parameter eines Laufs
  heißen `<Position>.<Name>`, nur die aus `ask`. Alte Schnappschüsse (ohne `target_type`)
  liest `StepSpec.from_dict` als Kette auf der Auswahl. Editor: React Flow
  (`@xyflow/react` 12, mitgeliefert), Anordnung in `frontend/src/templates/graph.ts`,
  Operationsauswahl mit Favoriten (`user_settings` `favorites.operations`) und den 5
  meistgenutzten der letzten 90 Tage (`/api/templates-blocks`). Annahme: kein Probelauf.
- **Merkmale eigener Operationen** (Wunsch des Eigentümers, wie in LaMa): `locks` („Sperrt
  Instanz oder Host“, Standard an; aus: läuft neben anderen Aktivitäten und blockiert keine,
  Spalte `activities.locks`, die Konfliktprüfung in `_submit` beachtet nur sperrende) und
  `standalone` (aus: „Nicht für Einzelausführung“, nur als Schritt einer Vorlage; nicht in
  Menüs, Landschaft, Massenoperationen, Einplanungen, `Catalog.for_target` filtert).
- **Einplanen** (Tabelle `schedules`): beliebige Katalog-Operation, Ziele (mehrere →
  Massenoperation; Vorlage: ein Lauf mit allen Zielen als Auswahl; Vorlage mit festen Zielen:
  `target_type` "" ohne Ziele), Werte, `once`/`daily` (Ortszeit in `OSLO_TIMEZONE`, Standard
  `Europe/Berlin` als Annahme)/`interval` (≥ 5 Minuten). Läuft mit den Rechten von
  `created_by`, beim Start erneut geprüft; Fehler in `last_error`. Der `Scheduler` prüft alle
  30 Sekunden (`oslo-server` startet ihn, `create_app(run_scheduler=True)`); Tests rufen
  `app.state.scheduler.tick()` mit eigener Uhr (`scheduler.now`). Verpasste Wiederholungen
  werden nicht nachgeholt, ein fälliger Lauf schon.
- **API mit Sitzungs-Cookie:** `require_user` nimmt ein Token oder das Sitzungs-Cookie; mit
  Cookie brauchen ändernde Aufrufe den Header `X-OSLO-Request: 1` (Schutz gegen fremde Seiten,
  es gibt kein CORS), ein Startpasswort sperrt die API. Rollen wie bisher über
  `permissions.required_role`.
- **Content-Security-Policy** auf allen Antworten (Middleware in `create_app`): nur `'self'`,
  keine Inline-Skripte oder -Stile. Die Jinja-Vorlagen (Anmeldung, Einrichtung, Passwort)
  dürfen keine `style=`-Attribute und keine Inline-Handler enthalten; React setzt Stile per
  CSSOM, das erlaubt die Policy.
- **Katalog der Operationen** (`catalog.py`): Neue eingebaute Operationen werden dort
  eingetragen; eigene und Vorlagen kommen aus der Datenbank. Alle erscheinen in der Landschaft
  (Leiste, Detailleiste, Befehlspalette; gefiltert nach Rolle und Instanztyp),
  Massenoperationen und `/api/operations`. Routen für
  Operationen brauchen mindestens Operator (`permissions.OPERATION_ROUTES`); die Rolle der
  einzelnen Operation prüft der Handler.
- **Eigene Operationen** (Wunsch des Eigentümers, angelehnt an die kundendefinierten
  Operationen in LaMa): Skripte aus `operations.d` des Host Agents, aufgerufen mit
  `ExecuteOperation` asynchron (Timeout 0), dann `IsOperationFinished` und
  `GetOperationResults` im Takt der Statusabfrage; neue Zeilen kommen ins Protokoll (die
  Übergangszeile „saphostcontrol: Executing … hook“ nicht). Fault 255 heißt „läuft noch“,
  Fault 127 „Skript fehlgeschlagen“ (mit allen Zeilen im Detail `OperationException`),
  -20 „unbekannte Operation“. Nur Admins legen sie an (Tabellen `custom_operations`,
  `custom_operation_parameters`, Migration 0005); jede hat eine eigene Rolle zum Ausführen.
  Die Aktivität (`kind` CUSTOM) speichert die Beschreibung der Operation und die Werte in
  `options`, damit spätere Änderungen laufende Aktivitäten nicht berühren. Parameter: Text,
  Ganzzahl, Ja/Nein; leere optionale Werte werden wie in LaMa nicht übergeben (Wunsch des
  Eigentümers: Aufrücken der Positionsargumente ist Sache des Skripts), fehlende bekommen
  den Standardwert. Text ohne eigenes Muster nur `[A-Za-z0-9._-]*`. `SERVICE_SUBTYPE` wird
  aus dem Instanztyp und den Anwendungsservern des Systems abgeleitet (Annahme). Ihre Parameter
  fragt in der Landschaft `ParameterDialog` ab. Eingebaute Schlüssel (`start`, `stop`, `restart`, `discover`) sind für eigene gesperrt.
- **Abbrechen** (`OperationRunner.cancel`, Wunsch des Eigentümers): Start, Stopp und Neustart
  hören nur auf zu warten; eigene Operationen werden per `CancelOperation` (O-HARD) auf dem
  Host abgebrochen, ebenso beim Zeitlimit; Massenoperationen brechen laufende Kinder ab und
  überspringen wartende. Endstatus CANCELLED. Ein Abbruch des Benutzers unterbricht eine
  Aktivität nur an **sicheren Stellen** (`_pause` statt `_sleep`, `_wait_for_any`), nie mitten
  in einem Datenbankzugriff: Sonst bleibt die aiosqlite-Verbindung gesperrt und das Ende der
  Aktivität lässt sich nicht schreiben („database is locked“). Welche Aufgaben zu einer
  Aktivität gehören, auch die von `asyncio.gather`, steht in der Kontextvariablen
  `_CURRENT_ACTIVITY`. Neue Wartestellen in Aktivitäten nutzen `_pause`. `cancel` beendet
  vor dem Warten die Lesetransaktion der Anfrage, sonst blockieren sich beide. `_run` schließt
  die Aktivität in einer frischen Sitzung ab. Beim Herunterfahren (`shutdown`) halten
  Aktivitäten ebenfalls an der nächsten sicheren Stelle an („Interrupted“); was nach
  5 Sekunden noch läuft, wird hart abgebrochen.
- **Massenoperationen** (Wunsch des Eigentümers: Systeme, Instanzen und Hosts, Standard 5
  gleichzeitig, bei Fehlern weitermachen, keine zusätzliche Bestätigung): eine
  Sammelaktivität (`target_type` MASS, Einstellungen als JSON in `activities.options`) mit
  Teilaktivitäten (`parent_id`). `_run_mass` startet Kinder bis zur Parallelität, beachtet
  Abhängigkeiten der ausgewählten Systeme, lässt bei Sperrkonflikt auf Geschwister warten und
  überspringt Ziele, die von außen belegt sind. Endstatus SUCCEEDED, PARTIAL oder FAILED.
- **Instanz-Agent registrieren, abmelden, neu registrieren** (Wunsch des Eigentümers, statt der
  in LaMa eingebauten Operation, die bei neuen Systemen scheiterte): eingebaute Operationen
  `register`, `unregister`, `reregister` für Instanzen (`OperationKind` REGISTER usw., Rolle
  Operator, auch als Massenoperation und Vorlagenschritt). Sie rufen am Host Agent
  `RegisterInstanceService` bzw. `UnregisterInstanceService` synchron (Timeout -1) mit SID,
  Nummer und `mHostname`; die Zeilen der Antwort kommen ins Protokoll. Abmelden und neu
  Registrieren werden abgelehnt, solange ein Prozess der Instanz nicht gestoppt ist; antwortet
  der sapstartsrv nicht, geht es weiter. Nach dem Registrieren wartet OSLO, bis der sapstartsrv
  antwortet (`_service_operation`). Der Mock bildet das mit `MockInstance.service_running`
  nach (abgemeldet: Verbindung abgelehnt). Annahme: `sapadm` darf beide Methoden per SOAP
  aufrufen (geprüft ist nur `saphostctrl` als root).
- **Host-Operationen** (bisher nur Discovery) laufen als Aktivität mit `host_id`; je Host
  höchstens eine gleichzeitig.
- **Migration 0004** fügt Spalten mit Fremdschlüssel per `ALTER TABLE … REFERENCES` an, weil
  Alembics Batch-Modus `activities` neu aufbauen würde und das Löschen der alten Tabelle bei
  aktiven Fremdschlüsseln das Protokoll per `ON DELETE CASCADE` mitlöschen würde. Der
  Vergleichstest ignoriert deshalb das nicht zurückgelesene `ON DELETE` dieser Spalten.
- **Aufbau der Oberfläche:** Übersicht (Statusmatrix, „Braucht Aufmerksamkeit“), Landscape (beobachten und bedienen:
  Systeme, Hosts), Activities (Aktivitäten, Schritte), Configuration (einrichten: Hosts,
  Systeme, Pools), Operations (eigene Operationen unter `/operations/custom` und
  Operationsvorlagen unter `/operations/templates` nur für Admins, Einplanungen unter
  `/operations/schedules` ab Operator), Administration (Allgemein, Benutzer,
  Regeln für „Braucht Aufmerksamkeit“, Zertifikate, Import/Export), „Mein Konto“ (Passwort, API-Tokens). Menüpunkte deutsch:
  Übersicht, Landschaft, Aktivitäten, Konfiguration, Operationen, Administration; englisch
  unverändert (Wunsch des Eigentümers, 2026-11-20).
- **Bereiche mit Unterbereichen** (Wunsch des Eigentümers nach LaMa-Vorbild): Configuration,
  Operations und Administration haben links eine Seitennavigation (`SECTIONS` in
  `web/routes.py`, gerendert in `base.html`; markiert ist der längste passende Unterbereich;
  auf schmalen Bildschirmen über dem Inhalt). Jeder Unterbereich hat oben Überschrift und
  Anlegen-Knopf rechts, darunter Reiter mit „Übersicht“ zuerst (`PageHead` in
  `frontend/src/lib/forms.tsx`). Anlegen läuft
  über eigene Seiten (`…/new`), keine Formulare unter Listen. Nicht zugeordnete Instanzen sind
  ein eigener Reiter (`/configuration/systems/unassigned`). Alte Links
  (`/configuration?tab=…`, `/operations`, `/administration?tab=users`) leiten weiter. Rechte: `/operations/…` nur Admin;
  `/operations` allein ist in der API der Katalog (viewer).
- **Übersicht als Statusmatrix** (Phase 4, Entwurf 4, Wunsch des Eigentümers): Zeilen sind
  die Pools („Produkt“, dazu „ohne Pool“), Spalten die Stufen (`systems.stage`, Migration 0009:
  `sandbox`, `development`, `quality`, `preprod`, `production`; Entwicklung, Qualität,
  Produktion immer, Sandbox und PreProd nur, wenn ein System sie hat, „ohne Stufe“ bei Bedarf).
  Jede Instanz ein Statuskästchen; Klick öffnet die Landschaft. Daten aus `/api/overview`
  (`landscape.overview_snapshot`).
- **„Braucht Aufmerksamkeit“** (`attention.py`): Regeln mit Einstellungen (`DEFAULT_RULES`):
  fehlgeschlagene Aktivitäten (Zeitraum, Einplanungen mit kurzem Intervall ausblenden, z. B.
  stündliche; bestimmte Operationen ausblenden; ausblenden nach späterem Erfolg auf demselben
  Ziel; Stufen), Systeme mit Fehlern (Status, Stufen; nicht während einer Aktivität), gestoppte
  Systeme (Stufen, Standard Produktion), lange Läufe (Minuten), nicht erreichbare Hosts,
  Einplanungsfehler, alte Discovery (Tage, Standard aus). Global gespeichert in
  `platform_settings` (`attention.rules`), nur Admins ändern sie (`/api/attention-rules`,
  Seite Administration → Braucht Aufmerksamkeit). Ausnahmen je Benutzer in `user_settings`
  (`attention.user`: Regeln aus, Systeme und Pools ausgeblendet; `/api/me/attention`). Jeder
  Eintrag liefert einen Textschlüssel `att.*` mit Werten, übersetzt im Browser.
- **Formularseiten in React** (Phase 5): Je Bereich eine App (`configuration`, `operations`,
  `administration`, `account`, `activities`); der Server rendert `app_page.html` mit
  `boot.page` (und `boot.id`) und prüft vorher Rolle und Existenz (404). Seitenwechsel sind
  normale Links; Hinweise nach dem Speichern über `?notice=…`, die `base.html` anzeigt.
  Servergerendert bleiben Anmeldung, Einrichtung, Sprachwechsel und der Passwortwechsel
  (`/account/password`, auch für Startpasswörter). Die alten Jinja-Seiten, ihre POST-Routen und
  Tests sind entfernt; Tests prüfen die API und in `test_web.py` die Hüllen der Seiten.
- **Systeme alphabetisch**, ohne Rücksicht auf Groß- und Kleinschreibung
  (`order_by(func.lower(System.name))` in `api/app.py` und `landscape.py`, im Browser
  zusätzlich `byName` in `configuration/Systems.tsx`), z. B. in der Auswahl „Einem System
  zuordnen“.
- **Pools** gruppieren zusammengehörige Systeme (z. B. Entwicklung, Test, Produktion eines
  Produkts). Ein System gehört zu höchstens einem Pool (Tabelle `pool_systems`). Name und
  Beschreibung lassen sich ändern (`PATCH /api/pools/{id}`, Seite `/configuration/pools/{id}`).
- **Mehrere Hosts auf einmal** (`POST /api/hosts/batch`, Wunsch des Eigentümers): Namen durch
  Kommas im Feld „Name“ (`hostNames` in `Hosts.tsx`), gleiche Einstellungen und Zugangsdaten,
  Adresse = Name, alle oder keiner (vorhandene oder doppelte Namen, auch in anderer
  Schreibweise, lehnen den ganzen Auftrag ab).
- **Logo und Favicon** (Vorlagen des Eigentümers im Wissens-Repository, 2026-11-23): Die
  Vorlagen sind RGB mit eingebranntem Schachbrettmuster statt Transparenz; die Dateien in
  `web/static/` sind daraus freigestellt (Alpha aus dem Abstand zum hellen Hintergrund),
  verkleinert (Logo 720 px breit, Favicon 32 px, Apple-Icon 180 px) und für dunkle Farben
  umgefärbt (`oslo-logo-dark.png`, Grau wird hell, Petrol bleibt). Logo nur auf Anmeldung und
  Einrichtung (`.login-logo`), in der Kopfzeile jeder Seite ein kleines Logo aus Symbol und
  Schriftzug ohne Unterzeile (`oslo-header.png`, 56 px hoch für 28 px Anzeige, Wunsch des
  Eigentümers), Favicon in `base.html`. Jedes Logo gibt es hell und dunkel (`img.logo-light`,
  `img.logo-dark`); `style.css` zeigt das passende nach denselben Regeln wie die Farben.
  Anmeldung und Einrichtung haben kein `data-theme` und folgen damit dem Betriebssystem.
- **Konfigurationsprotokoll** (Wunsch des Eigentümers, 2026-11-23): Tabelle `config_changes`
  (Migration 0012), Reiter Aktivitäten → Konfiguration, „Letzte Änderungen“ auf den Seiten von
  Host, System, Pool, eigener Operation, Einplanung und Benutzer (`frontend/src/lib/changes.tsx`).
  Erfasst wird automatisch beim Flush (`config_log.install`, Ereignis `before_flush`), nur
  Felder aus `SPECS` (Konfiguration, nicht Status, Versionen, nächste Läufe) und nur im Namen
  eines Benutzers: `require_user` und `require_login` setzen ihn per Kontextvariable
  (`set_actor`); Aktivitäten setzen ihn in `_run` zurück, Scheduler und Discovery-Ergebnisse
  erscheinen daher nicht. Kindzeilen (Tags, Parameter, Vorlagenschritte) zählen beim Eltern-
  objekt; neu angehängte haben vor dem Flush noch keinen Fremdschlüssel, entfernte werden erst
  im Flush als Waisen gelöscht (deshalb über die Historie der Liste). Instanzen zuordnen
  erscheint beim System. Pools und Abhängigkeiten ändern Zwischentabellen ohne ORM und rufen
  `config_log.record` selbst; der Import schreibt zusätzlich einen Sammeleintrag. Neue Objekte
  bekommen ihre Id erst im Flush (`after_flush_postexec` trägt sie nach). Geheimnisse und Werte
  über 120 Zeichen nur als `(changed)`. Einträge zu Benutzern sieht nur der Admin, sonst ab
  Viewer. Aufbewahrung `platform_settings` `config_log.retention_days` (Standard 365,
  Administration → Allgemein), gelöscht im `Scheduler.tick` höchstens stündlich. Neue
  Konfigurationsmodelle oder -felder in `SPECS` eintragen.
- **OSLO-Operationen** (ToDo 10, Entscheidung des Eigentümers 2026-11-23): OSLO-eigene Dateien
  für `operations.d` als signiertes Bündel (`bundle.py`, Quellen in `src/oslo/bundle_files/`:
  `oslo_*.conf` und `oslo/`). `DeployConfiguration` scheidet aus (am Host „Remote deployment not
  permitted“, auch lokal als root). Erstinstallation einmal je Host von Hand oder per Ansible aus
  dem Erstinstallationspaket (`/api/bundles/bootstrap`, `install.sh`, legt auch
  `oslo/bundle_key.pem` und `oslo/oslo.cfg` mit `OSLO_URL` an). Updates: Admins laden
  `.oslobundle`-Dateien hoch (signiert mit `oslo-bundle build`, privater Schlüssel nie auf dem
  Server; OSLO prüft gegen den eingetragenen öffentlichen Schlüssel, `platform_settings`
  `bundle.*`), die eingebaute Host-Operation `update_bundle` (`OperationKind.UPDATE_BUNDLE`, nur
  Admin) ruft `oslo_update` auf, der Host lädt `/bundle/payload.tar.gz` und `.sig` (öffentlich,
  ohne Anmeldung) und prüft selbst Signatur, Dateinamen (`oslo_*.conf`, `oslo/…`, keine Links)
  und `SHA256SUMS`; ersetzt werden nur OSLO-Dateien, per Umbenennen (laufende Skripte behalten
  ihre Kopie). Die Hosts dürfen OSLO per HTTPS erreichen (Eigentümer, 2026-11-23). Jede
  Discovery ruft `oslo_version` auf (wie eigene Operationen: asynchron, dann Abfrage) und
  speichert `hosts.bundle_version`/`bundle_integrity`/`bundle_checked_at` (Migration 0013);
  unbekannte Operation heißt „nicht installiert“. Zustand (`bundles.host_state`, im Browser
  `lib/bundle.ts`): unknown, missing, modified, outdated, current, installed (ohne aktives
  Bündel). Regel `bundle_outdated` für „Braucht Aufmerksamkeit“. Der Mock bildet beide
  Operationen nach (`MockHost.bundle_version`, `bundle_key`, `MockLandscape.bundle_source`,
  Signaturprüfung mit `bundle.check_bundle`); in der Standardlandschaft der Tests ist kein
  Bündel installiert, `oslo-server --mock` gibt `sapapp1` Version 0.9.0. Annahmen: Ausführung
  als root, OpenSSL ≥ 1.1.1, nur UNIX, kein `ReloadConfiguration` nötig. Der Name `oslo_*` ist
  reserviert. Neue OSLO-eigene Operationen kommen als Dateien nach `bundle_files/`.
- **Darstellung je Benutzer** (Wunsch des Eigentümers): `user_settings` `ui.language` (""
  folgt Cookie bzw. Browser) und `ui.theme` (`system`, `light`, `dark`), `users.get_preferences`
  bzw. `set_preferences`, `/api/me/preferences`. `require_login` legt sie in
  `request.state.preferences` ab; `_language` nimmt zuerst die gewählte Sprache, dann Cookie,
  dann `Accept-Language`. `base.html` setzt `data-theme` auf `<html>`; `style.css` nutzt die
  dunklen Farben bei `prefers-color-scheme: dark` außer mit `data-theme="light"` und immer mit
  `data-theme="dark"`. Den Umschalter EN/DE in der Kopfzeile zeigt `base.html` nur ohne
  angemeldeten Benutzer (Anmeldung, Einrichtung; Wunsch des Eigentümers); `/language/{code}`
  setzt nur das Cookie.
- **Einplanungen als Bereich** (ToDo 9, Wunsch des Eigentümers, nach dem Vorbild der LaMa-Liste
  „Schedules“ im Bereich Operationen): Unterbereich „Einplanungen“ unter Operationen
  (`/operations/schedules`, App `operations`, `frontend/src/operations/Schedules.tsx`) mit
  allen Einplanungen, Filtern, Status des letzten Laufs (`last_status` aus der Aktivität),
  Zeitzone und Serverzeit (`/api/server-time`) und Löschen mehrerer; anlegen und ändern unter
  `/operations/schedules/new` bzw. `/{id}`. Ab Operator (`permissions.required_role`); die
  Einträge der Seitennavigation haben je eine Rolle (`SECTIONS`, `_section` filtert), deshalb
  sehen Operatoren und Konfiguratoren unter Operationen nur die Einplanungen, `/operations`
  leitet sie dorthin. Name je Einplanung (`schedules.name`, Migration 0011, leer: Name der
  Operation). Jede Katalog-Operation mit `standalone`, Ziele aus `/api/landscape`, Parameter
  eigener Operationen aus `/api/operations`; Werte von Vorlagen (`ask`) bleiben im Editor der
  Vorlage, beim Ändern bleiben vorhandene Werte erhalten. `/activities?tab=schedules` leitet
  auf die neue Adresse. Gemeinsame Beschreibung der Wiederholung in
  `frontend/src/lib/schedules.ts`.
- **Zeiten immer in UTC** (2026-11-22): Alle Zeitspalten nutzen `models.UTCDateTime`; es
  schreibt UTC ohne Zone (SQLite kennt keine) und liest UTC mit Zone zurück, so trägt jede Zeit
  der API ihr `+00:00`. Vorher kamen Zeiten ohne Zone an, und der Browser zeigte sie als
  Ortszeit (in Berlin eine Stunde zu früh). Naive Werte gelten beim Schreiben als UTC. Neue
  Zeitspalten nehmen `UTCDateTime()`, nicht `DateTime`.
- **Anzeige der Zeiten je Benutzer** (Wunsch des Eigentümers, wie in der AWS-Konsole):
  `user_settings` `ui.time` (`browser` Standard, `utc`) in „Mein Konto → Darstellung“, in den
  Startdaten als `time_display`. `formatTime` in `frontend/src/landscape/ui.tsx` zeigt UTC mit
  dem Zusatz „UTC“; Eingaben (`datetime-local`) rechnen `toInputValue`/`fromInputValue` in
  der gewählten Zone um. Tägliche Einplanungen bleiben in `OSLO_TIMEZONE`.
- **Import/Export** (Wunsch des Eigentümers, 2026-11-23; Format JSON statt XML wie in LaMa,
  Entscheidung des Eigentümers): `transfer.py`, Administration → Import/Export
  (`/administration/transfer`, `frontend/src/administration/Transfer.tsx`), API `/api/export`
  und `/api/import` (nur Admin). Bezüge über Namen (Instanz: Host, SID, Nummer). Passwörter
  nur mit Export-Passwort, verschlüsselt mit scrypt + Fernet (Salz und Prüfwert im Kopf
  `credentials`), nie mit `OSLO_SECRET_KEY`. Keine Benutzer (Entscheidung des Eigentümers).
  Import: Reihenfolge Hosts, SIDs, Pools, Systeme, Abhängigkeiten, eigene Operationen,
  Vorlagen, Einplanungen, Regeln, Zertifikate; je Eintrag ein Savepoint (`begin_nested`), ein
  Fehler betrifft nur den Eintrag. `_begin` startet die Transaktion ausdrücklich, weil der
  SQLite-Treiber sonst beim Freigeben eines Savepoints festschreibt und die Vorschau (Rollback)
  nicht wirkt. Modus `add`/`update`, nie löschen. Keine Discovery beim Import (Entscheidung des
  Eigentümers); Systeme ohne bekannte Instanz werden abgelehnt. Nach dem Import lädt die API
  Katalog und vertrauenswürdige Zertifikate neu.
- In `api/app.py` steht bewusst kein `from __future__ import annotations`: FastAPI löst die
  Typangaben der Routen zur Laufzeit auf, und sie verweisen auf lokale Namen.

## Tests

- Die Tests laufen gegen die simulierte Landschaft in `mock/`. `MockLandscapeTransport`
  leitet Anfragen ohne Netzwerk nach Port an die Mock-Dienste weiter.
- Die Fixture `extended_landscape` ergänzt einen Diagnostics Agent `DAA/98` auf `sapapp1` und
  einen Host `sapapp2` mit einer zweiten Instanz `DEV/00`; damit werden Rollen,
  Parallelstart und doppelte Instanznummern getestet.
- Die Standardlandschaft hat zwei SIDs: `DEV` (ABAP) und `HDV` (HANA, eigene SID). Nach der
  Discovery sind alle Instanzen nicht zugeordnet; die Tests der Operationen, der API und der
  Oberfläche legen daraus die Systeme `DEV` und `HDV` an. Ein Test fasst alle drei Instanzen
  in einem System zusammen und prüft die Reihenfolge über SIDs hinweg. Die Fixture
  `single_sid_landscape` legt HANA in `DEV`; sie testet den simulierten `StartSystem`.
- Benutzer für Tests legt `make_user(app, name, role)` aus `tests/conftest.py` an (Passwort
  `PASSWORD`, liefert ein API-Token). Eine autouse-Fixture senkt die scrypt-Kosten.
- `hold_activities(app)` aus `tests/conftest.py` hält laufende Aktivitäten fest, bis das
  zurückgegebene Event gesetzt ist. Tests, die eine noch laufende Aktivität brauchen, nutzen es;
  ohne es kann die Aktivität mit der falschen Uhr schon fertig sein (wackelige Tests).
- Zeit wird über eine falsche Uhr gesteuert (`FakeClock` in `tests/conftest.py`). Tests, die
  Operationen ausführen, übergeben `sleep` und `clock` an `create_app`.
- Pools bearbeiten, mehrere Hosts anlegen und die Darstellung je Benutzer testet
  `tests/test_settings_pages.py` (Fixtures von `test_web.py`).
- Das Konfigurationsprotokoll testet `tests/test_config_log.py` (Fixtures von `test_mass.py`),
  die Darstellung der Änderungen `frontend/src/lib/changes.test.ts`.
- Das Bündel der OSLO-Operationen testet `tests/test_bundle.py`: Bauen, Signatur, abgelehnte
  Inhalte, die echten Shellskripte (`oslo_update.sh --local`, `oslo_version.sh`, braucht `sh`,
  `openssl`, `tar`, `sha256sum`), API, Download der Hosts und Update gegen den Mock.
- Import und Export testet `tests/test_transfer.py` (Import in ein zweites, leeres OSLO gegen
  dieselbe simulierte Landschaft, `second_oslo`).
- Zertifikate testet `tests/test_certificates.py` mit echten TLS-Servern auf 127.0.0.1 und
  selbst erzeugten Zertifikaten (`self_signed`, `TlsServer`).
- Die neuen API-Teile für die Oberfläche (Cookie, Landscape-Daten, Prozesse, Ereignisse,
  Texte, Header, Filter der Aktivitäten, strukturierte Protokolleinträge) testet
  `tests/test_interface_api.py`, die Übersicht und die Regeln `tests/test_overview.py`;
  `tests/test_web.py` prüft Anmeldung, Sprachen und dass jede Adresse ihre App mit den
  richtigen Startdaten liefert. Das Frontend hat eigene Tests (Vitest, `*.test.ts(x)` in
  `frontend/src`): Filter mit denselben Fällen wie früher auf dem Server, Auswahllogik,
  Aktionsleiste, Zeitplan (`timeline.test.ts`). Ende-zu-Ende-Tests im Browser gibt es noch
  nicht.
- Vorlagen und Einplanungen testet `tests/test_templates.py` (Fixtures von `test_mass.py`),
  die Graph-Logik des Editors `frontend/src/templates/graph.test.ts`.
- Eigene Operationen testet `tests/test_custom.py` mit den Fixtures von `test_mass.py` und der
  simulierten Operation `OSLO_TEST` (`PARAM-SLEEP` Laufzeit, `PARAM-RC` Exit-Code).
- Neue Funktionen brauchen Tests, auch für Fehlerfälle. Verhalten, das der Mock simulieren
  soll, wird zuerst im Mock ergänzt.

## Quellen für die Schnittstellen

Die Nachrichtenformate stammen aus den WSDLs eines Host Agent 7.22 und eines sapstartsrv sowie
aus Beispielausgaben von `saphostctrl`. Die Dateien liegen nicht in diesem Repository, sondern
im privaten Wissens-Repository des Eigentümers (`secondbrain`, Ordner `raw/` und `wiki/`).
Aktuelle WSDLs lassen sich von einem Host abrufen:

- Host Agent: `http://<host>:1128/SAPHostControl/?wsdl`
- sapstartsrv: `http://<host>:5<NR>13/?wsdl`

## Teststand gegen echte Hosts

- Zwei Host Agents ohne SAP-Instanz: Verbindung und Anmeldung mit Basic Auth,
  `GetComputerSystem` (Betriebssystemdaten werden gefunden), `ListInstances` und
  `ListDatabases` mit leeren Listen.
- Ein Host mit ABAP-System und HANA-Datenbank, Discovery nur mit `sapadm`: alle Instanzen
  erkannt; `GetProcessList` und `GetSystemInstanceList` am sapstartsrv funktionieren mit
  `sapadm`; `Database/InstanceName` und `Database/Release` sind gefüllt; SystemDB und Tenant
  erscheinen einzeln; `SAPHostControl-DB-WARNING` kommt vor; HANA hat eine eigene SID.
- `StopSystem` am sapstartsrv mit `sapadm` wird mit „Permission denied“ abgelehnt. Der Mock
  bildet das mit `strict_sapstartsrv_auth` nach. Deshalb laufen Systemoperationen über den
  Host Agent.
- Stopp und Start einer Dialoginstanz über den Host Agent mit `sapadm` funktionieren; das Flag
  `O-INSTANCE` wird akzeptiert, und die Instanz meldet danach alle Prozesse grau bzw. grün.
- Ganze Systeme über den Host Agent funktionieren: ABAP-System (zentrale Dienste und
  Dialoginstanz) nach Startpriorität, HANA-Instanz, und ein vollständiger Neustart mit
  Abhängigkeit vom Datenbanksystem. Der Statuswechsel kann nach der Anforderung einige
  Sekunden auf sich warten lassen.
- Das Systemmodell (Schema 2) funktioniert: Ein System aus zentralen Diensten, Dialoginstanz
  und HANA-Instanz mit eigener SID ließ sich als Ganzes stoppen und starten, einzelne
  Instanzen darin ließen sich neu starten und starten.
- `ExecuteOperation` `versioninfo` funktioniert mit `sapadm` (per `saphostctrl` geprüft); die
  Antwort sind Protokollzeilen mit `kernel release` und `patch number`. Diagnostics Agents
  melden `SMDAGENT`. Zentrale Dienste und Anwendungsserver können auf verschiedenen Hosts
  dieselbe Instanznummer haben.
- Aus dem Tool bestätigt: Die Version des Host Agents wird per SOAP gelesen und richtig
  angezeigt (die Schlüssel der Meldungen sind weiter unbekannt; der Parser ignoriert sie).
  Der Parallelstart von Datenbank und zentralen Diensten funktioniert.
- **Virtuelle Hostnamen:** `StartInstance` nur mit SID und Nummer schlug für eine Instanz mit
  virtuellem Hostnamen mit „SAP Instance not found!“ fehl. Der Host Agent erkennt eine
  Instanz an SID, Nummer und SAPLOCALHOST; das Tool sendet deshalb `mHostname` (Hostname aus
  `ListInstances`), und der Mock verlangt ihn wie der echte Host Agent. Mit `mHostname`
  funktionieren Start, Stopp und Neustart eines über zwei Hosts verteilten Systems.
- **Eigene Operationen** (Testskript mit `Mode: async`, `ResultConverter: hook`):
  `ExecuteOperation` asynchron liefert sofort eine Operation-ID; Argumente kommen als
  `KEY=value`, fehlende fallen weg und folgende rücken auf. `GetOperationResults` während des
  Laufs: Fault 255 „Timeout occurred“ mit den bisherigen Zeilen (zuletzt „saphostcontrol:
  Executing <Description> hook“); `IsOperationFinished` „noch nicht fertig“. Erfolg endet mit
  „… hook successfully executed“; Exit-Code ≠ 0 gibt Fault 127 „Command execution failed.“
  mit „… hook failed (exit code = N)“. `CancelOperation`
  beendet das Skript (Exit-Code 15, Antwort Fault 127); danach `IsOperationFinished` „Failed
  to determine operation status“ und `GetOperationResults` Fault -20 „Operation ID not found“.
- **Rohe Antwort von `GetOperationResults`** (aus dem Tool und per `curl` geprüft): Das
  Antwortelement heißt wie in der WSDL `GetOperationResponse`, nicht
  `GetOperationResultsResponse` (`soapxml.RESPONSE_ELEMENTS`). Jede Zeile kommt als vier
  Meldungen `LogMsg/TimeStamp` (leer), `LogMsg/Severity` (`Info`, `Warning`, `Error`),
  `LogMsg/Source` (Beschreibung der Operation bzw. `saphostcontrol`) und `LogMsg/Text`;
  `hostagent.log_messages` fasst sie zu Zeilen zusammen. `saphostctrl` zeigt dieselben
  Zeilen als „Severity: Source: Text“. Nach der Korrektur läuft eine eigene Host-Operation
  aus dem Tool heraus erfolgreich durch; die Ausgabe des Skripts steht vollständig und in
  der richtigen Reihenfolge im Protokoll. Noch offen aus dem Tool: Fehler mit Exit-Code,
  Abbruch, Operationen auf Instanzen und Systemen.
- **Operationsvorlagen und Einplanen** (2026-11-21): Eine Vorlage mit festen Zielen (System
  stoppen → eigene Operation auf zwei Hosts als Massenoperation → System starten) lief
  erfolgreich, auch als eingeplante Operation; Zeitplan und Protokoll zeigen die Schritte richtig.
- **Instanz-Agent** (2026-11-21, per `saphostctrl` als root, nicht aus dem Tool):
  `UnregisterInstanceService` führt `sapcontrol -function StopService` und `sapstartsrv
  -unreg` aus, `RegisterInstanceService` `sapstartsrv -reg` und `sapcontrol -function
  StartService`; beide antworten synchron mit diesen Zeilen (je „exitcode=0“ und „… successfully
  executed“). Die Operation-ID ist danach nicht mehr bekannt (Fault -20).
- **Instanz-Agent aus dem Tool** (2026-11-21): Registrieren funktioniert per SOAP mit den
  Zugangsdaten des Hosts. Neu registrieren lief bei einer Instanz mit laufenden Prozessen
  trotzdem durch; vermutlich scheiterte die Abfrage von `GetProcessList` und OSLO ging weiter wie
  bei einem nicht antwortenden sapstartsrv. Ausführlicher Test durch den Eigentümer steht aus,
  Korrektur vorgeschlagen (ToDo 11).
- **`DeployConfiguration`** (2026-11-23, per `saphostctrl` als root und per SOAP mit `curl`):
  abgelehnt mit „Remote deployment not permitted“; eine Einstellung dafür war in `host_profile`
  nicht zu finden. Laut WSDL nimmt die Webmethode den Inhalt zeilenweise an
  (`HostAgentConfiguration`: `target`, `name`, `configuration`). Deshalb holen die Hosts das
  Bündel der OSLO-Operationen selbst.
- **HTTPS zum Host Agent** (2026-11-21): OSLO erreicht einen Host Agent über Port 1129 mit
  abgeschalteter Zertifikatsprüfung (selbst signiertes Zertifikat). Mit Zertifikatsprüfung
  (2026-11-22): Das über „Zertifikat abrufen“ übernommene selbst signierte Zertifikat des Host
  Agents wird akzeptiert, die Verbindung geht, wenn „Hostnamen prüfen“ aus ist (Zugriff über
  die IP-Adresse); damit besteht es auch `VERIFY_X509_STRICT`. Die sapstartsrv-Instanzen auf
  Port 5NN14 zeigen andere Zertifikate (selbst signiert bzw. mit unbekanntem Aussteller) und
  wurden abgelehnt; deshalb gilt HTTPS seither nur für den Host Agent. Danach läuft die
  Discovery (Host Agent über HTTPS mit Zertifikatsprüfung, sapstartsrv über HTTP) ohne Warnungen.

## Offene Annahmen, die ein Test mit einer echten Instanz klären muss

1. **Flag `O-INSTANCE`:** Geklärt, ein echter Host Agent akzeptiert es.
2. **Operation-ID:** Geklärt für eigene Operationen: `ExecuteOperation` mit Timeout 0 liefert
   sofort eine Operation-ID, `IsOperationFinished`, `GetOperationResults` und
   `CancelOperation` funktionieren damit (Faults 255, 127, -20 wie im Mock). Start und Stopp
   werten ihre Operation-ID weiterhin nicht aus, sie verfolgen den Status der Prozesse.
3. **Zielzustand:** Geklärt für Dialoginstanz, zentrale Dienste und HANA-Instanz (alle
   Prozesse grün bzw. grau).
4. **Geschützte Methoden am sapstartsrv:** Geklärt: Lesen geht mit `sapadm`, `StopSystem`
   nicht. Ob `<sid>adm` für `StartSystem` reicht, ist ohne Belang, weil das Tool es nicht
   mehr nutzt.
5. **Datenbanken:** Der Schlüssel `Database/Vendor` ist angenommen.
6. **Verschachtelung bei `GetComputerSystem`:** Der Client sucht Klassen in jeder Tiefe. Die
   echte Struktur ist nicht mit der des Mocks verglichen.
7. **HTTPS:** Geklärt für den Host Agent (Port 1129), mit und ohne Zertifikatsprüfung. Offen
   ist HTTPS zum sapstartsrv (ToDo 13).
8. **`GetSystemInstanceList` bei getrennter Datenbank-SID:** Dass die Liste eines
   ABAP-Systems die HANA-Instanz nicht enthält, ist aus den getrennten SIDs abgeleitet, aber
   nicht direkt beobachtet.

Wenn ein Test eine Annahme bestätigt oder widerlegt: Mock, Client und Tests anpassen und den
Abschnitt „Teststand gegen echte Hosts“ hier und im README aktualisieren.

## ToDo-Liste des Eigentümers

Gewünscht (2026-11-20), noch nicht umgesetzt; vor der Umsetzung jeweils einen Vorschlag machen
und freigeben lassen:

1. ~~Mehrere Hosts auf einmal anlegen, Namen durch Komma getrennt.~~ Erledigt 2026-11-22.
2. Zwei-Faktor-Anmeldung mit YubiKey (z. B. WebAuthn/FIDO2).
3. ~~Sprache und Dark Mode als Benutzereinstellung (in „Mein Konto“).~~ Erledigt 2026-11-22.
4. Kernel-Repository (Ablage der Kernel-Versionen für Kernel-Tausch-Skripte).
5. Zertifikatsbasierte Anmeldung am Host Agent (mTLS, Client-Zertifikat statt Passwort).
6. Docker-Container für OSLO.
7. Ansteuerung von außen, z. B. AWS SSM: ein externer Auftrag lässt OSLO ein SAP-System starten.
8. „Erneut ausführen“-Knopf an einer abgebrochenen Aktivität (gleiche Operation, Ziele und Werte;
   gewünscht 2026-11-21).
9. ~~Bereich „Schedules“ für alle geplanten Operationen.~~ Erledigt 2026-11-22 (Operationen → Einplanungen).
10. ~~Konzept für OSLO-eigene Operationen: Dateien in `operations.d` verteilen und prüfen.~~
    Erledigt 2026-11-23 (signiertes Bündel, siehe „OSLO-Operationen“). Offen: Operationen für den
    Neustart des Instanz-Agents (normal und forciert) ins Bündel aufnehmen; Test des Bündels an
    einem echten Host.
11. Prüfung vor dem Neu-Registrieren des Instanz-Agents festlegen (heute: Abbruch, solange ein
    Prozess der Instanz läuft; gewünscht 2026-11-21). Am Host lief Neu registrieren trotz
    laufender Prozesse durch. Vorschlag: nur bei abgelehnter Verbindung weitermachen, sonst
    abbrechen; zusätzlich `ListInstances` mit `S-RUNNING` am Host Agent prüfen.
12. ~~Pools bearbeiten (Name, Beschreibung).~~ Erledigt 2026-11-22.
13. HTTPS zum Instanz-Agent (sapstartsrv, Port 5NN14) als Einstellung je System oder Instanz,
    mit eigener Zertifikatsprüfung (gewünscht 2026-11-22).

## Bekannte Lücken

- nur lokale Benutzer, kein LDAP oder SSO
- Konfigurationsprotokoll ohne Einzelheiten zu Vorlagenschritten und Parametern eigener
  Operationen (nur „geändert“), ohne An- und Abmeldungen
- Migrationen nur vorwärts; zurück geht es über die Sicherungskopie
- Abbrechen von Start und Stopp beendet nur das Warten
- kein Probelauf für Operationsvorlagen
- Werte, nach denen eine Vorlage beim Start fragt, lassen sich nur im Editor der Vorlage
  einplanen, nicht unter Operationen → Einplanungen
- Instanz-Agent neu starten (normal und forciert) fehlt noch (kommt ins Bündel der
  OSLO-Operationen)
- Bündel der OSLO-Operationen nur für UNIX-Hosts
- keine Kernel-Repositories (Ablage der Kernel-Versionen für Kernel-Tausch-Skripte)
- keine Hooks und kein HTTP-Provider für eigene Operationen
- keine eigenen Datenbank-Operationen (`StartDatabase`, `StopDatabase`)
- jede SID nur einmal
- Abhängigkeiten zwischen Systemen werden nicht automatisch erkannt
- eine Instanz gehört zu höchstens einem System; Verschieben geht nur über Entfernen und
  erneutes Zuordnen
- Protokollmeldungen der Aktivitäten sind nur englisch
- kein Verschieben von Instanzen (Adaptive Computing)
- keine Diagramme und Diagnosenachrichten in der Übersicht
- keine Ende-zu-Ende-Tests der Oberfläche im Browser (geprüft wurde die Landscape von Hand
  mit Playwright gegen `oslo-server --mock`)
