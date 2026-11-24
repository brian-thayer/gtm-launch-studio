import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
        <CardContent>
          <Badge variant="secondary">Scaffold</Badge>
        </CardContent>
      </Card>
    </section>
  );
}
