import * as vscode from "vscode";
import * as http from "http";
import * as https from "https";
import { URL } from "url";

export interface FileChange {
  path: string;
  action: "created" | "modified" | string;
  before?: string | null;
  after?: string | null;
}

export interface RunResult {
  content: string;
  provider: string;
  model: string;
  steps: number;
  tool_calls: number;
  usage_total_tokens: number;
  events: Array<Record<string, unknown>>;
  file_changes: FileChange[];
}

export interface EditorFileContext {
  path: string;
  content?: string;
  selection?: string;
  language?: string;
}

export interface WorkspaceContextPayload {
  active_file?: EditorFileContext;
  open_files?: EditorFileContext[];
  max_depth?: number;
}

export interface RunOptions {
  prompt: string;
  workspace: string;
  maxSteps: number;
  apiKeys: Record<string, string>;
  context?: WorkspaceContextPayload;
  onEvent?: (type: string, payload: Record<string, unknown>) => void;
}

function requestJson<T>(
  method: string,
  urlStr: string,
  body?: unknown,
  timeoutMs = 600_000
): Promise<T> {
  const url = new URL(urlStr);
  const lib = url.protocol === "https:" ? https : http;
  const payload = body === undefined ? undefined : JSON.stringify(body);

  return new Promise((resolve, reject) => {
    const req = lib.request(
      {
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method,
        headers: {
          "Content-Type": "application/json",
          ...(payload ? { "Content-Length": Buffer.byteLength(payload) } : {}),
        },
        timeout: timeoutMs,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if ((res.statusCode || 500) >= 400) {
            let detail = text;
            try {
              const parsed = JSON.parse(text) as { detail?: string };
              if (parsed.detail) {
                detail = parsed.detail;
              }
            } catch {
              /* keep raw */
            }
            reject(new Error(detail || `HTTP ${res.statusCode}`));
            return;
          }
          try {
            resolve(JSON.parse(text) as T);
          } catch (err) {
            reject(err);
          }
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out"));
    });
    if (payload) {
      req.write(payload);
    }
    req.end();
  });
}

export class AgentClient {
  constructor(private getBaseUrl: () => string) {}

  async health(): Promise<{ ok: boolean; providers: string[] }> {
    return requestJson("GET", `${this.getBaseUrl()}/health`, undefined, 5_000);
  }

  async run(options: RunOptions): Promise<RunResult> {
    const body = {
      prompt: options.prompt,
      workspace: options.workspace,
      max_steps: options.maxSteps,
      task_type: "coding",
      api_keys: options.apiKeys,
      context: options.context,
    };
    // Prefer streaming endpoint; fall back to blocking /v1/run.
    try {
      return await this.runStream(options, body);
    } catch {
      return requestJson<RunResult>("POST", `${this.getBaseUrl()}/v1/run`, body);
    }
  }

  private runStream(
    options: RunOptions,
    body: Record<string, unknown>
  ): Promise<RunResult> {
    const url = new URL(`${this.getBaseUrl()}/v1/run/stream`);
    const lib = url.protocol === "https:" ? https : http;
    const payload = JSON.stringify(body);

    return new Promise((resolve, reject) => {
      const req = lib.request(
        {
          protocol: url.protocol,
          hostname: url.hostname,
          port: url.port,
          path: url.pathname,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            "Content-Length": Buffer.byteLength(payload),
          },
          timeout: 600_000,
        },
        (res) => {
          if ((res.statusCode || 500) >= 400) {
            const chunks: Buffer[] = [];
            res.on("data", (c) => chunks.push(c));
            res.on("end", () => {
              reject(new Error(Buffer.concat(chunks).toString("utf8") || `HTTP ${res.statusCode}`));
            });
            return;
          }

          let buffer = "";
          let eventName = "message";
          let dataLines: string[] = [];
          let settled = false;

          const flush = () => {
            if (!dataLines.length) {
              return;
            }
            const data = dataLines.join("\n");
            dataLines = [];
            const type = eventName;
            eventName = "message";
            try {
              const payloadObj = JSON.parse(data) as Record<string, unknown>;
              if (type === "done") {
                settled = true;
                resolve(payloadObj as unknown as RunResult);
              } else if (type === "error") {
                settled = true;
                reject(new Error(String(payloadObj.message || "Agent error")));
              } else {
                options.onEvent?.(type, payloadObj);
              }
            } catch (err) {
              if (!settled) {
                settled = true;
                reject(err);
              }
            }
          };

          res.on("data", (chunk: Buffer) => {
            buffer += chunk.toString("utf8");
            const parts = buffer.split(/\r?\n/);
            buffer = parts.pop() || "";
            for (const line of parts) {
              if (line.startsWith("event:")) {
                eventName = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                dataLines.push(line.slice(5).trimStart());
              } else if (line === "") {
                flush();
              }
            }
          });
          res.on("end", () => {
            flush();
            if (!settled) {
              reject(new Error("Stream ended without result"));
            }
          });
        }
      );
      req.on("error", reject);
      req.write(payload);
      req.end();
    });
  }
}

export function collectApiKeys(): Record<string, string> {
  const cfg = vscode.workspace.getConfiguration("codehub");
  const keys: Record<string, string> = {};
  const deepseek = cfg.get<string>("deepseekApiKey")?.trim();
  const qwen = cfg.get<string>("qwenApiKey")?.trim();
  const glm = cfg.get<string>("glmApiKey")?.trim();
  const kimi = cfg.get<string>("kimiApiKey")?.trim();
  if (deepseek) {
    keys.DEEPSEEK_API_KEY = deepseek;
  }
  if (qwen) {
    keys.DASHSCOPE_API_KEY = qwen;
  }
  if (glm) {
    keys.ZHIPU_API_KEY = glm;
  }
  if (kimi) {
    keys.MOONSHOT_API_KEY = kimi;
  }
  return keys;
}
