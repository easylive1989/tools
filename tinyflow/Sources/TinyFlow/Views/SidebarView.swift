import SwiftUI

struct SidebarView: View {
    @EnvironmentObject var viewModel: AppViewModel

    var body: some View {
        VStack(spacing: 0) {
            List(selection: $viewModel.activeSessionId) {
                ForEach(viewModel.sessions) { session in
                    SessionRowView(session: session)
                        .tag(session.id)
                        .contextMenu {
                            Button("刪除 Session", role: .destructive) {
                                viewModel.deleteSession(session)
                            }
                        }
                }
            }
            .listStyle(.sidebar)

            Divider()

            Button(action: { viewModel.showNewSessionSheet = true }) {
                Label("新增 Session", systemImage: "plus")
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
            }
            .buttonStyle(.plain)
            .foregroundColor(.accentColor)
        }
        .frame(minWidth: 200)
    }
}

struct SessionRowView: View {
    let session: Session

    private var accentColor: Color {
        session.cliType == .claude
            ? Color(red: 0.15, green: 0.39, blue: 0.92)
            : Color(red: 0.10, green: 0.45, blue: 0.91)
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(accentColor)
                .frame(width: 7, height: 7)

            VStack(alignment: .leading, spacing: 2) {
                Text(session.name)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)

                Text(session.folderName)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            Text(session.cliType.displayName)
                .font(.system(size: 10, weight: .semibold))
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(accentColor.opacity(0.12))
                .foregroundColor(accentColor)
                .cornerRadius(4)
        }
        .padding(.vertical, 3)
    }
}
