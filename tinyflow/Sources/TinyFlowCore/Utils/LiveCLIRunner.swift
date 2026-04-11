import Foundation

struct LiveCLIRunner: CLIRunning {
    func run(
        cliType: CLIType,
        message: String,
        sessionId: String?,
        workingDir: String
    ) -> AsyncStream<String> {
        CLIRunner.run(cliType: cliType, message: message, sessionId: sessionId, workingDir: workingDir)
    }
}
