export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-4 rounded-lg border border-red-300/30 bg-red-500/15 px-3.5 py-2.5 text-sm text-red-200 animate-fade-in">
      {message}
    </div>
  );
}
