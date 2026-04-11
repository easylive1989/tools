import Foundation

struct ParsedLine {
    var text: String?
    var sessionId: String?
    var toolName: String?
}

enum CLIStreamParser {
    static func parseLine(_ line: String, cliType: CLIType) -> ParsedLine {
        guard
            let data = line.data(using: .utf8),
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let type_ = obj["type"] as? String
        else {
            return ParsedLine()
        }

        switch cliType {
        case .claude:
            return parseClaudeLine(type_: type_, obj: obj)
        case .gemini:
            return parseGeminiLine(type_: type_, obj: obj)
        }
    }

    private static func parseClaudeLine(type_: String, obj: [String: Any]) -> ParsedLine {
        var result = ParsedLine()
        switch type_ {
        case "stream_event":
            // Partial text delta: stream_event → event.content_block_delta → delta.text_delta
            if let event = obj["event"] as? [String: Any],
               event["type"] as? String == "content_block_delta",
               let delta = event["delta"] as? [String: Any],
               delta["type"] as? String == "text_delta",
               let text = delta["text"] as? String {
                result.text = text
            }
        case "result":
            result.sessionId = obj["session_id"] as? String
        case "tool_use":
            result.toolName = obj["name"] as? String
        default:
            break
        }
        return result
    }

    private static func parseGeminiLine(type_: String, obj: [String: Any]) -> ParsedLine {
        var result = ParsedLine()
        switch type_ {
        case "message":
            // Streaming text delta: role=assistant, delta=true
            if obj["role"] as? String == "assistant",
               obj["delta"] as? Bool == true,
               let content = obj["content"] as? String {
                result.text = content
            }
        case "init":
            // Session ID is in the init line for Gemini
            result.sessionId = obj["session_id"] as? String
        default:
            break
        }
        return result
    }
}
