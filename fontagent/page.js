// In-page helpers for the renderer. Evaluated once per page; exposes window.__fsa.
// Kept free of dependencies so the same code runs on a static HTML file or a live
// dev server.
(() => {
  const ICON_FONT = /icon|symbol|awesome|glyph|emoji/i;
  const CONTROL = "button,a,nav,label,th,td,select,input,textarea,summary," +
    "[role=button],[role=tab],[role=menuitem],[role=link]";
  const FORM_FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

  const firstFamily = (stack) => stack.split(",")[0].trim().replace(/^["']|["']$/g, "");
  const norm = (name) => name.toLowerCase().replace(/[^a-z0-9]/g, "");

  function isVisible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function ownText(el) {
    if (FORM_FIELDS.has(el.tagName)) return el.value || el.placeholder || "";
    let text = "";
    for (const n of el.childNodes) if (n.nodeType === Node.TEXT_NODE) text += n.textContent;
    return text.trim();
  }

  function isHeading(el, bodySize) {
    if (/^H[1-6]$/.test(el.tagName) || el.closest("h1,h2,h3,h4,h5,h6,[role=heading]")) return true;
    return parseFloat(getComputedStyle(el).fontSize) >= 1.5 * bodySize;
  }

  // Tag every visible element that holds text with a stable id (document order), and
  // mark the ones a font change should apply to. Icon fonts are never targeted:
  // overriding them turns ligature icons ("search") into words.
  function prepare({ scope }) {
    const bodySize = parseFloat(getComputedStyle(document.body).fontSize) || 16;
    const weights = new Set();
    let italic = false;
    let sample = "";
    let id = 0;
    let targets = 0;
    for (const el of document.body.querySelectorAll("*")) {
      if (["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(el.tagName)) continue;
      const text = ownText(el);
      if (!text || !isVisible(el)) continue;
      const cs = getComputedStyle(el);
      el.dataset.fsaId = String(id++);
      el.dataset.fsaStack = cs.fontFamily;
      const icon = ICON_FONT.test(firstFamily(cs.fontFamily));
      if (icon) el.dataset.fsaIcon = "1";
      const heading = isHeading(el, bodySize);
      const inScope = scope === "all" || (scope === "headings") === heading;
      if (!icon && inScope) {
        el.dataset.fsaTarget = "1";
        targets++;
        weights.add(Math.round(parseInt(cs.fontWeight, 10) / 100) * 100);
        if (cs.fontStyle !== "normal") italic = true;
        if (sample.length < 400) sample += text + " ";
      }
    }
    return { text_elements: id, targets, weights: [...weights], italic, sample };
  }

  // v2: set the font on targeted elements only, keeping each element's original stack
  // as the fallback so missing glyphs fall back to what the page already used.
  function apply({ family }) {
    for (const el of document.querySelectorAll("[data-fsa-target]")) {
      el.style.setProperty("font-family", `"${family}", ${el.dataset.fsaStack}`, "important");
    }
  }

  async function waitForFonts({ family, weights, italic, sample, timeoutMs }) {
    const loads = [];
    for (const w of weights.length ? weights : [400]) {
      loads.push(document.fonts.load(`${w} 16px "${family}"`, sample || "Aa"));
      if (italic) loads.push(document.fonts.load(`italic ${w} 16px "${family}"`, sample || "Aa"));
    }
    const timeout = new Promise((resolve) => setTimeout(() => resolve("timeout"), timeoutMs));
    const outcome = await Promise.race([Promise.allSettled(loads).then(() => "ok"), timeout]);
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    return outcome;
  }

  function faceWeights(face) {
    const parts = String(face.weight).split(/\s+/).map((w) => parseInt(w, 10) || 400);
    return [Math.min(...parts), Math.max(...parts)];
  }

  // Which faces of `family` actually loaded, and which targeted elements the browser
  // will have to fake: bold text with no bold face, italic text with no italic face.
  function faces({ family }) {
    const loaded = [...document.fonts].filter(
      (f) => norm(f.family) === norm(family) && f.status === "loaded");
    const hasBold = loaded.some((f) => faceWeights(f)[1] >= 600);
    const hasItalic = loaded.some((f) => f.style !== "normal");
    const syntheticBold = [];
    const syntheticItalic = [];
    for (const el of document.querySelectorAll("[data-fsa-target]")) {
      const cs = getComputedStyle(el);
      if (parseInt(cs.fontWeight, 10) >= 600 && !hasBold) syntheticBold.push(el.dataset.fsaId);
      if (cs.fontStyle !== "normal" && !hasItalic) syntheticItalic.push(el.dataset.fsaId);
    }
    return {
      loaded_faces: loaded.map((f) => `${f.style} ${f.weight}`).filter((v, i, a) => a.indexOf(v) === i),
      synthetic_bold: syntheticBold,
      synthetic_italic: syntheticItalic,
    };
  }

  // Count rendered lines from the boxes of the element's own text nodes.
  function lineCount(el) {
    if (FORM_FIELDS.has(el.tagName)) return 1;
    const tops = [];
    const range = document.createRange();
    for (const n of el.childNodes) {
      if (n.nodeType !== Node.TEXT_NODE || !n.textContent.trim()) continue;
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (r.width < 1) continue;
        if (!tops.some((t) => Math.abs(t - r.top) < Math.max(3, r.height / 2))) tops.push(r.top);
      }
    }
    return Math.max(tops.length, 1);
  }

  function measure() {
    const blocks = [];
    for (const el of document.querySelectorAll("[data-fsa-id]")) {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      const block = !cs.display.startsWith("inline") || cs.display === "inline-block";
      // Overflow in px per axis. Compared with the baseline by amount, because many
      // real buttons already overflow by a pixel or two of line-height, invisibly.
      const overX = block ? Math.max(0, el.scrollWidth - el.clientWidth) : 0;
      const overY = block ? Math.max(0, el.scrollHeight - el.clientHeight) : 0;
      blocks.push({
        id: el.dataset.fsaId,
        tag: el.tagName.toLowerCase(),
        text: ownText(el).slice(0, 60),
        control: !!el.closest(CONTROL),
        heading: /^h[1-6]$/i.test(el.tagName),
        target: !!el.dataset.fsaTarget,
        icon: !!el.dataset.fsaIcon,
        family: firstFamily(cs.fontFamily),
        weight: parseInt(cs.fontWeight, 10),
        lines: lineCount(el),
        x: Math.round(r.left), y: Math.round(r.top + window.scrollY),
        w: Math.round(r.width), h: Math.round(r.height),
        clip_x: cs.overflowX !== "visible" ? overX : 0,
        clip_y: cs.overflowY !== "visible" ? overY : 0,
        spill_x: cs.overflowX === "visible" ? overX : 0,
        spill_y: cs.overflowY === "visible" ? overY : 0,
      });
    }
    const doc = document.documentElement;
    return {
      viewport_width: doc.clientWidth,
      scroll_width: doc.scrollWidth,
      page_height: doc.scrollHeight,
      blocks,
    };
  }

  window.__fsa = { prepare, apply, waitForFonts, faces, measure };
})();
