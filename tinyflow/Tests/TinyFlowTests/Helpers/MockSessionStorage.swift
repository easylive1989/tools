import Foundation
@testable import TinyFlowCore

final class MockSessionStorage: SessionStoring {
    var sessions: [Session] = []
    private(set) var saveCount = 0

    func loadAll() -> [Session] { sessions }
    func saveAll(_ sessions: [Session]) {
        self.sessions = sessions
        saveCount += 1
    }
}
