// Notebooks without the DOM: .ipynb (nbformat 4) in and out, and the program
// that runs cells 0..k ("prefix re-run": rupy compiles whole programs, so a cell
// sees the cells above it by running them again). Before each code cell the
// program prints a marker, RS i RS, which splits its output among the cells.

/**
 * A cell: { type: "code" | "markdown", source, outputs, count }; an output is
 * { name: "stdout" | "stderr", text }, or a picture { name: "svg" | "png", text }
 * (an SVG document, or base64 PNG data from Jupyter).
 */
export function newCell(type = "code", source = "") {
  return { type, source, outputs: [], count: null };
}

const joinText = (t) => (Array.isArray(t) ? t.join("") : t ?? "");

/** Parse .ipynb text (an empty or blank file is a notebook of one empty cell). */
export function parseNotebook(text) {
  if (!text.trim()) return { cells: [newCell()], metadata: {} };
  const nb = JSON.parse(text);
  if (!Array.isArray(nb.cells)) throw new Error("not a notebook: no cells");
  const cells = nb.cells
    .filter((c) => c.cell_type === "code" || c.cell_type === "markdown" || c.cell_type === "raw")
    .map((c) => ({
      type: c.cell_type === "code" ? "code" : "markdown",
      source: joinText(c.source),
      // streams, pictures, and other kinds (from Jupyter) as their text/plain
      outputs: (c.outputs ?? [])
        .map((o) =>
          o.output_type === "stream"
            ? { name: o.name === "stderr" ? "stderr" : "stdout", text: joinText(o.text) }
            : o.output_type === "error"
              ? { name: "stderr", text: (o.traceback ?? [`${o.ename}: ${o.evalue}`]).join("\n") + "\n" }
              : o.data?.["image/svg+xml"]
                ? { name: "svg", text: joinText(o.data["image/svg+xml"]) }
                : o.data?.["image/png"]
                  ? { name: "png", text: joinText(o.data["image/png"]) }
                  : { name: "stdout", text: joinText(o.data?.["text/plain"]) },
        )
        .filter((o) => o.text),
      count: c.cell_type === "code" ? c.execution_count ?? null : null,
    }));
  return { cells: cells.length ? cells : [newCell()], metadata: nb.metadata ?? {} };
}

// Jupyter's line arrays: each line keeps its "\n"
const lines = (s) => s.split(/(?<=\n)/).filter((l) => l !== "");

/** .ipynb text of a notebook. */
export function serializeNotebook({ cells, metadata = {} }) {
  const nb = {
    cells: cells.map((c, i) => {
      const cell = { cell_type: c.type, id: `cell-${i}`, metadata: {}, source: lines(c.source) };
      if (c.type === "code") {
        cell.execution_count = c.count;
        cell.outputs = c.outputs.map((o) =>
          o.name === "svg" || o.name === "png"
            ? { output_type: "display_data", data: { [o.name === "svg" ? "image/svg+xml" : "image/png"]: o.name === "svg" ? lines(o.text) : o.text, "text/plain": ["<Figure>"] }, metadata: {} }
            : { output_type: "stream", name: o.name, text: lines(o.text) },
        );
      }
      return cell;
    }),
    metadata: {
      ...metadata,
      kernelspec: { name: "rupy", display_name: "rupy", language: "python" },
      language_info: { name: "python" },
    },
    nbformat: 4,
    nbformat_minor: 5,
  };
  return JSON.stringify(nb, null, 1) + "\n";
}

/**
 * The program of code cells 0..upto: { src, starts }, starts[j] = { cell, line, count }
 * (the cell's index, its first line in src, its number of lines).
 */
export function buildProgram(cells, upto = cells.length - 1) {
  const out = [];
  const starts = [];
  cells.forEach((c, i) => {
    if (i > upto || c.type !== "code") return;
    out.push(`print("\\x1e${i}\\x1e", end="")`);
    const body = c.source.replace(/\n+$/, "").split("\n");
    starts.push({ cell: i, line: out.length + 1, count: body.length });
    out.push(...body);
  });
  return { src: out.join("\n") + "\n", starts };
}

/** The cell of a line of the program and the line in that cell (null: before every cell). */
export function locate(starts, line) {
  let at = null;
  for (const s of starts) if (s.line - 1 <= line) at = s; // a marker line belongs to the cell after it
  if (!at) return null;
  return { cell: at.cell, line: Math.min(Math.max(line - at.line + 1, 1), at.count) };
}

/**
 * Splits a stream of stdout chunks among cells: feed(text) calls emit(cell, text)
 * for each piece; `current` is the cell that printed last (-1: none yet).
 */
export function outputSplitter(emit) {
  const marker = /\x1e(\d+)\x1e/g;
  const self = {
    current: -1,
    feed(text) {
      let at = 0;
      for (const m of text.matchAll(marker)) {
        if (m.index > at && self.current >= 0) emit(self.current, text.slice(at, m.index));
        self.current = +m[1];
        emit(self.current, "");
        at = m.index + m[0].length;
      }
      if (at < text.length && self.current >= 0) emit(self.current, text.slice(at));
    },
  };
  return self;
}
