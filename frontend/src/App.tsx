import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { ContextMenuProvider } from "./contexts/ContextMenuContext";
import { MaterialsLayout } from "./components/MaterialsLayout";
import { AddMaterialPage } from "./pages/AddMaterialPage";
import { CompletedPage } from "./pages/CompletedPage";
import { QueuePage } from "./pages/QueuePage";
import { ReadingPage } from "./pages/ReadingPage";
import { RepeatPage } from "./pages/RepeatPage";
import { UpdateMaterialPage } from "./pages/UpdateMaterialPage";

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
          <Route element={<MaterialsLayout />}>
            <Route index element={<Navigate to="reading" replace />} />
            <Route path="queue" element={<QueuePage />} />
            <Route path="reading" element={<ReadingPage />} />
            <Route path="completed" element={<CompletedPage />} />
            <Route path="repeat-view" element={<RepeatPage />} />
            <Route path="add-view" element={<AddMaterialPage />} />
            <Route path="update-view" element={<UpdateMaterialPage />} />
          </Route>
        </Routes>
      </ContextMenuProvider>
    </QueryClientProvider>
  );
}
