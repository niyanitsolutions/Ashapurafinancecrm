export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-4 rounded-xl border border-danger/20 bg-danger/10 px-3.5 py-2.5 text-sm text-danger animate-fade-in">
      {message}
    </div>
  );
}
