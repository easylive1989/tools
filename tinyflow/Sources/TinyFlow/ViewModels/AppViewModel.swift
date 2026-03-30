import Foundation
import SwiftUI

@MainActor
class AppViewModel: ObservableObject {
    @Published var sessions: [Session] = []
    @Published var activeSessionId: UUID? = nil
    @Published var isStreaming: Bool = false
    @Published var showNewSessionSheet: Bool = false

    private var streamingTask: Task<Void, Never>?

    init() {
        sessions = SessionStorage.loadAll()
    }

    var activeSession: Session? {
        sessions.first { $0.id == activeSessionId }
    }

    // MARK: - Session Management

    func createSession(name: String, cliType: CLIType, folder: String) {
        let session = Session(name: name, cliType: cliType, folder: folder)
        sessions.append(session)
        activeSessionId = session.id
        persist()
    }

    func deleteSession(_ session: Session) {
        sessions.removeAll { $0.id == session.id }
        if activeSessionId == session.id {
            activeSessionId = sessions.first?.id
        }
        persist()
    }

    func loadAndSelectSession(_ session: Session) {
        activeSessionId = session.id
    }

    // MARK: - Messaging

    func sendMessage(_ content: String) {
        guard let session = activeSession, !isStreaming else { return }

        let sessionId = session.id
        let cliType = session.cliType
        let folder = session.folder
        let cliSessionId = session.cliSessionId

        // Add user message
        appendMessage(to: sessionId, message: Message(role: .user, content: content))
        isStreaming = true

        streamingTask = Task {
            var streamingMsgId: UUID? = nil
            var receivedCLISessionId: String? = nil

            let stream = CLIRunner.run(
                cliType: cliType,
                message: content,
                sessionId: cliSessionId,
                workingDir: folder
            )

            for await line in stream {
                if Task.isCancelled { break }

                let parsed = CLIStreamParser.parseLine(line, cliType: cliType)

                if let text = parsed.text, !text.isEmpty {
                    if let msgId = streamingMsgId {
                        appendToMessage(id: msgId, in: sessionId, text: text)
                    } else {
                        let msg = Message(role: .assistant, content: text, isStreaming: true)
                        streamingMsgId = msg.id
                        appendMessage(to: sessionId, message: msg)
                    }
                }

                if let toolName = parsed.toolName, let msgId = streamingMsgId {
                    appendToMessage(id: msgId, in: sessionId, text: "\n\n> 使用工具：`\(toolName)`\n\n")
                }

                if let sid = parsed.sessionId {
                    receivedCLISessionId = sid
                }
            }

            // Finalize streaming message
            if let msgId = streamingMsgId {
                finalizeMessage(id: msgId, in: sessionId)
            }

            // Store CLI session ID for future continuations
            if let cliSid = receivedCLISessionId {
                updateSession(id: sessionId) { s in
                    if s.cliType == .claude {
                        s.claudeSessionId = cliSid
                    } else {
                        s.geminiSessionId = cliSid
                    }
                }
            }

            persist()
            isStreaming = false
        }
    }

    func cancelStreaming() {
        streamingTask?.cancel()
        streamingTask = nil

        if let sid = activeSessionId {
            updateSession(id: sid) { s in
                if let idx = s.messages.indices.last, s.messages[idx].isStreaming {
                    s.messages[idx].isStreaming = false
                    s.messages[idx].content += "\n\n_[已取消]_"
                }
            }
        }
        isStreaming = false
    }

    // MARK: - Helpers

    private func appendMessage(to sessionId: UUID, message: Message) {
        updateSession(id: sessionId) { $0.messages.append(message) }
    }

    private func appendToMessage(id msgId: UUID, in sessionId: UUID, text: String) {
        updateSession(id: sessionId) { s in
            if let idx = s.messages.firstIndex(where: { $0.id == msgId }) {
                s.messages[idx].content += text
            }
        }
    }

    private func finalizeMessage(id msgId: UUID, in sessionId: UUID) {
        updateSession(id: sessionId) { s in
            if let idx = s.messages.firstIndex(where: { $0.id == msgId }) {
                s.messages[idx].isStreaming = false
            }
        }
    }

    private func updateSession(id: UUID, update: (inout Session) -> Void) {
        guard let idx = sessions.firstIndex(where: { $0.id == id }) else { return }
        update(&sessions[idx])
        sessions[idx].updatedAt = Date()
    }

    private func persist() {
        SessionStorage.saveAll(sessions)
    }
}
