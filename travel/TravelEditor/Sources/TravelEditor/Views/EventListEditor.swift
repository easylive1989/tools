import SwiftUI
import UniformTypeIdentifiers

// MARK: - Event List Editor

struct EventListEditor: View {
    @Binding var events: [Event]
    @State private var editingEvent: Event? = nil
    @State private var editingIndex: Int? = nil
    @State private var showingAdd = false
    @State private var draggingID: UUID? = nil
    @State private var hoveredID: UUID? = nil

    var body: some View {
        Group {
        SectionCard {
            VStack(alignment: .leading, spacing: 10) {
            Label("行程", systemImage: "calendar")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 0) {
                if events.isEmpty {
                    Text("尚無行程項目")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(events.enumerated()), id: \.element.id) { idx, event in
                            EventRowView(event: event)
                                .opacity(draggingID == event.id ? 0.4 : 1.0)
                                .overlay(alignment: .trailing) {
                                    if hoveredID == event.id {
                                        Button {
                                            let i = idx
                                            withAnimation { events.removeSubrange(i...i) }
                                        } label: {
                                            Image(systemName: "trash")
                                                .foregroundStyle(.red)
                                                .padding(8)
                                                .background(.regularMaterial, in: Circle())
                                        }
                                        .buttonStyle(.plain)
                                        .padding(.trailing, 8)
                                    }
                                }
                                .onHover { hoveredID = $0 ? event.id : nil }
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    editingEvent = event
                                    editingIndex = idx
                                }
                                .contextMenu {
                                    Button("編輯") {
                                        editingEvent = event
                                        editingIndex = idx
                                    }
                                    Divider()
                                    Button("刪除", role: .destructive) {
                                        events.remove(at: idx)
                                    }
                                }
                                .onDrag {
                                    draggingID = event.id
                                    return NSItemProvider(object: event.id.uuidString as NSString)
                                }
                                .onDrop(of: [UTType.plainText], delegate: EventDropDelegate(
                                    targetEvent: event,
                                    events: $events,
                                    draggingID: $draggingID
                                ))

                            if idx < events.count - 1 {
                                Divider().padding(.leading, 44)
                            }
                        }
                    }
                }

                Divider().padding(.top, 8)

                Button {
                    showingAdd = true
                } label: {
                    Label("新增行程", systemImage: "plus")
                }
                .buttonStyle(.borderless)
                .padding(.top, 6)
            }
            } // end VStack
        } // end SectionCard
        } // end Group
        .sheet(item: $editingEvent) { event in
            EventEditorSheet(
                event: event,
                onSave: { updated in
                    if let idx = editingIndex {
                        events[idx] = updated
                    }
                    editingEvent = nil
                    editingIndex = nil
                },
                onCancel: {
                    editingEvent = nil
                    editingIndex = nil
                }
            )
        }
        .sheet(isPresented: $showingAdd) {
            EventEditorSheet(
                event: Event(),
                onSave: { newEvent in
                    events.append(newEvent)
                    showingAdd = false
                },
                onCancel: { showingAdd = false }
            )
        }
    }
}

// MARK: - Event Row View

struct EventRowView: View {
    let event: Event

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "line.3.horizontal")
                .foregroundStyle(.tertiary)
                .font(.system(size: 15))
                .padding(.top, 8)

            // Time + icon column
            VStack(alignment: .trailing, spacing: 2) {
                Text(event.time.isEmpty ? "--:--" : event.time)
                    .font(.system(size: 18, design: .monospaced))
                    .foregroundStyle(.secondary)
                Text(event.icon.isEmpty ? event.type.defaultIcon : event.icon)
                    .font(.system(size: 34))
            }
            .frame(width: 82, alignment: .trailing)

            // Content
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 7) {
                    Text(event.title.isEmpty ? "（未命名）" : event.title)
                        .font(.system(size: 20, weight: .semibold))
                        .lineLimit(1)
                    TypeBadge(type: event.type)
                    if !event.mapUrl.isEmpty {
                        Image(systemName: "map.fill")
                            .font(.system(size: 13))
                            .foregroundStyle(Color.accentColor.opacity(0.7))
                    }
                }
                if !event.subtitle.isEmpty {
                    Text(event.subtitle)
                        .font(.system(size: 18))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if !event.notes.isEmpty {
                    Text(event.notes.prefix(2).joined(separator: "・"))
                        .font(.system(size: 16))
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 14))
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Type Badge

struct TypeBadge: View {
    let type: EventType

    var color: Color {
        switch type {
        case .transport: return .blue
        case .food: return .orange
        case .sight: return .green
        case .hotel: return .purple
        case .info: return .gray
        }
    }

    var body: some View {
        Text(type.label)
            .font(.system(size: 14, weight: .medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - Event Editor Sheet

struct EventEditorSheet: View {
    @State var event: Event
    let onSave: (Event) -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button("取消", action: onCancel)
                Spacer()
                Text(event.title.isEmpty ? "新增行程" : event.title)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Button("儲存") { onSave(event) }
                    .fontWeight(.semibold)
            }
            .padding()

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {

                    // Basic info
                    GroupBox("行程資訊") {
                        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
                            GridRow {
                                Text("時間").foregroundStyle(.secondary)
                                TextField("例：10:46", text: $event.time)
                                    .textFieldStyle(.roundedBorder)
                            }
                            GridRow {
                                Text("類型").foregroundStyle(.secondary)
                                Picker("", selection: $event.type) {
                                    ForEach(EventType.allCases, id: \.self) { t in
                                        Text(t.label).tag(t)
                                    }
                                }
                                .pickerStyle(.segmented)
                            }
                            GridRow {
                                Text("圖示").foregroundStyle(.secondary)
                                HStack {
                                    TextField("🚌", text: $event.icon)
                                        .textFieldStyle(.roundedBorder)
                                        .frame(width: 60)
                                    Button("預設") {
                                        event.icon = event.type.defaultIcon
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                }
                            }
                            GridRow {
                                Text("標題").foregroundStyle(.secondary)
                                TextField("行程標題", text: $event.title)
                                    .textFieldStyle(.roundedBorder)
                            }
                            GridRow {
                                Text("副標題").foregroundStyle(.secondary)
                                TextField("地點或說明", text: $event.subtitle)
                                    .textFieldStyle(.roundedBorder)
                            }
                            GridRow {
                                Text("地圖").foregroundStyle(.secondary)
                                MapUrlField(url: $event.mapUrl)
                            }
                        }
                        .padding(4)
                    }

                    // Notes
                    StringListEditor(
                        title: "注意事項",
                        systemImage: "note.text",
                        items: $event.notes,
                        placeholder: "新增注意事項..."
                    )
                }
                .padding(20)
            }
        }
        .frame(width: 580, height: 640)
        .environment(\.font, .system(size: 17))
        .controlSize(.large)
    }
}

// MARK: - Drop Delegate

struct EventDropDelegate: DropDelegate {
    let targetEvent: Event
    @Binding var events: [Event]
    @Binding var draggingID: UUID?

    func dropEntered(info: DropInfo) {
        guard let draggingID,
              draggingID != targetEvent.id,
              let from = events.firstIndex(where: { $0.id == draggingID }),
              let to   = events.firstIndex(where: { $0.id == targetEvent.id })
        else { return }
        withAnimation(.easeInOut(duration: 0.2)) {
            events.move(fromOffsets: IndexSet(integer: from),
                        toOffset: to > from ? to + 1 : to)
        }
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        draggingID = nil
        return true
    }
}
