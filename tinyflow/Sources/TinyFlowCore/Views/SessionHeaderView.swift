import SwiftUI

struct SessionHeaderView: View {
    let session: Session

    private var accentColor: Color {
        session.cliType == .claude
            ? Color(red: 0.15, green: 0.39, blue: 0.92)
            : Color(red: 0.10, green: 0.45, blue: 0.91)
    }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(session.name)
                    .font(.headline)
                    .lineLimit(1)

                Text(session.folder)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            Text(session.cliType.displayName)
                .font(.caption)
                .fontWeight(.semibold)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(accentColor.opacity(0.12))
                .foregroundColor(accentColor)
                .cornerRadius(6)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(NSColor.windowBackgroundColor))
    }
}
