import AppKit
import ApplicationServices
import AVFoundation
import SwiftUI

// MARK: - CLI Mode: --get-selection
// 透過 Accessibility API 讀取當前 focused element 的選取文字，印到 stdout 後離開。
// 首次呼叫會觸發系統授權提示（系統設定 → 隱私權 → 輔助使用）。

if CommandLine.arguments.contains("--get-selection") {
    let promptKey = "AXTrustedCheckOptionPrompt" as CFString
    _ = AXIsProcessTrustedWithOptions([promptKey: true] as CFDictionary)

    // 讀出 translator_app GUI instance 的 PID（若有在跑），之後排除它，
    // 避免使用者在 translator_app 輸出框裡選了文字時，AX 回傳到自己。
    let selfPIDPath = "/tmp/translator_gui_\(ProcessInfo.processInfo.environment["USER"] ?? "user").pid"
    let selfPID = pid_t((try? String(contentsOfFile: selfPIDPath, encoding: .utf8))?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "") ?? 0

    // 等 focus 從 Raycast / translator_app 回到來源 app（最多 500ms）
    var frontmostPID: pid_t = 0
    for _ in 0..<10 {
        if let app = NSWorkspace.shared.frontmostApplication,
           app.bundleIdentifier != "com.raycast.macos",
           app.processIdentifier != selfPID {
            frontmostPID = app.processIdentifier
            break
        }
        Thread.sleep(forTimeInterval: 0.05)
    }

    if frontmostPID > 0 {
        let appEl = AXUIElementCreateApplication(frontmostPID)
        var focused: CFTypeRef?
        if AXUIElementCopyAttributeValue(
            appEl, kAXFocusedUIElementAttribute as CFString, &focused
        ) == .success, let element = focused {
            var value: CFTypeRef?
            if AXUIElementCopyAttributeValue(
                element as! AXUIElement, kAXSelectedTextAttribute as CFString, &value
            ) == .success, let text = value as? String {
                print(text, terminator: "")
            }
        }
    }
    exit(0)
}

// MARK: - Constants & Helpers

private let SYSTEM_PROMPT =
    "你是翻譯工具。將輸入翻譯成繁體中文。" +
    "僅輸出翻譯結果，不加解釋、引號或額外格式。" +
    "保留原文的排版結構：若原文是 Markdown 格式（如標題、粗體、清單等），翻譯結果也須維持相同的 Markdown 格式；" +
    "若原文以換行分隔段落，翻譯結果也須在對應位置以相同方式換行。"

private let SUMMARY_PROMPT = """
你是一個專業的內容總結工具。請閱讀以下內容，並以繁體中文產生結構化總結。

輸出格式：
## 重點摘要
- （列出 3-5 個關鍵重點）

## 關鍵論點
- （列出核心論點與支持依據）

## 結論
（一段簡潔的結論總結）

規則：
- 一律使用繁體中文輸出
- 保持客觀，忠於原文
- 簡潔有力，避免冗長
- 僅輸出 Markdown 內容，不要加任何前言、結語或程式碼圍欄
"""

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

private let vocabularyFilePath: String = {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    return "\(home)/Library/Mobile Documents/com~apple~CloudDocs/vocabulary.md"
}()

// MARK: - Data Model

struct TranslationTab: Identifiable {
    let id: UUID = UUID()
    let ordinal: Int
    let source: String
    var result: String = ""
    var isTranslating: Bool = true
    var summary: String = ""
    var isSummarizing: Bool = false
    var hasSummary: Bool = false
}

// MARK: - VocabularyStore

@MainActor
class VocabularyStore: ObservableObject {
    @Published var words: [String] = []

    func load() {
        let content = (try? String(contentsOfFile: vocabularyFilePath, encoding: .utf8)) ?? ""
        words = content.components(separatedBy: "\n")
            .filter { $0.hasPrefix("- ") }
            .map { String($0.dropFirst(2)).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    func add(_ input: String) {
        let word = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !word.isEmpty else { return }
        let lower = word.lowercased()
        guard !words.contains(where: { $0.lowercased() == lower }) else { return }
        words.append(word)
        save()
    }

    func remove(at index: Int) {
        guard words.indices.contains(index) else { return }
        words.remove(at: index)
        save()
    }

    private func save() {
        let existing = (try? String(contentsOfFile: vocabularyFilePath, encoding: .utf8)) ?? ""
        let lines = existing.components(separatedBy: "\n")
        var firstBullet: Int? = nil
        var lastBullet: Int? = nil
        for (i, line) in lines.enumerated() {
            if line.hasPrefix("- ") {
                if firstBullet == nil { firstBullet = i }
                lastBullet = i
            }
        }
        let newBullets = words.map { "- \($0)" }
        var result: [String]
        if let first = firstBullet, let last = lastBullet {
            let suffix = last + 1 < lines.count ? Array(lines[(last + 1)...]) : []
            result = Array(lines[..<first]) + newBullets + suffix
        } else if lines == [""] || lines.isEmpty {
            result = newBullets
        } else {
            result = lines + [""] + newBullets
        }
        let content = result.joined(separator: "\n")
        let dir = (vocabularyFilePath as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try? content.write(toFile: vocabularyFilePath, atomically: true, encoding: .utf8)
    }
}

// MARK: - VocabularyPopover

struct VocabularyPopover: View {
    @ObservedObject var store: VocabularyStore
    @State private var newWord: String = ""
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                TextField("新增單字…", text: $newWord)
                    .textFieldStyle(.roundedBorder)
                    .focused($inputFocused)
                    .onSubmit {
                        store.add(newWord)
                        newWord = ""
                    }
                Text("↵")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .padding(12)

            Divider()

            if store.words.isEmpty {
                Text("還沒有任何單字 — 在上方輸入框新增")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                    .padding(16)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(store.words.enumerated()), id: \.offset) { index, word in
                            HStack {
                                Text("• \(word)")
                                    .font(.system(size: 13))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                Button("×") {
                                    store.remove(at: index)
                                }
                                .buttonStyle(.plain)
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                        }
                    }
                }
                .frame(maxHeight: 300)

                Divider()

                Text("共 \(store.words.count) 個")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
            }
        }
        .frame(width: 280)
        .onAppear { inputFocused = true }
    }
}

// MARK: - ClaudeRunner Actor

actor ClaudeRunner {
    private var liveTasks: [UUID: Process] = [:]

    func translate(id: UUID, text: String) async -> String {
        let prompt = "\(SYSTEM_PROMPT)\n\n翻譯：\(text)"
        return await run(id: id, prompt: prompt)
    }

    func summarize(id: UUID, text: String) async -> String {
        let prompt = "\(SUMMARY_PROMPT)\n\n內容：\n\(text)"
        return await run(id: id, prompt: prompt)
    }

    func explainWord(id: UUID, word: String) async -> String {
        let prompt = """
        你是英文單字解析助手。針對以下單字提供深入的繁體中文解析，使用 Markdown 標題格式輸出，依下列章節組織內容（每個章節都要有，內容務求精準實用）：

        ## 中文意思與詞性
        列出主要詞性與對應的中文意思。

        ## 常見用法／搭配詞
        列出常見的搭配詞（collocations）與用法說明。

        ## 例句
        提供 2-3 個英中對照的例句。

        ## 同義／反義字
        列出主要的同義字與反義字。

        ## 易混淆字辨析
        列出與此字容易混淆的字並說明差異。

        僅輸出 Markdown 內容，不要加任何前言、結語或程式碼圍欄。

        單字：\(word)
        """
        return await run(id: id, prompt: prompt)
    }

    private func run(id: UUID, prompt: String) async -> String {
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "")

        return await withCheckedContinuation { continuation in
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            proc.arguments = ["claude", "-p", prompt, "--model", "sonnet"]
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
                ? Color(nsColor: .controlBackgroundColor)
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

// MARK: - SelectableTextView

struct SelectableTextView: NSViewRepresentable {
    let text: String
    let fontSize: CGFloat
    let store: VocabularyStore

    func makeCoordinator() -> Coordinator {
        Coordinator(store: store)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let textView = VocabularyTextView()
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = true
        textView.backgroundColor = .textBackgroundColor
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.coordinator = context.coordinator

        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.backgroundColor = .clear
        scrollView.documentView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? VocabularyTextView else { return }
        if textView.string != text {
            textView.string = text
        }
        textView.font = .systemFont(ofSize: fontSize)
        context.coordinator.store = store
    }

    class Coordinator {
        var store: VocabularyStore
        init(store: VocabularyStore) { self.store = store }
    }
}

class VocabularyTextView: NSTextView {
    weak var coordinator: SelectableTextView.Coordinator?
    private static let speechSynthesizer = AVSpeechSynthesizer()

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        let hasSelection = selectedRange().length > 0

        let speakItem = NSMenuItem(
            title: "發音",
            action: #selector(speakSelection),
            keyEquivalent: ""
        )
        speakItem.target = self
        speakItem.isEnabled = hasSelection
        menu.insertItem(speakItem, at: 0)

        let vocabItem = NSMenuItem(
            title: "加入單字庫",
            action: #selector(addToVocabulary),
            keyEquivalent: ""
        )
        vocabItem.target = self
        vocabItem.isEnabled = hasSelection
        menu.insertItem(vocabItem, at: 1)

        if menu.items.count > 2 {
            menu.insertItem(.separator(), at: 2)
        }
        return menu
    }

    @objc private func addToVocabulary() {
        let selected = (string as NSString)
            .substring(with: selectedRange())
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !selected.isEmpty else { return }
        Task { @MainActor [weak self] in
            self?.coordinator?.store.add(selected)
        }
    }

    @objc private func speakSelection() {
        let selected = (string as NSString)
            .substring(with: selectedRange())
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !selected.isEmpty else { return }

        let synth = Self.speechSynthesizer
        if synth.isSpeaking {
            synth.stopSpeaking(at: .immediate)
        }
        let utterance = AVSpeechUtterance(string: selected)
        if let voice = preferredVoice(for: selected) {
            utterance.voice = voice
        }
        synth.speak(utterance)
    }

    private func preferredVoice(for text: String) -> AVSpeechSynthesisVoice? {
        let tagger = NSLinguisticTagger(tagSchemes: [.language], options: 0)
        tagger.string = text
        guard let detected = tagger.dominantLanguage, !detected.isEmpty else {
            return nil
        }
        let bcp47: String
        switch detected {
        case "zh-Hant": bcp47 = "zh-TW"
        case "zh-Hans": bcp47 = "zh-CN"
        case "zh":      bcp47 = "zh-TW"
        case "en":      bcp47 = "en-US"
        case "ja":      bcp47 = "ja-JP"
        case "ko":      bcp47 = "ko-KR"
        default:        bcp47 = detected
        }
        return AVSpeechSynthesisVoice(language: bcp47)
    }
}

// MARK: - ContentView

struct ContentView: View {
    let initialText: String
    let runner: ClaudeRunner

    @State private var inputText: String = ""
    @State private var tabs: [TranslationTab] = []
    @State private var activeTabID: UUID? = nil
    @State private var fontSize: CGFloat = 14
    @State private var copiedRecently: Bool = false
    @StateObject private var store = VocabularyStore()
    @State private var practiceWord: String? = nil
    @State private var vocabPopoverShown: Bool = false
    @State private var isFileTranslating: Bool = false
    @FocusState private var inputFocused: Bool

    private var activeTab: TranslationTab? {
        guard let id = activeTabID else { return nil }
        return tabs.first(where: { $0.id == id })
    }

    private var canCopy: Bool {
        guard let tab = activeTab else { return false }
        return !tab.isTranslating && !tab.result.isEmpty
    }

    private var canSummarize: Bool {
        guard let tab = activeTab else { return false }
        return !tab.isTranslating && !tab.isSummarizing && !tab.hasSummary
    }

    private var outputText: String {
        guard let tab = activeTab else { return "" }
        let result = tab.isTranslating ? "翻譯中…" : tab.result
        var text = "【原文】\n\(tab.source)\n\n────────────────────\n\n【翻譯】\n\(result)"
        if tab.isSummarizing {
            text += "\n\n────────────────────\n\n【總結】\n總結中…"
        } else if tab.hasSummary {
            text += "\n\n────────────────────\n\n【總結】\n\(tab.summary)"
        }
        return text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // 第一排：輸入框 + 翻譯按鈕 + 🔖
            HStack(spacing: 8) {
                ZStack(alignment: .topLeading) {
                    TextEditor(text: $inputText)
                        .font(.system(size: 14))
                        .frame(height: 28)
                        .scrollContentBackground(.hidden)
                        .background(Color(nsColor: .textBackgroundColor))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                        )
                        .focused($inputFocused)

                    if inputText.isEmpty, !inputFocused, let hint = practiceWord {
                        Text(hint)
                            .font(.system(size: 14))
                            .foregroundColor(Color(nsColor: .placeholderTextColor))
                            .padding(.leading, 5)
                            .padding(.top, 4)
                            .allowsHitTesting(false)
                    }
                }

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

                Button(action: { if !isFileTranslating { pickAndTranslateFile() } }) {
                    Text(isFileTranslating ? "翻譯中…" : "📄")
                        .font(.system(size: 14))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .disabled(isFileTranslating)
                .help(isFileTranslating ? "翻譯檔案中…" : "選擇 .docx 或 .pdf 檔案翻譯")

                Button(action: { vocabPopoverShown.toggle() }) {
                    Text("🔖")
                        .font(.system(size: 14))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .help("單字庫")
                .popover(isPresented: $vocabPopoverShown) {
                    VocabularyPopover(store: store)
                }
            }

            // Tab 列 + 輸出區（ZStack 讓 active tab 與內容框融合）
            ZStack(alignment: .topLeading) {
                // 輸出區（內容框）— 永遠預留 tabHeight 空間給上方列
                SelectableTextView(text: outputText, fontSize: fontSize, store: store)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
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

                    Button(copiedRecently ? "✓" : "📋") { copyResult() }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                        .layoutPriority(1)
                        .disabled(!canCopy)
                        .opacity(canCopy ? 1 : 0.4)

                    Button("總結") { summarizeActive() }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                        .layoutPriority(1)
                        .disabled(!canSummarize)
                        .opacity(canSummarize ? 1 : 0.4)
                        .help("總結目前 Tab 的原文")

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
            store.load()
            practiceWord = store.words.randomElement()
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
        if text.isEmpty {
            guard let word = practiceWord else { return }
            let ordinal = (tabs.map(\.ordinal).max() ?? 0) + 1
            let tab = TranslationTab(ordinal: ordinal, source: word)
            tabs.append(tab)
            activeTabID = tab.id
            practiceWord = store.words.randomElement()

            Task {
                let result = await runner.explainWord(id: tab.id, word: word)
                if let idx = tabs.firstIndex(where: { $0.id == tab.id }) {
                    tabs[idx].result = result
                    tabs[idx].isTranslating = false
                }
            }
            return
        }

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

    private func pickAndTranslateFile() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedFileTypes = ["docx", "pdf"]
        panel.message = "選擇要翻譯的 .docx 或 .pdf 檔案"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        runFileTranslation(at: url.path)
    }

    private func runFileTranslation(at filePath: String) {
        isFileTranslating = true
        Task {
            let result = await translateFileViaScript(path: filePath)
            isFileTranslating = false
            showFileTranslateAlert(success: result.success, message: result.message)
        }
    }

    private func translateFileViaScript(path: String) async -> (success: Bool, message: String) {
        await withCheckedContinuation { continuation in
            let exec = Bundle.main.executablePath ?? CommandLine.arguments[0]
            let scriptPath = (exec as NSString).deletingLastPathComponent + "/file_translator.py"

            var env = ProcessInfo.processInfo.environment
            env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "")

            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            proc.arguments = ["uv", "run", "--quiet", scriptPath, path]
            proc.environment = env

            let outPipe = Pipe()
            let errPipe = Pipe()
            proc.standardOutput = outPipe
            proc.standardError = errPipe

            proc.terminationHandler = { p in
                let outStr = (String(data: outPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                let errStr = (String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if p.terminationStatus == 0 && !outStr.isEmpty {
                    continuation.resume(returning: (true, outStr))
                } else {
                    let msg = errStr.isEmpty ? "翻譯失敗（exit \(p.terminationStatus)）" : String(errStr.suffix(500))
                    continuation.resume(returning: (false, msg))
                }
            }

            do {
                try proc.run()
            } catch {
                continuation.resume(returning: (false, "啟動失敗：\(error.localizedDescription)"))
            }
        }
    }

    private func showFileTranslateAlert(success: Bool, message: String) {
        let alert = NSAlert()
        alert.messageText = success ? "翻譯完成" : "翻譯失敗"
        alert.informativeText = message
        alert.alertStyle = success ? .informational : .warning
        if success {
            alert.addButton(withTitle: "在 Finder 顯示")
            alert.addButton(withTitle: "完成")
        } else {
            alert.addButton(withTitle: "確定")
        }
        let response = alert.runModal()
        if success && response == .alertFirstButtonReturn {
            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: message)])
        }
    }

    private func summarizeActive() {
        guard let id = activeTabID,
              let idx = tabs.firstIndex(where: { $0.id == id }) else { return }
        let tab = tabs[idx]
        guard !tab.isTranslating, !tab.isSummarizing, !tab.hasSummary else { return }
        let source = tab.source
        tabs[idx].isSummarizing = true

        Task {
            let summary = await runner.summarize(id: id, text: source)
            if let i = tabs.firstIndex(where: { $0.id == id }) {
                tabs[i].summary = summary
                tabs[i].isSummarizing = false
                tabs[i].hasSummary = true
            }
        }
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

    private func copyResult() {
        guard let tab = activeTab, !tab.isTranslating, !tab.result.isEmpty else { return }
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(tab.result, forType: .string)
        copiedRecently = true
        Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            copiedRecently = false
        }
    }
}

// MARK: - AppDelegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let runner = ClaudeRunner()
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
