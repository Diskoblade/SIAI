import {
  addBlankSlide,
  addSlideImage,
  addSlideShape,
  addSlideTextBox,
  createPresentation,
  findShapesOutsideCanvas,
  getSlides,
  inches,
  loadPresentation,
  savePresentation,
  setShapeAlignment,
  setShapeFill,
  setShapeNoStroke,
  setShapeTextAutoFit,
  setShapeTextFormat,
  setShapeTextMargins,
  setSlideBackground,
  setSlideTransition,
  validatePresentation,
} from "@office-kit/pptx";

const MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
const COLORS = {
  ink: "#172033",
  paper: "#F7F9FC",
  white: "#FFFFFF",
  muted: "#5F6B7A",
  mist: "#E8EEF4",
  teal: "#147D75",
  coral: "#D9634C",
  gold: "#E0A933",
};
const FONT = "Aptos";

function addText(slide, { x, y, w, h, text, size, color, bold = false, align = "left" }) {
  const shape = addSlideTextBox(slide, {
    x: inches(x),
    y: inches(y),
    w: inches(w),
    h: inches(h),
    text,
  });
  setShapeTextFormat(shape, { font: FONT, size, color, bold });
  setShapeAlignment(shape, align);
  setShapeTextAutoFit(shape, "normal");
  setShapeTextMargins(shape, {
    left: inches(0.03),
    right: inches(0.03),
    top: inches(0.03),
    bottom: inches(0.03),
  });
  return shape;
}

function addFooter(slide, current, total, sourceMode) {
  addText(slide, {
    x: 0.7,
    y: 7.08,
    w: 7.5,
    h: 0.2,
    text: sourceMode === "general_knowledge"
      ? "Sovereign Knowledge Portal | General model knowledge"
      : "Sovereign Knowledge Portal | Authorized evidence",
    size: 9,
    color: COLORS.muted,
  });
  addText(slide, {
    x: 11.7,
    y: 7.04,
    w: 0.9,
    h: 0.25,
    text: `${current} / ${total}`,
    size: 9,
    color: COLORS.muted,
    align: "right",
  });
}

function addCard(slide, { x, y, w, h, text, accent, index, compact = false }) {
  const card = addSlideShape(slide, {
    preset: "roundRect",
    x: inches(x),
    y: inches(y),
    w: inches(w),
    h: inches(h),
    text,
    textAnchor: "ctr",
  });
  setShapeFill(card, COLORS.white);
  setShapeNoStroke(card);
  setShapeTextFormat(card, {
    font: FONT,
    size: compact ? 17 : 22,
    color: COLORS.ink,
  });
  setShapeTextAutoFit(card, "normal");
  setShapeTextMargins(card, {
    left: inches(0.55),
    right: inches(0.3),
    top: inches(0.22),
    bottom: inches(0.2),
  });

  const marker = addSlideShape(slide, {
    preset: "ellipse",
    x: inches(x + 0.16),
    y: inches(y + 0.2),
    w: inches(0.28),
    h: inches(0.28),
    text: String(index),
    textAnchor: "ctr",
  });
  setShapeFill(marker, accent);
  setShapeNoStroke(marker);
  setShapeTextFormat(marker, { font: FONT, size: 9, color: COLORS.white, bold: true });
  setShapeAlignment(marker, "center");
}

function addTitleSlide(presentation, spec, total) {
  const slide = addBlankSlide(presentation);
  setSlideBackground(slide, COLORS.ink);

  const accent = addSlideShape(slide, {
    preset: "rect",
    x: inches(11.95),
    y: inches(0),
    w: inches(1.38),
    h: inches(7.5),
  });
  setShapeFill(accent, COLORS.coral);
  setShapeNoStroke(accent);

  addText(slide, {
    x: 0.85,
    y: 0.7,
    w: 6.3,
    h: 0.3,
    text: "SOVEREIGN KNOWLEDGE PORTAL",
    size: 12,
    color: COLORS.gold,
    bold: true,
  });
  addText(slide, {
    x: 0.82,
    y: 1.7,
    w: 10.3,
    h: 2.3,
    text: spec.title,
    size: 50,
    color: COLORS.white,
    bold: true,
  });
  addText(slide, {
    x: 0.85,
    y: 4.35,
    w: 8.8,
    h: 0.7,
    text: spec.subtitle,
    size: 18,
    color: COLORS.mist,
  });
  addText(slide, {
    x: 0.85,
    y: 6.62,
    w: 4.8,
    h: 0.28,
    text: `${total} slides | Generated on demand`,
    size: 10,
    color: COLORS.mist,
  });
  setSlideTransition(slide, { effect: "fade" });
}

function base64ToBytes(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// Read intrinsic pixel size from a PNG's IHDR chunk (bytes 16-23).
function pngSize(bytes) {
  if (bytes.length < 24) return { w: 16, h: 9 };
  const rd = (o) => (bytes[o] << 24) | (bytes[o + 1] << 16) | (bytes[o + 2] << 8) | bytes[o + 3];
  return { w: rd(16) >>> 0 || 16, h: rd(20) >>> 0 || 9 };
}

function addSlideHeader(slide, item, accent) {
  addText(slide, {
    x: 0.7, y: 0.48, w: 10.7, h: 0.55, text: item.title,
    size: 32, color: COLORS.ink, bold: true,
  });
  addText(slide, {
    x: 11.3, y: 0.52, w: 1.25, h: 0.3, text: item.layout.toUpperCase(),
    size: 9, color: accent, bold: true, align: "right",
  });
}

function addImageSlide(presentation, item, current, total, sourceMode) {
  const slide = addBlankSlide(presentation);
  setSlideBackground(slide, COLORS.paper);
  addSlideHeader(slide, item, COLORS.teal);

  const bytes = base64ToBytes(item.image_base64);
  const { w: pw, h: ph } = pngSize(bytes);
  const boxX = 0.72, boxY = 1.35, boxW = 11.9, boxH = 5.45;
  const aspect = pw / ph || 16 / 9;
  let w = boxW;
  let h = w / aspect;
  if (h > boxH) {
    h = boxH;
    w = h * aspect;
  }
  const x = boxX + (boxW - w) / 2;
  const y = boxY + (boxH - h) / 2;
  addSlideImage(slide, bytes, { x: inches(x), y: inches(y), w: inches(w), h: inches(h) });

  addFooter(slide, current, total, sourceMode);
  setSlideTransition(slide, { effect: "fade" });
}

function addTableSlide(presentation, item, current, total, sourceMode) {
  const slide = addBlankSlide(presentation);
  setSlideBackground(slide, COLORS.paper);
  addSlideHeader(slide, item, COLORS.gold);

  const columns = (item.table.columns || []).slice(0, 6);
  const rows = (item.table.rows || []).slice(0, 8);
  const nCols = Math.max(columns.length, 1);
  const areaX = 0.72, areaY = 1.5, areaW = 11.9, areaH = 5.2;
  const colW = areaW / nCols;
  const rowH = Math.min(0.62, areaH / (rows.length + 1));

  const cell = (text, cx, cy, cw, ch, { header = false, alt = false } = {}) => {
    const shape = addSlideShape(slide, {
      preset: "rect", x: inches(cx), y: inches(cy), w: inches(cw), h: inches(ch),
      text: String(text ?? ""), textAnchor: "ctr",
    });
    setShapeFill(shape, header ? COLORS.teal : alt ? COLORS.mist : COLORS.white);
    setShapeNoStroke(shape);
    setShapeTextFormat(shape, {
      font: FONT, size: 12, color: header ? COLORS.white : COLORS.ink, bold: header,
    });
    setShapeAlignment(shape, "center");
    setShapeTextMargins(shape, {
      left: inches(0.06), right: inches(0.06), top: inches(0.04), bottom: inches(0.04),
    });
  };

  columns.forEach((col, c) => cell(col, areaX + c * colW, areaY, colW, rowH, { header: true }));
  rows.forEach((row, r) => {
    for (let c = 0; c < nCols; c += 1) {
      cell(row[c], areaX + c * colW, areaY + (r + 1) * rowH, colW, rowH, { alt: r % 2 === 1 });
    }
  });

  addFooter(slide, current, total, sourceMode);
  setSlideTransition(slide, { effect: "fade" });
}

function addContentSlide(presentation, item, current, total, sourceMode) {
  const slide = addBlankSlide(presentation);
  setSlideBackground(slide, COLORS.paper);
  const accent = item.layout === "sources" ? COLORS.gold : item.layout === "notice" ? COLORS.coral : COLORS.teal;

  addText(slide, {
    x: 0.7,
    y: 0.48,
    w: 10.7,
    h: 0.55,
    text: item.title,
    size: 35,
    color: COLORS.ink,
    bold: true,
  });
  addText(slide, {
    x: 11.3,
    y: 0.52,
    w: 1.25,
    h: 0.3,
    text: item.layout.toUpperCase(),
    size: 9,
    color: accent,
    bold: true,
    align: "right",
  });

  const bullets = item.bullets.slice(0, 6);
  if (bullets.length === 1) {
    addCard(slide, {
      x: 0.72,
      y: 1.45,
      w: 11.9,
      h: 4.75,
      text: bullets[0],
      accent,
      index: 1,
      compact: bullets[0].length > 300,
    });
  } else {
    const columns = bullets.length <= 3 ? 1 : 2;
    const rows = Math.ceil(bullets.length / columns);
    const cardWidth = columns === 1 ? 11.9 : 5.75;
    const cardHeight = Math.min(1.55, 4.95 / rows);
    bullets.forEach((bullet, index) => {
      const column = columns === 1 ? 0 : index % 2;
      const row = columns === 1 ? index : Math.floor(index / 2);
      addCard(slide, {
        x: 0.72 + column * 6.12,
        y: 1.38 + row * (cardHeight + 0.22),
        w: cardWidth,
        h: cardHeight,
        text: bullet,
        accent,
        index: index + 1,
        compact: bullet.length > 170,
      });
    });
  }

  addFooter(slide, current, total, sourceMode);
  setSlideTransition(slide, { effect: "fade" });
}

export async function buildPresentationBytes(spec) {
  if (!spec || spec.kind !== "pptx" || !Array.isArray(spec.slides)) {
    throw new Error("The server returned an invalid presentation specification.");
  }

  const presentation = createPresentation({ size: "16:9" });
  const total = spec.slides.length + 1;
  addTitleSlide(presentation, spec, total);
  spec.slides.forEach((slide, index) => {
    const position = index + 2;
    if (slide.image_base64) {
      addImageSlide(presentation, slide, position, total, spec.source_mode);
    } else if (slide.table && (slide.table.columns || []).length) {
      addTableSlide(presentation, slide, position, total, spec.source_mode);
    } else {
      addContentSlide(presentation, slide, position, total, spec.source_mode);
    }
  });

  const validationErrors = validatePresentation(presentation).filter(
    (issue) => issue.severity === "error"
  );
  if (validationErrors.length) {
    throw new Error(`Presentation validation failed: ${validationErrors[0].message}`);
  }
  for (const slide of getSlides(presentation)) {
    if (findShapesOutsideCanvas(slide, presentation).length) {
      throw new Error("Presentation layout contains content outside the slide canvas.");
    }
  }

  const bytes = await savePresentation(presentation);
  const roundTrip = await loadPresentation(bytes);
  if (getSlides(roundTrip).length !== total) {
    throw new Error("Presentation round-trip validation failed.");
  }
  return bytes;
}

export async function downloadPresentation(spec) {
  const bytes = await buildPresentationBytes(spec);
  const blob = new Blob([bytes], { type: MIME_TYPE });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = spec.filename || "department-briefing.pptx";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
