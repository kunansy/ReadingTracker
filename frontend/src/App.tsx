import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { ContextMenuProvider } from "./contexts/ContextMenuContext";
import { MaterialsLayout } from "./components/MaterialsLayout";
import { NotesLayout } from "./components/NotesLayout";
import { AddMaterialPage } from "./pages/AddMaterialPage";
import { CompletedPage } from "./pages/CompletedPage";
import { QueuePage } from "./pages/QueuePage";
import { ReadingPage } from "./pages/ReadingPage";
import { RepeatPage } from "./pages/RepeatPage";
import { UpdateMaterialPage } from "./pages/UpdateMaterialPage";
import { AddNotePage } from "./pages/notes/AddNotePage";
import { GraphPage } from "./pages/notes/GraphPage";
import { SearchNotesPage } from "./pages/notes/SearchNotesPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ContextMenuProvider>
        <Routes>
          <Route path="/materials" element={<MaterialsLayout />}>
            <Route index element={<Navigate to="reading" replace />} />
            <Route path="queue" element={<QueuePage />} />
            <Route path="reading" element={<ReadingPage />} />
            <Route path="completed" element={<CompletedPage />} />
            <Route path="repeat-view" element={<RepeatPage />} />
            <Route path="add-view" element={<AddMaterialPage />} />
            <Route path="update-view" element={<UpdateMaterialPage />} />
          </Route>
          <Route path="/notes" element={<NotesLayout />}>
            <Route index element={<SearchNotesPage />} />
            <Route path="add-view" element={<AddNotePage />} />
            <Route path="graph" element={<GraphPage />} />
          </Route>
        </Routes>
      </ContextMenuProvider>
    </QueryClientProvider>
  );
}
