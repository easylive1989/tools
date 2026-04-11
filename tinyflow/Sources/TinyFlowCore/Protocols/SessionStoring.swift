import Foundation

protocol SessionStoring {
    func loadAll() -> [Session]
    func saveAll(_ sessions: [Session])
}
