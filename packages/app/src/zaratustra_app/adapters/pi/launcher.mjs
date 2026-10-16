// Pi owns OAuth and refresh; this launcher receives only a selected auth path.
import { pathToFileURL } from "node:url";
import { createInterface } from "node:readline";

// OAuth library errors can contain token-endpoint bodies. Do not expose those
// bodies through lazy-refresh errors emitted before prompt() rejects.
const emit = event => process.stdout.write(JSON.stringify(event, (key, value) =>
  ["errorMessage", "stack", "cause"].includes(key) || (key === "error" && typeof value === "string")
    ? "pi_native_error_details_withheld" : value) + "\n");
console.error = () => process.stderr.write("pi_native_warning_details_withheld\n");
let session;
let unsubscribe;
try {
  const sdkUrl = pathToFileURL(process.env.ZARA_PI_SDK);
  const sdk = await import(sdkUrl.href);
  const { AuthStorage } = await import(new URL("./core/auth-storage.js", sdkUrl));
  const storage = AuthStorage.create(process.env.ZARA_PI_AUTH_PATH);
  const requireOAuth = value => {
    if (value?.type !== "oauth") throw new Error("selected_native_oauth_unavailable");
    return value;
  };
  // Check every Pi-owned read/refresh, including concurrent credential replacement.
  const credentials = {
    async read(provider, options) {
      if (provider !== "openai") return undefined;
      return requireOAuth(await storage.read(provider, options));
    },
    async list(options) {
      const entries = (await storage.list(options)).filter(item => item.providerId === "openai");
      if (!entries.some(item => item.type === "oauth")) throw new Error("selected_native_oauth_unavailable");
      return entries;
    },
    async modify(provider, fn, options) {
      if (provider !== "openai") throw new Error("unsupported_auth_provider");
      return storage.modify(provider, async current => {
        const next = await fn(requireOAuth(current));
        return next === undefined ? undefined : requireOAuth(next);
      }, options);
    },
    async delete() { throw new Error("auth_deletion_unavailable"); },
  };
  await credentials.list();
  const { ModelRuntime, DefaultResourceLoader, SettingsManager,
    SessionManager, createAgentSession } = sdk;
  const cwd = process.cwd();
  const agentDir = process.env.PI_CODING_AGENT_DIR;
  const settingsManager = SettingsManager.inMemory({
    retry: { enabled: false, provider: { maxRetries: 0 } },
    compaction: { enabled: false }, cacheWarming: "off", transport: "sse",
  });
  const modelRuntime = await ModelRuntime.create({
    credentials,
    modelsPath: process.env.ZARA_PI_MODELS_PATH,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  const model = modelRuntime.getModel("openai", process.env.ZARA_PI_MODEL);
  if (!model) throw new Error("selected_model_unavailable");
  const resourceLoader = new DefaultResourceLoader({
    cwd, agentDir, settingsManager, noExtensions: true,
    additionalExtensionPaths: [process.env.ZARA_PI_EXTENSION],
    noContextFiles: true, noSkills: true, noPromptTemplates: true, noThemes: true,
    systemPromptOverride: () => process.env.ZARA_PI_SYSTEM_PROMPT,
  });
  await resourceLoader.reload();
  if (resourceLoader.getExtensions().errors.length) throw new Error("extension_load_failed");
  ({ session } = await createAgentSession({
    cwd, agentDir, modelRuntime, model, settingsManager, resourceLoader,
    sessionManager: SessionManager.inMemory(cwd),
    noTools: "builtin", tools: ["zara_change"],
  }));
  unsubscribe = session.subscribe(emit);
  await session.bindExtensions({mode: "rpc", onError: () => emit({
    type: "response", success: false, error: "pi_extension_error",
  })});
  const lines = createInterface({input: process.stdin});
  for await (const line of lines) {
    const request = JSON.parse(line);
    if (request.type !== "prompt" || typeof request.message !== "string")
      throw new Error("unsupported_launcher_command");
    await session.prompt(request.message, {expandPromptTemplates: false});
    lines.close();
    break;
  }
} catch {
  // Never serialize initialization/auth exceptions, which may hold HTTP secrets.
  emit({type: "response", success: false, error: "pi_launcher_failed"});
  process.exitCode = 1;
} finally {
  unsubscribe?.();
  session?.dispose();
}
