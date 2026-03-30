import Foundation

enum CLIRunner {
    static let claudePath = "/Users/paulwu/.claude/local/claude"
    static let geminiPath = "/opt/homebrew/bin/gemini"

    static func binaryPath(for cliType: CLIType) -> String {
        switch cliType {
        case .claude: return claudePath
        case .gemini: return geminiPath
        }
    }

    static func buildArgs(cliType: CLIType, message: String, sessionId: String?) -> [String] {
        var args: [String] = []

        if let sessionId, !sessionId.isEmpty {
            args += ["-r", sessionId]
        }

        switch cliType {
        case .claude:
            args += [
                "-p", message,
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--dangerously-skip-permissions",
                "--verbose"
            ]
        case .gemini:
            args += [
                "-p", message,
                "--output-format", "stream-json",
                "-y"
            ]
        }

        return args
    }

    /// Runs the CLI and returns an AsyncStream of raw stdout lines.
    static func run(
        cliType: CLIType,
        message: String,
        sessionId: String?,
        workingDir: String
    ) -> AsyncStream<String> {
        AsyncStream { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: binaryPath(for: cliType))
            process.arguments = buildArgs(cliType: cliType, message: message, sessionId: sessionId)
            process.currentDirectoryURL = URL(fileURLWithPath: workingDir)

            let pipe = Pipe()
            let errPipe = Pipe()
            process.standardOutput = pipe
            process.standardError = errPipe

            let fileHandle = pipe.fileHandleForReading
            var buffer = Data()

            fileHandle.readabilityHandler = { handle in
                let data = handle.availableData
                guard !data.isEmpty else {
                    fileHandle.readabilityHandler = nil
                    // Flush remaining buffer as a final line
                    if let line = String(data: buffer, encoding: .utf8),
                       !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        continuation.yield(line)
                    }
                    return
                }

                buffer.append(data)

                // Split on newline (0x0A)
                while let nlIdx = buffer.firstIndex(of: 0x0A) {
                    let lineData = buffer[buffer.startIndex..<nlIdx]
                    buffer = Data(buffer[buffer.index(after: nlIdx)...])
                    if let line = String(data: lineData, encoding: .utf8),
                       !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        continuation.yield(line)
                    }
                }
            }

            process.terminationHandler = { _ in
                fileHandle.readabilityHandler = nil
                continuation.finish()
            }

            do {
                try process.run()
            } catch {
                continuation.finish()
            }
        }
    }
}
