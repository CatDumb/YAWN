export function FieldError({
  id,
  message,
  visible = true,
}: {
  id?: string;
  message?: string;
  visible?: boolean;
}) {
  if (!message || !visible) return null;
  return (
    <p className="text-error mt-1 text-sm" id={id}>
      {message}
    </p>
  );
}
