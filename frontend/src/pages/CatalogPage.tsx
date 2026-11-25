import { useState } from "react";
import { isApiError } from "@/api/client";
import type { CatalogResponse } from "@/api/types";
import { AssetTypesTab } from "@/components/catalog/AssetTypesTab";
import { AssetTypeSheet } from "@/components/catalog/AssetTypeSheet";
import { BrandTab } from "@/components/catalog/BrandTab";
import { IssuesList } from "@/components/catalog/IssuesList";
import { LifecycleTab } from "@/components/catalog/LifecycleTab";
import { MatrixTab } from "@/components/catalog/MatrixTab";
import { TiersTab } from "@/components/catalog/TiersTab";
import { ForbiddenPage } from "@/components/ForbiddenPage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCatalog, useReloadCatalog } from "@/hooks/useCatalog";
import { can, useMe } from "@/hooks/useMe";
import { relativeTime } from "@/lib/time";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The Reload button (admins only) and what the last reload said. A 409 lists the issues and keeps the old catalog. */
function ReloadControl() {
  const { data: me } = useMe();
  const reload = useReloadCatalog();
  const result = reload.data;
  if (!can(me, "catalog:admin")) return null;

  return (
    <div className="space-y-3">
      <Button variant="outline" disabled={reload.isPending} onClick={() => reload.mutate()}>
        {reload.isPending ? "Reloading…" : "Reload"}
      </Button>
      {reload.isError && (
        <p role="alert" className="text-sm text-destructive">
          Could not reload the catalog.
        </p>
      )}
      {result?.ok && (
        <div role="status" className="space-y-2 rounded-md border p-3 text-sm">
          <p>
            Catalog reloaded. Version <span className="font-mono">{result.new_hash}</span>.
          </p>
          {result.issues.length > 0 && <IssuesList issues={result.issues} />}
        </div>
      )}
      {result && !result.ok && (
        <div role="alert" className="space-y-2 rounded-md border border-destructive/50 p-3 text-sm">
          <p>The catalog files have errors, so the version already loaded stays.</p>
          <IssuesList issues={result.issues} />
        </div>
      )}
    </div>
  );
}

function CatalogHeader({ catalog }: { catalog: CatalogResponse }) {
  const { errors, warnings, todo_count, items } = catalog.issues;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span>
          Version <span className="font-mono">{catalog.version_hash}</span>
        </span>
        <span className="text-muted-foreground">
          Loaded{" "}
          <time dateTime={catalog.loaded_at} title={relativeTime(catalog.loaded_at)}>
            {new Date(catalog.loaded_at).toLocaleString()}
          </time>
        </span>
        <Badge variant={errors > 0 ? "destructive" : "outline"}>{plural(errors, "error")}</Badge>
        <Badge variant="outline">{plural(warnings, "warning")}</Badge>
        {todo_count > 0 && <Badge variant="secondary">{todo_count} TODO to confirm</Badge>}
      </div>
      {items.length > 0 && (
        <details className="rounded-md border p-3">
          <summary className="cursor-pointer text-sm font-medium">Issues ({items.length})</summary>
          <div className="pt-2">
            <IssuesList issues={items} />
          </div>
        </details>
      )}
    </div>
  );
}

function NoCatalog() {
  return (
    <div className="space-y-2 rounded-md border border-dashed p-6">
      <h2 className="text-lg font-semibold">No catalog is loaded</h2>
      <p className="text-sm text-muted-foreground">
        Point <code className="font-mono">GTM_CATALOG_DIR</code> at a catalog folder and restart the
        API. The demo catalog is at <code className="font-mono">fixtures/demo/catalog</code>. If you
        have just added the files, an administrator can press Reload.
      </p>
    </div>
  );
}

/** Read-only view of the GTM framework the system follows. Everything shown is computed by the backend. */
export function CatalogPage() {
  const catalog = useCatalog();
  const [openAsset, setOpenAsset] = useState<string | null>(null);

  if (isApiError(catalog.error) && catalog.error.status === 403) {
    return <ForbiddenPage what="the catalog" />;
  }
  const missing = isApiError(catalog.error) && catalog.error.status === 404;

  return (
    <section className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Catalog</h1>

      {catalog.isPending && <p role="status">Loading catalog…</p>}
      {catalog.isError && !missing && (
        <p role="alert" className="text-destructive">
          Could not load the catalog.
        </p>
      )}
      {catalog.data && <CatalogHeader catalog={catalog.data} />}
      <ReloadControl />
      {missing && <NoCatalog />}

      {catalog.data && (
        <>
          <Tabs defaultValue="matrix">
            <TabsList>
              <TabsTrigger value="matrix">Matrix</TabsTrigger>
              <TabsTrigger value="lifecycle">Lifecycle</TabsTrigger>
              <TabsTrigger value="tiers">Tiers</TabsTrigger>
              <TabsTrigger value="assets">Asset types</TabsTrigger>
              <TabsTrigger value="brand">Brand</TabsTrigger>
            </TabsList>
            <TabsContent value="matrix" className="pt-4">
              <MatrixTab catalog={catalog.data} onOpenAsset={setOpenAsset} />
            </TabsContent>
            <TabsContent value="lifecycle" className="pt-4">
              <LifecycleTab catalog={catalog.data} />
            </TabsContent>
            <TabsContent value="tiers" className="pt-4">
              <TiersTab catalog={catalog.data} />
            </TabsContent>
            <TabsContent value="assets" className="pt-4">
              <AssetTypesTab catalog={catalog.data} onOpenAsset={setOpenAsset} />
            </TabsContent>
            <TabsContent value="brand" className="pt-4">
              <BrandTab />
            </TabsContent>
          </Tabs>
          <AssetTypeSheet
            assetKey={openAsset}
            catalog={catalog.data}
            onClose={() => setOpenAsset(null)}
          />
        </>
      )}
    </section>
  );
}
