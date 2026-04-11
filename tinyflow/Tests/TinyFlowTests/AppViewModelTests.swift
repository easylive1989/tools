import XCTest
@testable import TinyFlowCore

@MainActor
final class AppViewModelTests: XCTestCase {
    var runner: MockCLIRunner!
    var storage: MockSessionStorage!
    var vm: AppViewModel!
    var session: Session!

    override func setUp() async throws {
        runner = MockCLIRunner()
        storage = MockSessionStorage()
        session = Session(name: "Test", cliType: .claude, folder: "/tmp/test")
        storage.sessions = [session]
        vm = AppViewModel(cliRunner: runner, storage: storage)
        vm.activeSessionId = session.id
    }

    // MARK: - Core E2E flow

    func testMessageAppearsAfterStreaming() async throws {
        runner.nextResponse = .claude(text: "Hello")
        vm.sendMessage("Hi")
        await waitForStreaming()

        let messages = vm.sessions[0].messages
        XCTAssertEqual(messages.count, 2)
        XCTAssertEqual(messages[0].role, .user)
        XCTAssertEqual(messages[0].content, "Hi")
        XCTAssertEqual(messages[1].role, .assistant)
        XCTAssertEqual(messages[1].content, "Hello")
        XCTAssertFalse(messages[1].isStreaming)
        XCTAssertFalse(vm.isStreaming)
    }

    func testCLISessionIdStoredAfterFirstMessage() async throws {
        runner.nextResponse = .claude(text: "Hi", sessionId: "sid-abc")
        vm.sendMessage("Hello")
        await waitForStreaming()

        XCTAssertEqual(vm.sessions[0].claudeSessionId, "sid-abc")
    }

    func testSecondMessagePassesPreviousSessionId() async throws {
        runner.nextResponse = .claude(text: "First reply", sessionId: "sid-first")
        vm.sendMessage("First")
        await waitForStreaming()

        runner.nextResponse = .claude(text: "Second reply", sessionId: "sid-second")
        vm.sendMessage("Second")
        await waitForStreaming()

        XCTAssertEqual(runner.capturedCalls.count, 2)
        XCTAssertEqual(runner.capturedCalls[1].sessionId, "sid-first")
    }

    func testPersistCalledAfterStreaming() async throws {
        runner.nextResponse = .claude(text: "Hi")
        vm.sendMessage("Hello")
        await waitForStreaming()

        XCTAssertEqual(storage.saveCount, 1)
    }

    func testGeminiPathWorks() async throws {
        let geminiSession = Session(name: "Gemini", cliType: .gemini, folder: "/tmp/test")
        storage.sessions = [geminiSession]
        vm = AppViewModel(cliRunner: runner, storage: storage)
        vm.activeSessionId = geminiSession.id

        runner.nextResponse = .gemini(text: "World", sessionId: "gsid-xyz")
        vm.sendMessage("Hey")
        await waitForStreaming()

        let messages = vm.sessions[0].messages
        XCTAssertEqual(messages[1].content, "World")
        XCTAssertEqual(vm.sessions[0].geminiSessionId, "gsid-xyz")
    }

    // MARK: - Helper

    private func waitForStreaming(timeout: TimeInterval = 2) async {
        let deadline = Date().addingTimeInterval(timeout)
        while vm.isStreaming {
            guard Date() < deadline else {
                XCTFail("Timed out waiting for streaming to finish")
                return
            }
            await Task.yield()
        }
    }
}
