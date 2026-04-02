import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { ContextMenuProvider } from "./contexts/ContextMenuContext";
import { MaterialsLayout } from "./components/MaterialsLayout";
import { NotesLayout } from "./components/NotesLayout";
import { AddMaterialPage } from "./pages/materials/AddMaterialPage";
import { CompletedPage } from "./pages/materials/CompletedPage";
import { QueuePage } from "./pages/materials/QueuePage";
import { ReadingPage } from "./pages/materials/ReadingPage";
import { RepeatPage } from "./pages/materials/RepeatPage";
import { UpdateMaterialPage } from "./pages/materials/UpdateMaterialPage";
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
            <Route path="repeat" element={<RepeatPage />} />
            <Route path="add" element={<AddMaterialPage />} />
            <Route path="update" element={<UpdateMaterialPage />} />
          </Route>
          <Route path="/notes" element={<NotesLayout />}>
            <Route index element={<SearchNotesPage />} />
            <Route path="add" element={<AddNotePage />} />
            <Route path="graph" element={<GraphPage />} />
          </Route>
        </Routes>
      </ContextMenuProvider>
    </QueryClientProvider>
  );
}
