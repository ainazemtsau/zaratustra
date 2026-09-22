import { closeSync, existsSync, fsyncSync, openSync, readFileSync, writeSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { createProvider, openAICompletionsApi } from "@earendil-works/pi-ai";

type InvocationPurpose = "content" | "compaction-summary" | "overflow-retry";

function appendDurable(path: string, value: unknown): void {
	const fd = openSync(path, "a");
	try {
		writeSync(fd, `${JSON.stringify(value)}\n`, undefined, "utf8");
		fsyncSync(fd);
	} finally {
		closeSync(fd);
	}
}

function digest(body: string): string {
	return createHash("sha256").update(Buffer.from(body, "utf8")).digest("hex");
}

function compactUsage(value: any): unknown {
	if (!value || typeof value !== "object") return null;
	return {
		input: value.input ?? value.promptTokens ?? 0,
		output: value.output ?? value.completionTokens ?? 0,
		cacheRead: value.cacheRead ?? 0,
		cacheWrite: value.cacheWrite ?? 0,
		totalTokens: value.totalTokens ?? value.total_tokens ?? 0,
	};
}

export default function (pi: any): void {
	const evidencePath = process.env.ZARATUSTRA_PROBE_EXTENSION_LOG;
	const resourcePath = process.env.ZARATUSTRA_PROBE_RESOURCE_LOG;
	const waitPath = process.env.ZARATUSTRA_PROBE_WAIT_LOG;
	const failPath = process.env.ZARATUSTRA_PROBE_FAIL_PERSIST;
	const baseUrl = process.env.ZARATUSTRA_PROBE_PROVIDER_BASE_URL;
	if (!evidencePath || !resourcePath || !waitPath || !failPath || !baseUrl) {
		throw new Error("missing Pi integration probe environment");
	}

	let nextPurpose: InvocationPurpose = "content";
	let pendingPayloadSha256: string | null = null;
	let compactionInvocationId: string | null = null;
	let turnInvocationId: string | null = null;
	let turnInvocationPurpose: InvocationPurpose | null = null;
	const transport = openAICompletionsApi();
	const guardedFetch = async (input: any, init?: any): Promise<Response> => {
		const body = typeof init?.body === "string" ? init.body : String(init?.body ?? "");
		const invocationId = randomUUID();
		const purpose = nextPurpose;
		nextPurpose = "content";
		if (existsSync(failPath)) {
			throw new Error("probe persistence unavailable before transport");
		}
		const bodySha256 = digest(body);
		let reserveUnits = 256;
		try {
			const payload = JSON.parse(body);
			reserveUnits = Number(payload.max_tokens ?? payload.max_completion_tokens ?? 256);
		} catch {
			// The final serialized bytes remain evidence if a future adapter changes shape.
		}
		appendDurable(resourcePath, {
			type: "resource_reserved",
			invocationId,
			purpose,
			reservedUnits: reserveUnits,
			bodySha256,
		});
		const observation = {
			type: "transport_ready",
			invocationId,
			purpose,
			bodySha256,
			payloadHookSha256: pendingPayloadSha256,
			body,
		};
		appendDurable(evidencePath, observation);
		pendingPayloadSha256 = null;
		if (purpose === "compaction-summary") compactionInvocationId = invocationId;
		else {
			turnInvocationId = invocationId;
			turnInvocationPurpose = purpose;
		}
		const headers = new Headers(init?.headers ?? {});
		headers.set("x-zara-invocation-id", invocationId);
		headers.set("x-zara-body-sha256", observation.bodySha256);
		headers.set("x-zara-purpose", purpose);
		try {
			const response = await fetch(input, { ...init, headers });
			appendDurable(resourcePath, {
				type: "transport_outcome",
				invocationId,
				purpose,
				outcome: "http-response",
				status: response.status,
			});
			return response;
		} catch (error) {
			appendDurable(resourcePath, {
				type: "transport_outcome",
				invocationId,
				purpose,
				outcome: "unknown",
				error: String(error),
			});
			throw error;
		}
	};

	const guardedTransport = {
		stream(model: any, context: any, options?: any): any {
			return transport.stream(model, context, {
				...options,
				fetch: guardedFetch,
				maxRetries: 0,
			});
		},
		streamSimple(model: any, context: any, options?: any): any {
			return transport.streamSimple(model, context, {
				...options,
				fetch: guardedFetch,
				maxRetries: 0,
			});
		},
	};

	pi.registerProvider(
		createProvider({
			id: "zara-probe",
			name: "Zaratustra localhost probe",
			baseUrl,
			auth: {
				apiKey: {
					name: "Local probe key",
					async login(): Promise<any> {
						return { type: "api_key", key: "local-probe" };
					},
					async resolve(): Promise<any> {
						return { auth: { apiKey: "local-probe" }, source: "localhost probe" };
					},
				},
			},
			models: [
				{
					id: "probe-model",
					name: "Probe model",
					api: "openai-completions",
					provider: "zara-probe",
					baseUrl,
					reasoning: false,
					input: ["text"],
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
					contextWindow: 16384,
					maxTokens: 256,
				},
			],
			api: guardedTransport,
		}),
	);

	pi.on("before_provider_request", (event: any) => {
		pendingPayloadSha256 = digest(JSON.stringify(event.payload));
		appendDurable(evidencePath, {
			type: "payload_hook",
			payloadSha256: pendingPayloadSha256,
		});
	});
	pi.on("after_provider_response", (event: any) => {
		appendDurable(evidencePath, { type: "provider_response", status: event.status });
	});
	pi.on("session_before_compact", (event: any) => {
		nextPurpose = "compaction-summary";
		appendDurable(evidencePath, {
			type: "session_before_compact",
			reason: event.reason,
			willRetry: event.willRetry,
			tokensBefore: event.preparation?.tokensBefore,
			firstKeptEntryId: event.preparation?.firstKeptEntryId,
		});
	});
	pi.on("session_compact", (event: any) => {
		appendDurable(evidencePath, {
			type: "session_compact",
			reason: event.reason,
			willRetry: event.willRetry,
			invocationId: compactionInvocationId,
			entryId: event.compactionEntry?.id,
			usage: compactUsage(event.compactionEntry?.usage),
		});
		appendDurable(resourcePath, {
			type: "resource_accounted",
			invocationId: compactionInvocationId,
			purpose: "compaction-summary",
			usage: compactUsage(event.compactionEntry?.usage),
		});
		nextPurpose = event.willRetry ? "overflow-retry" : "content";
		compactionInvocationId = null;
	});
	pi.on("session_compact_failed", (event: any) => {
		appendDurable(evidencePath, {
			type: "session_compact_failed",
			reason: event.reason,
			willRetry: event.willRetry,
			aborted: event.aborted,
			errorMessage: event.errorMessage,
			invocationId: compactionInvocationId,
		});
		nextPurpose = "content";
		compactionInvocationId = null;
	});
	pi.on("turn_end", (event: any) => {
		const usage = compactUsage(event.message?.usage);
		appendDurable(evidencePath, {
			type: "turn_end",
			turnIndex: event.turnIndex,
			outcome: event.outcome,
			invocationId: turnInvocationId,
			usage,
		});
		appendDurable(resourcePath, {
			type: "resource_accounted",
			invocationId: turnInvocationId,
			purpose: turnInvocationPurpose,
			usage,
			outcome: event.outcome,
		});
		turnInvocationId = null;
		turnInvocationPurpose = null;
	});

	async function ask(ctx: any, resumed: boolean): Promise<void> {
		let waitId = randomUUID();
		if (resumed && existsSync(waitPath)) {
			const rows = readFileSync(waitPath, "utf8")
				.trim()
				.split("\n")
				.filter(Boolean)
				.map((line) => JSON.parse(line));
			const pending = [...rows].reverse().find((row: any) => row.state === "pending");
			if (pending) waitId = pending.waitId;
		}
		appendDurable(waitPath, { state: resumed ? "redisplayed" : "pending", waitId });
		const confirmed = await ctx.ui.confirm("Synthetic wait", `Continue ${waitId}?`);
		appendDurable(waitPath, { state: "continued", waitId, confirmed });
	}

	pi.registerCommand("probe-question", {
		description: "Display a synthetic durable-wait question",
		handler: async (_args: string, ctx: any) => ask(ctx, false),
	});
	pi.registerCommand("probe-resume-question", {
		description: "Redisplay the latest synthetic durable-wait question",
		handler: async (_args: string, ctx: any) => ask(ctx, true),
	});
}
