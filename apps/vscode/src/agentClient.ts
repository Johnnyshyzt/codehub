import * as vscode from "vscode";
import * as http from "http";
import * as https from "https";
import { URL } from "url";
import { ClientRequest } from "http";

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

export class AgentCancelledError extends Error {
  constructor(message = "Cancelled by user") {
    super(message);
    this.name = "AgentCancelledError";
  }
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
  private activeRequest: ClientRequest | undefined;
  private activeReject: ((err: Error) => void) | undefined;

  constructor(private getBaseUrl: () => string) {}

  async health(): Promise<{ ok: boolean; providers: string[] }> {
    return requestJson("GET", `${this.getBaseUrl()}/health`, undefined, 5_000);
  }

  cancel(): void {
    const reject = this.activeReject;
    const req = this.activeRequest;
    this.activeRequest = undefined;
    this.activeReject = undefined;
    if (req) {
      req.destroy();
    }
    if (reject) {
      reject(new AgentCancelledError());
    }
  }

  get isRunning(): boolean {
    return !!this.activeRequest;
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
    } catch (err) {
      if (err instanceof AgentCancelledError) {
        throw err;
      }
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
      let settled = false;
      const settleReject = (err: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        this.activeRequest = undefined;
        this.activeReject = undefined;
        reject(err);
      };
      const settleResolve = (result: RunResult) => {
        if (settled) {
          return;
        }
        settled = true;
        this.activeRequest = undefined;
        this.activeReject = undefined;
        resolve(result);
      };

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
              settleReject(
                new Error(Buffer.concat(chunks).toString("utf8") || `HTTP ${res.statusCode}`)
              );
            });
            return;
          }

          let buffer = "";
          let eventName = "message";
          let dataLines: string[] = [];

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
                settleResolve(payloadObj as unknown as RunResult);
              } else if (type === "error") {
                if (payloadObj.cancelled) {
                  settleReject(new AgentCancelledError(String(payloadObj.message || "Cancelled")));
                } else {
                  settleReject(new Error(String(payloadObj.message || "Agent error")));
                }
              } else {
                options.onEvent?.(type, payloadObj);
              }
            } catch (err) {
              settleReject(err instanceof Error ? err : new Error(String(err)));
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
              settleReject(new Error("Stream ended without result"));
            }
          });
        }
      );

      this.activeRequest = req;
      this.activeReject = settleReject;

      req.on("error", (err) => {
        if (settled) {
          return;
        }
        // Destroyed by cancel() often surfaces as an error.
        if (this.activeReject === settleReject) {
          settleReject(
            err.message.includes("socket") || err.message.includes("aborted")
              ? new AgentCancelledError()
              : err
          );
        }
      });
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

export function hasAnyApiKeyConfigured(): boolean {
  return Object.keys(collectApiKeys()).length > 0;
}
