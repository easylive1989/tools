import SwiftUI

struct DayDetailView: View {
    @Binding var day: Day

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {


                HStack(alignment: .top, spacing: 16) {

                    // ── Left: 行程 + 英文字卡 ─────────────────────────────────
                    VStack(spacing: 16) {
                        EventListEditor(events: $day.events)
                        PhraseListEditor(
                            title: "英文字卡",
                            phrases: $day.phrases
                        )
                    }
                    .frame(minWidth: 0, maxWidth: .infinity)

                    // ── Right: 基本資料 + 住宿 + 今日重點 ─────────────────────
                    VStack(spacing: 16) {
                        // 基本資料
                        SectionCard {
                            VStack(alignment: .leading, spacing: 10) {
                                Label("基本資料", systemImage: "info.circle")
                                    .font(.subheadline).fontWeight(.semibold)
                                    .foregroundStyle(.secondary)

                                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 10) {
                                    GridRow {
                                        Text("天期").foregroundStyle(.secondary)
                                        HStack(spacing: 6) {
                                            Text("第").foregroundStyle(.secondary)
                                            TextField("", value: $day.day, format: .number)
                                                .frame(width: 44)
                                                .textFieldStyle(.roundedBorder)
                                            Text("天").foregroundStyle(.secondary)
                                        }
                                    }
                                    GridRow {
                                        Text("日期").foregroundStyle(.secondary)
                                        DatePickerRow(dateString: $day.date)
                                    }
                                    Divider().gridCellUnsizedAxes(.horizontal)
                                    GridRow {
                                        Text("標題").foregroundStyle(.secondary)
                                        TextField("出發 → 維也納", text: $day.title)
                                            .textFieldStyle(.roundedBorder)
                                    }
                                    Divider().gridCellUnsizedAxes(.horizontal)
                                    GridRow {
                                        Text("城市").foregroundStyle(.secondary)
                                        HStack(spacing: 8) {
                                            TextField("台灣 → 維也納", text: $day.city)
                                                .textFieldStyle(.roundedBorder)
                                            FlagPicker(flag: $day.flag)
                                        }
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        HotelEditor(hotel: $day.hotel)

                        StringListEditor(
                            title: "今日重點",
                            systemImage: "star.fill",
                            items: $day.highlights,
                            placeholder: "新增重點..."
                        )
                    }
                    .frame(width: 320)
                }
            }
            .padding(20)
        }
        .background(Color(NSColor.windowBackgroundColor))
        .navigationTitle("第 \(day.day) 天 · \(day.title)")
    }
}

// MARK: - Section Card (replaces GroupBox for cleaner look)

struct SectionCard<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(NSColor.controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.06), radius: 4, x: 0, y: 2)
    }
}

// MARK: - Hotel Editor

struct HotelEditor: View {
    @Binding var hotel: Hotel?
    @State private var isExpanded = true

    var body: some View {
        SectionCard {
            VStack(alignment: .leading, spacing: 10) {
                Label("住宿", systemImage: "bed.double.fill")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)

                if hotel != nil {
                    Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
                        GridRow {
                            Text("名稱").foregroundStyle(.secondary)
                            TextField("飯店名稱", text: Binding(
                                get: { hotel?.name ?? "" },
                                set: { hotel?.name = $0 }
                            ))
                            .textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("地址").foregroundStyle(.secondary)
                            TextField("地址", text: Binding(
                                get: { hotel?.address ?? "" },
                                set: { hotel?.address = $0 }
                            ))
                            .textFieldStyle(.roundedBorder)
                        }
                        GridRow {
                            Text("地圖").foregroundStyle(.secondary)
                            MapUrlField(url: Binding(
                                get: { hotel?.mapUrl ?? "" },
                                set: { hotel?.mapUrl = $0 }
                            ))
                        }
                    }

                    // Notes
                    Divider()
                    HotelNotesEditor(notes: Binding(
                        get: { hotel?.notes ?? [] },
                        set: { hotel?.notes = $0 }
                    ))

                    Button("移除住宿資訊", role: .destructive) { hotel = nil }
                        .buttonStyle(.borderless)
                        .foregroundStyle(.red)
                        .font(.footnote)
                } else {
                    HStack {
                        Text("尚未設定住宿").foregroundStyle(.tertiary)
                        Spacer()
                        Button("新增住宿") { hotel = Hotel() }
                            .buttonStyle(.bordered)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

// MARK: - Hotel Notes Editor

struct HotelNotesEditor: View {
    @Binding var notes: [String]
    @State private var newNote = ""
    @FocusState private var focusNew: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("備註", systemImage: "note.text")
                .font(.footnote)
                .foregroundStyle(.secondary)

            ForEach(Array(notes.enumerated()), id: \.offset) { idx, _ in
                HStack {
                    Image(systemName: "line.3.horizontal")
                        .foregroundStyle(.tertiary).font(.footnote)
                    TextField("備註內容", text: $notes[idx])
                        .textFieldStyle(.plain)
                    Button {
                        notes.remove(at: idx)
                    } label: {
                        Image(systemName: "minus.circle.fill")
                            .foregroundStyle(.red.opacity(0.7))
                    }
                    .buttonStyle(.borderless)
                }
            }

            HStack {
                Image(systemName: "plus.circle").foregroundStyle(Color.accentColor)
                TextField("新增備註...", text: $newNote)
                    .textFieldStyle(.plain)
                    .focused($focusNew)
                    .onSubmit {
                        let t = newNote.trimmingCharacters(in: .whitespaces)
                        guard !t.isEmpty else { return }
                        notes.append(t)
                        newNote = ""
                        focusNew = true
                    }
            }
        }
    }
}

// MARK: - String List Editor

struct StringListEditor: View {
    let title: String
    let systemImage: String
    @Binding var items: [String]
    var placeholder: String = "新增..."

    @State private var newItem = ""
    @FocusState private var focusNew: Bool

    var body: some View {
        SectionCard {
            VStack(alignment: .leading, spacing: 10) {
                Label(title, systemImage: systemImage)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(items.enumerated()), id: \.offset) { idx, item in
                        HStack {
                            Image(systemName: "line.3.horizontal")
                                .foregroundStyle(.tertiary)
                                .font(.footnote)
                            TextField("", text: $items[idx])
                                .textFieldStyle(.plain)
                            Button {
                                items.remove(at: idx)
                            } label: {
                                Image(systemName: "minus.circle.fill")
                                    .foregroundStyle(.red.opacity(0.7))
                            }
                            .buttonStyle(.borderless)
                        }
                    }
                }

                HStack {
                    Image(systemName: "plus.circle")
                        .foregroundStyle(Color.accentColor)
                    TextField(placeholder, text: $newItem)
                        .textFieldStyle(.plain)
                        .focused($focusNew)
                        .onSubmit { commitNew() }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func commitNew() {
        let trimmed = newItem.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        items.append(trimmed)
        newItem = ""
        focusNew = true
    }
}

// MARK: - Date Picker Row
// Converts between stored "4/1 (三)" string and SwiftUI DatePicker Date

struct DatePickerRow: View {
    @Binding var dateString: String

    // Parse "4/1 (三)" → Date (assume year 2026)
    private var date: Date {
        let parts = dateString.components(separatedBy: "/")
        guard parts.count >= 2,
              let month = Int(parts[0].trimmingCharacters(in: .whitespaces)),
              let dayPart = parts[1].components(separatedBy: " ").first,
              let day = Int(dayPart)
        else { return Date() }

        var comps = DateComponents()
        comps.year = 2026
        comps.month = month
        comps.day = day
        return Calendar.current.date(from: comps) ?? Date()
    }

    private func dateToString(_ d: Date) -> String {
        let cal = Calendar.current
        let month = cal.component(.month, from: d)
        let day = cal.component(.day, from: d)
        let weekdays = ["日", "一", "二", "三", "四", "五", "六"]
        let wd = cal.component(.weekday, from: d) - 1 // 1=Sun
        let wdStr = weekdays[safe: wd] ?? ""
        return "\(month)/\(day) (\(wdStr))"
    }

    var body: some View {
        HStack(spacing: 6) {
            DatePicker(
                "",
                selection: Binding(
                    get: { date },
                    set: { dateString = dateToString($0) }
                ),
                in: Date.from(year: 2026, month: 1, day: 1)...,
                displayedComponents: [.date]
            )
            .labelsHidden()
            .datePickerStyle(.field)
            .environment(\.locale, Locale(identifier: "zh_TW"))
            // Show only month/day by hiding the year via clip + fixed width
            .frame(width: 120)
            .clipped()

            if !dateString.isEmpty {
                Text(weekdayLabel)
                    .foregroundStyle(.secondary)
                    .font(.body)
            }
        }
    }

    private var weekdayLabel: String {
        let weekdays = ["日", "一", "二", "三", "四", "五", "六"]
        let cal = Calendar.current
        let wd = cal.component(.weekday, from: date) - 1
        return "(\(weekdays[safe: wd] ?? ""))"
    }
}

// MARK: - Flag Picker

private let commonFlags: [(String, String)] = [
    ("🇹🇼", "台灣"), ("🇦🇹", "奧地利"), ("🇨🇿", "捷克"),
    ("🇩🇪", "德國"), ("🇨🇭", "瑞士"), ("🇮🇹", "義大利"),
    ("🇫🇷", "法國"), ("🇪🇸", "西班牙"), ("🇬🇧", "英國"),
    ("🇯🇵", "日本"), ("🇰🇷", "韓國"), ("🇺🇸", "美國"),
    ("🇹🇭", "泰國"), ("🇸🇬", "新加坡"), ("🇭🇰", "香港"),
    ("🇳🇱", "荷蘭"), ("🇧🇪", "比利時"), ("🇵🇱", "波蘭"),
    ("🇭🇺", "匈牙利"), ("🇸🇰", "斯洛伐克"), ("🇭🇷", "克羅埃西亞"),
]

struct FlagPicker: View {
    @Binding var flag: String
    @State private var showPopover = false

    var body: some View {
        Button {
            showPopover.toggle()
        } label: {
            Text(flag.isEmpty ? "🏳️" : flag)
                .font(.title2)
                .frame(width: 44, height: 34)
                .background(Color(NSColor.controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color(NSColor.separatorColor), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showPopover, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 10) {
                Text("選擇國旗")
                    .font(.headline)
                    .padding(.horizontal, 4)

                let columns = Array(repeating: GridItem(.fixed(52), spacing: 6), count: 6)
                LazyVGrid(columns: columns, spacing: 6) {
                    ForEach(commonFlags, id: \.0) { emoji, name in
                        Button {
                            flag = emoji
                            showPopover = false
                        } label: {
                            VStack(spacing: 2) {
                                Text(emoji).font(.title2)
                                Text(name)
                                    .font(.system(size: 9))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            .frame(width: 50, height: 44)
                            .background(flag == emoji ? Color.accentColor.opacity(0.15) : Color.clear)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(12)
            .frame(width: 360)
        }
    }
}

// MARK: - Map URL Field

struct MapUrlField: View {
    @Binding var url: String

    var body: some View {
        TextField("Google Maps URL", text: $url)
            .textFieldStyle(.roundedBorder)
    }
}

// MARK: - Helpers

extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

extension Date {
    static func from(year: Int, month: Int, day: Int) -> Date {
        var c = DateComponents(); c.year = year; c.month = month; c.day = day
        return Calendar.current.date(from: c) ?? Date()
    }
}
