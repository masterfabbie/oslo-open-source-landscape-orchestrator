"""Texts of the web interface in English and German."""

from __future__ import annotations

from ..roles import instance_type_key

__all__ = ["instance_type_key"]

LANGUAGES = ("en", "de")
DEFAULT_LANGUAGE = "en"

# key -> (English, German)
TEXTS: dict[str, tuple[str, str]] = {
    "app.title": ("OSLO", "OSLO"),
    "nav.overview": ("Overview", "Übersicht"),
    "nav.landscape": ("Landscape", "Landschaft"),
    "nav.activities": ("Activities", "Aktivitäten"),
    "nav.configuration": ("Configuration", "Konfiguration"),
    "nav.operations": ("Operations", "Operationen"),
    "nav.administration": ("Administration", "Administration"),
    "tab.systems": ("Systems", "Systeme"),
    "tab.hosts": ("Hosts", "Hosts"),
    "tab.activities": ("Activities", "Aktivitäten"),
    "tab.steps": ("Steps", "Schritte"),
    "tab.schedules": ("Schedules", "Einplanungen"),
    "tab.pools": ("Pools", "Pools"),
    "tab.overview": ("Overview", "Übersicht"),
    "tab.custom_operations": ("Custom operations", "Eigene Operationen"),
    "tab.unassigned": ("Unassigned instances", "Nicht zugeordnete Instanzen"),
    "section.navigation": ("Sections", "Bereiche"),
    "action.configure": ("Configure", "Konfigurieren"),
    "action.view": ("Show in landscape", "In der Landschaft anzeigen"),
    "action.save": ("Save", "Speichern"),
    "overview.instances": ("Instances", "Instanzen"),
    "overview.hosts": ("Hosts", "Hosts"),
    "overview.activities_24h": ("Activities (24 h)", "Aktivitäten (24 h)"),
    "overview.none": ("Nothing yet.", "Noch nichts vorhanden."),
    "reach.GREEN": ("reachable", "erreichbar"),
    "reach.RED": ("not reachable", "nicht erreichbar"),
    "reach.UNKNOWN": ("not checked yet", "noch nicht geprüft"),
    "field.pool": ("Pool", "Pool"),
    "field.description": ("Description", "Beschreibung"),
    "pool.all": ("All", "Alle"),
    "pool.none": ("No pool", "Kein Pool"),
    "pool.add": ("Create pool", "Pool anlegen"),
    "pool.delete": ("Delete", "Löschen"),
    "pool.delete_confirm": (
        "Delete this pool? Its systems stay and are no longer in a pool.",
        "Diesen Pool löschen? Seine Systeme bleiben erhalten und gehören dann zu keinem Pool.",
    ),
    "pool.empty": ("No pools yet.", "Noch keine Pools."),
    "pool.title": ("Pool {name}", "Pool {name}"),
    "pool.systems_hint": (
        "Systems are put into a pool on the page of the system.",
        "Systeme ordnest du auf der Seite des Systems einem Pool zu.",
    ),
    "pool.none_defined": ("No pools are defined yet.", "Es sind noch keine Pools angelegt."),
    "pool.explanation": (
        "A pool groups systems that belong together, for example the development, test and "
        "production system of one product. A system belongs to at most one pool.",
        "Ein Pool fasst Systeme zusammen, die zusammengehören, zum Beispiel Entwicklungs-, "
        "Test- und Produktivsystem eines Produkts. Ein System gehört zu höchstens einem Pool.",
    ),
    "config.systems_hint": (
        "A system groups instances that are started and stopped together, for example an "
        "ABAP system with the HANA instance of its database. Its instances may have "
        "different SIDs. Discovery finds instances; you assign them to systems here.",
        "Ein System fasst Instanzen zusammen, die gemeinsam gestartet und gestoppt werden, "
        "zum Beispiel ein ABAP-System mit der HANA-Instanz seiner Datenbank. Seine Instanzen "
        "dürfen verschiedene SIDs haben. Die Discovery findet Instanzen, hier ordnest du sie "
        "Systemen zu.",
    ),
    "config.no_systems": ("No systems yet.", "Noch keine Systeme."),
    "unassigned.title": ("Unassigned instances", "Nicht zugeordnete Instanzen"),
    "unassigned.none": (
        "All known instances belong to a system. New instances appear here after a discovery.",
        "Alle bekannten Instanzen gehören zu einem System. Neue Instanzen erscheinen hier "
        "nach einer Discovery.",
    ),
    "unassigned.select": ("Select", "Auswählen"),
    "unassigned.suggestion": ("Suggestion", "Vorschlag"),
    "unassigned.assign_to": ("Assign to {name}", "{name} zuordnen"),
    "unassigned.label": ("not assigned", "nicht zugeordnet"),
    "system.create": ("Create system", "System anlegen"),
    "system.assign": ("Assign to existing system", "Vorhandenem System zuordnen"),
    "system.create_title": ("Create system", "System anlegen"),
    "system.create_hint": (
        "The name is suggested from the SID of the application instances and can be changed.",
        "Der Name ist aus der SID der Anwendungsinstanzen vorgeschlagen und kann geändert werden.",
    ),
    "system.choose_instances": ("Instances of the system", "Instanzen des Systems"),
    "system.create_none": (
        "There are no unassigned instances. A discovery of a host finds new instances.",
        "Es gibt keine nicht zugeordneten Instanzen. Die Discovery eines Hosts findet neue "
        "Instanzen.",
    ),
    "system.remove_instance": ("Remove", "Entfernen"),
    "system.remove_instance_confirm": (
        "Remove this instance from the system? It stays in the inventory, unassigned.",
        "Diese Instanz aus dem System entfernen? Sie bleibt im Inventar, ohne Zuordnung.",
    ),
    "system.delete": ("Delete system", "System löschen"),
    "system.delete_confirm": (
        "Delete this system? Its instances stay in the inventory, unassigned.",
        "Dieses System löschen? Seine Instanzen bleiben im Inventar, ohne Zuordnung.",
    ),
    "system.general": ("General", "Allgemein"),
    "system.no_instances": ("No instances.", "Keine Instanzen."),
    "system.depends_hint": (
        "Database and central services start first and in parallel, application servers "
        "after both; stops run the other way round. “Depends on” shows the other SIDs an "
        "application server needs. It follows from the instance types and cannot be edited.",
        "Datenbank und zentrale Dienste starten zuerst und parallel, Anwendungsserver nach "
        "beiden; gestoppt wird umgekehrt. „Hängt ab von“ zeigt die anderen SIDs, die ein "
        "Anwendungsserver braucht. Es ergibt sich aus den Instanztypen und lässt sich nicht "
        "bearbeiten.",
    ),
    "field.sid": ("SID", "SID"),
    "field.hostagent": ("Host agent", "Host Agent"),
    "field.tags": ("Tags", "Tags"),
    "tags.hint": (
        "Separate tags with commas. A tag is a key with an optional value, e.g. dev, "
        "internetfacing, sla=1. Keys: lowercase letters, digits, - and _.",
        "Tags durch Kommas trennen. Ein Tag ist ein Schlüssel mit optionalem Wert, z. B. dev, "
        "internetfacing, sla=1. Schlüssel: Kleinbuchstaben, Ziffern, - und _.",
    ),
    "notice.tags_saved": ("Tags saved.", "Tags gespeichert."),
    "error.tag_invalid": (
        "Invalid tag: {tag}. Keys may contain lowercase letters, digits, - and _; values "
        "letters, digits, ., - and _.",
        "Ungültiges Tag: {tag}. Schlüssel dürfen Kleinbuchstaben, Ziffern, - und _ enthalten, "
        "Werte Buchstaben, Ziffern, ., - und _.",
    ),
    "error.tag_duplicate": (
        "The tag key {tag} is given twice.",
        "Der Tag-Schlüssel {tag} ist doppelt angegeben.",
    ),
    "error.tag_too_many": ("Too many tags.{tag}", "Zu viele Tags.{tag}"),
    "refresh.button": ("Refresh status", "Status aktualisieren"),
    "refresh.hint": (
        "Read the status of all instances of this system once",
        "Status aller Instanzen dieses Systems einmal neu abfragen",
    ),
    "notice.status_refreshed": ("Status refreshed.", "Status aktualisiert."),
    "filter.name": ("Name", "Name"),
    "filter.status": ("Status", "Status"),
    "filter.pool": ("Pool", "Pool"),
    "filter.host": ("Host", "Host"),
    "filter.type": ("Instance type", "Instanztyp"),
    "filter.tag": ("Tags", "Tags"),
    "filter.hosttag": ("Host tags", "Host-Tags"),
    "filter.reach": ("Reachable", "Erreichbar"),
    "filter.os": ("Operating system", "Betriebssystem"),
    "filter.agent": ("Host agent", "Host Agent"),
    "filter.any": ("Any", "Alle"),
    "filter.selected": ("selected", "ausgewählt"),
    "filter.no_values": ("No values yet", "Noch keine Werte"),
    "filter.text_hint": ("contains …", "enthält …"),
    "filter.apply": ("Apply filters", "Filter anwenden"),
    "filter.reset": ("Reset", "Zurücksetzen"),
    "filter.customize": ("Customize filters", "Filter anpassen"),
    "filter.customize_hint": (
        "The choice is stored in this browser. Filters with a value are always shown.",
        "Die Auswahl wird in diesem Browser gespeichert. Filter mit einem Wert werden immer "
        "angezeigt.",
    ),
    "filter.no_match": ("Nothing matches the filters.", "Nichts passt zu den Filtern."),
    "landscape.counts": (
        "Systems: {systems}, instances: {instances}",
        "Systeme: {systems}, Instanzen: {instances}",
    ),
    "landscape.host_count": ("Hosts: {hosts}", "Hosts: {hosts}"),
    "agents.group": ("Diagnostics agents", "Diagnostics-Agents"),
    "agents.short": ("agents", "Agents"),
    "agents.hint": (
        "Diagnostics agents belong to the system but are not started or stopped with it. "
        "They can be operated one by one.",
        "Diagnostics-Agents gehören zum System, werden aber nicht mit ihm gestartet oder "
        "gestoppt. Sie lassen sich einzeln bedienen.",
    ),
    "itype.agent": ("Diagnostics agent", "Diagnostics-Agent"),
    "sid.credentials_title": ("Credentials per SID", "Zugangsdaten je SID"),
    "notice.system_created": ("System {name} created.", "System {name} angelegt."),
    "notice.system_saved": ("System saved.", "System gespeichert."),
    "notice.system_deleted": ("System deleted.", "System gelöscht."),
    "notice.instances_assigned": ("Instances assigned.", "Instanzen zugeordnet."),
    "notice.instance_removed": ("Instance removed.", "Instanz entfernt."),
    "error.system_name_missing": ("The system needs a name.", "Das System braucht einen Namen."),
    "error.system_name_too_long": (
        "The name may have at most 64 characters.",
        "Der Name darf höchstens 64 Zeichen haben.",
    ),
    "error.system_name_taken": (
        "A system with this name already exists.",
        "Ein System mit diesem Namen existiert bereits.",
    ),
    "error.system_no_instances": (
        "Select at least one instance.",
        "Wähle mindestens eine Instanz aus.",
    ),
    "error.system_unknown_instance": ("Unknown instance.", "Unbekannte Instanz."),
    "error.system_unknown_system": ("Unknown system.", "Unbekanntes System."),
    "error.system_assigned": (
        "An instance is already assigned to a system.",
        "Eine Instanz ist bereits einem System zugeordnet.",
    ),
    "error.system_busy": (
        "An activity is still running for this system. Try again later.",
        "Für dieses System läuft noch eine Aktivität. Versuche es später erneut.",
    ),
    "error.not_assigned": (
        "Only instances that belong to a system can be started or stopped.",
        "Nur Instanzen, die zu einem System gehören, lassen sich starten oder stoppen.",
    ),
    "credentials.host_used": ("those of the host", "die des Hosts"),
    "tab.changes": ("Configuration", "Konfiguration"),
    "cert.details": ("Details", "Details"),
    "cert.hide_details": ("Hide details", "Details ausblenden"),
    "cfg.object": ("Object", "Objekt"),
    "cfg.action": ("Action", "Aktion"),
    "cfg.changes": ("Changes", "Änderungen"),
    "cfg.changed": ("changed", "geändert"),
    "cfg.yes": ("yes", "ja"),
    "cfg.no": ("no", "nein"),
    "cfg.empty": ("No changes recorded.", "Keine Änderungen protokolliert."),
    "cfg.none": ("No changes recorded yet.", "Noch keine Änderungen protokolliert."),
    "cfg.recent": ("Recent changes", "Letzte Änderungen"),
    "cfg.all_of_object": ("All changes of this object", "Alle Änderungen dieses Objekts"),
    "cfg.only": ("Only the changes of one object.", "Nur die Änderungen eines Objekts."),
    "cfg.all": ("All changes", "Alle Änderungen"),
    "cfg.period": ("Period", "Zeitraum"),
    "cfg.days": ("last {days} days", "letzte {days} Tage"),
    "cfg.day": ("last 24 hours", "letzte 24 Stunden"),
    "cfg.hint": (
        "Changes of the configuration in a user's name. Passwords are never shown, only that "
        "they changed. Status and results of discoveries are not configuration.",
        "Änderungen an der Konfiguration im Namen eines Benutzers. Passwörter erscheinen nie, "
        "nur dass sie geändert wurden. Status und Ergebnisse von Discoveries zählen nicht dazu.",
    ),
    "cfg.retention": ("Keep the configuration log", "Konfigurationsprotokoll aufbewahren"),
    "cfg.retention_days": ("Days", "Tage"),
    "cfg.retention_hint": (
        "Older entries are deleted once an hour.",
        "Ältere Einträge werden stündlich gelöscht.",
    ),
    "cfg.action.created": ("created", "angelegt"),
    "cfg.action.updated": ("changed", "geändert"),
    "cfg.action.deleted": ("deleted", "gelöscht"),
    "cfg.action.imported": ("imported", "importiert"),
    "cfg.count.created": ("created", "angelegt"),
    "cfg.count.updated": ("updated", "aktualisiert"),
    "cfg.count.skipped": ("skipped", "übersprungen"),
    "cfg.count.failed": ("failed", "fehlgeschlagen"),
    "cfg.count.warning": ("warnings", "Warnungen"),
    "cfg.type.host": ("Host", "Host"),
    "cfg.type.sid": ("SID", "SID"),
    "cfg.type.system": ("System", "System"),
    "cfg.type.pool": ("Pool", "Pool"),
    "cfg.type.custom_operation": ("Custom operation", "Eigene Operation"),
    "cfg.type.template": ("Operation template", "Operationsvorlage"),
    "cfg.type.schedule": ("Schedule", "Einplanung"),
    "cfg.type.certificate": ("Certificate", "Zertifikat"),
    "cfg.type.attention_rules": ("Needs attention", "Braucht Aufmerksamkeit"),
    "cfg.type.platform": ("Platform", "Plattform"),
    "cfg.type.user": ("User", "Benutzer"),
    "cfg.type.import": ("Import", "Import"),
    "cfg.field.name": ("Name", "Name"),
    "cfg.field.address": ("Address", "Adresse"),
    "cfg.field.hostagent_port": ("Host agent port", "Port des Host Agents"),
    "cfg.field.https": ("HTTPS", "HTTPS"),
    "cfg.field.verify_tls": ("Verify certificate", "Zertifikat prüfen"),
    "cfg.field.verify_hostname": ("Verify host name", "Hostnamen prüfen"),
    "cfg.field.sapcontrol_port_offset": ("Port offset", "Port-Verschiebung"),
    "cfg.field.username": ("User", "Benutzer"),
    "cfg.field.password_encrypted": ("Password", "Passwort"),
    "cfg.field.password_hash": ("Password", "Passwort"),
    "cfg.field.description": ("Description", "Beschreibung"),
    "cfg.field.stage": ("Stage", "Stufe"),
    "cfg.field.tags": ("Tags", "Tags"),
    "cfg.field.instances": ("Instances", "Instanzen"),
    "cfg.field.depends_on": ("Depends on", "Hängt ab von"),
    "cfg.field.pool": ("Pool", "Pool"),
    "cfg.field.systems": ("Systems", "Systeme"),
    "cfg.field.key": ("Key", "Schlüssel"),
    "cfg.field.agent_operation": ("Host agent operation", "Operation am Host Agent"),
    "cfg.field.target": ("Target", "Ziel"),
    "cfg.field.instance_types": ("Instance types", "Instanztypen"),
    "cfg.field.ordering": ("Order", "Reihenfolge"),
    "cfg.field.role": ("Role", "Rolle"),
    "cfg.field.locks": ("Locks", "Sperrt"),
    "cfg.field.standalone": ("Standalone", "Einzeln ausführbar"),
    "cfg.field.timeout_seconds": ("Time limit (s)", "Zeitlimit (s)"),
    "cfg.field.parameters": ("Parameters", "Parameter"),
    "cfg.field.steps": ("Steps", "Schritte"),
    "cfg.field.operation": ("Operation", "Operation"),
    "cfg.field.target_type": ("Target type", "Zieltyp"),
    "cfg.field.target_ids": ("Targets", "Ziele"),
    "cfg.field.recurrence": ("Recurrence", "Wiederholung"),
    "cfg.field.run_at": ("Run at", "Ausführen am"),
    "cfg.field.time_of_day": ("Time of day", "Uhrzeit"),
    "cfg.field.weekdays": ("Weekdays", "Wochentage"),
    "cfg.field.interval_minutes": ("Interval (min)", "Intervall (min)"),
    "cfg.field.enabled": ("Enabled", "Aktiv"),
    "cfg.field.display_name": ("Display name", "Anzeigename"),
    "cfg.field.active": ("Active", "Aktiv"),
    "cfg.field.must_change_password": ("Must change password", "Muss Passwort ändern"),
    "cfg.field.value": ("Value", "Wert"),
    "steps.empty": ("No steps yet.", "Noch keine Schritte."),
    "steps.only": ("Only the steps of {number}.", "Nur die Schritte von {number}."),
    "steps.all": ("All steps", "Alle Schritte"),
    "steps.of_activity": ("Show all steps in the list", "Alle Schritte in der Liste zeigen"),
    "step.title": ("Step", "Schritt"),
    "field.id": ("ID", "ID"),
    "field.duration": ("Duration", "Dauer"),
    "field.activity_number": ("Activity", "Aktivität"),
    "admin.planned": (
        "Platform settings will follow. Current configuration:",
        "Plattform-Einstellungen folgen. Aktuelle Konfiguration:",
    ),
    "admin.version": ("Version", "Version"),
    "admin.database": ("Database", "Datenbank"),
    "admin.session": ("Sign-in valid for", "Anmeldung gültig für"),
    "admin.session_hours": ("{hours} hours", "{hours} Stunden"),
    "notice.pool_created": ("Pool created.", "Pool angelegt."),
    "notice.pool_deleted": ("Pool deleted.", "Pool gelöscht."),
    "notice.pool_saved": ("Pool saved.", "Pool gespeichert."),
    "error.pool_exists": (
        "A pool with this name already exists.",
        "Ein Pool mit diesem Namen existiert bereits.",
    ),
    "nav.logout": ("Sign out", "Abmelden"),
    "login.title": ("Sign in", "Anmelden"),
    "login.invalid": (
        "Sign-in failed. Check user and password; after several failed attempts the account "
        "is locked for a minute.",
        "Anmeldung fehlgeschlagen. Prüfe Benutzer und Passwort; nach mehreren Fehlversuchen "
        "ist das Konto eine Minute gesperrt.",
    ),
    "setup.title": ("Set up", "Einrichtung"),
    "setup.hint": (
        "No user exists yet. Create the first administrator. The setup code was printed in "
        "the console when the server started.",
        "Es gibt noch keinen Benutzer. Lege den ersten Administrator an. Der "
        "Einrichtungscode steht in der Konsole, in der der Server gestartet wurde.",
    ),
    "setup.code": ("Setup code", "Einrichtungscode"),
    "setup.submit": ("Create administrator", "Administrator anlegen"),
    "notice.setup_done": ("Administrator created. Welcome!", "Administrator angelegt. Willkommen!"),
    "error.setup_code": (
        "The setup code is not valid. It was printed when the server started.",
        "Der Einrichtungscode ist ungültig. Er wurde beim Start des Servers ausgegeben.",
    ),
    "field.display_name": ("Display name", "Anzeigename"),
    "field.password_repeat": ("Repeat password", "Passwort wiederholen"),
    "field.role": ("Role", "Rolle"),
    "field.requested_by": ("Requested by", "Angefordert von"),
    "role.viewer": ("Viewer", "Viewer"),
    "role.operator": ("Operator", "Operator"),
    "role.configurator": ("Configurator", "Configurator"),
    "role.admin": ("Admin", "Admin"),
    "tab.general": ("General", "Allgemein"),
    "tab.users": ("Users", "Benutzer"),
    "users.roles_hint": (
        "Viewer: read and refresh status. Operator: also start, stop and restart. "
        "Configurator: also change the configuration. Admin: also users and settings.",
        "Viewer: lesen und Status aktualisieren. Operator: zusätzlich starten, stoppen und "
        "neu starten. Configurator: zusätzlich die Konfiguration ändern. Admin: zusätzlich "
        "Benutzer und Einstellungen.",
    ),
    "users.add": ("Add user", "Benutzer anlegen"),
    "users.user": ("User", "Benutzer"),
    "users.active": ("active", "aktiv"),
    "users.inactive": ("inactive", "inaktiv"),
    "users.must_change": ("must change password", "muss Passwort ändern"),
    "users.last_login": ("Last sign-in", "Letzte Anmeldung"),
    "users.start_password": ("Start password", "Startpasswort"),
    "users.start_password_hint": (
        "At least 12 characters. The user must choose a new password at the next sign-in.",
        "Mindestens 12 Zeichen. Der Benutzer muss bei der nächsten Anmeldung ein neues "
        "Passwort wählen.",
    ),
    "users.reset_password": ("Reset password", "Passwort zurücksetzen"),
    "users.save_hint": (
        "Changing the role or deactivating signs the user out.",
        "Eine Änderung der Rolle oder das Deaktivieren meldet den Benutzer ab.",
    ),
    "notice.user_created": ("User {name} created.", "Benutzer {name} angelegt."),
    "notice.user_saved": ("User saved.", "Benutzer gespeichert."),
    "notice.password_reset": (
        "Start password set. The user must change it at the next sign-in.",
        "Startpasswort gesetzt. Der Benutzer muss es bei der nächsten Anmeldung ändern.",
    ),
    "error.username_invalid": (
        "User names consist of lowercase letters, digits, '.', '-' and '_'.",
        "Benutzernamen bestehen aus Kleinbuchstaben, Ziffern, '.', '-' und '_'.",
    ),
    "error.username_taken": (
        "A user with this name already exists.",
        "Ein Benutzer mit diesem Namen existiert bereits.",
    ),
    "error.password_short": (
        "The password needs at least 12 characters.",
        "Das Passwort braucht mindestens 12 Zeichen.",
    ),
    "error.password_mismatch": (
        "The passwords do not match.",
        "Die Passwörter stimmen nicht überein.",
    ),
    "error.password_wrong": ("The current password is wrong.", "Das aktuelle Passwort ist falsch."),
    "error.password_same": (
        "Choose a password different from the current one.",
        "Wähle ein anderes Passwort als das aktuelle.",
    ),
    "error.last_admin": (
        "The last active admin must stay an active admin.",
        "Der letzte aktive Admin muss aktiver Admin bleiben.",
    ),
    "account.title": ("My account", "Mein Konto"),
    "account.display": ("Display", "Darstellung"),
    "account.display_hint": (
        "Applies to you on every device. “Like the browser” uses the language of the browser.",
        "Gilt für dich auf jedem Gerät. „Wie im Browser“ nimmt die Sprache des Browsers.",
    ),
    "account.language": ("Language", "Sprache"),
    "account.language_auto": ("Like the browser", "Wie im Browser"),
    "account.theme": ("Color scheme", "Farbschema"),
    "account.time": ("Times", "Zeitangaben"),
    "time.browser": ("Local time of the browser", "Ortszeit des Browsers"),
    "time.utc": ("UTC", "UTC"),
    "time.hint": (
        "OSLO stores and computes all times in UTC; this only changes how they are shown and "
        "entered. Daily schedules keep the time zone of the schedules.",
        "OSLO speichert und rechnet alle Zeiten in UTC; das ändert nur, wie sie angezeigt und "
        "eingegeben werden. Tägliche Einplanungen bleiben in der Zeitzone der Einplanungen.",
    ),
    "time.input_utc": ("Date and time (UTC)", "Datum und Uhrzeit (UTC)"),
    "theme.system": ("Like the operating system", "Wie im Betriebssystem"),
    "theme.light": ("Light", "Hell"),
    "theme.dark": ("Dark", "Dunkel"),
    "account.password": ("Change password", "Passwort ändern"),
    "account.current_password": ("Current password", "Aktuelles Passwort"),
    "account.new_password": ("New password", "Neues Passwort"),
    "account.password_hint": (
        "At least 12 characters. Changing it signs out your other browser sessions.",
        "Mindestens 12 Zeichen. Die Änderung meldet deine anderen Browser-Sitzungen ab.",
    ),
    "notice.password_changed": ("Password changed.", "Passwort geändert."),
    "notice.password_change_required": (
        "Please choose a new password first.",
        "Bitte wähle zuerst ein neues Passwort.",
    ),
    "token.title": ("API tokens", "API-Tokens"),
    "token.hint": (
        "Personal tokens for the REST API (header Authorization: Bearer <token>). They have "
        "the rights of your role. Only a hash is stored.",
        "Persönliche Tokens für die REST-API (Header Authorization: Bearer <token>). Sie haben "
        "die Rechte deiner Rolle. Gespeichert wird nur ein Hash.",
    ),
    "token.created": (
        "New token. Copy it now; it is not shown again:",
        "Neues Token. Kopiere es jetzt, es wird nicht wieder angezeigt:",
    ),
    "token.prefix": ("Begins with", "Beginnt mit"),
    "token.created_at": ("Created", "Angelegt"),
    "token.expires": ("Expires", "Läuft ab"),
    "token.expires_days": ("Valid for days", "Gültig für Tage"),
    "token.last_used": ("Last used", "Zuletzt benutzt"),
    "token.never": ("never", "nie"),
    "token.name_hint": ("e.g. monitoring script", "z. B. Monitoring-Skript"),
    "token.create": ("Create token", "Token anlegen"),
    "token.delete": ("Delete", "Löschen"),
    "token.delete_confirm": (
        "Delete this token? Programs using it lose access.",
        "Dieses Token löschen? Programme, die es nutzen, verlieren den Zugriff.",
    ),
    "notice.token_deleted": ("Token deleted.", "Token gelöscht."),
    "error.token_name": ("The token needs a name.", "Das Token braucht einen Namen."),
    "overview.systems": ("Systems", "Systeme"),
    "overview.databases": ("Databases", "Datenbanken"),
    "overview.empty": (
        "No systems yet. Add a host, run a discovery and create systems from its instances.",
        "Noch keine Systeme. Lege einen Host an, starte eine Discovery und lege aus den "
        "Instanzen Systeme an.",
    ),
    "overview.status_note": (
        "Status as of the last discovery or operation.",
        "Status zum Zeitpunkt der letzten Discovery oder Operation.",
    ),
    "overview.running": ("Activity running", "Aktivität läuft"),
    "hosts.add": ("Create host", "Host anlegen"),
    "hosts.empty": ("No hosts yet.", "Noch keine Hosts."),
    "hosts.never": ("never", "nie"),
    "host.discover": ("Run discovery", "Discovery starten"),
    "host.delete": ("Delete host", "Host löschen"),
    "host.delete_confirm": (
        "Delete this host with its instances and databases?",
        "Diesen Host samt Instanzen und Datenbanken löschen?",
    ),
    "host.connection": ("Connection", "Verbindung"),
    "host.edit_connection": ("Change connection", "Verbindung ändern"),
    "host.connection_hint": (
        "The new data is not checked when saving. Run a discovery afterwards to check it.",
        "Die neuen Daten werden beim Speichern nicht geprüft. Starte danach eine Discovery, "
        "um sie zu prüfen.",
    ),
    "notice.connection_saved": (
        "Connection saved. Run a discovery to check it.",
        "Verbindung gespeichert. Starte eine Discovery, um sie zu prüfen.",
    ),
    "error.host_busy": (
        "An activity is still running on this host. Try again later.",
        "Auf diesem Host läuft noch eine Aktivität. Versuche es später erneut.",
    ),
    "host.system_info": ("System information", "Systeminformationen"),
    "host.no_instances": (
        "No instances known. Run a discovery.",
        "Keine Instanzen bekannt. Starte eine Discovery.",
    ),
    "host.no_databases": ("No databases known.", "Keine Datenbanken bekannt."),
    "host.certificate": ("Certificate", "Zertifikat"),
    "host.certificate_hint": (
        "Shows the certificate the host agent presents on its HTTPS port, without checking it. "
        "Compare the fingerprint with the one on the host before you trust it.",
        "Zeigt das Zertifikat, das der Host Agent an seinem HTTPS-Port vorzeigt, ohne es zu "
        "prüfen. Vergleiche den Fingerabdruck mit dem auf dem Host, bevor du ihm vertraust.",
    ),
    "host.fetch_certificate": ("Read certificate", "Zertifikat abrufen"),
    "host.certificate_trusted": (
        "Trusted (Administration → Certificates).",
        "Vertrauenswürdig (Administration → Zertifikate).",
    ),
    "host.certificate_untrusted": (
        "Not trusted yet. Without trust, “Verify certificate” fails unless the operating "
        "system trusts its issuer.",
        "Noch nicht vertrauenswürdig. Ohne Vertrauen schlägt „Zertifikat prüfen“ fehl, außer "
        "das Betriebssystem vertraut seinem Aussteller.",
    ),
    "host.trust": ("Trust this certificate", "Diesem Zertifikat vertrauen"),
    "host.trust_admin_only": (
        "Only admins can trust certificates.",
        "Nur Admins können Zertifikaten vertrauen.",
    ),
    "host.https_off": (
        "This host is reached over HTTP. Switch on HTTPS to use a certificate.",
        "Dieser Host wird über HTTP erreicht. Schalte HTTPS ein, um ein Zertifikat zu nutzen.",
    ),
    "host.verify_hint": (
        "Only for the host agent (port 1129); instance agents are reached over HTTP. "
        "“Verify certificate”: the host agent must show a certificate the operating system or "
        "Administration → Certificates trusts. “Check host name”: the name in the certificate "
        "must also match the address.",
        "Nur für den Host Agent (Port 1129); Instanz-Agents werden über HTTP angesprochen. "
        "„Zertifikat prüfen“: Der Host Agent muss ein Zertifikat zeigen, dem das Betriebssystem "
        "oder Administration → Zertifikate vertraut. „Hostnamen prüfen“: Zusätzlich muss der "
        "Name im Zertifikat zur Adresse passen.",
    ),
    "field.verify_hostname": ("Check host name", "Hostnamen prüfen"),
    "field.subject": ("Subject", "Inhaber"),
    "field.issuer": ("Issuer", "Aussteller"),
    "field.valid_from": ("Valid from", "Gültig ab"),
    "field.valid_until": ("Valid until", "Gültig bis"),
    "field.fingerprint": ("Fingerprint (SHA-256)", "Fingerabdruck (SHA-256)"),
    "tab.certificates": ("Certificates", "Zertifikate"),
    "tab.transfer": ("Import/Export", "Import/Export"),
    "tab.bundle": ("OSLO operations", "OSLO-Operationen"),
    "tab.tls": ("HTTPS", "HTTPS"),
    "cat.instance_agent": ("Instance agent", "Instanz-Agent"),
    "cat.oslo": ("OSLO operations", "OSLO-Operationen"),
    "cat.more": ("More", "Weitere"),
    "op.reason.not_mass": (
        "Only for one target at a time",
        "Nur für ein Ziel auf einmal",
    ),
    "op.reason.instance_type": (
        "Not for this instance type",
        "Nicht für diesen Instanztyp",
    ),
    "op.reason.bundle": (
        "OSLO operations on the host are not current",
        "OSLO-Operationen auf dem Host nicht aktuell",
    ),
    "field.category": ("Category", "Kategorie"),
    "category.hint": (
        "Menu in the landscape, at most two levels, e.g. Automation/Kernel. Empty: More.",
        "Menü in der Landschaft, höchstens zwei Ebenen, z. B. Automation/Kernel. Leer: Weitere.",
    ),
    "tls.intro": (
        "The certificate OSLO serves HTTPS with. The private key is created on this server and "
        "never leaves it: create a self-signed certificate, or a request for your own CA and "
        "upload the certificate it signs. Then restart OSLO with --tls (or OSLO_TLS=1).",
        "Das Zertifikat, mit dem OSLO HTTPS anbietet. Der private Schlüssel entsteht auf diesem "
        "Server und verlässt ihn nie: ein selbst signiertes Zertifikat erzeugen, oder eine "
        "Anforderung für die eigene CA und das von ihr signierte Zertifikat hochladen. Danach "
        "OSLO mit --tls (oder OSLO_TLS=1) neu starten.",
    ),
    "tls.status": ("State", "Stand"),
    "tls.connection": ("This connection", "Diese Verbindung"),
    "tls.certificate": ("Stored certificate", "Gespeichertes Zertifikat"),
    "tls.none": ("none", "keines"),
    "tls.restart": (
        "OSLO serves plain HTTP. Restart it with:",
        "OSLO läuft noch mit HTTP. Neu starten mit:",
    ),
    "tls.download_cert": ("Download certificate", "Zertifikat herunterladen"),
    "tls.ca_hint": (
        "Self-signed: put it on the hosts as CA file (OSLO operations).",
        "Selbst signiert: auf den Hosts als CA-Datei hinterlegen (OSLO-Operationen).",
    ),
    "tls.self_signed": ("Self-signed certificate", "Selbst signiertes Zertifikat"),
    "tls.self_signed_hint": (
        "Quick to set up; browsers and hosts must trust it explicitly.",
        "Schnell eingerichtet; Browser und Hosts müssen ihm ausdrücklich vertrauen.",
    ),
    "tls.names": (
        "Host names of OSLO (comma separated)",
        "Hostnamen von OSLO (durch Kommas getrennt)",
    ),
    "tls.ips": ("IP addresses (comma separated)", "IP-Adressen (durch Kommas getrennt)"),
    "tls.days": ("Valid for days", "Gültig für Tage"),
    "tls.create": ("Create certificate", "Zertifikat erzeugen"),
    "tls.replace_confirm": (
        "Replace the stored certificate? The new one is used after the next restart.",
        "Das gespeicherte Zertifikat ersetzen? Das neue gilt nach dem nächsten Neustart.",
    ),
    "tls.request": ("Certificate of your own CA", "Zertifikat der eigenen CA"),
    "tls.request_hint": (
        "Creates a key and a certificate signing request (CSR) for your CA.",
        "Erzeugt einen Schlüssel und eine Zertifikatsanforderung (CSR) für eure CA.",
    ),
    "tls.create_request": ("Create request", "Anforderung erzeugen"),
    "tls.request_open": (
        "Have this request signed by your CA, then upload the certificate with its "
        "intermediate certificates. The current certificate stays until then.",
        "Diese Anforderung von eurer CA signieren lassen, dann das Zertifikat samt "
        "Zwischenzertifikaten hochladen. Bis dahin gilt das bisherige Zertifikat.",
    ),
    "tls.download_csr": ("Download request", "Anforderung herunterladen"),
    "tls.signed": ("Signed certificate (PEM)", "Signiertes Zertifikat (PEM)"),
    "tls.signed_file": ("or as a file", "oder als Datei"),
    "tls.upload_signed": ("Use certificate", "Zertifikat übernehmen"),
    "tls.cancel_request": ("Discard request", "Anforderung verwerfen"),
    "bundle.intro": (
        "OSLO installs a few operations of its own into operations.d of the host agents, as a "
        "signed bundle. The first installation is done once per host with the bootstrap "
        "package; later versions are uploaded here and installed from OSLO: the hosts "
        "download them over HTTPS and check the signature themselves.",
        "OSLO installiert einige eigene Operationen in operations.d der Host Agents, als "
        "signiertes Bündel. Die Erstinstallation geschieht einmal je Host mit dem "
        "Erstinstallationspaket; neue Versionen werden hier hochgeladen und aus OSLO heraus "
        "installiert: Die Hosts laden sie per HTTPS und prüfen die Signatur selbst.",
    ),
    "bundle.settings": ("Signature and address", "Signatur und Adresse"),
    "bundle.settings_hint": (
        "Only bundles signed with the private key of this public key are accepted, here and "
        "on the hosts. The private key stays with whoever builds bundles (oslo-bundle).",
        "Angenommen werden nur Bündel, die mit dem privaten Schlüssel zu diesem öffentlichen "
        "Schlüssel signiert sind, hier und auf den Hosts. Der private Schlüssel bleibt bei "
        "dem, der Bündel baut (oslo-bundle).",
    ),
    "bundle.public_key": ("Public key (Ed25519, PEM)", "Öffentlicher Schlüssel (Ed25519, PEM)"),
    "bundle.base_url": (
        "Address of OSLO for the hosts (https://…)",
        "Adresse von OSLO für die Hosts (https://…)",
    ),
    "bundle.ca_path": (
        "CA file on the hosts (optional, for a certificate not in their store)",
        "CA-Datei auf den Hosts (optional, für ein Zertifikat außerhalb ihres Speichers)",
    ),
    "bundle.upload": ("Upload a bundle", "Bündel hochladen"),
    "bundle.upload_hint": (
        "A .oslobundle file. It becomes the version the hosts install.",
        "Eine .oslobundle-Datei. Sie wird die Version, die die Hosts installieren.",
    ),
    "bundle.file": ("Bundle file", "Bündeldatei"),
    "bundle.key_first": (
        "Enter the public key first.",
        "Zuerst den öffentlichen Schlüssel eintragen.",
    ),
    "bundle.upload_button": ("Upload", "Hochladen"),
    "bundle.uploaded": ("Bundle uploaded and active.", "Bündel hochgeladen und aktiv."),
    "bundle.bootstrap": ("First installation", "Erstinstallation"),
    "bundle.bootstrap_hint": (
        "Once per host, as root: copy the package to the host and run install.sh, by hand or "
        "with your own tools (e.g. Ansible). It also installs the key and the address of OSLO.",
        "Einmal je Host, als root: Paket auf den Host kopieren und install.sh ausführen, von "
        "Hand oder mit eigenen Werkzeugen (z. B. Ansible). Es installiert auch den Schlüssel "
        "und die Adresse von OSLO.",
    ),
    "bundle.bootstrap_missing": (
        "Needs the public key, the address of OSLO and an active bundle.",
        "Braucht den öffentlichen Schlüssel, die Adresse von OSLO und ein aktives Bündel.",
    ),
    "bundle.bootstrap_download": ("Download package", "Paket herunterladen"),
    "bundle.list": ("Bundles", "Bündel"),
    "bundle.none": ("No bundle uploaded yet.", "Noch kein Bündel hochgeladen."),
    "bundle.version": ("Version", "Version"),
    "bundle.active": ("active", "aktiv"),
    "bundle.files": ("{count} files", "{count} Dateien"),
    "bundle.activate": ("Make active", "Aktiv setzen"),
    "bundle.operations": ("Operations of the bundle", "Operationen des Bündels"),
    "bundle.operations_hint": (
        "From oslo/operations.json of the active bundle. They run only on hosts where this "
        "version is installed. Hidden ones stay usable as steps of templates; the role can "
        "only be raised.",
        "Aus oslo/operations.json des aktiven Bündels. Sie laufen nur auf Hosts, auf denen "
        "diese Version installiert ist. Ausgeblendete bleiben als Schritte von Vorlagen "
        "nutzbar; die Rolle lässt sich nur erhöhen.",
    ),
    "bundle.operations_none": (
        "The active bundle brings no operations.",
        "Das aktive Bündel bringt keine Operationen mit.",
    ),
    "bundle.in_menus": ("In menus", "In Menüs"),
    "bundle.hosts": ("Hosts", "Hosts"),
    "bundle.hosts_hint": (
        "Read with oslo_version at every discovery.",
        "Gelesen mit oslo_version bei jeder Discovery.",
    ),
    "bundle.update_all": ("Update {count} hosts", "{count} Hosts aktualisieren"),
    "bundle.update_started": ("Activity {number} started", "Aktivität {number} gestartet"),
    "bundle.state": ("State", "Zustand"),
    "bundle.checked": ("Checked", "Geprüft"),
    "bundle.state.unknown": ("not checked", "nicht geprüft"),
    "bundle.state.missing": ("not installed", "nicht installiert"),
    "bundle.state.modified": ("changed", "verändert"),
    "bundle.state.outdated": ("outdated", "veraltet"),
    "bundle.state.current": ("current", "aktuell"),
    "bundle.state.installed": ("installed", "installiert"),
    "bundle.on_host": ("OSLO operations", "OSLO-Operationen"),
    "transfer.part.hosts": (
        "Hosts (connection, tags, credentials)",
        "Hosts (Verbindung, Tags, Zugangsdaten)",
    ),
    "transfer.part.sids": ("Credentials per SID", "Zugangsdaten je SID"),
    "transfer.part.pools": ("Pools", "Pools"),
    "transfer.part.systems": (
        "Systems (stage, pool, tags, dependencies, instances)",
        "Systeme (Stufe, Pool, Tags, Abhängigkeiten, Instanzen)",
    ),
    "transfer.part.custom_operations": ("Custom operations", "Eigene Operationen"),
    "transfer.part.templates": ("Operation templates", "Operationsvorlagen"),
    "transfer.part.schedules": ("Schedules", "Einplanungen"),
    "transfer.part.attention_rules": (
        "Rules of “needs attention”",
        "Regeln für „Braucht Aufmerksamkeit“",
    ),
    "transfer.part.certificates": ("Trusted certificates", "Vertrauenswürdige Zertifikate"),
    "transfer.part.dependencies": ("Dependencies", "Abhängigkeiten"),
    "transfer.part.credentials": ("Credentials", "Zugangsdaten"),
    "transfer.export": ("Export", "Export"),
    "transfer.export_hint": (
        "Downloads the chosen parts as a JSON file. Activities, logs and users are never "
        "part of it.",
        "Lädt die gewählten Teile als JSON-Datei herunter. Aktivitäten, Protokolle und Benutzer "
        "sind nie dabei.",
    ),
    "transfer.with_passwords": (
        "Include the passwords of hosts and SIDs, encrypted with an export password",
        "Passwörter von Hosts und SIDs mitexportieren, verschlüsselt mit einem Export-Passwort",
    ),
    "transfer.password": ("Export password", "Export-Passwort"),
    "transfer.password_repeat": ("Repeat export password", "Export-Passwort wiederholen"),
    "transfer.password_hint": (
        "At least 8 characters. Keep it apart from the file; without it the passwords cannot "
        "be imported.",
        "Mindestens 8 Zeichen. Getrennt von der Datei aufbewahren; ohne es lassen sich die "
        "Passwörter nicht importieren.",
    ),
    "transfer.password_mismatch": (
        "The passwords differ.",
        "Die Passwörter stimmen nicht überein.",
    ),
    "transfer.download": ("Download", "Herunterladen"),
    "transfer.import": ("Import", "Import"),
    "transfer.import_hint": (
        "Nothing is deleted. Instances come from a discovery: run one for new hosts and import "
        "again to assign them to their systems. Schedules run with your rights.",
        "Es wird nichts gelöscht. Instanzen kommen aus einer Discovery: für neue Hosts eine "
        "starten und erneut importieren, um sie ihren Systemen zuzuordnen. Einplanungen laufen "
        "mit deinen Rechten.",
    ),
    "transfer.file": ("Export file (JSON)", "Exportdatei (JSON)"),
    "transfer.file_info": (
        "Exported {date}; parts: {parts}.",
        "Exportiert am {date}; Teile: {parts}.",
    ),
    "transfer.file_passwords": (
        "The file contains encrypted passwords.",
        "Die Datei enthält verschlüsselte Passwörter.",
    ),
    "transfer.bad_file": ("The file is not valid JSON.", "Die Datei ist kein gültiges JSON."),
    "transfer.mode": ("Existing entries", "Vorhandene Einträge"),
    "transfer.mode.add": (
        "leave unchanged, only add new ones",
        "unverändert lassen, nur Neues anlegen",
    ),
    "transfer.mode.update": ("update with the file", "mit der Datei aktualisieren"),
    "transfer.import_password": (
        "Export password (for the passwords)",
        "Export-Passwort (für die Passwörter)",
    ),
    "transfer.preview": ("Preview", "Vorschau"),
    "transfer.apply": ("Import", "Importieren"),
    "transfer.apply_confirm": ("Import the file now?", "Die Datei jetzt importieren?"),
    "transfer.preview_note": (
        "Preview: nothing has been changed yet.",
        "Vorschau: Es wurde noch nichts geändert.",
    ),
    "transfer.applied_note": ("Imported.", "Importiert."),
    "transfer.counts": (
        "{created} new, {updated} changed, {skipped} skipped, {failed} failed",
        "{created} neu, {updated} geändert, {skipped} übersprungen, {failed} fehlgeschlagen",
    ),
    "transfer.part": ("Part", "Teil"),
    "transfer.result": ("Result", "Ergebnis"),
    "transfer.note": ("Note", "Hinweis"),
    "transfer.action.created": ("new", "neu"),
    "transfer.action.updated": ("changed", "geändert"),
    "transfer.action.skipped": ("skipped", "übersprungen"),
    "transfer.action.failed": ("failed", "fehlgeschlagen"),
    "transfer.action.warning": ("note", "Hinweis"),
    "error.transfer_password": ("Wrong export password.", "Falsches Export-Passwort."),
    "error.transfer_format": ("Not an OSLO export.", "Keine Exportdatei von OSLO."),
    "error.transfer_version": (
        "The export is from a newer OSLO.",
        "Der Export stammt von einem neueren OSLO.",
    ),
    "cert.add": ("Add certificate", "Zertifikat hinzufügen"),
    "cert.intro": (
        "OSLO trusts these certificates for HTTPS to hosts, in addition to those of the "
        "operating system. Add the certificate of the issuing CA, or the self-signed "
        "certificate of a host agent. They apply to hosts with “Verify certificate”.",
        "OSLO vertraut diesen Zertifikaten bei HTTPS zu den Hosts, zusätzlich zu denen des "
        "Betriebssystems. Hinterlege das Zertifikat der ausstellenden CA oder das selbst "
        "signierte Zertifikat eines Host Agents. Sie gelten für Hosts mit „Zertifikat prüfen“.",
    ),
    "cert.empty": ("No certificates yet.", "Noch keine Zertifikate."),
    "cert.pem": ("Certificate (PEM)", "Zertifikat (PEM)"),
    "cert.pem_hint": (
        "Paste the text from -----BEGIN CERTIFICATE----- to -----END CERTIFICATE-----, or "
        "choose a file. Never add a private key.",
        "Füge den Text von -----BEGIN CERTIFICATE----- bis -----END CERTIFICATE----- ein oder "
        "wähle eine Datei. Niemals einen privaten Schlüssel hinterlegen.",
    ),
    "cert.file": ("From file", "Aus Datei"),
    "cert.check": ("Check", "Prüfen"),
    "cert.expired": ("expired", "abgelaufen"),
    "cert.self_signed": ("self-signed", "selbst signiert"),
    "cert.delete": ("Remove", "Entfernen"),
    "cert.delete_confirm": (
        "Stop trusting this certificate? Hosts that rely on it fail the check afterwards.",
        "Diesem Zertifikat nicht mehr vertrauen? Hosts, die darauf angewiesen sind, bestehen "
        "die Prüfung danach nicht mehr.",
    ),
    "cert.added_by": ("Added", "Hinzugefügt"),
    "notice.certificate_added": ("Certificate added.", "Zertifikat hinzugefügt."),
    "credentials.title": ("Credentials", "Zugangsdaten"),
    "credentials.save": ("Save credentials", "Zugangsdaten speichern"),
    "credentials.set": ("stored", "hinterlegt"),
    "credentials.missing": ("not set", "nicht gesetzt"),
    "credentials.host_hint": (
        "Used for the host agent, typically sapadm.",
        "Gilt für den Host Agent, typischerweise sapadm.",
    ),
    "credentials.sid_hint": (
        "Optional. Starts and stops run through the host agent with the credentials of the "
        "host, and sapstartsrv is only read. Store credentials for a SID, typically <sid>adm, "
        "only if its sapstartsrv rejects reading with those of the host.",
        "Optional. Start und Stopp laufen über den Host Agent mit den Zugangsdaten des Hosts, "
        "den sapstartsrv liest das Tool nur. Hinterlege Zugangsdaten für eine SID, "
        "typischerweise <sid>adm, nur wenn ihr sapstartsrv das Lesen mit denen des Hosts "
        "ablehnt.",
    ),
    "field.name": ("Name", "Name"),
    "field.address": ("Address", "Adresse"),
    "field.address_hint": (
        "Hostname or IP; defaults to the name",
        "Hostname oder IP; Standard ist der Name",
    ),
    "field.hostagent_port": ("Host agent port", "Host-Agent-Port"),
    "field.port_offset": ("sapstartsrv port offset", "Port-Verschiebung sapstartsrv"),
    "field.port_offset_hint": ("only for test setups", "nur für Testaufbauten"),
    "field.https": ("HTTPS to the host agent", "HTTPS zum Host Agent"),
    "field.verify_tls": ("Verify certificate", "Zertifikat prüfen"),
    "field.username": ("User", "Benutzer"),
    "field.password": ("Password", "Passwort"),
    "field.os": ("Operating system", "Betriebssystem"),
    "field.cpus": ("CPUs", "CPUs"),
    "field.memory": ("Memory", "Arbeitsspeicher"),
    "field.reachable": ("Reachable", "Erreichbar"),
    "field.last_discovery": ("Last discovery", "Letzte Discovery"),
    "field.last_error": ("Last error", "Letzter Fehler"),
    "field.instance": ("Instance", "Instanz"),
    "field.instances": ("Instances", "Instanzen"),
    "field.host": ("Host", "Host"),
    "field.hostname": ("Hostname", "Hostname"),
    "field.type": ("Type", "Typ"),
    "field.status": ("Status", "Status"),
    "field.checked": ("Checked", "Geprüft"),
    "field.actions": ("Actions", "Aktionen"),
    "field.database": ("Database", "Datenbank"),
    "field.release": ("Release", "Release"),
    "field.system": ("System", "System"),
    "field.target": ("Target", "Ziel"),
    "field.operation": ("Operation", "Operation"),
    "field.requested": ("Requested", "Angefordert"),
    "field.finished": ("Finished", "Beendet"),
    "field.time": ("Time", "Zeit"),
    "field.message": ("Message", "Meldung"),
    "field.priority": ("Start priority", "Startpriorität"),
    "yes": ("yes", "ja"),
    "no": ("no", "nein"),
    "unknown": ("unknown", "unbekannt"),
    "op.start": ("Start", "Starten"),
    "op.stop": ("Stop", "Stoppen"),
    "op.restart": ("Restart", "Neu starten"),
    "op.start_system": ("Start system", "System starten"),
    "op.stop_system": ("Stop system", "System stoppen"),
    "op.restart_system": ("Restart system", "System neu starten"),
    "op.confirm": ("Run this operation?", "Diese Operation ausführen?"),
    "op.menu": ("Operations", "Operationen"),
    "op.discover": ("Run discovery", "Discovery starten"),
    "op.register": ("Register instance agent", "Instanz-Agent registrieren"),
    "op.unregister": ("Unregister instance agent", "Instanz-Agent abmelden"),
    "op.reregister": ("Re-register instance agent", "Instanz-Agent neu registrieren"),
    "op.update_bundle": ("Update OSLO operations", "OSLO-Operationen aktualisieren"),
    "kind.DISCOVER": ("Discovery", "Discovery"),
    "target.HOST": ("Host", "Host"),
    "target.MASS": ("Mass operation", "Massenoperation"),
    "activity.PARTIAL": ("partly failed", "teilweise fehlgeschlagen"),
    "mass.button": ("Mass operation", "Massenoperation"),
    "mass.title": ("Mass operation", "Massenoperation"),
    "mass.settings": ("Operation", "Operation"),
    "mass.parallel": ("At the same time", "Gleichzeitig"),
    "mass.continue": ("Continue after failures", "Bei Fehlern weitermachen"),
    "mass.stop": ("Stop at the first failure", "Beim ersten Fehler anhalten"),
    "mass.run": ("Run mass operation", "Massenoperation ausführen"),
    "mass.cancel": ("Cancel", "Abbrechen"),
    "mass.targets_system": ("Systems", "Systeme"),
    "mass.targets_instance": ("Instances", "Instanzen"),
    "mass.targets_host": ("Hosts", "Hosts"),
    "mass.hint_system": (
        "Selected systems that depend on each other run in order: for a start or restart "
        "the dependencies first, for a stop the dependent systems first.",
        "Ausgewählte Systeme, die voneinander abhängen, laufen in Reihenfolge: beim Start "
        "und Neustart zuerst die Abhängigkeiten, beim Stopp zuerst die abhängigen Systeme.",
    ),
    "mass.hint_instance": (
        "Each instance is handled on its own, without the rest of its system.",
        "Jede Instanz wird für sich bedient, ohne den Rest ihres Systems.",
    ),
    "mass.hint_host": (
        "A discovery reads each host and updates the inventory.",
        "Eine Discovery liest jeden Host aus und aktualisiert das Inventar.",
    ),
    "mass.busy": ("activity running", "Aktivität läuft"),
    "mass.busy_hint": (
        "Targets with a running activity wait for a sibling of this mass operation or are skipped.",
        "Ziele mit laufender Aktivität warten auf eine andere Teilaktivität dieser "
        "Massenoperation oder werden übersprungen.",
    ),
    "mass.no_targets": (
        "No targets match the current filters.",
        "Zu den aktuellen Filtern gibt es keine Ziele.",
    ),
    "mass.no_operations": (
        "Your role allows no mass operation on these targets.",
        "Deine Rolle erlaubt keine Massenoperation auf diesen Zielen.",
    ),
    "mass.children": ("Targets", "Ziele"),
    "mass.settings_summary": (
        "{total} targets, {parallel} at the same time.",
        "{total} Ziele, {parallel} gleichzeitig.",
    ),
    "mass.part_of": ("Part of activity {id}", "Teil von Aktivität {id}"),
    "error.mass_operation": (
        "This operation cannot run as a mass operation on these targets.",
        "Diese Operation lässt sich auf diesen Zielen nicht als Massenoperation ausführen.",
    ),
    "error.mass_no_targets": ("Select at least one target.", "Wähle mindestens ein Ziel aus."),
    "op.busy": ("An activity is running:", "Es läuft eine Aktivität:"),
    "tree.instance_one": ("1 instance", "1 Instanz"),
    "tree.instances": ("{count} instances", "{count} Instanzen"),
    "tree.toggle": ("Show or hide instances", "Instanzen ein- oder ausblenden"),
    "tree.expand_all": ("Expand all", "Alle aufklappen"),
    "tree.collapse_all": ("Collapse all", "Alle zuklappen"),
    "tree.hidden": (
        "{count} more instances do not match the instance type filter.",
        "{count} weitere Instanzen passen nicht zum Filter Instanztyp.",
    ),
    "kind.START": ("Start", "Start"),
    "kind.STOP": ("Stop", "Stopp"),
    "kind.RESTART": ("Restart", "Neustart"),
    "kind.REGISTER": ("Register instance agent", "Instanz-Agent registrieren"),
    "kind.UNREGISTER": ("Unregister instance agent", "Instanz-Agent abmelden"),
    "kind.REREGISTER": ("Re-register instance agent", "Instanz-Agent neu registrieren"),
    "kind.UPDATE_BUNDLE": ("Update OSLO operations", "OSLO-Operationen aktualisieren"),
    "target.INSTANCE": ("Instance", "Instanz"),
    "target.SYSTEM": ("System", "System"),
    "status.GREEN": ("running", "läuft"),
    "status.YELLOW": ("in transition", "im Übergang"),
    "status.RED": ("error", "Fehler"),
    "status.GRAY": ("stopped", "gestoppt"),
    "status.UNKNOWN": ("unknown", "unbekannt"),
    "status.RUNNING": ("running", "läuft"),
    "status.STOPPED": ("stopped", "gestoppt"),
    "status.STARTING": ("starting", "startet"),
    "status.STOPPING": ("stopping", "stoppt"),
    "status.WARNING": ("warning", "Warnung"),
    "status.INSERVICE": ("in service", "in Wartung"),
    "status.ERROR": ("error", "Fehler"),
    "activity.PENDING": ("pending", "wartet"),
    "activity.RUNNING": ("running", "läuft"),
    "activity.SUCCEEDED": ("succeeded", "erfolgreich"),
    "activity.FAILED": ("failed", "fehlgeschlagen"),
    "activities.empty": ("No activities yet.", "Noch keine Aktivitäten."),
    "activity.title": ("Activity", "Aktivität"),
    "activity.log": ("Log", "Protokoll"),
    "activity.refreshing": (
        "This page refreshes automatically while the activity is running.",
        "Diese Seite aktualisiert sich automatisch, solange die Aktivität läuft.",
    ),
    "activity.log_language": (
        "Log messages are recorded in English.",
        "Protokollmeldungen werden auf Englisch aufgezeichnet.",
    ),
    "itype.hana": ("SAP HANA", "SAP HANA"),
    "itype.scs": ("Central services", "Zentrale Dienste"),
    "itype.ers": ("Enqueue replication", "Enqueue-Replikation"),
    "itype.abap": ("ABAP application server", "ABAP-Anwendungsserver"),
    "itype.java": ("Java application server", "Java-Anwendungsserver"),
    "itype.dual": ("ABAP+Java application server", "ABAP+Java-Anwendungsserver"),
    "notice.host_created": ("Host created.", "Host angelegt."),
    "notice.hosts_created": ("{count} hosts created.", "{count} Hosts angelegt."),
    "hosts.names_hint": (
        "Several hosts at once: names separated by commas, e.g. sapapp1, sapapp2. They get the "
        "same settings and credentials, and each is reached under its name.",
        "Mehrere Hosts auf einmal: Namen durch Kommas getrennt, z. B. sapapp1, sapapp2. Sie "
        "bekommen dieselben Einstellungen und Zugangsdaten und werden unter ihrem Namen "
        "erreicht.",
    ),
    "hosts.add_many": ("Create {count} hosts", "{count} Hosts anlegen"),
    "hosts.address_from_names": (
        "With several hosts, each name is its address.",
        "Bei mehreren Hosts ist der Name jeweils die Adresse.",
    ),
    "notice.host_deleted": ("Host deleted.", "Host gelöscht."),
    "notice.credentials_saved": ("Credentials saved.", "Zugangsdaten gespeichert."),
    "notice.discovered": (
        "Discovery finished: {added} new, {updated} updated, {missing} missing.",
        "Discovery abgeschlossen: {added} neu, {updated} aktualisiert, {missing} fehlend.",
    ),
    "error.host_exists": (
        "A host with this name already exists.",
        "Ein Host mit diesem Namen existiert bereits.",
    ),
    "error.credentials_incomplete": (
        "User and password must be given together.",
        "Benutzer und Passwort müssen zusammen angegeben werden.",
    ),
    "error.invalid_input": ("The input is not valid.", "Die Eingabe ist ungültig."),
    "error.discovery_failed": (
        "The host agent could not be queried: {detail}",
        "Der Host Agent konnte nicht abgefragt werden: {detail}",
    ),
    "error.conflict": (
        "Another activity is still running for this system.",
        "Für dieses System läuft bereits eine Aktivität.",
    ),
    "warning.discovery": ("Warnings", "Warnungen"),
    "deps.title": ("Dependencies", "Abhängigkeiten"),
    "deps.depends_on": ("Depends on", "Hängt ab von"),
    "deps.required_by": ("Required by", "Wird benötigt von"),
    "deps.none": ("none", "keine"),
    "deps.add": ("Add dependency", "Abhängigkeit hinzufügen"),
    "deps.remove": ("Remove", "Entfernen"),
    "deps.no_candidates": (
        "No other system can be added.",
        "Es kann kein weiteres System hinzugefügt werden.",
    ),
    "deps.explanation": (
        "Starting this system starts the systems it depends on first, for example its "
        "database system. Stopping it stops this system first and then its dependencies, "
        "unless another system still needs them.",
        "Beim Starten dieses Systems werden zuerst die Systeme gestartet, von denen es "
        "abhängt, zum Beispiel sein Datenbanksystem. Beim Stoppen wird erst dieses System "
        "gestoppt, dann seine Abhängigkeiten, sofern kein anderes System sie noch benötigt.",
    ),
    "deps.required_note": (
        "Stopping this system does not stop the systems that need it. Stop those first.",
        "Das Stoppen dieses Systems stoppt nicht die Systeme, die es benötigen. "
        "Stoppe diese zuerst.",
    ),
    "notice.dependencies_saved": ("Dependencies saved.", "Abhängigkeiten gespeichert."),
    "error.dependency_self": (
        "A system cannot depend on itself.",
        "Ein System kann nicht von sich selbst abhängen.",
    ),
    "error.dependency_unknown": ("Unknown system.", "Unbekanntes System."),
    "error.dependency_cycle": (
        "This dependency would create a cycle.",
        "Diese Abhängigkeit würde einen Kreis bilden.",
    ),
    # custom operations
    "tab.operations": ("Operations", "Operationen"),
    "kind.CUSTOM": ("Custom operation", "Eigene Operation"),
    "activity.CANCELLED": ("cancelled", "abgebrochen"),
    "activity.cancel": ("Cancel", "Abbrechen"),
    "activity.cancel_confirm": (
        "Cancel this activity? Start and stop only stop waiting; custom operations are "
        "cancelled on the host.",
        "Diese Aktivität abbrechen? Start und Stopp warten nur nicht mehr; eigene "
        "Operationen werden auf dem Host abgebrochen.",
    ),
    "notice.activity_cancelled": (
        "The activity was cancelled.",
        "Die Aktivität wurde abgebrochen.",
    ),
    "error.not_active": ("The activity has already finished.", "Die Aktivität ist schon beendet."),
    "custom.intro": (
        "Custom operations run a script that is configured in operations.d of the host "
        "agent. Only admins define them; each one has its own role for running it.",
        "Eigene Operationen führen ein Skript aus, das im Host Agent unter operations.d "
        "eingerichtet ist. Nur Admins legen sie an; jede hat eine eigene Rolle zum Ausführen.",
    ),
    "custom.empty": ("No custom operations yet.", "Noch keine eigenen Operationen."),
    "custom.add": ("Create operation", "Operation anlegen"),
    "custom.locks": ("Locks instance or host", "Sperrt Instanz oder Host"),
    "custom.template_only": (
        "Not applicable for standalone execution",
        "Nicht für Einzelausführung",
    ),
    "custom.flags_hint": (
        "An operation that locks waits for other activities on its targets and keeps them "
        "from starting, like start and stop; switch it off for scripts that only read, e.g. "
        "logs. Not for standalone execution: only as a step of an operation template, not "
        "in menus, the landscape or schedules.",
        "Eine sperrende Operation wartet auf andere Aktivitäten ihrer Ziele und hält sie vom "
        "Start ab, wie Start und Stopp; abschalten für Skripte, die nur lesen, z. B. "
        "Protokolle. Nicht für Einzelausführung: nur als Schritt einer Operationsvorlage, "
        "nicht in Menüs, der Landschaft oder Einplanungen.",
    ),
    "custom.key": ("Key", "Schlüssel"),
    "custom.name_hint": ("e.g. Copy kernel", "z. B. Kernel kopieren"),
    "custom.agent_operation": ("Host agent operation", "Host-Agent-Operation"),
    "custom.agent_hint": (
        "Host agent operation is the Name: of the configuration file in operations.d. The "
        "tool passes context parameters such as SAPSYSTEMNAME and the own parameters as "
        "PARAM-<name>.",
        "Host-Agent-Operation ist der Name: der Konfigurationsdatei in operations.d. Das "
        "Tool übergibt Kontextparameter wie SAPSYSTEMNAME und die eigenen Parameter als "
        "PARAM-<Name>.",
    ),
    "custom.ordering": ("Order on systems", "Reihenfolge bei Systemen"),
    "custom.ordering.parallel": ("all instances at once", "alle Instanzen gleichzeitig"),
    "custom.ordering.roles": (
        "by roles like a start (database and central services first)",
        "nach Rollen wie ein Start (Datenbank und zentrale Dienste zuerst)",
    ),
    "custom.ordering.sequential": ("one instance after the other", "eine Instanz nach der anderen"),
    "custom.role": ("Role to run it", "Rolle zum Ausführen"),
    "custom.timeout": ("Timeout (seconds)", "Zeitlimit (Sekunden)"),
    "custom.instance_types": ("Instance types", "Instanztypen"),
    "custom.instance_types_hint": (
        "Only for instances and systems. None: all instances; diagnostics agents are then "
        "left out on systems.",
        "Nur für Instanzen und Systeme. Keiner: alle Instanzen; Diagnostics Agents bleiben "
        "dann bei Systemen außen vor.",
    ),
    "custom.mass": ("Allowed as mass operation", "Als Massenoperation erlaubt"),
    "custom.delete": ("Delete operation", "Operation löschen"),
    "custom.delete_confirm": ("Delete this custom operation?", "Diese eigene Operation löschen?"),
    "custom.operation": ("Custom operation", "Eigene Operation"),
    "custom.parameters": ("Parameters", "Parameter"),
    "custom.parameters_intro": (
        "Passed to the host agent as PARAM-<name>, e.g. $[PARAM-KRNLREL] in Command:.",
        "Werden dem Host Agent als PARAM-<Name> übergeben, z. B. $[PARAM-KRNLREL] in Command:.",
    ),
    "custom.parameters_hint": (
        "An empty optional field is not passed; following positional arguments of the "
        "script then move up.",
        "Ein leeres optionales Feld wird nicht übergeben; folgende Positionsargumente des "
        "Skripts rücken dann auf.",
    ),
    "custom.no_parameters": ("No parameters.", "Keine Parameter."),
    "custom.parameter_add": ("Add parameter", "Parameter hinzufügen"),
    "custom.parameter_delete": ("Delete parameter", "Parameter löschen"),
    "custom.parameter_delete_confirm": ("Delete this parameter?", "Diesen Parameter löschen?"),
    "custom.parameter_name": ("Name", "Name"),
    "custom.parameter_label": ("Display name", "Anzeigename"),
    "custom.parameter_type": ("Type", "Typ"),
    "custom.type.STRING": ("Text", "Text"),
    "custom.type.INTEGER": ("Integer", "Ganzzahl"),
    "custom.type.BOOLEAN": ("Yes/no", "Ja/Nein"),
    "custom.required": ("required", "Pflichtfeld"),
    "custom.default": ("Default", "Standardwert"),
    "custom.pattern": ("Pattern (regular expression)", "Muster (regulärer Ausdruck)"),
    "custom.help": ("Help text", "Hilfetext"),
    "custom.context": ("Context parameters", "Kontextparameter"),
    "custom.context_intro": (
        "Filled from the inventory and always passed. SERVICE_SUBTYPE is derived from the "
        "instance type and the application servers of the system.",
        "Aus dem Inventar gefüllt und immer übergeben. SERVICE_SUBTYPE wird aus dem "
        "Instanztyp und den Anwendungsservern des Systems abgeleitet.",
    ),
    "custom.run": ("Run", "Ausführen"),
    "mass.choose": ("Choose", "Auswählen"),
    "notice.operation_saved": ("Operation saved.", "Operation gespeichert."),
    "notice.operation_deleted": ("Operation deleted.", "Operation gelöscht."),
    "notice.parameter_saved": ("Parameter saved.", "Parameter gespeichert."),
    "notice.parameter_deleted": ("Parameter deleted.", "Parameter gelöscht."),
    "error.operation_key": (
        "Key: lowercase letters, digits and _, not the key of a built-in operation.",
        "Schlüssel: Kleinbuchstaben, Ziffern und _, nicht der einer eingebauten Operation.",
    ),
    "error.operation_name": ("The operation needs a name.", "Die Operation braucht einen Namen."),
    "error.operation_agent": (
        "Host agent operation: letters, digits, '.', '_' and '-'.",
        "Host-Agent-Operation: Buchstaben, Ziffern, '.', '_' und '-'.",
    ),
    "error.operation_key_taken": (
        "An operation with this key already exists.",
        "Es gibt schon eine Operation mit diesem Schlüssel.",
    ),
    "error.parameter_name": (
        "Parameter name: letters, digits and _, e.g. KRNLREL.",
        "Parametername: Buchstaben, Ziffern und _, z. B. KRNLREL.",
    ),
    "error.parameter_label": (
        "The parameter needs a display name.",
        "Der Parameter braucht einen Anzeigenamen.",
    ),
    "error.parameter_pattern": (
        "The pattern is not a valid regular expression.",
        "Das Muster ist kein gültiger regulärer Ausdruck.",
    ),
    "error.parameter_default": (
        "The default value does not fit the type or pattern.",
        "Der Standardwert passt nicht zu Typ oder Muster.",
    ),
    "error.parameter_taken": (
        "A parameter with this name already exists.",
        "Es gibt schon einen Parameter mit diesem Namen.",
    ),
    "error.parameter_values": ("Invalid parameters: {detail}", "Ungültige Parameter: {detail}"),
    # browser interface (frontend/), landscape
    "ui.loading": ("Loading…", "Wird geladen …"),
    "ui.load_failed": ("The data could not be loaded.", "Die Daten ließen sich nicht laden."),
    "ui.needs_javascript": (
        "This page needs JavaScript.",
        "Diese Seite braucht JavaScript.",
    ),
    "ui.activity": ("Activity", "Aktivität"),
    "ui.busy": (
        "An activity is already running for this target.",
        "Für dieses Ziel läuft schon eine Aktivität.",
    ),
    "ui.started": ("{operation} started.", "{operation} gestartet."),
    "ui.show_activity": ("Activity {id}", "Aktivität {id}"),
    "ui.close": ("Close", "Schließen"),
    "ui.search": ("Search", "Suchen"),
    "ui.search_systems": (
        "System, SID, instance, host or tag",
        "System, SID, Instanz, Host oder Tag",
    ),
    "ui.search_hosts": (
        "Host, address, OS or tag",
        "Host, Adresse, Betriebssystem oder Tag",
    ),
    "ui.count_systems": (
        "{systems} systems, {instances} instances",
        "{systems} Systeme, {instances} Instanzen",
    ),
    "ui.count_hosts": ("{hosts} hosts", "{hosts} Hosts"),
    "ui.instance_count": ("{count} instances", "{count} Instanzen"),
    "ui.select": ("Select {name}", "{name} auswählen"),
    "ui.select_all_systems": ("Select all systems shown", "Alle angezeigten Systeme auswählen"),
    "ui.select_all_hosts": ("Select all hosts shown", "Alle angezeigten Hosts auswählen"),
    "ui.selection": ("Selection", "Auswahl"),
    "ui.selected_system": ("{count} system(s) selected", "{count} System(e) ausgewählt"),
    "ui.selected_instance": ("{count} instance(s) selected", "{count} Instanz(en) ausgewählt"),
    "ui.selected_host": ("{count} host(s) selected", "{count} Host(s) ausgewählt"),
    "ui.clear_selection": ("Clear selection", "Auswahl aufheben"),
    "ui.no_operations": (
        "No operation fits the whole selection.",
        "Keine Operation passt zur ganzen Auswahl.",
    ),
    "ui.confirm_operation": ("Really: {operation}", "Wirklich: {operation}"),
    "ui.stop_on_error": ("stop on error", "bei Fehler anhalten"),
    "ui.role.database": ("Database", "Datenbank"),
    "ui.role.central": ("Central services", "Zentrale Dienste"),
    "ui.role.application": ("Application server", "Anwendungsserver"),
    "ui.role.agent": ("Diagnostics agent", "Diagnostics Agent"),
    "ui.refresh_status": ("Refresh status", "Status aktualisieren"),
    "ui.open_page": ("Open page", "Seite öffnen"),
    "ui.instances_in_order": ("Instances in start order", "Instanzen in Startreihenfolge"),
    "ui.process": ("Process", "Prozess"),
    "ui.started_at": ("Started", "Gestartet"),
    "ui.processes_unavailable": (
        "The sapstartsrv could not be queried",
        "Der sapstartsrv ließ sich nicht abfragen",
    ),
    "ui.no_processes": ("No processes reported.", "Keine Prozesse gemeldet."),
    "ui.checked_at": ("Read at {time}", "Gelesen um {time}"),
    "ui.no_instances_on_host": (
        "No instances of systems on this host.",
        "Keine Instanzen von Systemen auf diesem Host.",
    ),
    "ui.palette": ("Command palette", "Befehlspalette"),
    "ui.palette_open": ("Command or system", "Befehl oder System"),
    "ui.palette_placeholder": (
        "Find a system, host or operation …",
        "System, Host oder Operation suchen …",
    ),
    "ui.palette_operations": ("Operations on the selection", "Operationen auf der Auswahl"),
    "ui.palette_pages": ("Go to", "Gehe zu"),
    "ui.palette_keys": (
        "↑ ↓ choose · Enter run · Esc close",
        "↑ ↓ auswählen · Enter ausführen · Esc schließen",
    ),
    "ui.account": ("My account", "Mein Konto"),
    "ui.instances_running": (
        "{running} of {total} instances running",
        "{running} von {total} Instanzen laufen",
    ),
    "ui.recent_activities": ("Last activities", "Letzte Aktivitäten"),
    "ui.no_activities": ("No activities yet.", "Noch keine Aktivitäten."),
    "ui.tab_status": ("Status", "Status"),
    "ui.tab_log": ("Activities", "Aktivitäten"),
    "ui.read_again": ("Read again", "Neu lesen"),
    "ui.instance_number": ("Instance number", "Instanznummer"),
    "ui.kernel": ("Kernel", "Kernel"),
    "ui.duration": ("Duration", "Dauer"),
    "ui.timeout_of": ("time limit {minutes} min", "Zeitlimit {minutes} min"),
    "ui.timeline": ("Timeline", "Zeitplan"),
    "ui.timeline_hint": (
        "A click on an instance filters the log.",
        "Ein Klick auf eine Instanz filtert das Protokoll.",
    ),
    "ui.seg_stop": ("stop", "Stopp"),
    "ui.seg_start": ("start", "Start"),
    "ui.seg_op": ("operation", "Operation"),
    "ui.seg_failed": ("failed", "fehlgeschlagen"),
    "ui.log_all": ("All", "Alle"),
    "ui.log_warnings": ("Warnings", "Warnungen"),
    "ui.log_errors": ("Errors", "Fehler"),
    "ui.log_subject": ("Instance", "Instanz"),
    "ui.log_search": ("Search the log", "Im Protokoll suchen"),
    "ui.log_follow": ("follow", "mitlaufen"),
    # operation templates and schedules (frontend/src/templates)
    "tpl.title": ("Operation templates", "Operationsvorlagen"),
    "tpl.intro": (
        "A template chains operations that run one after another on a system or host, e.g. "
        "prepare kernel, stop, copy kernel, start. Each step has its own values and its own "
        "behavior on error.",
        "Eine Vorlage verkettet Operationen, die nacheinander auf einem System oder Host "
        "laufen, z. B. Kernel vorbereiten, stoppen, Kernel kopieren, starten. Jeder Schritt "
        "hat eigene Werte und ein eigenes Verhalten bei Fehler.",
    ),
    "tpl.new": ("Create template", "Vorlage anlegen"),
    "tpl.new_title": ("New template", "Neue Vorlage"),
    "tpl.empty": ("No templates yet.", "Noch keine Vorlagen."),
    "tpl.invalid": (
        "A step uses an operation that no longer exists; the template cannot run.",
        "Ein Schritt nutzt eine Operation, die es nicht mehr gibt; die Vorlage kann nicht laufen.",
    ),
    "tpl.steps": ("Steps", "Schritte"),
    "tpl.step": ("Step", "Schritt"),
    "tpl.kind_builtin": ("built-in", "eingebaut"),
    "tpl.kind_custom": ("custom operation", "eigene Operation"),
    "tpl.remove": ("Remove step", "Schritt entfernen"),
    "kind.TEMPLATE": ("Operation template", "Operationsvorlage"),
    "target.TEMPLATE": ("Template", "Vorlage"),
    "ui.palette_nothing": ("Nothing found.", "Nichts gefunden."),
    "tpl.steps_tab": ("Steps ({count})", "Schritte ({count})"),
    "tpl.on_selection": (
        "Target when it starts: $selection ({type})",
        "Ziel beim Start: $Auswahl ({type})",
    ),
    "tpl.fixed_targets": ("Fixed targets", "Feste Ziele"),
    "tpl.selection_placeholder": ("$selection ({type})", "$Auswahl ({type})"),
    "tpl.selection_hint": (
        "A dialog template: it is started in the landscape on the selected targets.",
        "Eine Dialog-Vorlage: Sie wird in der Landschaft auf der Auswahl gestartet.",
    ),
    "tpl.fixed_hint": (
        "Every step has fixed targets: the template runs as it is, e.g. scheduled.",
        "Jeder Schritt hat feste Ziele: Die Vorlage läuft, wie sie ist, z. B. eingeplant.",
    ),
    "tpl.selection_mixed": (
        "Steps on the selection must all run on the same target type.",
        "Schritte auf der Auswahl müssen alle denselben Zieltyp haben.",
    ),
    "tpl.graph_empty": ("No steps yet.", "Noch keine Schritte."),
    "tpl.add_first": ("Add the first step", "Ersten Schritt hinzufügen"),
    "tpl.add_parallel": ("+ Step without predecessor", "+ Schritt ohne Vorgänger"),
    "tpl.graph_hint": (
        "A step starts when all its predecessors have finished; steps side by side run in "
        "parallel. Choose a step for + (next step), → (connect) and delete; drag from the "
        "lower to the upper edge of a step to connect; Delete removes a selected arrow.",
        "Ein Schritt startet, wenn alle Vorgänger fertig sind; Schritte nebeneinander laufen "
        "parallel. Einen Schritt wählen für + (nächster Schritt), → (verbinden) und Löschen; "
        "vom unteren zum oberen Rand eines Schritts ziehen verbindet; Entf löscht einen "
        "gewählten Pfeil.",
    ),
    "tpl.add_after": ("Add a step after this one", "Schritt danach hinzufügen"),
    "tpl.connect": ("Connect to a following step", "Mit einem folgenden Schritt verbinden"),
    "tpl.connect_hint": (
        "Choose the step that runs after step {n}.",
        "Den Schritt wählen, der nach Schritt {n} läuft.",
    ),
    "tpl.step_number": ("Step {n}", "Schritt {n}"),
    "tpl.current_operation": ("Operation", "Operation"),
    "tpl.change_operation": ("Change operation …", "Operation ändern …"),
    "tpl.target_type": ("Runs on", "Läuft auf"),
    "tpl.locks_nothing": (
        "This operation locks nothing; it may run beside other steps on the same targets.",
        "Diese Operation sperrt nichts; sie darf neben anderen Schritten auf denselben Zielen "
        "laufen.",
    ),
    "tpl.parameters": ("Operation parameters", "Parameter der Operation"),
    "tpl.ask": ("Ask when it starts", "Beim Start fragen"),
    "tpl.param_missing": (
        "Required: give a value or ask for it when the template starts.",
        "Pflichtfeld: einen Wert eintragen oder beim Start fragen.",
    ),
    "tpl.entities": ("Targets", "Ziele"),
    "tpl.fixed": ("Fixed targets", "Feste Ziele"),
    "tpl.selection_step_hint": (
        "The step runs on the targets selected when the template starts.",
        "Der Schritt läuft auf den Zielen, die beim Start ausgewählt sind.",
    ),
    "tpl.fixed_step_hint": (
        "The step always runs on these targets; several run as a mass operation.",
        "Der Schritt läuft immer auf diesen Zielen; mehrere laufen als Massenoperation.",
    ),
    "tpl.filter_targets": ("Filter targets", "Ziele filtern"),
    "tpl.no_targets": ("No matching targets.", "Keine passenden Ziele."),
    "tpl.predecessors": ("Predecessors", "Vorgänger"),
    "tpl.no_predecessors": ("There are no other steps.", "Es gibt keine anderen Schritte."),
    "tpl.pick_operation": ("Choose an operation", "Operation wählen"),
    "tpl.search_operations": ("Search operations", "Operationen suchen"),
    "tpl.favorites": ("Favorites", "Favoriten"),
    "tpl.most_used": ("Used most (90 days)", "Meistgenutzt (90 Tage)"),
    "tpl.all_operations": ("All operations", "Alle Operationen"),
    "tpl.found": ("Found", "Gefunden"),
    "tpl.favorite": ("Mark as favorite", "Als Favorit markieren"),
    "tpl.unfavorite": ("Remove from favorites", "Aus den Favoriten entfernen"),
    "tpl.template_only": ("only in templates", "nur in Vorlagen"),
    "tpl.picker_keys": (
        "↑ ↓ choose · Enter take · ☆ favorite · Esc close",
        "↑ ↓ wählen · Enter übernehmen · ☆ Favorit · Esc schließen",
    ),
    "tpl.run": ("Run", "Ausführen"),
    "tpl.run_title": ("Run {name}", "{name} ausführen"),
    "tpl.run_hint": (
        "The template runs on its fixed targets with the values below.",
        "Die Vorlage läuft auf ihren festen Zielen mit den Werten unten.",
    ),
    # form pages (frontend/src/configuration, operations, administration, account, activities)
    "ui.saved": ("Saved.", "Gespeichert."),
    "ui.expand": ("Show instances", "Instanzen zeigen"),
    "ui.log_level": ("Level", "Stufe"),
    "field.stage": ("Stage", "Stufe"),
    "field.databases": ("Databases", "Datenbanken"),
    "credentials.per_sid": ("Credentials per SID", "Zugangsdaten je SID"),
    "custom.flags": ("Flags", "Merkmale"),
    "custom.flag_locks": ("locks", "sperrt"),
    "custom.flag_no_lock": ("locks nothing", "sperrt nichts"),
    "custom.flag_mass": ("mass operation", "Massenoperation"),
    "userstate.GREEN": ("active", "aktiv"),
    "userstate.GRAY": ("inactive", "inaktiv"),
    "admin.timezone": ("Time zone of schedules", "Zeitzone der Einplanungen"),
    "token.none": ("No tokens yet.", "Noch keine Tokens."),
    "att.rules_intro": (
        "The rules decide what the overview shows under \"needs attention\", for everyone. "
        "Each user can switch rules off and hide systems or pools for themselves.",
        "Die Regeln bestimmen, was die Übersicht unter „Braucht Aufmerksamkeit“ zeigt, für "
        "alle. Jeder Benutzer kann Regeln für sich abschalten und Systeme oder Pools "
        "ausblenden.",
    ),
    "att.enabled": ("Rule active", "Regel aktiv"),
    "att.hint.failed_activities": (
        "Failed or partly failed activities.",
        "Fehlgeschlagene oder teilweise fehlgeschlagene Aktivitäten.",
    ),
    "att.hint.system_status": (
        "Systems with one of the chosen statuses, unless an activity runs on them.",
        "Systeme mit einem der gewählten Status, außer während einer Aktivität darauf.",
    ),
    "att.hint.stopped_systems": (
        "Stopped systems of the chosen stages, e.g. production.",
        "Gestoppte Systeme der gewählten Stufen, z. B. Produktion.",
    ),
    "att.hint.long_running": (
        "Activities that run longer than this.",
        "Aktivitäten, die länger als angegeben laufen.",
    ),
    "att.hint.host_unreachable": (
        "Hosts whose host agent could not be reached at the last discovery.",
        "Hosts, deren Host Agent bei der letzten Discovery nicht erreichbar war.",
    ),
    "att.hint.schedule_errors": (
        "Schedules whose last run could not start.",
        "Einplanungen, deren letzter Lauf nicht starten konnte.",
    ),
    "att.hint.stale_discovery": (
        "Hosts without a discovery for this many days.",
        "Hosts ohne Discovery seit so vielen Tagen.",
    ),
    "att.hint.tls_expiry": (
        "The HTTPS certificate of OSLO expires within this many days.",
        "Das HTTPS-Zertifikat von OSLO läuft in so vielen Tagen ab.",
    ),
    "att.hint.bundle_outdated": (
        "Hosts whose OSLO operations are missing, changed or not the active version.",
        "Hosts, deren OSLO-Operationen fehlen, verändert sind oder nicht der aktiven Version "
        "entsprechen.",
    ),
    "att.setting.hours": ("Of the last hours", "Der letzten Stunden"),
    "att.setting.hide_scheduled_every_minutes": (
        "Hide schedules repeating at least every … minutes (0: none)",
        "Einplanungen ausblenden, die mindestens alle … Minuten laufen (0: keine)",
    ),
    "att.setting.hide_when_succeeded_later": (
        "Hide once a later run on the same target succeeded",
        "Ausblenden, sobald ein späterer Lauf auf demselben Ziel erfolgreich war",
    ),
    "att.setting.hide_operations": ("Hide these operations", "Diese Operationen ausblenden"),
    "att.setting.stages": ("Only these stages (none: all)", "Nur diese Stufen (keine: alle)"),
    "att.setting.statuses": ("Statuses", "Status"),
    "att.setting.minutes": ("Minutes", "Minuten"),
    "att.setting.days": ("Days", "Tage"),
    # overview (frontend/src/overview) and the rules of "needs attention" (attention.py)
    "ov.kpis": ("Key figures", "Kennzahlen"),
    "ov.matrix": ("Status by product and stage", "Status nach Produkt und Stufe"),
    "ov.product": ("Product", "Produkt"),
    "ov.matrix_hint": (
        "Products are the pools; set the stage of a system in its configuration. Each square "
        "is an instance; a click opens the system in the landscape.",
        "Produkte sind die Pools; die Stufe eines Systems steht in seiner Konfiguration. "
        "Jedes Kästchen ist eine Instanz; ein Klick öffnet das System in der Landschaft.",
    ),
    "ov.attention": ("Needs attention", "Braucht Aufmerksamkeit"),
    "ov.all_fine": ("Nothing needs attention.", "Nichts braucht Aufmerksamkeit."),
    "ov.customize": ("Customize", "Anpassen"),
    "ov.customize_hint": (
        "These exceptions apply to you only; the rules themselves are the same for everyone.",
        "Diese Ausnahmen gelten nur für dich; die Regeln selbst gelten für alle.",
    ),
    "ov.rules_for_me": ("Rules shown to me", "Regeln, die ich sehe"),
    "ov.rule_off_globally": ("switched off for everyone", "für alle abgeschaltet"),
    "ov.hidden": ("Hidden for me", "Für mich ausgeblendet"),
    "ov.show_again": ("Show again", "Wieder anzeigen"),
    "ov.hide_pool": ("Hide a pool for me", "Einen Pool für mich ausblenden"),
    "ov.hide_system": ("Hide system for me", "System für mich ausblenden"),
    "ov.rule_off": ("Switch rule off for me", "Regel für mich abschalten"),
    "ov.edit_rules": ("Edit the rules for everyone", "Regeln für alle bearbeiten"),
    "stage.sandbox": ("Sandbox", "Sandbox"),
    "stage.development": ("Development", "Entwicklung"),
    "stage.quality": ("Quality", "Qualität"),
    "stage.preprod": ("Pre-production", "PreProd"),
    "stage.production": ("Production", "Produktion"),
    "stage.none": ("No stage", "Ohne Stufe"),
    "att.rule.failed_activities": ("Failed activities", "Fehlgeschlagene Aktivitäten"),
    "att.rule.system_status": ("Systems with errors", "Systeme mit Fehlern"),
    "att.rule.stopped_systems": ("Stopped systems", "Gestoppte Systeme"),
    "att.rule.long_running": ("Long-running activities", "Lang laufende Aktivitäten"),
    "att.rule.host_unreachable": ("Unreachable hosts", "Nicht erreichbare Hosts"),
    "att.rule.schedule_errors": ("Schedules that could not start", "Einplanungen ohne Start"),
    "att.rule.stale_discovery": (
        "Hosts without a recent discovery",
        "Hosts ohne aktuelle Discovery",
    ),
    "att.rule.tls_expiry": (
        "HTTPS certificate of OSLO expires",
        "HTTPS-Zertifikat von OSLO läuft ab",
    ),
    "att.tls_expiring": (
        "The HTTPS certificate of OSLO expires on {date}",
        "Das HTTPS-Zertifikat von OSLO läuft am {date} ab",
    ),
    "att.tls_expired": (
        "The HTTPS certificate of OSLO expired on {date}",
        "Das HTTPS-Zertifikat von OSLO ist am {date} abgelaufen",
    ),
    "att.rule.bundle_outdated": (
        "Hosts with outdated OSLO operations",
        "Hosts mit veralteten OSLO-Operationen",
    ),
    "att.bundle_missing": (
        "Host {host}: OSLO operations not installed",
        "Host {host}: OSLO-Operationen nicht installiert",
    ),
    "att.bundle_outdated": (
        "Host {host}: OSLO operations {version} instead of {active}",
        "Host {host}: OSLO-Operationen {version} statt {active}",
    ),
    "att.bundle_modified": (
        "Host {host}: OSLO operations changed by hand",
        "Host {host}: OSLO-Operationen von Hand verändert",
    ),
    "att.failed": ("{kind} on {target} failed", "{kind} auf {target} fehlgeschlagen"),
    "att.system_status": ("System {system} is {status}", "System {system}: {status}"),
    "att.stopped": ("System {system} is stopped", "System {system} ist gestoppt"),
    "att.long_running": (
        "Activity {id} on {target} runs for {minutes} minutes",
        "Aktivität {id} auf {target} läuft seit {minutes} Minuten",
    ),
    "att.host_unreachable": ("Host {host} cannot be reached", "Host {host} ist nicht erreichbar"),
    "att.schedule_error": (
        "Schedule of {operation} could not start",
        "Einplanung von {operation} konnte nicht starten",
    ),
    "att.stale_discovery": (
        "No discovery of host {host} for {days} days",
        "Host {host}: seit {days} Tagen keine Discovery",
    ),
    "tpl.choose_step": (
        "Choose a step to set its values and its behavior on error.",
        "Einen Schritt wählen, um seine Werte und das Verhalten bei Fehler festzulegen.",
    ),
    "tpl.no_parameters": ("This step has no parameters.", "Dieser Schritt hat keine Parameter."),
    "tpl.param_default": ("default ({value})", "Standard ({value})"),
    "tpl.on_error": ("On error", "Bei Fehler"),
    "tpl.on_error.stop": ("stop the chain", "Kette anhalten"),
    "tpl.on_error.continue": ("go on", "weitermachen"),
    "tpl.on_error.stop_and_start": (
        "stop the chain, start the system",
        "Kette anhalten, System starten",
    ),
    "tpl.saved": ("Saved", "Gespeichert"),
    "tpl.unsaved": ("Not saved", "Nicht gespeichert"),
    "tpl.discard": ("Discard the changes?", "Die Änderungen verwerfen?"),
    "tpl.delete": ("Delete template", "Vorlage löschen"),
    "tpl.delete_confirm": ("Delete this template?", "Diese Vorlage löschen?"),
    "sched.title": ("Schedules", "Einplanen"),
    "sched.empty": ("Not scheduled.", "Nicht eingeplant."),
    "sched.add": ("Plan a run", "Lauf einplanen"),
    "sched.save_first": ("Save the template first.", "Zuerst die Vorlage speichern."),
    "sched.recurrence": ("Recurrence", "Wiederholung"),
    "sched.once": ("once", "einmalig"),
    "sched.daily": ("daily", "täglich"),
    "sched.interval": ("every … minutes", "alle … Minuten"),
    "sched.when": ("Date and time", "Datum und Uhrzeit"),
    "sched.time": ("Time", "Uhrzeit"),
    "sched.weekdays": ("Weekdays", "Wochentage"),
    "sched.timezone_hint": (
        "Times of day in the time zone {zone} of the server.",
        "Uhrzeiten in der Zeitzone {zone} des Servers.",
    ),
    "sched.plan": ("Plan", "Einplanen"),
    "sched.once_at": ("once at {time}", "einmalig am {time}"),
    "sched.daily_at": ("daily at {time} ({days})", "täglich um {time} ({days})"),
    "sched.every": ("every {minutes} minutes", "alle {minutes} Minuten"),
    "sched.next": ("next run {time}", "nächster Lauf {time}"),
    "sched.none_next": ("no further run", "kein weiterer Lauf"),
    "sched.last": ("last run {time}", "letzter Lauf {time}"),
    "sched.pause": ("Pause", "Pausieren"),
    "sched.resume": ("Resume", "Fortsetzen"),
    "sched.delete": ("Delete", "Löschen"),
    "sched.delete_confirm": ("Delete this schedule?", "Diese Einplanung löschen?"),
    "sched.new": ("Plan an operation", "Operation einplanen"),
    "sched.edit": ("Edit schedule", "Einplanung bearbeiten"),
    "sched.intro": (
        "Planned runs of all operations and templates. Each runs with the rights of the user "
        "who planned it, checked again when it is due.",
        "Geplante Läufe aller Operationen und Vorlagen. Jeder läuft mit den Rechten des "
        "Benutzers, der ihn eingeplant hat, beim Start erneut geprüft.",
    ),
    "sched.list_empty": ("Nothing is planned.", "Nichts eingeplant."),
    "sched.next_run": ("Next run", "Nächster Lauf"),
    "sched.name": ("Name", "Name"),
    "sched.clock": (
        "Time zone {zone} · Server time {time}",
        "Zeitzone {zone} · Serverzeit {time}",
    ),
    "sched.count": ("{count} schedules", "{count} Einplanungen"),
    "sched.never_run": ("never run", "noch nie gelaufen"),
    "sched.not_started": ("not started", "nicht gestartet"),
    "sched.unknown_run": ("unknown", "unbekannt"),
    "sched.state.planned": ("planned", "geplant"),
    "sched.state.paused": ("paused", "pausiert"),
    "sched.state.expired": ("expired", "abgelaufen"),
    "sched.delete_selected": ("Delete ({count})", "Löschen ({count})"),
    "sched.delete_selected_confirm": (
        "Delete the {count} selected schedules?",
        "Die {count} ausgewählten Einplanungen löschen?",
    ),
    "ui.select_all": ("Select all", "Alle auswählen"),
    "sched.last_run": ("Last run", "Letzter Lauf"),
    "sched.operation": ("Operation", "Operation"),
    "sched.targets": ("Targets", "Ziele"),
    "sched.planned_by": ("Planned by", "Eingeplant von"),
    "sched.state": ("State", "Zustand"),
    "sched.active": ("active", "aktiv"),
    "sched.paused": ("paused", "pausiert"),
    "sched.choose_operation": ("Choose an operation", "Operation wählen"),
    "sched.choose_targets": ("Choose at least one target.", "Mindestens ein Ziel wählen."),
    "sched.one_target": (
        "This operation runs on one target at a time; choose one.",
        "Diese Operation läuft nur auf einem Ziel; wähle eines.",
    ),
    "sched.fixed": (
        "This template has fixed targets; nothing to choose.",
        "Diese Vorlage hat feste Ziele; hier ist nichts zu wählen.",
    ),
    "sched.template_values": (
        "Values a template asks for at the start are planned in the template editor "
        "(Operations → Operation templates).",
        "Werte, nach denen eine Vorlage beim Start fragt, plant man im Editor der Vorlage "
        "(Operationen → Operationsvorlagen).",
    ),
    "sched.enabled": ("Active", "Aktiv"),
    "notice.schedule_saved": ("Schedule saved.", "Einplanung gespeichert."),
    "notice.schedule_deleted": ("Schedule deleted.", "Einplanung gelöscht."),
    "sched.day.1": ("Mon", "Mo"),
    "sched.day.2": ("Tue", "Di"),
    "sched.day.3": ("Wed", "Mi"),
    "sched.day.4": ("Thu", "Do"),
    "sched.day.5": ("Fri", "Fr"),
    "sched.day.6": ("Sat", "Sa"),
    "sched.day.7": ("Sun", "So"),
    "error.template_key": (
        "Key: lowercase letters, digits and _, not the key of a built-in operation.",
        "Schlüssel: Kleinbuchstaben, Ziffern und _, nicht der einer eingebauten Operation.",
    ),
    "error.template_key_taken": (
        "An operation or template with this key already exists.",
        "Es gibt schon eine Operation oder Vorlage mit diesem Schlüssel.",
    ),
    "error.template_name": ("The template needs a name.", "Die Vorlage braucht einen Namen."),
    "error.template_no_steps": (
        "A template needs at least one step.",
        "Eine Vorlage braucht mindestens einen Schritt.",
    ),
    "error.template_step": ("A step is not valid.", "Ein Schritt ist ungültig."),
    "error.template_cycle": ("The steps wait for each other.", "Die Schritte warten aufeinander."),
    "error.template_selection": (
        "Steps on the selection need the same target type.",
        "Schritte auf der Auswahl brauchen denselben Zieltyp.",
    ),
    "error.template_parallel": (
        "Two locking steps would run at the same time on the same targets.",
        "Zwei sperrende Schritte liefen gleichzeitig auf denselben Zielen.",
    ),
    "error.template_role": (
        "The role is lower than the role the steps need.",
        "Die Rolle ist niedriger als die, die die Schritte brauchen.",
    ),
    "error.schedule_operation": (
        "This operation cannot be planned here.",
        "Diese Operation lässt sich hier nicht einplanen.",
    ),
    "error.schedule_targets": ("Choose the targets.", "Ziele wählen."),
    "error.schedule_time": ("The time is not valid.", "Die Zeitangabe ist ungültig."),
    "error.forbidden": ("Your role does not allow this.", "Deine Rolle erlaubt das nicht."),
}


# Cookie with the chosen language of the interface.
LANGUAGE_COOKIE = "oslo_lang"


def all_texts(language: str) -> dict[str, str]:
    """Every text in ``language``, for the browser interface (unformatted templates)."""
    index = 1 if language == "de" else 0
    return {key: texts[index] for key, texts in TEXTS.items()}


def translate(language: str, key: str, **values: object) -> str:
    """Text for ``key``; unknown keys are returned unchanged so they stay visible."""
    texts = TEXTS.get(key)
    if texts is None:
        return key
    text = texts[1] if language == "de" else texts[0]
    return text.format(**values) if values else text


def pick_language(cookie: str | None, accept_language: str | None) -> str:
    if cookie in LANGUAGES:
        return cookie
    if accept_language:
        first = accept_language.split(",")[0].strip().lower()
        if first.startswith("de"):
            return "de"
    return DEFAULT_LANGUAGE
