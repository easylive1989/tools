import Foundation

enum SessionStorage {
    static var globalDir: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".tinyflow")
    }

    static var globalSessionsFile: URL {
        globalDir.appendingPathComponent("sessions.json")
    }

    static func loadAll() -> [Session] {
        guard let data = try? Data(contentsOf: globalSessionsFile) else { return [] }
        return (try? JSONDecoder().decode([Session].self, from: data)) ?? []
    }

    static func saveAll(_ sessions: [Session]) {
        try? FileManager.default.createDirectory(at: globalDir, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(sessions) {
            try? data.write(to: globalSessionsFile, options: .atomicWrite)
        }
    }
}
