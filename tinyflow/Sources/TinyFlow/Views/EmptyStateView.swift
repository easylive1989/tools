import SwiftUI

struct EmptyStateView: View {
    @EnvironmentObject var viewModel: AppViewModel

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "terminal.fill")
                .font(.system(size: 52))
                .foregroundColor(Color(NSColor.separatorColor))

            Text("選擇 Session 或新增一個開始對話")
                .font(.title3)
                .foregroundColor(.secondary)

            Button("新增 Session") {
                viewModel.showNewSessionSheet = true
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(NSColor.windowBackgroundColor))
    }
}
