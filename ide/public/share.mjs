// The read-only page of a share link (/s/<id>): a notebook's cells with their
// saved outputs, or a program's text; "open a copy" goes to the IDE (/#import=<id>).
import { parseNotebook } from "/nbformat.mjs";
import { outputNode } from "/rich.mjs";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls ?? "", textContent: text ?? "" });
const doc = $("doc");
const id = location.pathname.split("/").pop();

try {
  const res = await fetch("/api/s/" + encodeURIComponent(id));
  const data = await res.json();
  if (!res.ok) throw new Error(data.error);
  document.title = data.path + " · rupy";
  $("title").textContent = `${data.path} · 分享於 ${data.created_at.slice(0, 10)}（唯讀）`;
  $("open").href = "/#import=" + id;
  $("open").hidden = false;
  if (data.path.endsWith(".ipynb")) {
    const { renderMarkdown } = await import("/markdown.mjs");
    for (const c of parseNotebook(data.text).cells) {
      const cell = el("section", "share-cell " + c.type);
      if (c.type === "markdown") {
        const md = el("div", "md-view");
        md.innerHTML = renderMarkdown(c.source);
        cell.append(md);
      } else {
        cell.append(el("div", "count", c.count ? `[${c.count}]` : "[ ]"), el("pre", "code", c.source));
        if (c.outputs.length) {
          const out = el("pre", "cell-out");
          for (const o of c.outputs) out.append(outputNode(o));
          cell.append(out);
        }
      }
      doc.append(cell);
    }
  } else if (data.path.endsWith(".svg")) {
    doc.append(outputNode({ name: "svg", text: data.text }));
  } else {
    doc.append(el("pre", "code", data.text));
  }
} catch (e) {
  $("title").textContent = "無法開啟";
  doc.append(el("p", "error", e.message || "這個分享連結不存在或已經取消"));
}
