import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useHealth } from "@/hooks/useHealth";

function ApiStatusBadge() {
  const { isPending, isError } = useHealth();
  if (isPending) {
    return (
      <Badge role="status" variant="outline">
        API: checking
      </Badge>
    );
  }
  if (isError) {
    return (
      <Badge role="status" variant="destructive">
        API: unreachable
      </Badge>
    );
  }
  return (
    <Badge role="status" variant="secondary">
      API: ok
    </Badge>
  );
}

export function HomePage() {
  return (
    <section className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">GTM Launch Studio</h1>
      <Card>
        <CardHeader>
          <CardTitle>Workspace</CardTitle>
          <CardDescription>
            Solutions, assets and approvals will appear here once the backend is connected.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Scaffold</Badge>
          <ApiStatusBadge />
        </CardContent>
      </Card>
    </section>
  );
}
