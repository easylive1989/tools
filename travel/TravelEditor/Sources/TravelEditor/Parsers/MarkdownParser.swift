import Foundation

// Parses itinerary.md into the Itinerary model
enum MarkdownParser {

    static func parse(from text: String) -> Itinerary {
        var itinerary = Itinerary()
        let lines = text.components(separatedBy: "\n")
        var i = 0

        // ── Title block ──────────────────────────────────────────────────────
        while i < lines.count {
            let line = lines[i]
            if line.hasPrefix("# ") {
                itinerary.title = String(line.dropFirst(2))
                i += 1
                if i < lines.count && !lines[i].hasPrefix("#") && !lines[i].isEmpty {
                    itinerary.subtitle = lines[i]
                }
            } else if line == "## 通用字卡" {
                break
            }
            i += 1
        }

        // ── Common phrases ────────────────────────────────────────────────────
        if i < lines.count && lines[i] == "## 通用字卡" {
            i += 1
            while i < lines.count && !lines[i].hasPrefix("---") && !lines[i].hasPrefix("## 第") {
                if let phrase = parseTableRow(lines[i]) {
                    itinerary.commonPhrases.append(phrase)
                }
                i += 1
            }
        }

        // ── Days ──────────────────────────────────────────────────────────────
        while i < lines.count {
            let line = lines[i]
            if line.hasPrefix("## 第") {
                let (day, remaining) = parseDayHeader(line)
                i += 1
                let (dayData, nextIndex) = parseDay(day, remaining: remaining, lines: lines, from: i)
                itinerary.days.append(dayData)
                i = nextIndex
            } else {
                i += 1
            }
        }

        return itinerary
    }

    // MARK: - Day Header

    // "## 第 1 天｜4/1 (三)｜出發 → 維也納抵達｜🇦🇹｜台灣 → 維也納"
    private static func parseDayHeader(_ line: String) -> (Int, [String]) {
        let content = String(line.dropFirst(3)) // remove "## "
        let parts = content.components(separatedBy: "｜")
        // parts[0] = "第 1 天", parts[1] = "4/1 (三)", parts[2] = title, parts[3] = flag, parts[4] = city
        var dayNum = 1
        if parts.count > 0 {
            let nums = parts[0].components(separatedBy: " ").compactMap { Int($0) }
            dayNum = nums.first ?? 1
        }
        return (dayNum, parts)
    }

    private static func parseDay(_ dayNum: Int, remaining parts: [String], lines: [String], from start: Int) -> (Day, Int) {
        var day = Day()
        day.day = dayNum
        day.date    = parts.count > 1 ? parts[1].trimmingCharacters(in: .whitespaces) : ""
        day.title   = parts.count > 2 ? parts[2].trimmingCharacters(in: .whitespaces) : ""
        day.flag    = parts.count > 3 ? parts[3].trimmingCharacters(in: .whitespaces) : ""
        day.city    = parts.count > 4 ? parts[4].trimmingCharacters(in: .whitespaces) : ""

        var i = start
        var section = ""

        while i < lines.count {
            let line = lines[i]

            // Next day boundary
            if line.hasPrefix("## 第") { break }

            if line.hasPrefix("### ") {
                section = line
                i += 1
                continue
            }

            // Highlights
            if section.contains("今日重點") {
                if line.hasPrefix("- ") {
                    day.highlights.append(String(line.dropFirst(2)))
                }
                i += 1
                continue
            }

            // Hotel
            if section.contains("飯店") {
                if line.hasPrefix("名稱：") {
                    var hotel = day.hotel ?? Hotel()
                    hotel.name = String(line.dropFirst(3))
                    day.hotel = hotel
                } else if line.hasPrefix("地址：") {
                    day.hotel?.address = String(line.dropFirst(3))
                } else if line.hasPrefix("地圖：") {
                    day.hotel?.mapUrl = String(line.dropFirst(3))
                } else if line.hasPrefix("備註：") {
                    day.hotel?.notes.append(String(line.dropFirst(3)))
                } else if line.hasPrefix("- ") {
                    day.hotel?.notes.append(String(line.dropFirst(2)))
                }
                i += 1
                continue
            }

            // Events
            if section.contains("行程") {
                if line.hasPrefix("#### ") {
                    let (event, nextI) = parseEvent(lines: lines, from: i)
                    day.events.append(event)
                    i = nextI
                    continue
                }
                i += 1
                continue
            }

            // Phrases
            if section.contains("英文字卡") {
                if let phrase = parseTableRow(line) {
                    day.phrases.append(phrase)
                }
                i += 1
                continue
            }

            i += 1
        }

        return (day, i)
    }

    // MARK: - Event

    // "#### [10:46] transport 🚌 搭 20 號公車出發"
    private static func parseEvent(lines: [String], from start: Int) -> (Event, Int) {
        var event = Event()
        let header = String(lines[start].dropFirst(5)) // remove "#### "

        // Extract time [...]
        if let timeStart = header.range(of: "["),
           let timeEnd = header.range(of: "]") {
            event.time = String(header[header.index(after: timeStart.lowerBound)..<timeEnd.lowerBound])
        }

        // After "]" → "transport 🚌 title"
        var rest = header
        if let bracketEnd = rest.range(of: "] ") {
            rest = String(rest[bracketEnd.upperBound...])
        }

        // First word = type
        let tokens = rest.components(separatedBy: " ")
        if let typeStr = tokens.first, let t = EventType(rawValue: typeStr) {
            event.type = t
            rest = tokens.dropFirst().joined(separator: " ")
        }

        // Next token might be an icon (emoji)
        let remaining = rest.components(separatedBy: " ")
        if let first = remaining.first, first.containsEmoji {
            event.icon = first
            rest = remaining.dropFirst().joined(separator: " ")
        } else {
            event.icon = event.type.defaultIcon
        }

        event.title = rest

        // Parse body lines
        var i = start + 1
        var subtitleSet = false

        while i < lines.count {
            let line = lines[i]
            if line.hasPrefix("####") || line.hasPrefix("###") || line.hasPrefix("##") || line == "---" { break }

            if line.hasPrefix("📍 ") {
                event.mapUrl = String(line.dropFirst("📍 ".count))
            } else if line.hasPrefix("- ") {
                event.notes.append(String(line.dropFirst(2)))
            } else if !line.isEmpty && !subtitleSet {
                event.subtitle = line
                subtitleSet = true
            }
            i += 1
        }

        return (event, i)
    }

    // MARK: - Table Row

    // "| 中文 | 英文 | 分類 |" → Phrase
    private static func parseTableRow(_ line: String) -> Phrase? {
        guard line.hasPrefix("|") else { return nil }
        let cols = line.components(separatedBy: "|")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard cols.count >= 3 else { return nil }
        // Skip header and separator rows
        if cols[0] == "中文" || cols[0].hasPrefix("---") { return nil }
        var phrase = Phrase()
        phrase.zh = cols[0]
        phrase.en = cols[1]
        phrase.category = PhraseCategory(rawValue: cols[2]) ?? .general
        return phrase
    }
}

// MARK: - Emoji Detection Helper

extension String {
    var containsEmoji: Bool {
        unicodeScalars.contains { scalar in
            (scalar.value >= 0x1F600 && scalar.value <= 0x1FFFF)
                || (scalar.value >= 0x2600 && scalar.value <= 0x27BF)
                || scalar.value == 0xFE0F
        }
    }
}
