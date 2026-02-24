import AppKit

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!

    func applicationDidFinishLaunching(_ notification: Notification) {
        var text = ""
        if CommandLine.arguments.count > 1 {
            text = CommandLine.arguments.dropFirst().joined(separator: " ")
        } else {
            while let line = readLine(strippingNewline: false) {
                text += line
            }
        }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)

        if text.isEmpty {
            NSApp.terminate(nil)
            return
        }

        let windowWidth: CGFloat = 520
        let windowHeight: CGFloat = 300

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "翻譯結果"
        window.level = .floating
        window.center()
        window.isReleasedWhenClosed = false

        let scrollView = NSScrollView(frame: window.contentView!.bounds)
        scrollView.autoresizingMask = [.width, .height]
        scrollView.hasVerticalScroller = true
        scrollView.borderType = .noBorder

        let textView = NSTextView(frame: scrollView.bounds)
        textView.autoresizingMask = [.width]
        textView.isEditable = false
        textView.isSelectable = true
        textView.font = NSFont.systemFont(ofSize: 15)
        textView.textContainerInset = NSSize(width: 12, height: 12)
        textView.string = text
        textView.textContainer?.widthTracksTextView = true

        scrollView.documentView = textView
        window.contentView = scrollView

        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                NSApp.terminate(nil)
                return nil
            }
            return event
        }

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
