import SwiftUI

// MARK: - Trip Settings Sheet

struct TripSettingsSheet: View {
    @Binding var itinerary: Itinerary
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Text("旅程設定")
                    .font(.title3).fontWeight(.semibold)
                Spacer()
                Button("完成") { dismiss() }
                    .fontWeight(.semibold)
            }
            .padding()

            Divider()

            Form {
                Section("旅程資訊") {
                    LabeledContent("標題") {
                        TextField("奧捷旅遊手冊 2026", text: $itinerary.title)
                            .multilineTextAlignment(.trailing)
                    }
                    LabeledContent("副標題") {
                        TextField("日期・天數・城市", text: $itinerary.subtitle)
                            .multilineTextAlignment(.trailing)
                    }
                }
            }
            .formStyle(.grouped)
        }
        .frame(width: 460, height: 230)
        .environment(\.font, .system(size: 17))
        .controlSize(.large)
    }
}

// MARK: - Common Phrases Sheet

struct CommonPhrasesSheet: View {
    @Binding var phrases: [Phrase]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Text("通用字卡")
                    .font(.title3).fontWeight(.semibold)
                Spacer()
                Button("完成") { dismiss() }
                    .fontWeight(.semibold)
            }
            .padding()

            Divider()

            ScrollView {
                PhraseListEditor(
                    title: "通用字卡",
                    phrases: $phrases
                )
                .padding(20)
            }
        }
        .frame(width: 620, height: 680)
        .environment(\.font, .system(size: 17))
        .controlSize(.large)
    }
}
