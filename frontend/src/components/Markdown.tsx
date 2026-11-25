import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

/**
 * Catalog Markdown (prompts, rubrics, brand guidance). `react-markdown` with its defaults only: HTML in
 * the source is shown as text and never becomes an element, and links to `javascript:` are dropped.
 * Never add a plugin that lets raw HTML through.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div
      className={cn(
        "space-y-2 text-sm leading-relaxed",
        "[&_h1]:text-base [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:font-semibold",
        "[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs",
        "[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3",
        "[&_a]:underline [&_a]:underline-offset-4",
        className,
      )}
    >
      {/* No images: a remote one would make every viewer's browser fetch a URL that came from catalog text. */}
      <ReactMarkdown disallowedElements={["img"]}>{children}</ReactMarkdown>
    </div>
  );
}
