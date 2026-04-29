import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { ContextMenuProvider } from "./contexts/ContextMenuContext";
import { MaterialsLayout } from "./components/MaterialsLayout";
import { NotesLayout } from "./components/NotesLayout";
import { AddMaterialPage } from "./pages/materials/AddMaterialPage";
import { ListCompletedMaterialsPage } from "./pages/materials/ListCompletedMaterialsPage";
import { ListMaterialsQueuePage } from "./pages/materials/ListMaterialsQueuePage";
import { ListReadingMaterialsPage } from "./pages/materials/ListReadingMaterialsPage";
import { ListRepeatMaterialsPage } from "./pages/materials/ListRepeatMaterialsPage";
import { UpdateMaterialPage } from "./pages/materials/UpdateMaterialPage";
import { AddNotePage } from "./pages/notes/AddNotePage";
import { GraphPage } from "./pages/notes/GraphPage";
import { SearchNotesPage } from "./pages/notes/SearchNotesPage";
import { ReadingLogLayout } from "./components/ReadingLogLayout.tsx";
import { ListReadingLogsPage } from "./pages/reading_log/ListReadingLogsPage.tsx";
import { AddReadingLogPage } from "./pages/reading_log/AddReadingLogPage.tsx";
import { CardsLayout } from "./components/CardsLayout.tsx";
import { ListCardsPage } from "./pages/cards/ListCardsPage.tsx";
import { AddCardPage } from "./pages/cards/AddCardPage.tsx";

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
            <Route path="queue" element={<ListMaterialsQueuePage />} />
            <Route path="reading" element={<ListReadingMaterialsPage />} />
            <Route path="completed" element={<ListCompletedMaterialsPage />} />
            <Route path="repeat" element={<ListRepeatMaterialsPage />} />
            <Route path="add" element={<AddMaterialPage />} />
            <Route path="update" element={<UpdateMaterialPage />} />
          </Route>
          <Route path="/notes" element={<NotesLayout />}>
            <Route index element={<SearchNotesPage />} />
            <Route path="add" element={<AddNotePage />} />
            <Route path="graph" element={<GraphPage />} />
          </Route>
          <Route path="/reading_logs" element={<ReadingLogLayout />}>
            <Route index element={<ListReadingLogsPage />} />
            <Route path="add" element={<AddReadingLogPage />} />
          </Route>
          <Route path="/cards" element={<CardsLayout />}>
            <Route index element={<ListCardsPage />} />
            <Route path="add" element={<AddCardPage />} />
          </Route>
        </Routes>
      </ContextMenuProvider>
    </QueryClientProvider>
  );
}
