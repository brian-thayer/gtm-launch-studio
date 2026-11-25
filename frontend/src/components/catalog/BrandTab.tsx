import { Markdown } from "@/components/Markdown";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useBrand } from "@/hooks/useCatalog";

/** Voice, claims and legal guidance (Markdown), the terminology tables and the colour swatches. */
export function BrandTab() {
  const brand = useBrand();
  if (brand.isPending) return <p role="status">Loading brand…</p>;
  if (brand.isError) {
    return (
      <p role="alert" className="text-destructive">
        Could not load the brand.
      </p>
    );
  }
  const { voice_md, claims_md, legal_md, terminology, visual } = brand.data;

  return (
    <div className="space-y-8">
      {(
        [
          ["Voice", voice_md],
          ["Claims", claims_md],
          ["Legal", legal_md],
        ] as const
      ).map(([title, body]) => (
        <section key={title} className="space-y-2">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Markdown>{body}</Markdown>
        </section>
      ))}

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Terminology</h2>
        {terminology.product_names.length > 0 && (
          <Table aria-label="Product names">
            <TableHeader>
              <TableRow>
                <TableHead>Product name</TableHead>
                <TableHead>Rules</TableHead>
                <TableHead>Never write</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {terminology.product_names.map((product) => (
                <TableRow key={product.name}>
                  <TableCell className="font-medium">{product.name}</TableCell>
                  <TableCell>{product.rules}</TableCell>
                  <TableCell>{product.never.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {terminology.preferred.length > 0 && (
          <Table aria-label="Preferred terms">
            <TableHeader>
              <TableRow>
                <TableHead>Use</TableHead>
                <TableHead>Avoid</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {terminology.preferred.map((term) => (
                <TableRow key={term.use}>
                  <TableCell className="font-medium">{term.use}</TableCell>
                  <TableCell>{term.avoid.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {terminology.banned_external.length > 0 && (
          <div className="space-y-1">
            <h3 className="text-sm font-medium">Banned in external assets</h3>
            <ul className="flex flex-wrap gap-1">
              {terminology.banned_external.map((word) => (
                <li key={word}>
                  <Badge variant="destructive">{word}</Badge>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Colours</h2>
        <ul className="flex flex-wrap gap-4">
          {Object.entries(visual.colors).map(([name, hex]) => (
            <li key={name} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden
                className="size-8 rounded-md border"
                style={{ backgroundColor: hex }}
              />
              <span>
                <span className="block font-medium">{name}</span>
                <span className="block font-mono text-xs text-muted-foreground">{hex}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
