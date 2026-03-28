import { anthropic } from "@ai-sdk/anthropic";
import { frontendTools } from "@assistant-ui/react-ai-sdk";
import {
  JSONSchema7,
  streamText,
  stepCountIs,
  convertToModelMessages,
  type UIMessage,
} from "ai";
import { z } from "zod";

// Server-side: use direct backend URL (no browser proxy needed)
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8080";

const SYSTEM = `You are the Signal intelligence assistant — a CEO-facing tool that answers
questions about customer signal trends processed by the Signal Agent.

You have access to a searchSignals tool that queries the knowledge base where all
processed customer signals are stored. Use it to answer questions about:
- Recurring bugs or issues
- Top feature requests
- Churn risks
- Customer sentiment trends
- What actions have been taken automatically

Always search before answering questions about customer data. Be concise and action-oriented.
Lead with the key insight, then supporting details. If a search returns no results, say so.`;

const searchSchema = z.object({
  query: z
    .string()
    .describe("Search query — e.g. 'export bug', 'churn risk', 'feature requests'"),
});

export async function POST(req: Request) {
  const {
    messages,
    system,
    tools: clientTools,
  }: {
    messages: UIMessage[];
    system?: string;
    tools?: Record<string, { description?: string; parameters: JSONSchema7 }>;
  } = await req.json();

  const result = streamText({
    model: anthropic("claude-sonnet-4-5"),
    messages: await convertToModelMessages(messages),
    system: system ?? SYSTEM,
    stopWhen: stepCountIs(3),
    tools: {
      ...frontendTools(clientTools ?? {}),
      searchSignals: {
        description:
          "Search the knowledge base for customer signals. Use this to answer questions about bugs, feature requests, churn risks, and trends.",
        inputSchema: searchSchema,
        execute: async (input: z.infer<typeof searchSchema>) => {
          try {
            const res = await fetch(
              `${BACKEND_URL}/search?q=${encodeURIComponent(input.query)}`,
            );
            if (!res.ok)
              return { error: `Search failed: ${res.statusText}`, results: [] };
            return await res.json();
          } catch (err) {
            return { error: `Backend unreachable: ${err}`, results: [], frequency: 0 };
          }
        },
      },
    },
  });

  return result.toUIMessageStreamResponse();
}
