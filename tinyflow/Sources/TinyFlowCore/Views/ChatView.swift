import SwiftUI

struct ChatView: View {
    @EnvironmentObject var viewModel: AppViewModel
    @State private var inputText = ""
    @State private var scrollProxy: ScrollViewProxy? = nil

    private var session: Session? {
        viewModel.activeSession
    }

    private var messages: [Message] {
        session?.messages ?? []
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            if let session {
                SessionHeaderView(session: session)
                Divider()
            }

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 16) {
                        ForEach(messages) { message in
                            MessageView(message: message)
                                .id(message.id)
                        }

                        if viewModel.isStreaming && messages.last?.role == .user {
                            TypingDotsView()
                                .id("typing")
                        }

                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                }
                .onChange(of: messages.count) { _ in
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo("bottom")
                    }
                }
                .onChange(of: messages.last?.content) { _ in
                    proxy.scrollTo("bottom")
                }
                .onChange(of: viewModel.isStreaming) { streaming in
                    if streaming {
                        proxy.scrollTo("bottom")
                    }
                }
            }

            Divider()

            // Input
            MessageInputView(
                text: $inputText,
                isStreaming: viewModel.isStreaming
            ) {
                let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return }
                inputText = ""
                viewModel.sendMessage(text)
            } onCancel: {
                viewModel.cancelStreaming()
            }
        }
        .background(Color(NSColor.windowBackgroundColor))
    }
}
