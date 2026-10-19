import { pathToFileURL } from "node:url";
const { DefaultResourceLoader, SettingsManager } = await import(
  pathToFileURL(process.env.ZARA_PI_SDK).href
);
const agentDir = process.env.PI_CODING_AGENT_DIR;
const cwd = process.cwd();
const settingsManager = SettingsManager.create(cwd, agentDir);
const loader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
await loader.reload();
const extensions = loader.getExtensions();
console.log(
  JSON.stringify(
    {
      errors: extensions.errors,
      extensions: extensions.extensions.map((e) => ({
        path: e.path,
        tools: [...e.tools.keys()],
      })),
      skills: loader.getSkills().skills.map((s) => s.name),
    },
    null,
    2,
  ),
);
