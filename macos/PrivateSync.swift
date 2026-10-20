import AppKit
import EventKit
import Security
import Foundation
import Darwin

let appID = "fr.polytech.calendar.private"
let calendarTitle = "Polytech — EDT privé"
let privateRoot = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/PolytechCalendarPrivate", isDirectory: true)

struct SyncError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}
struct Credentials: Codable { var username: String; var password: String }
struct Appointment: Equatable {
    var uid: String
    var title: String
    var start: Date
    var end: Date
    var location: String
    var notes: String
}

func decodeICS(_ value: String) -> String {
    var result = "", escape = false
    for char in value {
        if escape { result.append(char == "n" || char == "N" ? "\n" : char); escape = false }
        else if char == "\\" { escape = true }
        else { result.append(char) }
    }
    if escape { result.append("\\") }
    return result
}

func readCalendar(_ data: Data) throws -> [Appointment] {
    guard let text = String(data: data, encoding: .utf8),
          text.hasPrefix("BEGIN:VCALENDAR"), text.trimmingCharacters(in: .whitespacesAndNewlines).hasSuffix("END:VCALENDAR") else {
        throw SyncError(message: "Le calendrier local est incomplet. Aucun événement iCloud n’a été modifié.")
    }
    let unfolded = text.replacingOccurrences(of: "\r\n ", with: "").replacingOccurrences(of: "\r\n\t", with: "")
    let dateParser = DateFormatter()
    dateParser.locale = Locale(identifier: "en_US_POSIX")
    dateParser.calendar = Calendar(identifier: .gregorian)
    dateParser.timeZone = TimeZone(secondsFromGMT: 0)
    dateParser.dateFormat = "yyyyMMdd'T'HHmmss'Z'"
    dateParser.isLenient = false
    var result: [Appointment] = [], fields: [String: String]? = nil
    var seen: Set<String> = []
    for raw in unfolded.components(separatedBy: .newlines) {
        let line = raw.trimmingCharacters(in: .newlines)
        if line == "BEGIN:VEVENT" {
            guard fields == nil else { throw SyncError(message: "Structure du calendrier invalide.") }
            fields = [:]
        } else if line == "END:VEVENT" {
            guard let f = fields, let uid = f["UID"], !uid.isEmpty,
                  seen.insert(uid).inserted, let title = f["SUMMARY"],
                  let startText = f["DTSTART"], let endText = f["DTEND"],
                  let start = dateParser.date(from: startText), let end = dateParser.date(from: endText), end > start else {
                throw SyncError(message: "Un événement local est invalide ou dupliqué. Synchronisation annulée.")
            }
            result.append(Appointment(uid: uid, title: decodeICS(title), start: start, end: end,
                                      location: decodeICS(f["LOCATION"] ?? ""),
                                      notes: decodeICS(f["DESCRIPTION"] ?? "") + "\nSource : Polyflex et calendrier officiel IIM 2026–2027."))
            fields = nil
        } else if fields != nil, let colon = line.firstIndex(of: ":") {
            let key = String(line[..<colon]), value = String(line[line.index(after: colon)...])
            guard fields?[key] == nil else { throw SyncError(message: "Propriété de calendrier dupliquée.") }
            fields?[key] = value
        }
    }
    guard fields == nil, !result.isEmpty else { throw SyncError(message: "Le calendrier reçu ne contient aucun événement valide.") }
    return result
}

func sourceUID(_ url: URL?) -> String? {
    guard let url = url, url.scheme == "polytech-private", url.host == "event" else { return nil }
    return url.lastPathComponent
}

func keychainLoad() throws -> Credentials? {
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: appID, kSecAttrAccount as String: "polyflex",
        kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = item as? Data else {
        throw SyncError(message: "Le trousseau est verrouillé ou l’accès a été refusé. Ouvre l’application pour réessayer.")
    }
    return try JSONDecoder().decode(Credentials.self, from: data)
}

func keychainSave(_ value: Credentials) throws {
    let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: appID, kSecAttrAccount as String: "polyflex"]
    let data = try JSONEncoder().encode(value)
    let update = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if update == errSecItemNotFound {
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrLabel as String] = "Polytech Sync privé — Polyflex"
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
            throw SyncError(message: "Impossible d’enregistrer la connexion dans le trousseau.")
        }
    } else if update != errSecSuccess {
        throw SyncError(message: "Impossible de mettre à jour la connexion dans le trousseau.")
    }
}

func execute(_ executable: String, _ arguments: [String], input: Data? = nil) async throws -> (Int32, String) {
    try await Task.detached(priority: .utility) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let output = Pipe(), source = Pipe()
        process.standardOutput = output
        process.standardError = output
        if input != nil { process.standardInput = source }
        try process.run()
        if let data = input {
            source.fileHandleForWriting.write(data)
            try? source.fileHandleForWriting.close()
        }
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (process.terminationStatus, String(data: data, encoding: .utf8) ?? "")
    }.value
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let store = EKEventStore()
    var window: NSWindow!
    let username = NSTextField(string: "")
    let password = NSSecureTextField(string: "")
    let status = NSTextField(wrappingLabelWithString: "Prêt à connecter ton emploi du temps privé.")
    var actionButton: NSButton!
    var working = false
    let background = CommandLine.arguments.contains("--sync")

    func applicationDidFinishLaunching(_ notification: Notification) {
        if background {
            Task {
                do {
                    guard let credentials = try keychainLoad() else { throw SyncError(message: "Connexion non configurée.") }
                    let count = try await synchronize(credentials, interactive: false)
                    print("Synchronisation iCloud privée réussie : \(count) événements.")
                } catch {
                    logFailure(error.localizedDescription)
                    fputs("Synchronisation privée interrompue : \(error.localizedDescription)\n", stderr)
                    exit(1)
                }
                NSApp.terminate(nil)
            }
        } else { createWindow() }
    }

    func label(_ text: String, size: CGFloat = 13, bold: Bool = false) -> NSTextField {
        let label = NSTextField(wrappingLabelWithString: text)
        label.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
        label.widthAnchor.constraint(equalToConstant: 564).isActive = true
        return label
    }

    func createWindow() {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu(), appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quitter Polytech Sync privé", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let item = NSMenuItem(); item.submenu = appMenu; menu.addItem(item); NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 660, height: 640),
            styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Polytech Sync privé"
        window.isReleasedWhenClosed = false
        let stack = NSStackView()
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 44),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -44),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 32)])
        stack.addArrangedSubview(label("POLYTECH · CALENDRIER ICLOUD", size: 11, bold: true))
        stack.addArrangedSubview(label("Ton EDT, en privé.", size: 30, bold: true))
        stack.addArrangedSubview(label("Polyflex → Calendrier iCloud → Mac et iPhone\nUn calendrier dédié. Aucun lien public. Aucun mot de passe sur GitHub.", size: 14))
        let divider = NSBox(); divider.boxType = .separator; stack.addArrangedSubview(divider)
        stack.addArrangedSubview(label("Compte Polyflex", size: 13, bold: true))
        username.placeholderString = "Adresse universitaire"; password.placeholderString = "Mot de passe Polyflex"
        for field in [username, password] {
            field.font = .systemFont(ofSize: 14); field.bezelStyle = .roundedBezel
            field.translatesAutoresizingMaskIntoConstraints = false
            field.widthAnchor.constraint(equalToConstant: 564).isActive = true
            field.heightAnchor.constraint(equalToConstant: 30).isActive = true
            stack.addArrangedSubview(field)
        }
        if let saved = try? keychainLoad() {
            username.stringValue = saved.username
            password.placeholderString = "Connexion enregistrée dans le trousseau"
        }
        stack.addArrangedSubview(label("L’activation enregistre la connexion dans le trousseau de ce Mac, crée « Polytech — EDT privé » dans iCloud et installe une actualisation toutes les 30 minutes. macOS demandera l’accès aux calendriers.", size: 12))
        actionButton = NSButton(title: "Activer et synchroniser en privé", target: self, action: #selector(activate))
        actionButton.bezelStyle = .rounded; actionButton.controlSize = .large
        actionButton.keyEquivalent = "\r"; stack.addArrangedSubview(actionButton)
        status.font = .systemFont(ofSize: 13); status.widthAnchor.constraint(equalToConstant: 564).isActive = true
        status.maximumNumberOfLines = 5; stack.addArrangedSubview(status)
        let actions = NSStackView(); actions.orientation = .horizontal; actions.spacing = 12
        let openCalendar = NSButton(title: "Ouvrir Calendrier", target: self, action: #selector(showCalendar))
        let disable = NSButton(title: "Arrêter l’actualisation", target: self, action: #selector(stopSchedule))
        openCalendar.bezelStyle = .rounded; disable.bezelStyle = .rounded
        actions.addArrangedSubview(openCalendar); actions.addArrangedSubview(disable); stack.addArrangedSubview(actions)
        stack.addArrangedSubview(label("Le Mac récupère les changements quand il est allumé et connecté. L’iPhone garde le dernier EDT synchronisé. Masque l’ancien abonnement Polytech pour éviter les doublons.", size: 11))
        loadLastStatus()
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }

    func loadLastStatus() {
        if let data = try? Data(contentsOf: privateRoot.appendingPathComponent("native-status.json")),
           let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let message = value["message"] as? String { status.stringValue = message }
    }

    @objc func activate() {
        guard !working else { return }
        Task {
            do {
                let saved = try keychainLoad()
                let login = username.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
                let secret = password.stringValue.isEmpty && saved?.username == login ? (saved?.password ?? "") : password.stringValue
                guard !login.isEmpty, !secret.isEmpty else { throw SyncError(message: "Renseigne ton adresse et ton mot de passe Polyflex.") }
                working = true; actionButton.isEnabled = false
                defer { working = false; actionButton.isEnabled = true }
                status.stringValue = "Vérification de l’accès iCloud, puis collecte des 52 semaines Polyflex…"
                let credentials = Credentials(username: login, password: secret)
                let count = try await synchronize(credentials, interactive: true)
                try keychainSave(credentials)
                try await installSchedule()
                password.stringValue = ""; password.placeholderString = "Connexion enregistrée dans le trousseau"
                status.stringValue = "Activé : \(count) événements dans « \(calendarTitle) ». Actualisation toutes les 30 minutes sur ce Mac ; iCloud les synchronise avec ton iPhone."
                saveNativeStatus(status.stringValue)
                actionButton.title = "Synchroniser maintenant"
            } catch {
                status.stringValue = error.localizedDescription
                status.textColor = .systemOrange
                logFailure(error.localizedDescription)
            }
        }
    }

    func requireCalendarAccess(interactive: Bool) async throws {
        let auth = EKEventStore.authorizationStatus(for: .event)
        if auth == .fullAccess { return }
        guard interactive else { throw SyncError(message: "Accès Calendrier non autorisé. Ouvre Polytech Sync privé pour l’accorder.") }
        let allowed = try await store.requestFullAccessToEvents()
        guard allowed else { throw SyncError(message: "Autorise Polytech Sync privé dans Réglages Système → Confidentialité et sécurité → Calendriers, puis réessaie.") }
    }

    func destinationCalendar() throws -> EKCalendar {
        func isICloud(_ source: EKSource) -> Bool {
            source.sourceType == .calDAV && source.title.localizedCaseInsensitiveContains("icloud")
        }
        if let id = UserDefaults.standard.string(forKey: "calendarID"), let existing = store.calendar(withIdentifier: id) {
            guard existing.allowsContentModifications, isICloud(existing.source) else {
                throw SyncError(message: "Le calendrier dédié n’est plus modifiable dans iCloud. Aucun autre calendrier ne sera utilisé.")
            }
            return existing
        }
        guard let source = store.sources.first(where: isICloud) else {
            throw SyncError(message: "Aucun compte Calendrier iCloud disponible. Active Calendriers dans les réglages iCloud du Mac, puis réessaie.")
        }
        // Retrouver uniquement un calendrier précédemment créé par cette application.
        // Aucun calendrier utilisateur homonyme n’est adopté ni nettoyé.
        let calendar = EKCalendar(for: .event, eventStore: store)
        calendar.title = calendarTitle; calendar.source = source; calendar.cgColor = NSColor.systemTeal.cgColor
        try store.saveCalendar(calendar, commit: true)
        UserDefaults.standard.set(calendar.calendarIdentifier, forKey: "calendarID")
        return calendar
    }

    func synchronize(_ credentials: Credentials, interactive: Bool) async throws -> Int {
        try FileManager.default.createDirectory(at: privateRoot, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let lockPath = privateRoot.appendingPathComponent("sync.lock").path
        let fd = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard fd >= 0 else { throw SyncError(message: "Impossible de verrouiller la synchronisation locale.") }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { close(fd); throw SyncError(message: "Une synchronisation est déjà en cours. Réessaie dans un instant.") }
        defer { flock(fd, LOCK_UN); close(fd) }
        try await requireCalendarAccess(interactive: interactive)
        let calendar = try destinationCalendar()
        guard let resources = Bundle.main.resourceURL else { throw SyncError(message: "Application incomplète.") }
        let python = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
        guard let python = python else { throw SyncError(message: "Python 3 est nécessaire pour la collecte Polyflex.") }
        let script = resources.appendingPathComponent("engine/polyflex_sync.py").path
        let (code, output) = try await execute(python, [script, "--credentials-stdin", "--output-root", privateRoot.path],
                                               input: JSONEncoder().encode(credentials))
        guard code == 0 else {
            let reason = output.components(separatedBy: .newlines).last { $0.hasPrefix("Synchronisation annulée :") }
            throw SyncError(message: reason ?? "La collecte Polyflex a échoué. Les événements iCloud existants sont conservés.")
        }
        let incoming = try readCalendar(Data(contentsOf: privateRoot.appendingPathComponent("docs/personal.ics")))
        let start = ISO8601DateFormatter().date(from: "2026-08-30T00:00:00Z")!
        let end = ISO8601DateFormatter().date(from: "2027-08-31T23:59:59Z")!
        let existing = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: [calendar]))
        var managed: [String: [EKEvent]] = [:]
        for event in existing {
            if let uid = sourceUID(event.url) { managed[uid, default: []].append(event) }
        }
        let incomingIDs = Set(incoming.map(\.uid))
        do {
            for value in incoming {
                let matches = managed[value.uid] ?? []
                let event = matches.first ?? EKEvent(eventStore: store)
                if matches.isEmpty { event.calendar = calendar }
                if event.title != value.title || event.startDate != value.start || event.endDate != value.end ||
                    (event.location ?? "") != value.location || (event.notes ?? "") != value.notes || event.isAllDay {
                    event.title = value.title; event.startDate = value.start; event.endDate = value.end
                    event.timeZone = TimeZone(identifier: "Europe/Paris"); event.isAllDay = false
                    event.location = value.location; event.notes = value.notes
                    event.url = URL(string: "polytech-private://event/" + value.uid)
                    try store.save(event, span: .thisEvent, commit: false)
                }
                // Nettoyage des doublons créés par l’application uniquement.
                for duplicate in matches.dropFirst() { try store.remove(duplicate, span: .thisEvent, commit: false) }
            }
            for (uid, events) in managed where !incomingIDs.contains(uid) {
                for event in events { try store.remove(event, span: .thisEvent, commit: false) }
            }
            try store.commit()
        } catch { store.reset(); throw error }
        let date = DateFormatter.localizedString(from: Date(), dateStyle: .medium, timeStyle: .short)
        saveNativeStatus("Dernière synchronisation iCloud réussie : \(date). \(incoming.count) événements privés.")
        return incoming.count
    }

    func installedApp() throws -> URL {
        let directory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = directory.appendingPathComponent("Polytech Sync privé.app", isDirectory: true)
        let current = Bundle.main.bundleURL
        if current.standardizedFileURL == target.standardizedFileURL { return target }
        if FileManager.default.fileExists(atPath: target.path) {
            guard Bundle(url: target)?.bundleIdentifier == appID else {
                throw SyncError(message: "Un autre logiciel porte déjà ce nom dans Applications. L’installation automatique a été arrêtée.")
            }
            // L’app existante peut être remplacée seulement s’il s’agit du même outil.
            let backup = directory.appendingPathComponent("Polytech Sync privé précédente.app", isDirectory: true)
            if FileManager.default.fileExists(atPath: backup.path) { try FileManager.default.removeItem(at: backup) }
            try FileManager.default.moveItem(at: target, to: backup)
        }
        try FileManager.default.copyItem(at: current, to: target)
        return target
    }

    func installSchedule() async throws {
        let installed = try installedApp()
        let executable = installed.appendingPathComponent("Contents/MacOS/PolytechPrivateSync").path
        let directory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(appID + ".plist")
        let settings: [String: Any] = ["Label": appID, "ProgramArguments": [executable, "--sync"],
            "StartInterval": 1800, "RunAtLoad": true,
            "StandardOutPath": privateRoot.appendingPathComponent("sync.log").path,
            "StandardErrorPath": privateRoot.appendingPathComponent("sync.log").path,
            "ProcessType": "Background"]
        let data = try PropertyListSerialization.data(fromPropertyList: settings, format: .xml, options: 0)
        try data.write(to: file, options: .atomic)
        let domain = "gui/\(getuid())"
        _ = try? await execute("/bin/launchctl", ["bootout", domain + "/" + appID])
        let (code, _) = try await execute("/bin/launchctl", ["bootstrap", domain, file.path])
        guard code == 0 else { throw SyncError(message: "Les cours ont été synchronisés, mais l’actualisation automatique n’a pas pu démarrer. Réessaie l’activation.") }
    }

    func saveNativeStatus(_ message: String) {
        let value: [String: Any] = ["message": message, "date": ISO8601DateFormatter().string(from: Date())]
        if let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]) {
            try? data.write(to: privateRoot.appendingPathComponent("native-status.json"), options: .atomic)
        }
    }
    func logFailure(_ message: String) {
        try? FileManager.default.createDirectory(at: privateRoot, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        saveNativeStatus("Actualisation interrompue : \(message) Derniers événements conservés.")
    }
    @objc func showCalendar() { NSWorkspace.shared.open(URL(string: "ical://")!) }
    @objc func stopSchedule() {
        Task {
            _ = try? await execute("/bin/launchctl", ["bootout", "gui/\(getuid())/" + appID])
            let path = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/" + appID + ".plist")
            try? FileManager.default.removeItem(at: path)
            status.stringValue = "Actualisation arrêtée. Les cours iCloud et la connexion du trousseau sont conservés."
            saveNativeStatus(status.stringValue)
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

if CommandLine.arguments.contains("--validate-ics"), let path = CommandLine.arguments.last {
    do {
        let events = try readCalendar(Data(contentsOf: URL(fileURLWithPath: path)))
        print("Calendrier valide : \(events.count) événements, \(Set(events.map(\.uid)).count) UID uniques.")
    } catch { fputs("\(error.localizedDescription)\n", stderr); exit(1) }
} else {
    MainActor.assumeIsolated {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        if CommandLine.arguments.contains("--sync") { app.setActivationPolicy(.prohibited) }
        app.run()
    }
}
