import { closeSync, existsSync, fsyncSync, openSync, readFileSync, writeSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { createProvider, openAICompletionsApi } from "@earendil-works/pi-ai";

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

export default function (pi: any): void {
	const evidencePath = process.env.ZARATUSTRA_PROBE_EXTENSION_LOG;
	const waitPath = process.env.ZARATUSTRA_PROBE_WAIT_LOG;
	const failPath = process.env.ZARATUSTRA_PROBE_FAIL_PERSIST;
	const baseUrl = process.env.ZARATUSTRA_PROBE_PROVIDER_BASE_URL;
	if (!evidencePath || !waitPath || !failPath || !baseUrl) {
		throw new Error("missing Pi integration probe environment");
	}

	const transport = openAICompletionsApi();
	const guardedFetch = async (input: any, init?: any): Promise<Response> => {
		const body = typeof init?.body === "string" ? init.body : String(init?.body ?? "");
		const invocationId = randomUUID();
		if (existsSync(failPath)) {
			throw new Error("probe persistence unavailable before transport");
		}
		const observation = {
			type: "transport_ready",
			invocationId,
			bodySha256: digest(body),
			body,
		};
		appendDurable(evidencePath, observation);
		const headers = new Headers(init?.headers ?? {});
		headers.set("x-zara-invocation-id", invocationId);
		headers.set("x-zara-body-sha256", observation.bodySha256);
		return fetch(input, { ...init, headers });
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
					contextWindow: 2048,
					maxTokens: 256,
				},
			],
			api: guardedTransport,
		}),
	);

	pi.on("before_provider_request", (event: any) => {
		appendDurable(evidencePath, { type: "payload_hook", payload: event.payload });
	});
	pi.on("after_provider_response", (event: any) => {
		appendDurable(evidencePath, { type: "provider_response", status: event.status });
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
