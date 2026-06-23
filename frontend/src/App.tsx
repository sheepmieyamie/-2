import { useEffect, useRef, useState } from "react";
import {
  Account,
  addAccount,
  deleteAccount,
  fetchAccounts,
  getAccountDetail,
  sendChat,
} from "./api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
  compliance?: string;
  riskLevel?: string;
}

export default function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [styleDetail, setStyleDetail] = useState<Record<string, unknown> | null>(null);
  const [shareInput, setShareInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const data = await fetchAccounts();
      setAccounts(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setStyleDetail(null);
      return;
    }
    getAccountDetail(selectedId).then((d) => setStyleDetail(d.style_profile));
  }, [selectedId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleAdd = async () => {
    if (!shareInput.trim()) return;
    setAdding(true);
    try {
      await addAccount(shareInput.trim());
      setShareInput("");
      await loadAccounts();
    } catch (e) {
      alert(e instanceof Error ? e.message : "添加失败");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除该对标账号？")) return;
    await deleteAccount(id);
    if (selectedId === id) setSelectedId(null);
    await loadAccounts();
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);

    try {
      const res = await sendChat(userMsg, sessionId, selectedId);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.reply,
          compliance: res.compliance,
          riskLevel: res.risk_level,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ ${e instanceof Error ? e.message : "生成失败"}`,
        },
      ]);
    }
  };

  const selected = accounts.find((a) => a.id === selectedId);

  return (
    <div className="app">
      <header className="header">
        <div className="logo">📕 小红书内容库</div>
        <p className="subtitle">对标账号分析 · AI 仿写文案 · 违禁词合规检测</p>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <section className="panel">
            <h2>添加对标账号</h2>
            <p className="hint">粘贴小红书主页分享链接或笔记链接</p>
            <textarea
              value={shareInput}
              onChange={(e) => setShareInput(e.target.value)}
              placeholder="例：https://xhslink.com/m/xxxxx 或 @用户名 分享文本"
              rows={3}
            />
            <button className="btn primary" onClick={handleAdd} disabled={adding}>
              {adding ? "抓取分析中…" : "抓取并分析"}
            </button>
          </section>

          <section className="panel">
            <h2>对标账号库 {loading && "…"}</h2>
            {accounts.length === 0 ? (
              <p className="empty">暂无对标账号，请先添加</p>
            ) : (
              <ul className="account-list">
                {accounts.map((a) => (
                  <li
                    key={a.id}
                    className={selectedId === a.id ? "active" : ""}
                    onClick={() => setSelectedId(a.id)}
                  >
                    <div className="account-row">
                      {a.avatar && <img src={a.avatar} alt="" className="avatar" />}
                      <div className="account-info">
                        <strong>{a.nickname || a.user_id}</strong>
                        <span>{a.follower_count.toLocaleString()} 粉丝 · {a.note_count} 笔记</span>
                      </div>
                      <button
                        className="btn-icon"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(a.id);
                        }}
                        title="删除"
                      >
                        ×
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {styleDetail && (
            <section className="panel style-panel">
              <h2>账号特征</h2>
              <p className="style-summary">{(styleDetail.summary as string) || ""}</p>
              {Array.isArray(styleDetail.writing_style_hints) && (
                <ul className="hints">
                  {(styleDetail.writing_style_hints as string[]).map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              )}
              {styleDetail.top_hashtags && (
                <div className="tags">
                  {(styleDetail.top_hashtags as string[]).slice(0, 8).map((t) => (
                    <span key={t} className="tag">#{t}</span>
                  ))}
                </div>
              )}
            </section>
          )}
        </aside>

        <main className="chat-area">
          <div className="chat-header">
            {selected ? (
              <span>正在模仿：<strong>{selected.nickname}</strong> 的风格</span>
            ) : (
              <span>未选择对标账号（将使用通用小红书风格）</span>
            )}
          </div>

          <div className="messages">
            {messages.length === 0 && (
              <div className="welcome">
                <h3>👋 开始创作</h3>
                <p>选择左侧对标账号后，告诉我你想写什么主题的笔记。</p>
                <div className="examples">
                  <button onClick={() => setInput("帮我写一篇夏季防晒好物推荐的笔记")}>
                    夏季防晒好物推荐
                  </button>
                  <button onClick={() => setInput("写一篇职场穿搭干货，目标人群是25-30岁白领")}>
                    职场穿搭干货
                  </button>
                  <button onClick={() => setInput("模仿对标账号风格，写一篇探店文案")}>
                    探店文案
                  </button>
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`message ${m.role}`}>
                <div className="bubble">
                  <pre>{m.content}</pre>
                  {m.compliance && (
                    <span className={`badge ${m.compliance}`}>
                      {m.compliance === "pass"
                        ? `✓ ${m.riskLevel || "可发布"}`
                        : m.compliance === "fail"
                          ? `✗ ${m.riskLevel || "高危"}`
                          : `⚠ ${m.riskLevel || "需调整"}`}
                    </span>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="input-area">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="描述你想写的笔记主题、产品、目标人群…"
              rows={2}
            />
            <button className="btn primary send" onClick={handleSend} disabled={!input.trim()}>
              生成文案
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}
