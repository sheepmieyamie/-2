const BASE = "/api";

export interface Account {
  id: number;
  user_id: string;
  nickname: string;
  avatar: string;
  bio: string;
  follower_count: number;
  note_count: number;
  style_summary: string;
  updated_at: string | null;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  compliance: "pass" | "warning" | "fail";
  risk_level: string;
  compliance_report?: {
    issue_count: number;
    layer1_forbidden: { word: string }[];
    layer2_limit: { word: string; replacement?: string }[];
    layer3_amateur: { word: string; suggestion: string }[];
  };
}

export async function fetchAccounts(): Promise<Account[]> {
  const res = await fetch(`${BASE}/accounts`);
  if (!res.ok) throw new Error("获取账号列表失败");
  return res.json();
}

export async function addAccount(shareText: string, noteLimit = 20) {
  const res = await fetch(`${BASE}/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ share_text: shareText, note_limit: noteLimit }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "添加对标账号失败");
  }
  return res.json();
}

export async function deleteAccount(id: number) {
  const res = await fetch(`${BASE}/accounts/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("删除失败");
  return res.json();
}

export async function getAccountDetail(id: number) {
  const res = await fetch(`${BASE}/accounts/${id}`);
  if (!res.ok) throw new Error("获取账号详情失败");
  return res.json();
}

export async function sendChat(
  message: string,
  sessionId: string,
  accountId: number | null
): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      account_id: accountId,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "AI 生成失败");
  }
  return res.json();
}

export async function checkForbidden(text: string) {
  const res = await fetch(`${BASE}/check-forbidden`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json();
}
