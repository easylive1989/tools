import SwiftUI

@main
struct TravelEditorApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .frame(minWidth: 800, minHeight: 500)
        }
        .commands {
            FileCommands(store: store)
        }
    }
}

// MARK: - App Store (global state)

@MainActor
class AppStore: ObservableObject {
    @Published var document: MarkdownFile? = nil
    @Published var isDirty = false

    // Open file via NSOpenPanel
    func openFile() {
        let panel = NSOpenPanel()
        panel.title = "開啟旅遊行程"
        panel.allowedContentTypes = [.plainText]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.nameFieldLabel = "itinerary.md"

        if panel.runModal() == .OK, let url = panel.url {
            loadFile(from: url)
        }
    }

    // Load from URL
    func loadFile(from url: URL) {
        do {
            let text = try String(contentsOf: url, encoding: .utf8)
            let itinerary = MarkdownParser.parse(from: text)
            document = MarkdownFile(url: url, itinerary: itinerary)
            isDirty = false
        } catch {
            NSAlert.show(message: "無法開啟檔案", info: error.localizedDescription)
        }
    }

    // Save (overwrite existing file)
    func save() {
        guard let doc = document else { saveAs(); return }
        writeFile(itinerary: doc.itinerary, to: doc.url)
    }

    // Save As
    func saveAs() {
        guard let doc = document else { return }
        let panel = NSSavePanel()
        panel.title = "儲存行程"
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = doc.url.lastPathComponent

        if panel.runModal() == .OK, let url = panel.url {
            writeFile(itinerary: doc.itinerary, to: url)
            document?.url = url
        }
    }

    private func writeFile(itinerary: Itinerary, to url: URL) {
        let text = MarkdownExporter.export(itinerary)
        do {
            try text.write(to: url, atomically: true, encoding: .utf8)
            isDirty = false
        } catch {
            NSAlert.show(message: "儲存失敗", info: error.localizedDescription)
        }
    }

    // Called when itinerary changes
    func markDirty() {
        isDirty = true
    }
}

// MARK: - MarkdownFile

struct MarkdownFile {
    var url: URL
    var itinerary: Itinerary
}

// MARK: - File Commands

struct FileCommands: Commands {
    let store: AppStore

    var body: some Commands {
        CommandGroup(replacing: .newItem) {
            Button("開新旅程") {
                store.document = MarkdownFile(
                    url: URL(fileURLWithPath: "untitled.md"),
                    itinerary: Itinerary(title: "新旅程", subtitle: "")
                )
            }
            .keyboardShortcut("n")

            Button("開啟…") { store.openFile() }
                .keyboardShortcut("o")
        }

        CommandGroup(replacing: .saveItem) {
            Button("儲存") { store.save() }
                .keyboardShortcut("s")

            Button("另存新檔…") { store.saveAs() }
                .keyboardShortcut("s", modifiers: [.command, .shift])
        }
    }
}

// MARK: - NSAlert Helper

extension NSAlert {
    static func show(message: String, info: String) {
        let alert = NSAlert()
        alert.messageText = message
        alert.informativeText = info
        alert.runModal()
    }
}
