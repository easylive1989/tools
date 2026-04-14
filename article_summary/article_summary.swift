import AppKit
import SwiftUI
import WebKit

// MARK: - Constants & Helpers

private let ARTICLE_PROMPT = """
你是一個專業的文章總結工具。請閱讀以下文章內容，並以繁體中文產生結構化總結。

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
"""

private let userName = ProcessInfo.processInfo.environment["USER"] ?? "user"
private let pidFilePath = "/tmp/article_summary_gui_\(userName).pid"
private let bringToFrontNotification = Notification.Name("BringToFront")
private let pasteToInputNotification = Notification.Name("PasteToInput")

private let ansiRegex = try! NSRegularExpression(
    pattern: #"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r"#
)

private func stripANSI(_ s: String) -> String {
    ansiRegex.stringByReplacingMatches(
        in: s, range: NSRange(s.startIndex..., in: s), withTemplate: ""
    )
}

// MARK: - HTML Helpers

private func extractTitle(from html: String) -> String {
    // 提取 <title> 標籤內容
    if let startRange = html.range(of: "<title", options: .caseInsensitive),
       let gtRange = html.range(of: ">", range: startRange.upperBound..<html.endIndex),
       let endRange = html.range(of: "</title>", options: .caseInsensitive, range: gtRange.upperBound..<html.endIndex) {
        let title = String(html[gtRange.upperBound..<endRange.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        // Decode basic HTML entities
        return decodeHTMLEntities(title)
    }
    return ""
}

private func extractBodyText(from html: String) -> String {
    var text = html

    // 移除 script 和 style 區塊
    let scriptPattern = try! NSRegularExpression(pattern: "<script[^>]*>[\\s\\S]*?</script>", options: .caseInsensitive)
    text = scriptPattern.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")

    let stylePattern = try! NSRegularExpression(pattern: "<style[^>]*>[\\s\\S]*?</style>", options: .caseInsensitive)
    text = stylePattern.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")

    // 移除所有 HTML 標籤
    let tagPattern = try! NSRegularExpression(pattern: "<[^>]+>")
    text = tagPattern.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")

    // Decode HTML entities
    text = decodeHTMLEntities(text)

    // 壓縮空白
    let whitespacePattern = try! NSRegularExpression(pattern: "\\s+")
    text = whitespacePattern.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")

    return text.trimmingCharacters(in: .whitespacesAndNewlines)
}

private func decodeHTMLEntities(_ s: String) -> String {
    var result = s
    let entities: [(String, String)] = [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
        ("&nbsp;", " "), ("&#x2F;", "/"), ("&#47;", "/"),
    ]
    for (entity, char) in entities {
        result = result.replacingOccurrences(of: entity, with: char)
    }
    // Decode numeric entities like &#123;
    let numericPattern = try! NSRegularExpression(pattern: "&#(\\d+);")
    let matches = numericPattern.matches(in: result, range: NSRange(result.startIndex..., in: result))
    for match in matches.reversed() {
        if let range = Range(match.range, in: result),
           let numRange = Range(match.range(at: 1), in: result),
           let code = UInt32(result[numRange]),
           let scalar = Unicode.Scalar(code) {
            result.replaceSubrange(range, with: String(Character(scalar)))
        }
    }
    return result
}

// MARK: - Data Model

struct SummaryTab: Identifiable {
    let id: UUID = UUID()
    let ordinal: Int
    let url: String
    var title: String = ""
    var result: String = ""
    var isProcessing: Bool = true
}

// MARK: - ArticleSummarizer Actor

actor ArticleSummarizer {
    private var liveTasks: [UUID: Process] = [:]

    func summarize(id: UUID, url: String) async -> (title: String, summary: String) {
        let (title, bodyText) = await fetchArticle(url: url)
        if bodyText.isEmpty {
            return (title: title.isEmpty ? url : title, summary: "錯誤：無法取得文章內容")
        }
        let truncatedBody = String(bodyText.prefix(15000))
        let prompt = "\(ARTICLE_PROMPT)\n\n文章內容：\n\(truncatedBody)"
        let summary = await callGeminiWithPrompt(id: id, prompt: prompt)
        return (title: title.isEmpty ? url : title, summary: summary)
    }

    private func fetchArticle(url urlString: String) async -> (title: String, body: String) {
        guard let url = URL(string: urlString) else {
            return ("", "")
        }

        do {
            var request = URLRequest(url: url)
            request.setValue(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                forHTTPHeaderField: "User-Agent"
            )
            let (data, _) = try await URLSession.shared.data(for: request)
            let html = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .ascii)
                ?? ""
            let title = extractTitle(from: html)
            let body = extractBodyText(from: html)
            return (title, body)
        } catch {
            return ("", "")
        }
    }

    private func callGeminiWithPrompt(id: UUID, prompt: String) async -> String {
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

// MARK: - Markdown Rendering

private let markdownCSS = """
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
    font-size: {{FONT_SIZE}}px;
    line-height: 1.6;
    color: -apple-system-label;
    padding: 12px 16px;
    margin: 0;
    background: transparent;
    -webkit-user-select: text;
  }
  h1 { font-size: 1.4em; margin: 0.6em 0 0.3em; }
  h2 { font-size: 1.2em; margin: 0.5em 0 0.3em; color: #3070E0; }
  h3 { font-size: 1.05em; margin: 0.4em 0 0.2em; }
  p { margin: 0.4em 0; }
  ul, ol { padding-left: 1.5em; margin: 0.3em 0; }
  li { margin: 0.2em 0; }
  strong { font-weight: 600; }
  em { font-style: italic; }
  code {
    font-family: "SF Mono", Menlo, monospace;
    font-size: 0.9em;
    background: rgba(128,128,128,0.15);
    padding: 0.1em 0.3em;
    border-radius: 3px;
  }
  pre { background: rgba(128,128,128,0.1); padding: 8px; border-radius: 6px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  hr { border: none; border-top: 1px solid rgba(128,128,128,0.3); margin: 0.8em 0; }
  blockquote {
    border-left: 3px solid #3070E0;
    margin: 0.4em 0;
    padding: 0.2em 0.8em;
    color: rgba(128,128,128,0.9);
  }
  .title-section { margin-bottom: 0.5em; }
  .title-label { font-size: 0.85em; color: rgba(128,128,128,0.7); margin-bottom: 0.1em; }
  .title-text { font-size: 1.2em; font-weight: 600; }
  .divider { border: none; border-top: 2px solid rgba(128,128,128,0.2); margin: 0.8em 0; }
</style>
"""

private func markdownToHTML(_ markdown: String) -> String {
    let lines = markdown.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    var html = ""
    var inList = false
    var inCodeBlock = false

    for line in lines {
        // Code block toggle
        if line.hasPrefix("```") {
            if inCodeBlock {
                html += "</code></pre>\n"
                inCodeBlock = false
            } else {
                if inList { html += "</ul>\n"; inList = false }
                html += "<pre><code>"
                inCodeBlock = true
            }
            continue
        }
        if inCodeBlock {
            html += escapeHTML(line) + "\n"
            continue
        }

        let trimmed = line.trimmingCharacters(in: .whitespaces)

        // Empty line
        if trimmed.isEmpty {
            if inList { html += "</ul>\n"; inList = false }
            continue
        }

        // Headings
        if trimmed.hasPrefix("### ") {
            if inList { html += "</ul>\n"; inList = false }
            html += "<h3>\(inlineMarkdown(String(trimmed.dropFirst(4))))</h3>\n"
            continue
        }
        if trimmed.hasPrefix("## ") {
            if inList { html += "</ul>\n"; inList = false }
            html += "<h2>\(inlineMarkdown(String(trimmed.dropFirst(3))))</h2>\n"
            continue
        }
        if trimmed.hasPrefix("# ") {
            if inList { html += "</ul>\n"; inList = false }
            html += "<h1>\(inlineMarkdown(String(trimmed.dropFirst(2))))</h1>\n"
            continue
        }

        // Horizontal rule
        if trimmed == "---" || trimmed == "***" || trimmed == "___" {
            if inList { html += "</ul>\n"; inList = false }
            html += "<hr>\n"
            continue
        }

        // Blockquote
        if trimmed.hasPrefix("> ") {
            if inList { html += "</ul>\n"; inList = false }
            html += "<blockquote>\(inlineMarkdown(String(trimmed.dropFirst(2))))</blockquote>\n"
            continue
        }

        // List items
        if trimmed.hasPrefix("- ") || trimmed.hasPrefix("* ") || trimmed.hasPrefix("• ") {
            if !inList { html += "<ul>\n"; inList = true }
            let content = String(trimmed.dropFirst(2))
            html += "<li>\(inlineMarkdown(content))</li>\n"
            continue
        }
        // Numbered list
        let numberedPattern = try! NSRegularExpression(pattern: "^\\d+\\.\\s")
        if numberedPattern.firstMatch(in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed)) != nil {
            if !inList { html += "<ul>\n"; inList = true }
            let content = trimmed.replacingOccurrences(of: "^\\d+\\.\\s", with: "", options: .regularExpression)
            html += "<li>\(inlineMarkdown(content))</li>\n"
            continue
        }

        // Paragraph
        if inList { html += "</ul>\n"; inList = false }
        html += "<p>\(inlineMarkdown(trimmed))</p>\n"
    }

    if inList { html += "</ul>\n" }
    if inCodeBlock { html += "</code></pre>\n" }
    return html
}

private func inlineMarkdown(_ text: String) -> String {
    var s = escapeHTML(text)
    // Bold: **text** or __text__
    let boldPattern = try! NSRegularExpression(pattern: "\\*\\*(.+?)\\*\\*|__(.+?)__")
    s = boldPattern.stringByReplacingMatches(in: s, range: NSRange(s.startIndex..., in: s),
        withTemplate: "<strong>$1$2</strong>")
    // Italic: *text* or _text_
    let italicPattern = try! NSRegularExpression(pattern: "(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
    s = italicPattern.stringByReplacingMatches(in: s, range: NSRange(s.startIndex..., in: s),
        withTemplate: "<em>$1$2</em>")
    // Inline code: `text`
    let codePattern = try! NSRegularExpression(pattern: "`(.+?)`")
    s = codePattern.stringByReplacingMatches(in: s, range: NSRange(s.startIndex..., in: s),
        withTemplate: "<code>$1</code>")
    return s
}

private func escapeHTML(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;")
     .replacingOccurrences(of: "<", with: "&lt;")
     .replacingOccurrences(of: ">", with: "&gt;")
}

private func buildFullHTML(title: String, summaryMarkdown: String, fontSize: CGFloat) -> String {
    let css = markdownCSS.replacingOccurrences(of: "{{FONT_SIZE}}", with: "\(Int(fontSize))")
    let summaryHTML = markdownToHTML(summaryMarkdown)
    return """
    <!DOCTYPE html><html><head><meta charset="utf-8">\(css)</head><body>
    <div class="title-section">
      <div class="title-label">標題</div>
      <div class="title-text">\(escapeHTML(title))</div>
    </div>
    <hr class="divider">
    \(summaryHTML)
    </body></html>
    """
}

struct MarkdownWebView: NSViewRepresentable {
    let html: String

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        webView.loadHTMLString(html, baseURL: nil)
    }
}

// MARK: - Shapes

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
    let tab: SummaryTab
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

// MARK: - ContentView

struct ContentView: View {
    let summarizer: ArticleSummarizer

    @State private var inputText: String = ""
    @State private var tabs: [SummaryTab] = []
    @State private var activeTabID: UUID? = nil
    @State private var fontSize: CGFloat = 14

    private var outputHTML: String {
        guard let id = activeTabID,
              let tab = tabs.first(where: { $0.id == id }) else {
            return buildFullHTML(title: "", summaryMarkdown: "", fontSize: fontSize)
        }
        let titleLine = tab.title.isEmpty ? tab.url : tab.title
        let summary = tab.isProcessing ? "總結中…" : tab.result
        return buildFullHTML(title: titleLine, summaryMarkdown: summary, fontSize: fontSize)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ZStack(alignment: .leading) {
                    TextEditor(text: $inputText)
                        .font(.system(size: 14))
                        .frame(height: 28)
                        .scrollContentBackground(.hidden)
                        .background(Color(nsColor: .textBackgroundColor))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                        )

                    if inputText.isEmpty {
                        Text("貼入文章 URL…")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                            .padding(.leading, 5)
                            .allowsHitTesting(false)
                    }
                }

                Button(action: summarize) {
                    Text("總結  ⌘↩")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(Color(red: 0, green: 0.44, blue: 0.89))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: .command)
            }

            ZStack(alignment: .topLeading) {
                MarkdownWebView(html: outputHTML)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(nsColor: .textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
                    .padding(.top, tabHeight - 1)

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
        .onReceive(NotificationCenter.default.publisher(for: pasteToInputNotification)) { notification in
            if let text = notification.object as? String {
                inputText = text
                summarize()
            }
        }
    }

    private func summarize() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let ordinal = (tabs.map(\.ordinal).max() ?? 0) + 1
        let tab = SummaryTab(ordinal: ordinal, url: text)
        tabs.append(tab)
        activeTabID = tab.id
        inputText = ""

        Task {
            let (title, summary) = await summarizer.summarize(id: tab.id, url: text)
            if let idx = tabs.firstIndex(where: { $0.id == tab.id }) {
                tabs[idx].title = title
                tabs[idx].result = summary
                tabs[idx].isProcessing = false
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
}

// MARK: - AppDelegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let summarizer = ArticleSummarizer()
    var sigusr1Source: DispatchSourceSignal?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenu()

        let contentView = ContentView(summarizer: summarizer)
        let hosting = NSHostingController(rootView: contentView)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 780, height: 700),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "文章總結"
        window.level = .floating
        window.minSize = NSSize(width: 380, height: 600)
        window.contentViewController = hosting
        window.setFrame(NSRect(x: 0, y: 0, width: 780, height: 700), display: true)
        window.center()
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 { NSApp.terminate(nil); return nil }
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

        // 監聽 SIGUSR1：收到後帶到前景
        signal(SIGUSR1, SIG_IGN)
        let src = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
        src.setEventHandler { [weak self] in
            self?.window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        src.resume()
        sigusr1Source = src
    }

    private func setupMenu() {
        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "結束文章總結", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu

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
        Task { await summarizer.cancelAll() }
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
