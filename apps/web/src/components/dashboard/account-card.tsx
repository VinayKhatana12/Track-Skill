import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { UserPublic } from "@/types/api";

export function AccountCard({ user }: { user: UserPublic }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Account</CardTitle>
        <CardDescription>Session details from GET /auth/me</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Name</dt>
            <dd className="font-medium">{user.name}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="break-all font-medium">{user.email}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="font-medium uppercase">{user.role}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Demo account</dt>
            <dd className="font-medium">{user.is_demo ? "Yes" : "No"}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
