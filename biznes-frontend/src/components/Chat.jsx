import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = 'http://localhost:8000';
const ACCEPT = '.txt,.md,.csv,.xlsx,.docx,.pdf';
const MAX_MB = 10; // совпадает с MAX_FILE_BYTES на бэкенде (app/files.py)
const MAX_FILES = 5; // совпадает с ChatIn.file_ids (app/main.py)

function authHeaders(json = true) {
  const token = localStorage.getItem('auth_token');
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Бэкенд отдаёт ошибки как {"detail": "...", "code": "..."}; у ошибок валидации detail — список
async function errorText(response) {
  try {
    const d = await response.json();
    if (typeof d?.detail === 'string') return d.detail;
    if (Array.isArray(d?.detail)) return 'Неверный запрос: ' + d.detail.map((e) => e.msg).join('; ');
  } catch { /* нет тела */ }
  return `Ошибка сервера: ${response.status}`;
}

async function api(path, opts = {}) {
  const response = await fetch(`${API}${path}`, { ...opts, headers: authHeaders(!(opts.body instanceof FormData)) });
  if (!response.ok) {
    const err = new Error(await errorText(response));
    err.status = response.status;
    throw err;
  }
  return response.json();
}

const timeRu = (iso) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
const dateRu = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString()
    ? timeRu(iso)
    : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
};

const STATUS_TEXT = {
  confirmed: 'Подтверждено',
  rejected: 'Отклонено',
  expired: 'Время подтверждения истекло',
  failed: 'Не выполнено',
  error: 'Не выполнено',
  busy: 'Отправка…',
};

// Сообщение с сервера (display) → сообщение для отрисовки
const fromServer = (m) => ({
  role: m.role,
  content: m.content,
  files: m.files || [],
  isError: !!m.error,
  trace: (m.trace || []).map((t) => (t.ok === false ? `${t.tool} ✗` : t.tool)),
  pending_actions: m.pending_actions || [],
});

export default function Chat({ initial, clear }) {
  // История чатов хранится на сервере у каждого пользователя своя, в браузере ничего не храним
  const [chats, setChats] = useState([]); // [{id, title, updated_at}]
  const [activeId, setActiveId] = useState(null); // null — новый чат, ещё не отправлен
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [contextCategory, setContextCategory] = useState('Все');
  const [uploadedFile, setUploadedFile] = useState(null);
  // Загруженные файлы, которые приложатся к следующему сообщению: [{file_id, filename}]
  const [attachments, setAttachments] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const msgsRef = useRef(null);

  const push = (msg) => setMessages((prev) => [...prev, msg]);

  // Прокручиваем только окно сообщений, а не всю страницу
  useEffect(() => {
    const el = msgsRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const loadChats = async () => {
    try {
      const list = await api('/agent/conversations');
      setChats(list);
      return list;
    } catch {
      return [];
    }
  };

  const openChat = async (id) => {
    if (loading || opening) return;
    setOpening(true);
    try {
      const data = await api(`/agent/conversations/${id}`);
      setActiveId(id);
      setMessages(data.messages.map(fromServer));
      setAttachments([]);
    } catch (error) {
      push({ role: 'assistant', content: `Не удалось открыть чат: ${error.message}`, isError: true });
      if (error.status === 404) loadChats();
    } finally {
      setOpening(false);
    }
  };

  const newChat = () => {
    if (loading) return;
    setActiveId(null);
    setMessages([]);
    setAttachments([]);
    setUploadedFile(null);
  };

  const deleteChat = async (chat) => {
    if (!window.confirm(`Удалить чат «${chat.title}»? Восстановить его будет нельзя.`)) return;
    try {
      await api(`/agent/conversations/${chat.id}`, { method: 'DELETE' });
      if (chat.id === activeId) newChat();
    } catch (error) {
      push({ role: 'assistant', content: `Не удалось удалить чат: ${error.message}`, isError: true });
    }
    loadChats();
  };

  useEffect(() => {
    // Раньше история жила в localStorage и была общей для всех пользователей браузера: убираем её
    localStorage.removeItem('chat_messages');
    localStorage.removeItem('chat_conversation_id');
    (async () => {
      const list = await loadChats();
      if (initial) {
        // Вопрос с дашборда всегда начинает новый чат
        sendMessage(initial);
        if (clear) clear();
      } else if (list.length) {
        openChat(list[0].id);
      }
    })();
  }, []);

  const sendMessage = async (textToSend) => {
    const typed = textToSend ?? input;
    const text = typed.trim() || (attachments.length ? 'Посмотри приложенный файл' : '');
    if (!text || loading || uploading || opening) return;

    const files = attachments;
    push({ role: 'user', content: text, files: files.map((f) => f.filename) });
    if (textToSend === undefined) setInput('');
    setAttachments([]);
    setLoading(true);

    const post = (convId) =>
      api('/agent/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, conversation_id: convId, file_ids: files.map((f) => f.file_id) }),
      });

    try {
      let data;
      try {
        data = await post(activeId);
      } catch (error) {
        // Чат удалили в другой вкладке: продолжаем в новом
        if (!(error.status === 404 && activeId && error.message.startsWith('Диалог'))) throw error;
        data = await post(null);
      }
      setActiveId(data.conversation_id);
      push(fromServer({ role: 'assistant', content: data.message || 'Ответ получен без содержимого.', trace: data.trace, pending_actions: data.pending_actions }));
      loadChats();
    } catch (error) {
      setAttachments(files); // файлы не потерялись: их можно отправить ещё раз
      push({ role: 'assistant', content: `Ошибка при отправке запроса: ${error.message}`, isError: true });
    } finally {
      setLoading(false);
    }
  };

  const uploadFile = async (file) => {
    if (!file || uploading) return;
    if (attachments.length >= MAX_FILES) {
      push({ role: 'assistant', content: `К одному сообщению можно приложить не больше ${MAX_FILES} файлов.`, isError: true });
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      push({ role: 'assistant', content: `Файл «${file.name}» больше ${MAX_MB} МБ.`, isError: true });
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', contextCategory);

    try {
      const data = await api('/agent/upload', { method: 'POST', body: formData });
      setUploadedFile(data.filename);
      setAttachments((prev) => [...prev, { file_id: data.file_id, filename: data.filename }]);
      push({ role: 'assistant', content: `${data.message} Файл приложится к следующему сообщению.` });
    } catch (error) {
      push({ role: 'assistant', content: `Не удалось загрузить «${file.name}»: ${error.message}`, isError: true });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = ''; // чтобы тот же файл можно было выбрать снова
    }
  };

  const setActionStatus = (msgIdx, actionId, status) =>
    setMessages((prev) =>
      prev.map((m, i) =>
        i !== msgIdx ? m : { ...m, pending_actions: m.pending_actions.map((a) => (a.id === actionId ? { ...a, status } : a)) }
      )
    );

  // kind: 'confirm' | 'reject' → POST /agent/actions/{id}/confirm|reject
  const handleAction = async (msgIdx, action, kind) => {
    if (action.status !== 'pending') return;
    setActionStatus(msgIdx, action.id, 'busy');
    try {
      const data = await api(`/agent/actions/${action.id}/${kind}`, { method: 'POST' });
      setActionStatus(msgIdx, action.id, kind === 'confirm' ? 'confirmed' : 'rejected');
      push({ role: 'assistant', content: data.message });
    } catch (error) {
      // 409 — уже обработано, 410 — истекло, 422 — не выполнилось (например, не хватило товара)
      setActionStatus(msgIdx, action.id, error.status === 410 ? 'expired' : 'error');
      push({ role: 'assistant', content: `Не удалось: ${error.message}`, isError: true });
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    uploadFile(e.dataTransfer.files?.[0]);
  };

  return (
    <section className="on">
      <h1>ИИ-ассистент</h1>
      <p className="sub">Данные только из инструментов, записи только после вашего подтверждения</p>

      <div className="chat">
        <div className="card chat-main">
          <div className="msgs" ref={msgsRef}>
            {opening && <div className="src">Загрузка чата…</div>}

            {!opening && messages.length === 0 && (
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <div className="chip" onClick={() => sendMessage('Почему упала выручка в сентябре?')} style={{ cursor: 'pointer' }}>
                  Почему упала выручка в сентябре?
                </div>
              </div>
            )}

            {messages.map((m, idx) => (
              <div key={idx} className={`m ${m.role === 'user' ? 'me' : ''}`} style={m.isError ? { color: 'var(--bad)' } : undefined}>
                {m.role === 'assistant' && !m.isError ? (
                  // Ответ модели в markdown. Сырой HTML react-markdown не выполняет: это безопасно
                  <div className="md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                )}

                {m.files && m.files.length > 0 && <div className="src">📎 {m.files.join(', ')}</div>}

                {m.trace && m.trace.length > 0 && <div className="src">🔧 {m.trace.join(' · ')}</div>}

                {m.pending_actions?.map((a) => (
                  <div className="pend" key={a.id}>
                    <b>{a.summary}</b>
                    <div className="src">
                      {a.status === 'pending' ? `Ожидает подтверждения до ${timeRu(a.expires_at)}` : STATUS_TEXT[a.status]}
                    </div>
                    {a.status === 'pending' && (
                      <div className="row">
                        <button className="btn" onClick={() => handleAction(idx, a, 'confirm')}>
                          Подтвердить
                        </button>
                        <button className="btn ghost" onClick={() => handleAction(idx, a, 'reject')}>
                          Отклонить
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
            {loading && <div className="m">Ассистент думает...</div>}
          </div>

          {attachments.length > 0 && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '14px' }}>
              {attachments.map((f) => (
                <span
                  key={f.file_id}
                  className="chip"
                  title="Не прикладывать к сообщению"
                  onClick={() => setAttachments((prev) => prev.filter((x) => x.file_id !== f.file_id))}
                >
                  📎 {f.filename} ×
                </span>
              ))}
            </div>
          )}

          <div className="box" style={{ marginTop: '14px' }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={attachments.length ? 'Что сделать с файлом?' : 'Напишите сообщение…'}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            />
            <button className="btn" onClick={() => sendMessage()} disabled={loading || uploading || opening}>
              Отправить
            </button>
          </div>
        </div>

        <div className="chat-side">
          <div className="card side chats-card">
            <div className="head">
              <h2>Чаты</h2>
              <button className="btn ghost" onClick={newChat} disabled={loading}>
                + Новый
              </button>
            </div>
            <div className="chats">
              {chats.length === 0 && <div className="src">Пока нет сохранённых чатов</div>}
              {chats.map((c) => (
                <div
                  key={c.id}
                  className={`chat-item ${c.id === activeId ? 'on' : ''}`}
                  onClick={() => c.id !== activeId && openChat(c.id)}
                  title={c.title}
                >
                  <div className="t">
                    {c.title}
                    <div className="d">{dateRu(c.updated_at)}</div>
                  </div>
                  <button
                    className="x"
                    title="Удалить чат"
                    onClick={(e) => { e.stopPropagation(); deleteChat(c); }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="card side">
            <h2>Контекст</h2>
            <label>Категория</label>
            <select className="f" value={contextCategory} onChange={(e) => setContextCategory(e.target.value)}>
              <option>Все</option>
              <option>Налоги</option>
              <option>Продажи</option>
              <option>Право</option>
              <option>Склад</option>
            </select>
            <label>Файл</label>

            <input
              type="file"
              accept={ACCEPT}
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={(e) => uploadFile(e.target.files[0])}
            />

            <div
              className="drop"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              style={{ cursor: 'pointer', ...(dragOver ? { borderColor: 'var(--acc)' } : {}) }}
            >
              {uploading ? 'Загрузка…' : uploadedFile ? `Загружено: ${uploadedFile}` : 'Перетащите устав, отчёт или бизнес-план'}
            </div>
            <div className="src">txt, csv, xlsx, docx, pdf · до {MAX_MB} МБ</div>
          </div>
        </div>
      </div>
    </section>
  );
}
