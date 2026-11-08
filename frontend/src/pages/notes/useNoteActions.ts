import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, unwrap } from "../../api/client";

export interface NoteActions {
  deleteNote: (noteId: string) => void;
  restoreNote: (noteId: string) => void;
  repeatNote: (noteId: string) => void;
  error: string | null;
  dismissError: () => void;
}

interface Failure {
  seq: number;
  message: string;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Unexpected error";
}

export function useNoteActions(): NoteActions {
  const qc = useQueryClient();
  const seq = useRef(0);
  const [failure, setFailure] = useState<Failure | null>(null);

  // A failure stays visible until an action started after it succeeds.
  const common = {
    onMutate: () => ++seq.current,
    onError: (err: unknown, _noteId: string, started: number | undefined) => {
      setFailure({ seq: started ?? seq.current, message: errorMessage(err) });
    },
    onSuccess: (_data: void, _noteId: string, started: number) => {
      setFailure((prev) => (prev && prev.seq < started ? null : prev));
    },
  };
  const refreshNotes = () => {
    void qc.invalidateQueries({ queryKey: ["notes"] });
  };

  const deleteMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await unwrap(
        api.DELETE("/api/v1/notes/{note_id}", { params: { path: { note_id: noteId } } }),
      );
    },
    onSettled: refreshNotes,
  });

  const restoreMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await unwrap(
        api.POST("/api/v1/notes/{note_id}/restore", { params: { path: { note_id: noteId } } }),
      );
    },
    onSettled: refreshNotes,
  });

  const repeatMut = useMutation({
    ...common,
    mutationFn: async (noteId: string) => {
      await unwrap(
        api.POST("/api/v1/notes/{note_id}/repeat-queue", {
          params: { path: { note_id: noteId } },
        }),
      );
    },
  });

  return {
    deleteNote: deleteMut.mutate,
    restoreNote: restoreMut.mutate,
    repeatNote: repeatMut.mutate,
    error: failure?.message ?? null,
    dismissError: () => {
      setFailure(null);
    },
  };
}
