import SwiftUI

struct RootView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        if Binding($store.document) != nil {
            ContentView(
                itinerary: Binding(
                    get: { store.document!.itinerary },
                    set: { store.document!.itinerary = $0; store.markDirty() }
                )
            )
            .environment(\.font, .system(size: 17))
            .controlSize(.large)
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    HStack(alignment: .center, spacing: 6) {
                        Image(systemName: "doc.text")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(.primary)
                        Text(store.document?.url.lastPathComponent ?? "")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(.primary)
                        if store.isDirty {
                            Circle()
                                .fill(Color.accentColor)
                                .frame(width: 7, height: 7)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 7))
                }
            }
        } else {
            WelcomeView()
        }
    }
}

// MARK: - Welcome Screen

struct WelcomeView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "airplane.circle.fill")
                .font(.system(size: 80))
                .foregroundStyle(.blue.gradient)

            VStack(spacing: 6) {
                Text("旅遊行程編輯工具")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                Text("開啟或新建 itinerary.md 檔案開始編輯")
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                Button {
                    store.openFile()
                } label: {
                    Label("開啟行程檔案…", systemImage: "folder")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .keyboardShortcut("o")

                Button {
                    store.document = MarkdownFile(
                        url: URL(fileURLWithPath: "untitled.md"),
                        itinerary: Itinerary(title: "新旅程", subtitle: "")
                    )
                } label: {
                    Label("新建旅程", systemImage: "plus")
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }

            // Recent hint
            Text("提示：可直接把 itinerary.md 拖放到此視窗")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            providers.first?.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                if let data = item as? Data,
                   let url = URL(dataRepresentation: data, relativeTo: nil) {
                    DispatchQueue.main.async {
                        store.loadFile(from: url)
                    }
                }
            }
            return true
        }
    }
}
