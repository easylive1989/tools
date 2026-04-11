import Foundation

enum CLIType: String, Codable, CaseIterable {
    case claude = "claude"
    case gemini = "gemini"

    var displayName: String {
        switch self {
        case .claude: return "Claude"
        case .gemini: return "Gemini"
        }
    }
}

enum MessageRole: String, Codable {
    case user
    case assistant
}

struct Message: Identifiable, Codable {
    let id: UUID
    let role: MessageRole
    var content: String
    var isStreaming: Bool
    let timestamp: Date

    init(id: UUID = UUID(), role: MessageRole, content: String, isStreaming: Bool = false) {
        self.id = id
        self.role = role
        self.content = content
        self.isStreaming = isStreaming
        self.timestamp = Date()
    }
}

struct Session: Identifiable, Codable {
    let id: UUID
    var name: String
    var cliType: CLIType
    var folder: String
    var claudeSessionId: String?
    var geminiSessionId: String?
    var messages: [Message]
    let createdAt: Date
    var updatedAt: Date

    init(name: String, cliType: CLIType, folder: String) {
        self.id = UUID()
        self.name = name
        self.cliType = cliType
        self.folder = folder
        self.messages = []
        self.createdAt = Date()
        self.updatedAt = Date()
    }

    var cliSessionId: String? {
        switch cliType {
        case .claude: return claudeSessionId
        case .gemini: return geminiSessionId
        }
    }

    var folderName: String {
        URL(fileURLWithPath: folder).lastPathComponent
    }
}
