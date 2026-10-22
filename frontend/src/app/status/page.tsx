import { SystemStatus } from "@/components/features/system-status/system-status";

export const metadata = { title: "System status" };

export default function StatusPage() {
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-12">
      <SystemStatus />
    </main>
  );
}
