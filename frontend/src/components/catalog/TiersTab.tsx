import type { CatalogResponse, TierOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Signed days from the anchor, in words: -56 is "56 days before", 3 is "3 days after". */
function describeOffset(days: number): string {
  if (days === 0) return "on the day";
  const unit = Math.abs(days) === 1 ? "day" : "days";
  return `${Math.abs(days)} ${unit} ${days < 0 ? "before" : "after"}`;
}

function Timing({ timing }: { timing: NonNullable<TierOut["timing"]> }) {
  const parts = [
    timing.plan_start_days !== null && `Plan ${describeOffset(timing.plan_start_days)}`,
    timing.core_due_days !== null && `core due ${describeOffset(timing.core_due_days)}`,
  ].filter(Boolean);
  return (
    <p>
      {parts.join(" · ")}{" "}
      <span className="text-muted-foreground">(from {timing.anchor_label})</span>
    </p>
  );
}

/** Each tier: what it means, who it is for and when its assets are planned. All text comes from the catalog. */
export function TiersTab({ catalog }: { catalog: CatalogResponse }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {catalog.tiers.map((tier) => (
        <Card key={tier.key} aria-label={tier.label}>
          <CardHeader>
            <CardTitle>{tier.label}</CardTitle>
            <CardDescription>{tier.description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {tier.examples.length > 0 && (
              <div>
                <h3 className="font-medium">Examples</h3>
                <ul className="list-disc pl-5">
                  {tier.examples.map((example) => (
                    <li key={example}>{example}</li>
                  ))}
                </ul>
              </div>
            )}
            {tier.criteria.length > 0 && (
              <div>
                <h3 className="font-medium">Criteria</h3>
                <dl className="space-y-1">
                  {tier.criteria.map((criterion) => (
                    <div key={criterion.key}>
                      <dt className="inline font-medium">{criterion.label}: </dt>
                      <dd className="inline">{criterion.description}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {tier.channels.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <h3 className="font-medium">Channels</h3>
                {tier.channels.map((channel) => (
                  <Badge key={channel} variant="outline">
                    {channel}
                  </Badge>
                ))}
              </div>
            )}
            {tier.timing && <Timing timing={tier.timing} />}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
