import { useState, type ReactNode } from "react";
import type { AssetTypeResponse, CatalogResponse } from "@/api/types";
import { Markdown } from "@/components/Markdown";
import { RoleBadge } from "@/components/RoleBadge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useAssetType } from "@/hooks/useCatalog";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

function AssetTypeDetail({
  asset,
  catalog,
}: {
  asset: AssetTypeResponse;
  catalog: CatalogResponse;
}) {
  const { spec } = asset;
  const gate = catalog.gates.find((g) => g.key === spec.gate);
  const roleLabels = new Map(catalog.roles.map((role) => [role.key, role.label]));
  const facts: [string, string][] = [
    ["Gate", gate?.short ?? spec.gate],
    ["Audience", spec.audience],
    ["Family", spec.family],
    ["Formats", spec.formats.join(", ")],
    ["Effort", spec.effort],
    ["Route", spec.route],
    ["Foundation", spec.foundation ? "Yes" : "No"],
    ["Decides", spec.decides ?? ""],
    ["Depends on", spec.depends_on.join(", ")],
    ["Required context", spec.required_context.join(", ")],
    [
      "Length",
      Object.entries(spec.length ?? {})
        .map(([k, v]) => `${k}: ${v}`)
        .join(", "),
    ],
  ];

  return (
    <div className="space-y-6">
      <Section title="Spec">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {facts
            .filter(([, value]) => value !== "")
            .map(([name, value]) => (
              <div key={name} className="contents">
                <dt className="text-muted-foreground">{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </Section>

      <Section title="Approver roles">
        <div className="flex flex-wrap gap-1">
          {asset.approver_roles.map((key) => (
            <RoleBadge
              key={key}
              role={{ key, label: roleLabels.get(key) ?? key, kind: "approver" }}
            />
          ))}
        </div>
      </Section>

      <Section title="Prompt">
        <Markdown>{asset.prompt_md}</Markdown>
      </Section>

      <Section title="Rubric">
        <p className="text-sm">Pass threshold: {asset.rubric.pass_threshold}</p>
        <ol className="space-y-3">
          {asset.rubric.criteria.map((criterion) => (
            <li key={criterion.key}>
              <h4 className="text-sm font-medium">{criterion.title}</h4>
              <Markdown>{criterion.body_md}</Markdown>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Examples">
        {asset.examples.length === 0 && <p className="text-sm text-muted-foreground">None yet.</p>}
        {asset.examples.map((example) => (
          <article key={example.slug} className="space-y-2 rounded-md border p-3">
            <h4 className="text-sm font-medium">{example.title}</h4>
            {example.why_good.length > 0 && (
              <ul className="list-disc pl-5 text-sm">
                {example.why_good.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
            <Markdown>{example.body_md}</Markdown>
          </article>
        ))}
      </Section>
    </div>
  );
}

/** One asset type in a side sheet. Nothing is fetched until `assetKey` is set; closing it clears the key. */
export function AssetTypeSheet({
  assetKey,
  catalog,
  onClose,
}: {
  assetKey: string | null;
  catalog: CatalogResponse;
  onClose: () => void;
}) {
  // The sheet slides out for a moment after `assetKey` goes back to null. Keep showing the last asset type
  // until it is gone, instead of flashing an empty title and "Loading…".
  const [shownKey, setShownKey] = useState(assetKey);
  if (assetKey !== null && assetKey !== shownKey) setShownKey(assetKey);
  const asset = useAssetType(shownKey);
  return (
    <Sheet open={assetKey !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{asset.data?.spec.name ?? shownKey}</SheetTitle>
          <SheetDescription>
            Asset type <span className="font-mono">{shownKey}</span>
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          {asset.isPending && <p role="status">Loading…</p>}
          {asset.isError && (
            <p role="alert" className="text-destructive">
              Could not load this asset type.
            </p>
          )}
          {asset.data && <AssetTypeDetail asset={asset.data} catalog={catalog} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}
