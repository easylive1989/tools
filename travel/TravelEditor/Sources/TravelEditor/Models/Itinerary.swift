import Foundation

// MARK: - Top-Level Itinerary

struct Itinerary: Equatable {
    var title: String = ""
    var subtitle: String = ""
    var commonPhrases: [Phrase] = []
    var days: [Day] = []
}

// MARK: - Day

struct Day: Identifiable, Equatable {
    var id = UUID()
    var day: Int = 1
    var date: String = ""          // e.g. "4/1 (三)"
    var title: String = ""         // e.g. "出發 → 維也納抵達"
    var city: String = ""          // e.g. "台灣 → 維也納"
    var flag: String = "🇦🇹"
    var highlights: [String] = []
    var hotel: Hotel? = nil
    var events: [Event] = []
    var phrases: [Phrase] = []
}

// MARK: - Hotel

struct Hotel: Equatable {
    var name: String = ""
    var address: String = ""
    var mapUrl: String = ""
    var notes: [String] = []
}

// MARK: - Event

struct Event: Identifiable, Equatable {
    var id = UUID()
    var time: String = ""          // e.g. "10:46" or "(隔天) 06:50"
    var type: EventType = .info
    var icon: String = ""          // e.g. "🚌"
    var title: String = ""
    var subtitle: String = ""
    var mapUrl: String = ""
    var notes: [String] = []
}

enum EventType: String, CaseIterable {
    case transport = "transport"
    case food = "food"
    case sight = "sight"
    case hotel = "hotel"
    case info = "info"

    var label: String {
        switch self {
        case .transport: return "交通"
        case .food: return "飲食"
        case .sight: return "景點"
        case .hotel: return "住宿"
        case .info: return "資訊"
        }
    }

    var defaultIcon: String {
        switch self {
        case .transport: return "🚌"
        case .food: return "🍽️"
        case .sight: return "📸"
        case .hotel: return "🏨"
        case .info: return "ℹ️"
        }
    }
}

// MARK: - Phrase

struct Phrase: Identifiable, Equatable {
    var id = UUID()
    var zh: String = ""
    var en: String = ""
    var category: PhraseCategory = .general
}

enum PhraseCategory: String, CaseIterable {
    case general = "general"
    case transport = "transport"
    case food = "food"
    case emergency = "emergency"

    var label: String {
        switch self {
        case .general: return "一般"
        case .transport: return "交通"
        case .food: return "飲食"
        case .emergency: return "緊急"
        }
    }
}
