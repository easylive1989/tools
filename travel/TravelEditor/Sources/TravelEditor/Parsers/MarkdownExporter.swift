import Foundation

// Exports Itinerary model back to itinerary.md format
enum MarkdownExporter {

    static func export(_ itinerary: Itinerary) -> String {
        var lines: [String] = []

        // Title block
        lines.append("# \(itinerary.title)")
        if !itinerary.subtitle.isEmpty {
            lines.append(itinerary.subtitle)
        }
        lines.append("")

        // Common phrases
        lines.append("## 通用字卡")
        lines.append("")
        lines.append("| 中文 | 英文 | 分類 |")
        lines.append("|------|------|------|")
        for p in itinerary.commonPhrases {
            lines.append("| \(p.zh) | \(p.en) | \(p.category.rawValue) |")
        }
        lines.append("")

        // Days
        for day in itinerary.days {
            lines.append("---")
            lines.append("")
            lines.append(dayHeader(day))
            lines.append("")

            // Highlights
            if !day.highlights.isEmpty {
                lines.append("### 今日重點")
                for h in day.highlights {
                    lines.append("- \(h)")
                }
                lines.append("")
            }

            // Hotel
            if let hotel = day.hotel {
                lines.append("### 飯店")
                lines.append("名稱：\(hotel.name)")
                lines.append("地址：\(hotel.address)")
                if !hotel.mapUrl.isEmpty {
                    lines.append("地圖：\(hotel.mapUrl)")
                }
                for note in hotel.notes {
                    lines.append("備註：\(note)")
                }
                lines.append("")
            }

            // Events
            if !day.events.isEmpty {
                lines.append("### 行程")
                lines.append("")
                for event in day.events {
                    lines.append(eventHeader(event))
                    if !event.subtitle.isEmpty {
                        lines.append(event.subtitle)
                    }
                    if !event.mapUrl.isEmpty {
                        lines.append("📍 \(event.mapUrl)")
                    }
                    for note in event.notes {
                        lines.append("- \(note)")
                    }
                    lines.append("")
                }
            }

            // Phrases
            if !day.phrases.isEmpty {
                lines.append("### 英文字卡")
                lines.append("")
                lines.append("| 中文 | 英文 | 分類 |")
                lines.append("|------|------|------|")
                for p in day.phrases {
                    lines.append("| \(p.zh) | \(p.en) | \(p.category.rawValue) |")
                }
                lines.append("")
            }
        }

        return lines.joined(separator: "\n")
    }

    // MARK: - Helpers

    private static func dayHeader(_ day: Day) -> String {
        "## 第 \(day.day) 天｜\(day.date)｜\(day.title)｜\(day.flag)｜\(day.city)"
    }

    private static func eventHeader(_ event: Event) -> String {
        var parts = ["####", "[\(event.time)]", event.type.rawValue]
        if !event.icon.isEmpty {
            parts.append(event.icon)
        }
        parts.append(event.title)
        return parts.joined(separator: " ")
    }
}
