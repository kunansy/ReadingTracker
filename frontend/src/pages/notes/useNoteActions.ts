import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiFetch } from "../../api/notes";

export interface NoteActions {
  deleteNote: (noteId: string) => void;
  restoreNote: (noteId: string) => void;
  repeatNote: (noteId: string) => void;
  error: string | null;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Unexpected error";
}

export function useNoteActions(): NoteActions {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const common = {
    onMutate: () => {
      setError(null);
    },
    onError: (err: unknown) => {
      setError(errorMessage(err));
    },
  };
  const refreshNotes = () => {
    void qc.invalidateQueries({ queryKey: ["notes"] });
  };

  const deleteMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await apiFetch(`/${encodeURIComponent(noteId)}`, { method: "DELETE" });
    },
    onSettled: refreshNotes,
  });

  const restoreMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await apiFetch(`/${encodeURIComponent(noteId)}/restore`, { method: "POST" });
    },
    onSettled: refreshNotes,
  });

  const repeatMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await apiFetch(`/${encodeURIComponent(noteId)}/repeat-queue`, { method: "POST" });
    },
  });

  return {
    deleteNote: deleteMut.mutate,
    restoreNote: restoreMut.mutate,
    repeatNote: repeatMut.mutate,
    error,
  };
}
