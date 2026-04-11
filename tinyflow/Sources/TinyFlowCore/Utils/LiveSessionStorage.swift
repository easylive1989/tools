import Foundation

struct LiveSessionStorage: SessionStoring {
    func loadAll() -> [Session] { SessionStorage.loadAll() }
    func saveAll(_ sessions: [Session]) { SessionStorage.saveAll(sessions) }
}
