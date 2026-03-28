import SwiftUI

// MARK: - Phrase List Editor

struct PhraseListEditor: View {
    let title: String
    @Binding var phrases: [Phrase]
    @State private var filterCategory: PhraseCategory? = nil

    var filtered: [Phrase] {
        guard let cat = filterCategory else { return phrases }
        return phrases.filter { $0.category == cat }
    }

    var body: some View {
        SectionCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label(title, systemImage: "text.bubble")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                    Spacer()
                    // Category filter
                    HStack(spacing: 6) {
                        FilterChip(label: "全部", isActive: filterCategory == nil) {
                            filterCategory = nil
                        }
                        ForEach(PhraseCategory.allCases, id: \.self) { cat in
                            FilterChip(label: cat.label, isActive: filterCategory == cat) {
                                filterCategory = filterCategory == cat ? nil : cat
                            }
                        }
                    }
                }

                Divider()

                // Phrases
                ForEach(Array(phrases.enumerated()), id: \.element.id) { idx, phrase in
                    if filterCategory == nil || phrase.category == filterCategory {
                        PhraseRowView(phrase: $phrases[idx]) {
                            phrases.remove(at: idx)
                        }
                        if idx < phrases.count - 1 {
                            Divider().padding(.leading, 8)
                        }
                    }
                }

                if filtered.isEmpty {
                    Text("尚無字卡")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }

                Divider()

                Button {
                    phrases.append(Phrase())
                } label: {
                    Label("新增字卡", systemImage: "plus")
                }
                .buttonStyle(.borderless)
                .padding(.top, 4)
            }
        }
    }
}

// MARK: - Phrase Row View

struct PhraseRowView: View {
    @Binding var phrase: Phrase
    let onDelete: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                TextField("中文", text: $phrase.zh)
                    .font(.title3)
                    .textFieldStyle(.plain)
                TextField("English", text: $phrase.en)
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .textFieldStyle(.plain)
                Picker("", selection: $phrase.category) {
                    ForEach(PhraseCategory.allCases, id: \.self) { cat in
                        Text(cat.label).tag(cat)
                    }
                }
                .pickerStyle(.menu)
                .labelsHidden()
                .controlSize(.mini)
            }
            Spacer()
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .foregroundStyle(.red.opacity(0.7))
            }
            .buttonStyle(.borderless)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Filter Chip

struct FilterChip: View {
    let label: String
    let isActive: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.body)
                .fontWeight(isActive ? .semibold : .regular)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(isActive ? Color.accentColor : Color(NSColor.controlBackgroundColor))
                .foregroundStyle(isActive ? .white : Color.primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}
