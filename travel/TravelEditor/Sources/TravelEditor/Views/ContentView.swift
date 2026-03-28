import SwiftUI

struct ContentView: View {
    @Binding var itinerary: Itinerary
    @State private var selectedDayID: UUID? = nil
    @State private var showingCommonPhrases = false
    @State private var showingTripSettings = false

    var body: some View {
        NavigationSplitView {
            // ── Sidebar ──────────────────────────────────────────────────────
            VStack(spacing: 0) {
                // Trip header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(itinerary.title.isEmpty ? "未命名旅程" : itinerary.title)
                            .font(.headline)
                            .lineLimit(1)
                        if !itinerary.subtitle.isEmpty {
                            Text(itinerary.subtitle)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                    Spacer()
                    Button {
                        showingTripSettings = true
                    } label: {
                        Image(systemName: "pencil.circle")
                    }
                    .buttonStyle(.borderless)
                    .help("編輯旅程資訊")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(NSColor.controlBackgroundColor))

                Divider()

                // Day list
                List(selection: $selectedDayID) {
                    ForEach($itinerary.days) { $day in
                        DayRow(day: day)
                            .tag(day.id)
                            .contextMenu {
                                Button("刪除此天", role: .destructive) {
                                    deleteDay(id: day.id)
                                }
                            }
                    }
                    .onMove(perform: moveDays)
                }
                .listStyle(.sidebar)

                Divider()

                // Bottom toolbar
                HStack {
                    Button {
                        addDay()
                    } label: {
                        Label("新增天", systemImage: "plus")
                    }
                    .buttonStyle(.borderless)

                    Spacer()

                    Button {
                        showingCommonPhrases = true
                    } label: {
                        Label("通用字卡", systemImage: "globe")
                    }
                    .buttonStyle(.borderless)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
        } detail: {
            // ── Detail ───────────────────────────────────────────────────────
            if let id = selectedDayID,
               let idx = itinerary.days.firstIndex(where: { $0.id == id }) {
                DayDetailView(day: $itinerary.days[idx])
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "airplane.circle")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("選擇左側的天數開始編輯")
                        .foregroundStyle(.secondary)
                    Button("新增第一天") { addDay() }
                        .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle("")
        .sheet(isPresented: $showingTripSettings) {
            TripSettingsSheet(itinerary: $itinerary)
        }
        .sheet(isPresented: $showingCommonPhrases) {
            CommonPhrasesSheet(phrases: $itinerary.commonPhrases)
        }
    }

    // MARK: - Actions

    private func addDay() {
        let nextNum = (itinerary.days.map(\.day).max() ?? 0) + 1
        let newDay = Day(day: nextNum, date: "", title: "新行程", city: "", flag: "🇦🇹")
        itinerary.days.append(newDay)
        selectedDayID = newDay.id
    }

    private func deleteDay(id: UUID) {
        itinerary.days.removeAll { $0.id == id }
        if selectedDayID == id { selectedDayID = nil }
    }

    private func moveDays(from source: IndexSet, to destination: Int) {
        itinerary.days.move(fromOffsets: source, toOffset: destination)
        for (i, _) in itinerary.days.enumerated() {
            itinerary.days[i].day = i + 1
        }
    }
}

// MARK: - Day Row

struct DayRow: View {
    let day: Day

    var body: some View {
        HStack(spacing: 8) {
            Text(day.flag.isEmpty ? "📅" : day.flag)
                .font(.title3)

            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    Text("第 \(day.day) 天")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                    if !day.date.isEmpty {
                        Text("· \(day.date)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(day.title.isEmpty ? "（未命名）" : day.title)
                    .font(.title3)
                    .lineLimit(1)
                if !day.city.isEmpty {
                    Text(day.city)
                        .font(.footnote)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
