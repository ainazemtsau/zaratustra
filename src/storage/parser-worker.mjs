// Data-only bounded extraction. Never open a source path or fetch a document URL.
import { parentPort, workerData } from "node:worker_threads";
import { posix } from "node:path";
import { Parser } from "htmlparser2";
import yauzl from "yauzl";
import { crc32 } from "node:zlib";

globalThis.fetch = () => {
  throw new Error("External loads are disabled");
};
const MAX_TEXT = 8_000_000;
const MAX_EXPANDED = 128 * 1024 * 1024;
let text = "";
let points = 0;
const sections = [],
  warnings = [];
const result = {
  format: workerData.format,
  status: "readable",
  parser: "",
  parser_version: "",
  sections,
  warnings,
};
function append(value, locator, label, available = true) {
  const start = points;
  const remaining = MAX_TEXT - points;
  let count = 0,
    units = 0;
  for (const cp of value) {
    if (count === remaining) break;
    count++;
    units += cp.length;
  }
  text += value.slice(0, units);
  points += count;
  sections.push({ locator, label, start, end: points, available });
  if (units < value.length) {
    result.status = "partial";
    warnings.push(
      "Text truncated at 8000000 Unicode code points; later sections unavailable.",
    );
    return false;
  }
  return true;
}
const local = (s) => s.split(":").at(-1);
function xml(value, callbacks) {
  // htmlparser2 does not resolve custom/external entities. Reject declarations explicitly.
  if (/<!ENTITY/i.test(value))
    throw new Error("Custom entities are unsupported");
  const p = new Parser(callbacks, { xmlMode: true, decodeEntities: true });
  p.end(value);
}
const decode = (b) => {
  if (!b) throw new Error("Missing EPUB document");
  const encoding =
    b[0] === 0xff && b[1] === 0xfe
      ? "utf-16le"
      : b[0] === 0xfe && b[1] === 0xff
        ? "utf-16be"
        : "utf-8";
  return new TextDecoder(encoding, { fatal: true }).decode(b);
};
function chapter(value) {
  let out = "",
    skip = 0;
  xml(value, {
    onopentag(n) {
      if (["script", "style"].includes(local(n))) skip++;
      if (
        !skip &&
        ["p", "div", "br", "h1", "h2", "h3", "li", "section"].includes(local(n))
      )
        out += "\n";
    },
    onclosetag(n) {
      if (["script", "style"].includes(local(n))) skip--;
      if (
        !skip &&
        ["p", "div", "h1", "h2", "h3", "li", "section"].includes(local(n))
      )
        out += "\n";
    },
    ontext(s) {
      if (!skip) out += s;
    },
  });
  return out.replace(/\n{3,}/g, "\n\n").trim() + "\n";
}
async function epub(bytes) {
  result.parser = "yauzl + htmlparser2";
  result.parser_version = "3.4.0 + 12.0.0";
  const zip = await new Promise((ok, no) =>
    yauzl.fromBuffer(
      Buffer.from(bytes),
      { lazyEntries: true, validateEntrySizes: true, strictFileNames: true },
      (e, z) => (e ? no(e) : ok(z)),
    ),
  );
  const files = new Map();
  let expanded = 0,
    count = 0;
  try {
    await new Promise((ok, no) => {
      zip.on("error", no);
      zip.on("end", ok);
      zip.on("entry", (entry) => {
        const name = entry.fileName;
        if (
          ++count > 10000 ||
          entry.uncompressedSize > 16 * 1024 * 1024 ||
          (expanded += entry.uncompressedSize) > MAX_EXPANDED
        ) {
          no(
            Object.assign(
              new Error("EPUB ZIP expansion/entry limit exceeded"),
              { limit: true },
            ),
          );
          zip.close();
          return;
        }
        if (
          name.includes("\\") ||
          name.startsWith("/") ||
          name.split("/").some((p) => p === "..") ||
          /[:\0]/.test(name) ||
          files.has(name)
        ) {
          no(new Error("Unsafe or duplicate EPUB entry path"));
          zip.close();
          return;
        }
        if (entry.generalPurposeBitFlag & 1) {
          no(
            Object.assign(new Error("Encrypted ZIP entries are unsupported"), {
              encrypted: true,
            }),
          );
          zip.close();
          return;
        }
        if (name.endsWith("/")) {
          zip.readEntry();
          return;
        }
        zip.openReadStream(entry, (err, stream) => {
          if (err) {
            no(err);
            return;
          }
          const chunks = [];
          let n = 0;
          stream.on("error", no);
          stream.on("data", (b) => {
            n += b.length;
            if (n > entry.uncompressedSize || n > 16 * 1024 * 1024) {
              stream.destroy(new Error("ZIP output exceeds bound"));
              return;
            }
            chunks.push(b);
          });
          stream.on("end", () => {
            const data = Buffer.concat(chunks);
            if (crc32(data) !== entry.crc32) {
              no(new Error("EPUB entry CRC mismatch"));
              zip.close();
              return;
            }
            files.set(name, data);
            zip.readEntry();
          });
        });
      });
      zip.readEntry();
    });
    if (files.has("META-INF/encryption.xml")) {
      result.status = "encrypted";
      warnings.push("EPUB encryption manifest present; no text claimed.");
      return;
    }
    if (files.get("mimetype")?.toString() !== "application/epub+zip")
      throw new Error("Missing EPUB mimetype");
    let root;
    xml(decode(files.get("META-INF/container.xml")), {
      onopentag(n, a) {
        if (local(n) === "rootfile" && !root) root = a["full-path"];
      },
    });
    const safe = (base, href) => {
      const decoded = decodeURIComponent(href.split("#")[0]);
      if (
        /^[a-z][a-z0-9+.-]*:/i.test(decoded) ||
        decoded.startsWith("/") ||
        decoded.includes("\\") ||
        decoded.includes("\0")
      )
        throw new Error("External/unsafe EPUB reference");
      const name = posix.normalize(posix.join(base, decoded));
      if (name.startsWith("../") || !files.has(name))
        throw new Error("EPUB section unavailable: " + name);
      return name;
    };
    root = safe("", root ?? "");
    const items = new Map(),
      spine = [];
    xml(decode(files.get(root)), {
      onopentag(n, a) {
        if (local(n) === "item")
          items.set(a.id, { href: a.href, type: a["media-type"] });
        if (local(n) === "itemref") spine.push(a.idref);
      },
    });
    if (!spine.length) throw new Error("Missing EPUB reading order");
    if (spine.length > 2000)
      throw Object.assign(new Error("EPUB chapter limit exceeded"), {
        limit: true,
      });
    let blankChapters = 0;
    for (let i = 0; i < spine.length; i++) {
      const item = items.get(spine[i]);
      try {
        if (
          !item ||
          !["application/xhtml+xml", "text/html"].includes(item.type)
        )
          throw new Error("Unsupported/missing spine item");
        const name = safe(posix.dirname(root), item.href);
        const value = chapter(decode(files.get(name)));
        const hasText = !!value.trim();
        if (!hasText) {
          blankChapters++;
          result.status = "partial";
          warnings.push(
            "Chapter " +
              (i + 1) +
              " has no extractable text; blank or image-only (OCR unavailable).",
          );
        }
        if (!append(value, "chapter:" + (i + 1) + ":" + name, name, hasText)) {
          for (let j = i + 1; j < spine.length; j++)
            append("", "chapter:" + (j + 1), "Unextracted chapter", false);
          break;
        }
      } catch (e) {
        result.status = "partial";
        warnings.push("Chapter " + (i + 1) + ": " + e.message);
        append("", "chapter:" + (i + 1), "Unavailable chapter", false);
      }
    }
    if (blankChapters === spine.length) result.status = "scanned";
  } finally {
    zip.close();
  }
}
async function pdf(bytes) {
  result.parser = "pdfjs-dist";
  result.parser_version = "6.4.299";
  const { getDocument } = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const task = getDocument({
    data: new Uint8Array(bytes),
    isEvalSupported: false,
    useSystemFonts: false,
    disableFontFace: true,
    useWorkerFetch: false,
    useWasm: false,
    disableAutoFetch: true,
    disableStream: true,
    stopAtErrors: true,
    verbosity: 0,
    isOffscreenCanvasSupported: false,
    isImageDecoderSupported: false,
  });
  try {
    const doc = await task.promise;
    if (doc.numPages > 2000)
      throw Object.assign(new Error("PDF page limit exceeded"), {
        limit: true,
      });
    for (let i = 1; i <= doc.numPages; i++) {
      try {
        const page = await doc.getPage(i),
          content = await page.getTextContent();
        const value =
          content.items
            .filter((x) => "str" in x)
            .map((x) => x.str + (x.hasEOL ? "\n" : " "))
            .join("") + "\n";
        const hasText = !!value.trim();
        if (!hasText) {
          result.status = "partial";
          warnings.push(
            "Page " +
              i +
              " has no extractable text; blank or scanned (OCR unavailable).",
          );
        }
        if (!append(value, "page:" + i, "Page " + i, hasText)) {
          for (let j = i + 1; j <= doc.numPages; j++)
            append("", "page:" + j, "Page " + j, false);
          break;
        }
        page.cleanup();
      } catch (e) {
        result.status = "partial";
        warnings.push("Page " + i + ": " + e.message);
        append("", "page:" + i, "Page " + i, false);
      }
    }
    if (!text.trim()) result.status = "scanned";
  } finally {
    await task.destroy();
  }
}
try {
  if (workerData.format === "pdf") await pdf(workerData.bytes);
  else await epub(workerData.bytes);
} catch (e) {
  result.status =
    e.name === "PasswordException" || e.encrypted
      ? "encrypted"
      : e.limit
        ? "limit_exceeded"
        : "damaged";
  warnings.push(e.message);
  text = "";
  points = 0;
  sections.length = 0;
}
parentPort.postMessage({ ...result, text, total_characters: points });
