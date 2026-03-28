import AppKit
import SwiftUI

// MARK: - Constants & Helpers

private let SYSTEM_PROMPT =
    "你是翻譯工具。規則：若輸入為中文翻譯成英文，否則翻譯成繁體中文。" +
    "僅輸出翻譯結果，不加解釋、引號或其他格式。"

private let userName = ProcessInfo.processInfo.environment["USER"] ?? "user"
private let pidFilePath = "/tmp/translator_gui_\(userName).pid"
private let inputFilePath = "/tmp/translator_gui_\(userName).txt"
private let translateRequestNotification = Notification.Name("TranslateRequest")

private let ansiRegex = try! NSRegularExpression(
    pattern: #"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r"#
)

private func stripANSI(_ s: String) -> String {
    ansiRegex.stringByReplacingMatches(
        in: s, range: NSRange(s.startIndex..., in: s), withTemplate: ""
    )
}

// MARK: - Data Model

struct TranslationTab: Identifiable {
    let id: UUID = UUID()
    let ordinal: Int
    let source: String
    var result: String = ""
    var isTranslating: Bool = true
}

// MARK: - GeminiRunner Actor

actor GeminiRunner {
    private var liveTasks: [UUID: Process] = [:]

    func translate(id: UUID, text: String) async -> String {
        let prompt = "\(SYSTEM_PROMPT)\n\n翻譯：\(text)"
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "")

        return await withCheckedContinuation { continuation in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            proc.arguments = ["gemini", "-m", "gemini-2.5-flash", "-p", prompt]
            proc.environment = env

            let outPipe = Pipe()
            let errPipe = Pipe()
            proc.standardOutput = outPipe
            proc.standardError = errPipe

            proc.terminationHandler = { [weak self] _ in
                Task { await self?.removeLiveTask(id: id) }
                let data = outPipe.fileHandleForReading.readDataToEndOfFile()
                let out = stripANSI(String(data: data, encoding: .utf8) ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if out.isEmpty {
                    let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
                    let err = stripANSI(String(data: errData, encoding: .utf8) ?? "")
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    continuation.resume(returning: err.isEmpty
                        ? "錯誤：無回應"
                        : "錯誤：\(String(err.prefix(200)))")
                } else {
                    continuation.resume(returning: out)
                }
            }

            liveTasks[id] = proc
            do { try proc.run() } catch {
                continuation.resume(returning: "錯誤：\(error.localizedDescription)")
            }
        }
    }

    private func removeLiveTask(id: UUID) {
        liveTasks.removeValue(forKey: id)
    }

    func cancelAll() {
        liveTasks.values.forEach { $0.terminate() }
        liveTasks.removeAll()
    }
}

// MARK: - TabButton View

struct TabButton: View {
    let tab: TranslationTab
    let isActive: Bool
    let onSelect: () -> Void
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Button(action: onSelect) {
                Text("Tab \(tab.ordinal)")
                    .font(.system(size: 12))
                    .padding(.leading, 10)
                    .padding(.trailing, 4)
                    .padding(.vertical, 5)
            }
            .buttonStyle(.plain)

            Button(action: onClose) {
                Text("×")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .padding(.trailing, 8)
                    .padding(.vertical, 5)
            }
            .buttonStyle(.plain)
        }
        .background(isActive ? Color.orange : Color(nsColor: .controlBackgroundColor))
        .cornerRadius(5)
        .overlay(
            RoundedRectangle(cornerRadius: 5)
                .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
        )
    }
}

// MARK: - ContentView

struct ContentView: View {
    let initialText: String
    let runner: GeminiRunner

    @State private var inputText: String = ""
    @State private var tabs: [TranslationTab] = []
    @State private var activeTabID: UUID? = nil
    @State private var fontSize: CGFloat = 14

    private var outputText: String {
        guard let id = activeTabID,
              let tab = tabs.first(where: { $0.id == id }) else { return "" }
        let result = tab.isTranslating ? "翻譯中…" : tab.result
        return "【原文】\n\(tab.source)\n\n────────────────────\n\n【翻譯】\n\(result)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // 輸入區標籤
            Text("輸入文字")
                .font(.system(size: 11))
                .foregroundColor(.secondary)

            // 輸入框
            TextEditor(text: $inputText)
                .font(.system(size: 14))
                .frame(height: 72)
                .scrollContentBackground(.hidden)
                .background(Color(nsColor: .textBackgroundColor))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                )

            // 按鈕列
            HStack(spacing: 8) {
                Button(action: translate) {
                    Text("翻譯  ⌘↩")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(Color(red: 0, green: 0.44, blue: 0.89))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: .command)

                Button("清除") { clearInput() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(6)

                Spacer()

                Button("−") { changeFontSize(-1) }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(6)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))

                Button("+") { changeFontSize(1) }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .cornerRadius(6)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))

                Button("📝 Apple Notes") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/Notes.app"))
                }
                .buttonStyle(.plain)
                .font(.system(size: 12))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color(nsColor: .controlBackgroundColor))
                .cornerRadius(6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
            }

            // Tab 列（有 tab 才顯示）
            if !tabs.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 4) {
                        ForEach(tabs) { tab in
                            TabButton(
                                tab: tab,
                                isActive: tab.id == activeTabID,
                                onSelect: { activeTabID = tab.id },
                                onClose: { closeTab(id: tab.id) }
                            )
                        }
                    }
                    .padding(.vertical, 2)
                }
                .frame(height: 34)
            }

            // 輸出區
            ScrollView {
                Text(outputText)
                    .font(.system(size: fontSize))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
            }
            .frame(maxHeight: .infinity)
            .background(Color(nsColor: .textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
            )
        }
        .padding(14)
        .background(Color(nsColor: .windowBackgroundColor))
        .task {
            if !initialText.isEmpty {
                inputText = initialText
                translate()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: translateRequestNotification)) { notification in
            if let text = notification.object as? String, !text.isEmpty {
                inputText = text
                translate()
            }
        }
    }

    private func translate() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let ordinal = (tabs.map(\.ordinal).max() ?? 0) + 1
        let tab = TranslationTab(ordinal: ordinal, source: text)
        tabs.append(tab)
        activeTabID = tab.id
        inputText = ""

        Task {
            let result = await runner.translate(id: tab.id, text: text)
            if let idx = tabs.firstIndex(where: { $0.id == tab.id }) {
                tabs[idx].result = result
                tabs[idx].isTranslating = false
            }
        }
    }

    private func clearInput() {
        inputText = ""
    }

    private func closeTab(id: UUID) {
        guard let idx = tabs.firstIndex(where: { $0.id == id }) else { return }
        tabs.remove(at: idx)
        if activeTabID == id {
            activeTabID = tabs.isEmpty ? nil : tabs[max(0, idx - 1)].id
        }
    }

    private func changeFontSize(_ delta: CGFloat) {
        fontSize = max(8, min(32, fontSize + delta))
    }
}

// MARK: - AppDelegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let runner = GeminiRunner()
    var sigusr1Source: DispatchSourceSignal?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let initialText = ProcessInfo.processInfo.environment["TRANSLATOR_INITIAL_TEXT"] ?? ""

        let contentView = ContentView(initialText: initialText, runner: runner)
        let hosting = NSHostingController(rootView: contentView)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 1050),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "隨身翻譯"
        window.level = .floating
        window.minSize = NSSize(width: 380, height: 600)
        window.contentViewController = hosting
        window.center()
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 { NSApp.terminate(nil); return nil }
            return event
        }

        // 寫入 PID 檔
        try? "\(ProcessInfo.processInfo.processIdentifier)"
            .write(toFile: pidFilePath, atomically: true, encoding: .utf8)

        // 監聽 SIGUSR1：收到後讀 input 檔並觸發翻譯
        signal(SIGUSR1, SIG_IGN)
        let src = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
        src.setEventHandler { [weak self] in
            let text = (try? String(contentsOfFile: inputFilePath, encoding: .utf8))?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !text.isEmpty {
                NotificationCenter.default.post(name: translateRequestNotification, object: text)
            }
            self?.window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        src.resume()
        sigusr1Source = src
    }

    func applicationWillTerminate(_ notification: Notification) {
        try? FileManager.default.removeItem(atPath: pidFilePath)
        Task { await runner.cancelAll() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

// MARK: - Entry Point

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
