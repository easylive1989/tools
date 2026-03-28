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
private let pasteToInputNotification = Notification.Name("PasteToInput")

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

// MARK: - Shapes

/// 三邊框（上、左、右），底部開口，供 active tab 使用
private struct ThreeSidedBorder: Shape {
    let cornerRadius: CGFloat
    func path(in rect: CGRect) -> Path {
        let r = cornerRadius
        var p = Path()
        p.move(to: CGPoint(x: 0, y: rect.maxY + 1))
        p.addLine(to: CGPoint(x: 0, y: r))
        p.addQuadCurve(to: CGPoint(x: r, y: 0), control: .zero)
        p.addLine(to: CGPoint(x: rect.maxX - r, y: 0))
        p.addQuadCurve(to: CGPoint(x: rect.maxX, y: r),
                       control: CGPoint(x: rect.maxX, y: 0))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY + 1))
        return p
    }
}

/// 只有上方兩個圓角的形狀
private struct TopRoundedShape: Shape {
    let cornerRadius: CGFloat
    func path(in rect: CGRect) -> Path {
        let r = cornerRadius
        var p = Path()
        p.move(to: CGPoint(x: 0, y: rect.maxY))
        p.addLine(to: CGPoint(x: 0, y: r))
        p.addQuadCurve(to: CGPoint(x: r, y: 0), control: .zero)
        p.addLine(to: CGPoint(x: rect.maxX - r, y: 0))
        p.addQuadCurve(to: CGPoint(x: rect.maxX, y: r),
                       control: CGPoint(x: rect.maxX, y: 0))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        p.closeSubpath()
        return p
    }
}

// MARK: - TabButton View

private let tabHeight: CGFloat = 30

struct TabButton: View {
    let tab: TranslationTab
    let isActive: Bool
    let onSelect: () -> Void
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Button(action: onSelect) {
                Text("Tab \(tab.ordinal)")
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                    .foregroundColor(isActive ? Color(red: 0.2, green: 0.44, blue: 0.9) : .secondary)
                    .padding(.leading, 12)
                    .padding(.trailing, 4)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.plain)

            Button(action: onClose) {
                Text("×")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.trailing, 10)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.plain)
        }
        .frame(height: tabHeight)
        .background(
            isActive
                ? Color(nsColor: .windowBackgroundColor)
                : Color(nsColor: .controlColor)
        )
        .clipShape(TopRoundedShape(cornerRadius: 6))
        .overlay(
            Group {
                if isActive {
                    ThreeSidedBorder(cornerRadius: 6)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                } else {
                    TopRoundedShape(cornerRadius: 6)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                }
            }
        )
        .zIndex(isActive ? 1 : 0)
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
            // 第一排：輸入框 + 翻譯按鈕 + 📝
            HStack(spacing: 8) {
                TextEditor(text: $inputText)
                    .font(.system(size: 14))
                    .frame(height: 28)
                    .scrollContentBackground(.hidden)
                    .background(Color(nsColor: .textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                    )

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

                Button("📝") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/Notes.app"))
                }
                .buttonStyle(.plain)
                .font(.system(size: 14))
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color(nsColor: .controlBackgroundColor))
                .cornerRadius(6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
            }

            // Tab 列 + 輸出區（ZStack 讓 active tab 與內容框融合）
            ZStack(alignment: .topLeading) {
                // 輸出區（內容框）— 永遠預留 tabHeight 空間給上方列
                ScrollView {
                    Text(outputText)
                        .font(.system(size: fontSize))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(nsColor: .textBackgroundColor))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                )
                .padding(.top, tabHeight - 1)

                // Tab 列（疊在內容框頂端）+ −/+ 靠右
                HStack(spacing: 4) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(alignment: .bottom, spacing: 2) {
                            ForEach(tabs) { tab in
                                TabButton(
                                    tab: tab,
                                    isActive: tab.id == activeTabID,
                                    onSelect: { activeTabID = tab.id },
                                    onClose: { closeTab(id: tab.id) }
                                )
                            }
                        }
                    }
                    .layoutPriority(0)

                    Button("−") { changeFontSize(-1) }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                        .layoutPriority(1)

                    Button("+") { changeFontSize(1) }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                        .layoutPriority(1)
                }
                .frame(height: tabHeight)
            }
            .frame(maxHeight: .infinity)
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
        .onReceive(NotificationCenter.default.publisher(for: pasteToInputNotification)) { notification in
            if let text = notification.object as? String {
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
        setupMenu()

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
            // Cmd+V 且輸入框未 focus → 強制貼到輸入框
            if event.keyCode == 9 && event.modifierFlags.contains(.command),
               !(NSApp.keyWindow?.firstResponder is NSTextView),
               let text = NSPasteboard.general.string(forType: .string) {
                NotificationCenter.default.post(name: pasteToInputNotification, object: text)
                return nil
            }
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

    private func setupMenu() {
        let mainMenu = NSMenu()

        // App menu
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "結束隨身翻譯", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu

        // Edit menu（Cmd+V/C/X/A/Z 等都需要這個）
        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenuItem.submenu = editMenu

        NSApp.mainMenu = mainMenu
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
