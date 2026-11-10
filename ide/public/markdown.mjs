// Markdown cells: marked + DOMPurify, with TeX ($…$, $$…$$) by KaTeX. The math
// is taken out before marked (which would read `_` and `*` in it) and put back
// after sanitizing; code (``` and `…`) keeps its dollars.
import { marked } from "https://cdn.jsdelivr.net/npm/marked@15.0.12/lib/marked.esm.js";
import DOMPurify from "https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.es.mjs";
import katex from "https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.mjs";

const CODE = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)/;
const MATH = /\$\$([\s\S]+?)\$\$|(?<![\\$\w])\$(?!\s)([^$\n]+?)(?<!\s)\$(?![\w$])/g;

export function renderMarkdown(text) {
  const math = [];
  const src = text
    .split(CODE)
    .map((part, i) =>
      i % 2 ? part : part.replace(MATH, (_, block, inline) => {
        math.push(block !== undefined ? { tex: block, display: true } : { tex: inline, display: false });
        return `⁣MATH${math.length - 1}⁣`;
      }),
    )
    .join("");
  const html = DOMPurify.sanitize(marked.parse(src));
  return html.replace(/⁣MATH(\d+)⁣/g, (_, i) => katex.renderToString(math[i].tex, { displayMode: math[i].display, throwOnError: false }));
}
