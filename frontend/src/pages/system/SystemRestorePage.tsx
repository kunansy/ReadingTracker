import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "../../api/system";

type RestoreResponse = {
  materials_count: number;
  logs_count: number;
  statuses_count: number;
  notes_count: number;
};

export function SystemRestorePage() {
  const mut = useMutation({
    mutationFn: () =>
      apiFetch<RestoreResponse>("/restore", {
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
        {mut.isPending ? "Restoring…" : "Restore from backup"}
      </button>

      {mut.data ? (
        <div className="alert success status">
          Success! Restore was completed successfully. ({mut.data.materials_count} materials,{" "}
          {mut.data.logs_count} logs, {mut.data.statuses_count} statuses,{" "}
          {mut.data.notes_count} notes)
        </div>
      ) : null}
      {mut.error ? <div className="alert error status">Error! Restore failed.</div> : null}
    </div>
  );
}

