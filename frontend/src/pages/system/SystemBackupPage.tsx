import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { apiFetch } from "../../api/system";
import { BackupResponse } from "../../types.ts";

export function SystemBackupPage() {
  const mut = useMutation({
    mutationFn: () =>
      apiFetch<BackupResponse>("/backup", {
        method: "POST",
      }),
  });

  const didRunRef = useRef(false);
  useEffect(() => {
    // Avoid double-running in React StrictMode (dev)
    if (didRunRef.current) return;
    didRunRef.current = true;
    mut.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  let status = "";
  if (mut.isSuccess) {
    status = "success";
  }
  if (mut.isError) {
    status = "error";
  }

  return (
    <div className={`status alert ${status}`}>
      {mut.isPending ? <div>Backing up…</div> : null}

      {mut.data ? (
        <div>
          Success! Backup was created successfully. ({mut.data.materials_count} materials,{" "}
          {mut.data.reading_log_count} logs, {mut.data.statuses_count} statuses,{" "}
          {mut.data.notes_count} notes, {mut.data.cards_count} cards, {mut.data.repeats_count}{" "}
          repeats, {mut.data.note_repeats_history_count} note repeats)
        </div>
      ) : null}
      {mut.error ? <div>Error! Backup failed. Reason: {(mut.error as Error).message}</div> : null}
    </div>
  );
}

