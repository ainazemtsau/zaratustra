// Native Pi callback: principal and generation are supplied by the trusted host.
export default function (pi: any) {
  pi.registerTool({
    name: "zara_change", label: "Zaratustra change", executionMode: "sequential",
    description: "Apply bounded subject changes through the current core connection.",
    parameters: {type: "object", properties: {intent_json: {type: "string"}}, required: ["intent_json"], additionalProperties: false},
    async execute(callId: string, params: any) {
      const response = await fetch(process.env.ZARA_NEXT_TOOL_ENDPOINT!, {
        method: "POST", headers: {"Content-Type": "application/json", "Authorization": `Bearer ${process.env.ZARA_NEXT_TOOL_TOKEN}`},
        body: JSON.stringify({native_id: callId, intent: JSON.parse(params.intent_json)})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(result));
      return {content: [{type: "text", text: JSON.stringify(result)}], details: result};
    }
  });
}
