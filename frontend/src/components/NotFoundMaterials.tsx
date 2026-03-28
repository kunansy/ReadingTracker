type Props = { kind: string };

export function NotFoundMaterials({ kind }: Props) {
  return (
    <div className="not-found">
      <p className="message"> No {kind} found </p>
    </div>
  );
}
