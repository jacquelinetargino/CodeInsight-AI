import { Copy, Download } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";

export function ReadmePreview({ content }: { content: string }) {
  function copyToClipboard() {
    navigator.clipboard.writeText(content);
  }

  function download() {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "README.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-sm font-medium text-muted-foreground">README.md gerado</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={copyToClipboard}>
            <Copy className="mr-1.5 h-3.5 w-3.5" /> Copiar
          </Button>
          <Button variant="outline" size="sm" onClick={download}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Baixar
          </Button>
        </div>
      </div>
      <div className="prose prose-sm max-w-none p-4 dark:prose-invert prose-headings:font-semibold prose-pre:bg-[#0d1117]">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
