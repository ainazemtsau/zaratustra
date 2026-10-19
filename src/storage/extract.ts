import { Worker } from "node:worker_threads";
import type { Extraction } from "../core/index.ts";

export function extract(
  bytes: Uint8Array,
  format: string,
  signal?: AbortSignal,
): Promise<Extraction & { text: string }> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./parser-worker.mjs", import.meta.url), {
      workerData: { bytes, format },
      resourceLimits: { maxOldGenerationSizeMb: 256 },
    });
    const stop = () => {
      void worker.terminate();
    };
    const aborted = () => {
      stop();
      reject(
        new Error("Import cancelled: runtime or processing authority changed."),
      );
    };
    const timer = setTimeout(() => {
      stop();
      resolve({
        format,
        status: "limit_exceeded",
        parser: format === "pdf" ? "pdfjs-dist" : "yauzl + htmlparser2",
        parser_version: format === "pdf" ? "6.4.299" : "3.4.0 + 12.0.0",
        text: "",
        text_blob_ref: null,
        text_hash: null,
        total_characters: 0,
        sections: [],
        warnings: ["Extraction exceeded 45 seconds."],
      });
    }, 45000);
    signal?.addEventListener("abort", aborted, { once: true });
    worker.on("message", (value) => {
      resolve(value);
      stop();
    });
    worker.on("error", reject);
    worker.on("exit", (code) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", aborted);
      if (code !== 0)
        reject(
          new Error("Parser worker stopped; no readable handle was published."),
        );
    });
    if (signal?.aborted) aborted();
  });
}
