import XCTest
@testable import TinyFlowCore

final class CLIStreamParserTests: XCTestCase {

    // MARK: - Claude

    func testClaudeTextDelta() {
        let line = #"{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}}"#
        let result = CLIStreamParser.parseLine(line, cliType: .claude)
        XCTAssertEqual(result.text, "Hello")
        XCTAssertNil(result.sessionId)
        XCTAssertNil(result.toolName)
    }

    func testClaudeResultLine() {
        let line = #"{"type":"result","session_id":"abc-123"}"#
        let result = CLIStreamParser.parseLine(line, cliType: .claude)
        XCTAssertEqual(result.sessionId, "abc-123")
        XCTAssertNil(result.text)
    }

    func testClaudeToolUseLine() {
        let line = #"{"type":"tool_use","name":"read_file"}"#
        let result = CLIStreamParser.parseLine(line, cliType: .claude)
        XCTAssertEqual(result.toolName, "read_file")
        XCTAssertNil(result.text)
    }

    // MARK: - Gemini

    func testGeminiInitLine() {
        let line = #"{"type":"init","session_id":"gsid-456"}"#
        let result = CLIStreamParser.parseLine(line, cliType: .gemini)
        XCTAssertEqual(result.sessionId, "gsid-456")
        XCTAssertNil(result.text)
    }

    func testGeminiMessageLine() {
        let line = #"{"type":"message","role":"assistant","delta":true,"content":"World"}"#
        let result = CLIStreamParser.parseLine(line, cliType: .gemini)
        XCTAssertEqual(result.text, "World")
        XCTAssertNil(result.sessionId)
    }

    // MARK: - Edge cases

    func testNonJSONLine() {
        let result = CLIStreamParser.parseLine("not json at all", cliType: .claude)
        XCTAssertNil(result.text)
        XCTAssertNil(result.sessionId)
        XCTAssertNil(result.toolName)
    }

    func testUnknownTypeLine() {
        let line = #"{"type":"unknown","foo":"bar"}"#
        let result = CLIStreamParser.parseLine(line, cliType: .claude)
        XCTAssertNil(result.text)
        XCTAssertNil(result.sessionId)
        XCTAssertNil(result.toolName)
    }
}
