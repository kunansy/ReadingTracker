import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api, ApiError, unwrap } from "../../api/client";
import { materialKeys } from "../../materials/queries";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { ScrollArrows } from "../../components/ScrollArrows";
import { isUuid } from "../../utils/isUuid.ts";
import { CompletedMaterialCard } from "./CompletedMaterialCard";

const HTTP_NOT_FOUND = 404;

export function CompletedMaterialPage() {
  const { materialId = "" } = useParams();
  const isValidId = isUuid(materialId);

  const q = useQuery({
    queryKey: materialKeys.completedItem(materialId),
    enabled: isValidId,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/materials/completed/{material_id}", {
          params: { path: { material_id: materialId } },
        }),
      ),
  });

  if (!isValidId) {
    return <p className="error">Invalid material id</p>;
  }
  if (q.isLoading) {
    return <p>Loading…</p>;
  }
  if (q.error) {
    if (q.error instanceof ApiError && q.error.status === HTTP_NOT_FOUND) {
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
