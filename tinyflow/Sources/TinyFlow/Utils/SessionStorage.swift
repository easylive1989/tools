import Foundation

enum SessionStorage {
    static func workDir(for folder: String) -> URL {
        URL(fileURLWithPath: folder).appendingPathComponent(".tinyflow")
    }

    static func sessionsFile(for folder: String) -> URL {
        workDir(for: folder).appendingPathComponent("sessions.json")
    }

    static func load(for folder: String) -> [Session] {
        let file = sessionsFile(for: folder)
        guard let data = try? Data(contentsOf: file) else { return [] }
        return (try? JSONDecoder().decode([Session].self, from: data)) ?? []
    }

    static func save(_ sessions: [Session], for folder: String) {
        let dir = workDir(for: folder)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = sessionsFile(for: folder)
        if let data = try? JSONEncoder().encode(sessions) {
            try? data.write(to: file, options: .atomicWrite)
        }
    }
}
