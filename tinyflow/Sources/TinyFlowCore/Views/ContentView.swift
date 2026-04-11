import SwiftUI

public struct ContentView: View {
    public init() {}
    @EnvironmentObject var viewModel: AppViewModel

    public var body: some View {
        NavigationSplitView {
            SidebarView()
                .navigationSplitViewColumnWidth(min: 200, ideal: 260, max: 320)
        } detail: {
            if viewModel.activeSession != nil {
                ChatView()
            } else {
                EmptyStateView()
            }
        }
        .sheet(isPresented: $viewModel.showNewSessionSheet) {
            NewSessionSheet()
                .environmentObject(viewModel)
        }
    }
}
