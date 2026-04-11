// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TinyFlow",
    platforms: [
        .macOS(.v13)
    ],
    dependencies: [
        .package(url: "https://github.com/gonzalezreal/swift-markdown-ui", from: "2.4.1"),
    ],
    targets: [
        .target(
            name: "TinyFlowCore",
            dependencies: [
                .product(name: "MarkdownUI", package: "swift-markdown-ui"),
            ],
            path: "Sources/TinyFlowCore"
        ),
        .executableTarget(
            name: "TinyFlow",
            dependencies: ["TinyFlowCore"],
            path: "Sources/TinyFlow"
        ),
        .testTarget(
            name: "TinyFlowTests",
            dependencies: ["TinyFlowCore"],
            path: "Tests/TinyFlowTests"
        )
    ]
)
