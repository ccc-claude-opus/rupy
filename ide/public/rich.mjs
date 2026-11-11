// Rich output: an SVG document a program prints (rstatistics'
// `print(g.svg())`, the same under CPython) is shown as a picture. A line that
// starts with `<?xml` or `<svg` begins one, and it ends after `</svg>`; anything
// else is text.

const STARTS = ["<?xml", "<svg"];
const MAX = 8 << 20; // longer than this: not a picture, just text

/**
 * Splits a stream of text: feed(text) and, at the end, flush() call
 * emit("text", s) or emit("svg", document).
 */
export function richSplitter(emit) {
  let buf = "";
  let svg = false; // inside an SVG document
  let lineStart = true;
  let skipNewlines = 0; // the "\n"s right after `</svg>` (svg()'s own and print's) belong to the picture
  const text = (s) => s && emit("text", s);
  const self = {
    feed(s) {
      buf += s;
      for (;;) {
        while (skipNewlines && buf) {
          if (buf[0] === "\n") {
            buf = buf.slice(1);
            skipNewlines--;
          } else skipNewlines = 0;
        }
        if (!buf) return;
        if (svg) {
          const end = buf.indexOf("</svg>");
          if (end < 0) {
            if (buf.length > MAX) {
              text(buf);
              buf = "";
              svg = lineStart = false;
            }
            return;
          }
          const doc = buf.slice(0, end + 6);
          buf = buf.slice(end + 6);
          svg = false;
          lineStart = true;
          skipNewlines = 2;
          if (doc.includes("<svg")) emit("svg", doc);
          else text(doc);
          continue;
        }
        if (lineStart) {
          if (STARTS.some((p) => buf.startsWith(p))) {
            svg = true;
            continue;
          }
          if (STARTS.some((p) => p.startsWith(buf))) return; // maybe: wait for more
          lineStart = false;
        }
        const nl = buf.indexOf("\n");
        if (nl < 0) {
          text(buf);
          buf = "";
          return;
        }
        text(buf.slice(0, nl + 1));
        buf = buf.slice(nl + 1);
        lineStart = true;
      }
    },
    flush() {
      text(buf);
      buf = "";
      svg = false;
      skipNewlines = 0;
      lineStart = true;
    },
  };
  return self;
}

/** An image's src for a picture output ({ name: "svg" | "png", text }). */
export const imageSrc = (o) =>
  o.name === "svg" ? "data:image/svg+xml;charset=utf-8," + encodeURIComponent(o.text) : "data:image/png;base64," + o.text.replace(/\s/g, "");

export const isImage = (o) => o.name === "svg" || o.name === "png";

/** The element of an output: an <img> (a picture can run no script there), or a <span> of text. */
export function outputNode(o) {
  if (isImage(o)) {
    const img = document.createElement("img");
    img.className = "plot";
    img.alt = "圖";
    img.src = imageSrc(o);
    return img;
  }
  const span = document.createElement("span");
  if (o.name === "stderr") span.className = "stderr";
  span.textContent = o.text;
  return span;
}
