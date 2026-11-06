import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import type { ApiError } from "../../api/client";
import { apiFetch } from "../../api/materials";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { ScrollArrows } from "../../components/ScrollArrows";
import type { GetCompletedMaterialResponse } from "../../types";
import { isUuid } from "../../utils/isUuid.ts";
import { CompletedMaterialCard } from "./CompletedMaterialCard";

const HTTP_NOT_FOUND = 404;

export function CompletedMaterialPage() {
  const { materialId = "" } = useParams();
  const isValidId = isUuid(materialId);

  const q = useQuery({
    queryKey: ["materials", "completed", "item", materialId],
    enabled: isValidId,
    queryFn: () =>
      apiFetch<GetCompletedMaterialResponse>(`/completed/${encodeURIComponent(materialId)}`),
  });

  if (!isValidId) {
    return <p className="error">Invalid material id</p>;
  }
  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    if ((q.error as ApiError).status === HTTP_NOT_FOUND) {
      return <NotFoundMaterials kind="completed material" />;
    }
    return <p className="error">{q.error.message}</p>;
  }
  if (!q.data) {
    return <NotFoundMaterials kind="completed material" />;
  }

  return (
    <>
      <CompletedMaterialCard stats={q.data.statistics} />
      <ScrollArrows />
    </>
  );
}
