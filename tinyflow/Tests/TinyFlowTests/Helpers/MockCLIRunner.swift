import Foundation
@testable import TinyFlowCore

final class MockCLIRunner: CLIRunning, @unchecked Sendable {
    struct Response {
        var lines: [String]
    }

    var nextResponse = Response(lines: [])
    private(set) var capturedCalls: [(cliType: CLIType, message: String, sessionId: String?)] = []

    func run(
        cliType: CLIType,
        message: String,
        sessionId: String?,
        workingDir: String
    ) -> AsyncStream<String> {
        capturedCalls.append((cliType, message, sessionId))
        let lines = nextResponse.lines
        return AsyncStream { continuation in
            Task {
                for line in lines {
                    continuation.yield(line)
                }
                continuation.finish()
            }
        }
    }
}

extension MockCLIRunner.Response {
    static func claude(text: String, sessionId: String = "fake-sid") -> Self {
        Self(lines: [
            #"{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"\#(text)"}}}"#,
            #"{"type":"result","session_id":"\#(sessionId)"}"#
        ])
    }

    static func gemini(text: String, sessionId: String = "fake-gsid") -> Self {
        Self(lines: [
            #"{"type":"init","session_id":"\#(sessionId)"}"#,
            #"{"type":"message","role":"assistant","delta":true,"content":"\#(text)"}"#
        ])
    }
}
