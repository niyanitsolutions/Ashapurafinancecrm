export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="mb-4 rounded-[10px] border border-danger/20 bg-danger/5 px-3.5 py-2.5 text-sm text-danger">
      {message}
    </div>
  );
}
