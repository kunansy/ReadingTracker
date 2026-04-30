import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "../../api/system";

type BackupResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};

export function SystemBackupPage() {
  const mut = useMutation({
    mutationFn: () =>
      apiFetch<BackupResponse>("/backup", {
        method: "POST",
      }),
  });

  return (
    <div>
      <button
        className="submit-button"
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
      >
        {mut.isPending ? "Backing up…" : "Create backup"}
      </button>

      {mut.data ? (
        <div className="alert success status">
          Success! Backup was created successfully. ({mut.data.materials_count} materials,{" "}
          {mut.data.reading_log_count} logs, {mut.data.statuses_count} statuses,{" "}
          {mut.data.notes_count} notes, {mut.data.cards_count} cards, {mut.data.repeats_count}{" "}
          repeats, {mut.data.note_repeats_history_count} note repeats)
        </div>
      ) : null}
      {mut.error ? <div className="alert error status">Error! Backup failed.</div> : null}
    </div>
  );
}

