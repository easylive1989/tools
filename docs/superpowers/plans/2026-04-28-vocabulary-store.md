# Vocabulary Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Apple Notes button in the translator with a built-in vocabulary memory bank that shows a random word on the button for passive practice and lets users add/remove words via popover; also enables right-click → "加入單字庫" from the translation output area.

**Architecture:** All changes are in a single file (`translate/translator.swift`). `VocabularyStore` reads/writes a markdown bullet-list file in the user's Obsidian iCloud vault. `VocabularyPopover` provides add/delete UI. `SelectableTextView` wraps NSTextView to inject a custom right-click menu item. Five tasks, each ending with a compile check and commit.

**Tech Stack:** SwiftUI, AppKit, NSViewRepresentable, NSTextView (macOS). Compiled with `swiftc`. No test framework — verification is compile + manual run.

---

### Task 1: Add `vocabularyFilePath` constant and `VocabularyStore` class

**Files:**
- Modify: `translate/translator.swift` — `MARK: - Constants & Helpers` and after `MARK: - Data Model`

- [ ] **Step 1: Add `vocabularyFilePath` constant**

In `translate/translator.swift`, add these lines at the end of the `// MARK: - Constants & Helpers` section, after the `stripANSI` function (around line 70):

```swift
private let vocabularyFilePath: String = {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    return "\(home)/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/vocabulary.md"
}()
```

- [ ] **Step 2: Add `VocabularyStore` class**

Add this new section immediately after the closing brace of `struct TranslationTab` (after `// MARK: - Data Model`):

```swift
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
        let word = input.trimmingCharacters(in: .whitespaces)
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
            result = lines + newBullets
        }
        let content = result.joined(separator: "\n")
        let dir = (vocabularyFilePath as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try? content.write(toFile: vocabularyFilePath, atomically: true, encoding: .utf8)
    }
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && swiftc translator.swift -o /tmp/translator_vocab_test 2>&1
```

Expected: exits with no error output (warnings are OK).

- [ ] **Step 4: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && git add translator.swift && git -C /Users/paulwu/Documents/Github/tools commit -m "feat(translate): add VocabularyStore with Obsidian markdown persistence"
```

---

### Task 2: Add `VocabularyPopover` view

**Files:**
- Modify: `translate/translator.swift` — add new View after `VocabularyStore`

- [ ] **Step 1: Add `VocabularyPopover` view**

Add this block immediately after the closing brace of `VocabularyStore`:

```swift
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
                        ForEach(store.words, id: \.self) { word in
                            HStack {
                                Text("• \(word)")
                                    .font(.system(size: 13))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                Button("×") {
                                    if let idx = store.words.firstIndex(of: word) {
                                        store.remove(at: idx)
                                    }
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
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && swiftc translator.swift -o /tmp/translator_vocab_test 2>&1
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && git add translator.swift && git -C /Users/paulwu/Documents/Github/tools commit -m "feat(translate): add VocabularyPopover view with add/delete/empty-state"
```

---

### Task 3: Wire `VocabularyStore` into `ContentView` + replace vocabulary button

**Files:**
- Modify: `translate/translator.swift` — `ContentView` struct

- [ ] **Step 1: Add store and UI state properties to ContentView**

In `ContentView`, find this line (around line 237):

```swift
@State private var copiedRecently: Bool = false
```

Add three new properties immediately after it:

```swift
@StateObject private var store = VocabularyStore()
@State private var practiceWord: String? = nil
@State private var vocabPopoverShown: Bool = false
```

- [ ] **Step 2: Update `.task` to load store and pick random word**

Find this `.task` block in `ContentView.body`:

```swift
        .task {
            if !initialText.isEmpty {
                inputText = initialText
                translate()
            }
        }
```

Replace with:

```swift
        .task {
            store.load()
            practiceWord = store.words.randomElement()
            if !initialText.isEmpty {
                inputText = initialText
                translate()
            }
        }
```

- [ ] **Step 3: Replace the `📝` button**

Find this entire button block (approximately lines 281–290):

```swift
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
```

Replace with:

```swift
                Button(action: { vocabPopoverShown.toggle() }) {
                    Text(practiceWord ?? "📝")
                        .font(.system(size: 14))
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .frame(maxWidth: 140, alignment: .center)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color(nsColor: .controlBackgroundColor))
                .cornerRadius(6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1))
                .help(practiceWord ?? "")
                .popover(isPresented: $vocabPopoverShown) {
                    VocabularyPopover(store: store)
                }
```

- [ ] **Step 4: Verify compilation**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && swiftc translator.swift -o /tmp/translator_vocab_test 2>&1
```

Expected: no errors.

- [ ] **Step 5: Smoke test**

Launch `/tmp/translator_vocab_test`. Confirm:
- Button shows `📝` (empty vocab on first run)
- Clicking button opens popover with "還沒有任何單字" message
- Typing a word + Enter adds it to the list
- `×` removes a word
- After `⌘Q` and relaunch, button shows a random word from the saved list

- [ ] **Step 6: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && git add translator.swift && git -C /Users/paulwu/Documents/Github/tools commit -m "feat(translate): wire VocabularyStore into ContentView, replace Notes button with vocab popover"
```

---

### Task 4: Add `SelectableTextView` with right-click "加入單字庫"

**Files:**
- Modify: `translate/translator.swift` — add new types immediately before `// MARK: - ContentView`

- [ ] **Step 1: Add `SelectableTextView` and `VocabularyTextView`**

Add the following block immediately before the `// MARK: - ContentView` comment:

```swift
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
        textView.drawsBackground = false
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

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        let item = NSMenuItem(
            title: "加入單字庫",
            action: #selector(addToVocabulary),
            keyEquivalent: ""
        )
        item.target = self
        item.isEnabled = selectedRange().length > 0
        menu.insertItem(item, at: 0)
        if menu.items.count > 1 {
            menu.insertItem(.separator(), at: 1)
        }
        return menu
    }

    @objc private func addToVocabulary() {
        let selected = (string as NSString)
            .substring(with: selectedRange())
            .trimmingCharacters(in: .whitespaces)
        guard !selected.isEmpty else { return }
        Task { @MainActor [weak self] in
            self?.coordinator?.store.add(selected)
        }
    }
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && swiftc translator.swift -o /tmp/translator_vocab_test 2>&1
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && git add translator.swift && git -C /Users/paulwu/Documents/Github/tools commit -m "feat(translate): add SelectableTextView with right-click '加入單字庫' context menu"
```

---

### Task 5: Replace output `Text` with `SelectableTextView`

**Files:**
- Modify: `translate/translator.swift` — output area inside `ContentView.body`

- [ ] **Step 1: Replace the output ScrollView + Text block**

Find this block inside `ContentView.body` (the first child of the ZStack, approximately lines 295–310):

```swift
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
```

Replace with:

```swift
                // 輸出區（內容框）— 永遠預留 tabHeight 空間給上方列
                SelectableTextView(text: outputText, fontSize: fontSize, store: store)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(nsColor: .textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
                    .padding(.top, tabHeight - 1)
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && swiftc translator.swift -o /tmp/translator_vocab_test 2>&1
```

Expected: no errors.

- [ ] **Step 3: Full manual test**

Launch `/tmp/translator_vocab_test` and verify all of the following:

1. Existing translation flow works (select text in any app → Raycast hotkey → translation appears)
2. Output area is scrollable and text renders correctly at current font size
3. Font size `−` / `+` buttons still resize text in the output area
4. Select a word in the output area → right-click → "加入單字庫" appears at top, enabled
5. No text selected → right-click → "加入單字庫" is greyed out (disabled)
6. Right-click add → open vocab popover → word appears in list; `vocabulary.md` has the new `- word` line
7. Phrase selection (e.g., `make a commitment`) → right-click add → entire phrase stored as single entry
8. Right-click add a duplicate → silently ignored, list unchanged
9. Pre-existing Obsidian content (e.g., a `# 我的字庫` heading in vocabulary.md) is preserved after add/delete operations

- [ ] **Step 4: Final commit**

```bash
cd /Users/paulwu/Documents/Github/tools/translate && git add translator.swift && git -C /Users/paulwu/Documents/Github/tools commit -m "feat(translate): replace output Text with SelectableTextView for right-click vocab add"
```
