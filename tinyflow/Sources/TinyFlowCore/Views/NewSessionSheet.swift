import SwiftUI
import AppKit

struct NewSessionSheet: View {
    @EnvironmentObject var viewModel: AppViewModel
    @Environment(\.dismiss) var dismiss

    @State private var sessionName = ""
    @State private var selectedCLI: CLIType = .claude
    @State private var selectedFolder = ""

    private var displayFolderName: String {
        selectedFolder.isEmpty
            ? "尚未選擇"
            : URL(fileURLWithPath: selectedFolder).lastPathComponent
    }

    private var defaultName: String {
        let folder = selectedFolder.isEmpty ? "新 Session" : URL(fileURLWithPath: selectedFolder).lastPathComponent
        return "\(selectedCLI.displayName) — \(folder)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Title
            Text("新增 Session")
                .font(.title2)
                .fontWeight(.semibold)
                .padding(.bottom, 20)

            // CLI Picker
            VStack(alignment: .leading, spacing: 6) {
                Text("CLI 類型")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fontWeight(.medium)

                Picker("CLI", selection: $selectedCLI) {
                    ForEach(CLIType.allCases, id: \.self) { cli in
                        Text(cli.displayName).tag(cli)
                    }
                }
                .pickerStyle(.segmented)
            }
            .padding(.bottom, 16)

            // Folder Picker
            VStack(alignment: .leading, spacing: 6) {
                Text("工作資料夾")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fontWeight(.medium)

                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(displayFolderName)
                            .fontWeight(selectedFolder.isEmpty ? .regular : .medium)
                            .foregroundColor(selectedFolder.isEmpty ? .secondary : .primary)

                        if !selectedFolder.isEmpty {
                            Text(selectedFolder)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }

                    Spacer()

                    Button("選擇…") { pickFolder() }
                        .buttonStyle(.bordered)
                }
                .padding(10)
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)
            }
            .padding(.bottom, 16)

            // Session Name
            VStack(alignment: .leading, spacing: 6) {
                Text("Session 名稱（選填）")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fontWeight(.medium)

                TextField(defaultName, text: $sessionName)
                    .textFieldStyle(.roundedBorder)
            }
            .padding(.bottom, 24)

            // Buttons
            HStack {
                Button("取消") { dismiss() }
                    .keyboardShortcut(.escape)

                Spacer()

                Button("建立") { createSession() }
                    .keyboardShortcut(.return)
                    .disabled(selectedFolder.isEmpty)
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 420)
    }

    private func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.title = "選擇工作資料夾"
        panel.prompt = "選擇"

        if panel.runModal() == .OK {
            selectedFolder = panel.url?.path ?? ""
        }
    }

    private func createSession() {
        let name = sessionName.trimmingCharacters(in: .whitespaces).isEmpty ? defaultName : sessionName
        viewModel.createSession(name: name, cliType: selectedCLI, folder: selectedFolder)
        dismiss()
    }
}
