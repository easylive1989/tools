import SwiftUI

struct ContentView: View {
    @EnvironmentObject var viewModel: AppViewModel

    var body: some View {
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
