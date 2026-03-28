// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TravelEditor",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .executableTarget(
            name: "TravelEditor",
            path: "Sources/TravelEditor"
        )
    ]
)
