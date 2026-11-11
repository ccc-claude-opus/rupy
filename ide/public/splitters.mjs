// Draggable borders between the panes (like VS Code): the file list's width,
// the output panel's height and the AI panel's width. The sizes are CSS
// variables of .layout, kept in the store; a double click puts one back.

const SIZES = {
  // name: [CSS variable, which way it is dragged]
  side: ["--side-w", "x"],
  panel: ["--panel-h", "y"],
  "nb-panel": ["--nb-panel-h", "y"],
  ai: ["--ai-w", "x"],
};

/** The size (px) for a pointer at (x, y) in the layout, kept within limits
 * (the editor keeps at least 240px between the file list and the AI panel). */
function sizeAt(name, layout, x, y) {
  const r = layout.getBoundingClientRect();
  const clamp = (v, lo, hi) => Math.round(Math.max(lo, Math.min(hi, v)));
  const width = (sel) => layout.querySelector(sel)?.getBoundingClientRect().width || 0;
  switch (name) {
    case "side":
      return clamp(x - r.left, 120, Math.min(r.width * 0.5, r.width - width(".ai-panel") - 240));
    case "ai":
      return clamp(r.right - x, 240, Math.min(r.width * 0.6, r.width - width(".sidebar") - 240));
    default:
      return clamp(r.bottom - y, 40, r.height - 80);
  }
}

export function initSplitters(layout, store) {
  for (const name of Object.keys(SIZES)) {
    const v = Number(store.get("size." + name));
    if (v > 0) layout.style.setProperty(SIZES[name][0], v + "px");
  }
  const make = (cls, title) => {
    const d = document.createElement("div");
    d.className = "splitter " + cls;
    d.title = title + "（拖曳調整，點兩下還原）";
    d.setAttribute("role", "separator");
    layout.append(d);
    return d;
  };
  const grips = [
    [make("split-side", "檔案清單的寬度"), () => "side"],
    [make("split-panel", "輸出區的高度"), () => (layout.classList.contains("nb") ? "nb-panel" : "panel")],
    [make("split-ai", "AI 助手的寬度"), () => "ai"],
  ];
  for (const [grip, which] of grips) {
    grip.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const name = which();
      const [prop, axis] = SIZES[name];
      grip.setPointerCapture(e.pointerId);
      document.body.classList.add("dragging", "dragging-" + axis);
      const move = (ev) => {
        const v = sizeAt(name, layout, ev.clientX, ev.clientY);
        layout.style.setProperty(prop, v + "px");
      };
      const up = () => {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        document.body.classList.remove("dragging", "dragging-" + axis);
        const v = parseInt(layout.style.getPropertyValue(prop));
        if (v > 0) store.set("size." + name, String(v));
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    });
    grip.addEventListener("dblclick", () => {
      const name = which();
      layout.style.removeProperty(SIZES[name][0]);
      store.set("size." + name, "");
    });
  }
}
