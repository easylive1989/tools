import Foundation

protocol CLIRunning {
    func run(
        cliType: CLIType,
        message: String,
        sessionId: String?,
        workingDir: String
    ) -> AsyncStream<String>
}
