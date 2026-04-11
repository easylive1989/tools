import SwiftUI
import MarkdownUI

struct MessageView: View {
    let message: Message

    var body: some View {
        if message.role == .user {
            UserMessageView(content: message.content)
        } else {
            AssistantMessageView(message: message)
        }
    }
}

struct UserMessageView: View {
    let content: String

    var body: some View {
        HStack {
            Spacer(minLength: 60)
            Text(content)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color(red: 0.15, green: 0.39, blue: 0.92))
                .foregroundColor(.white)
                .cornerRadius(16)
                .textSelection(.enabled)
        }
    }
}

struct AssistantMessageView: View {
    let message: Message

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                if message.isStreaming {
                    // Plain text during streaming for performance
                    Text(message.content)
                        .font(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    TypingDotsView()
                } else {
                    // Rendered Markdown after streaming completes
                    Markdown(message.content)
                        .markdownTheme(.gitHub)
                        .textSelection(.enabled)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(16)

            Spacer(minLength: 60)
        }
    }
}
