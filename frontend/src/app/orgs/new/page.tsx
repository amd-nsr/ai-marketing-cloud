import { AuthShell } from "@/components/layout/auth-shell";
import { CreateOrgForm } from "@/features/org/create-org-form";

export const metadata = { title: "New organization" };

export default function NewOrganizationPage() {
  return (
    <AuthShell
      title="Create an organization"
      description="An organization holds one business's brand, content, accounts, and team."
    >
      <CreateOrgForm />
    </AuthShell>
  );
}
