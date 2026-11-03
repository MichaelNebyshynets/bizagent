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

// Названия инструментов агента → понятные пользователю подписи «Смотрел: …»
const TOOL_RU = {
  get_sales_summary: 'сводка продаж', compare_periods: 'сравнение периодов', get_top_products: 'топ товаров',
  get_product_sales_history: 'история продаж товара', find_product: 'каталог товаров', list_low_stock: 'остатки склада',
  list_slow_movers: 'залежавшиеся товары', find_client: 'клиенты', get_profit_summary: 'прибыль',
  search_knowledge_base: 'база знаний', list_uploaded_files: 'загруженные файлы', read_uploaded_file: 'приложенный файл',
  create_client: 'создание клиента', create_order: 'создание заказа', record_expense: 'запись расхода',
};
const toolRu = (t) => {
  const failed = t.endsWith(' ✗');
  const name = failed ? t.slice(0, -2) : t;
  return (TOOL_RU[name] || name) + (failed ? ' (ошибка)' : '');
};

const EXAMPLES = [
  ['Разобраться в цифрах', 'Продажи, склад, клиенты', ['Почему упала выручка в сентябре?', 'Что заканчивается на складе?']],
  ['Внести запись', 'Клиент, заказ, расход. Только после вашего подтверждения', ['Создай клиента Мария Ковальчук, телефон +375 29 123-45-67', 'Запиши расход на аренду 1200 BYN']],
  ['Вопрос по законам РБ', 'Ответ со ссылкой на документ', ['Какую форму налогообложения выбрать?', 'Какие взносы платит ИП в ФСЗН?']],
];

export default function Chat({ initial, clear, company, onEvent }) {
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
      onEvent?.('ask');
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
      onEvent?.('upload');
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

  const busy = loading || uploading || opening;
  const autoGrow = (el) => { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; };

  return (
    <section>
      {company && (
        <div className="crumbs">{company} / Ассистент</div>
      )}
      <div className="page-head">
        <div>
          <h1>Ассистент</h1>
          <p>Отвечает по данным вашей компании и документам базы знаний. Записи вносит только после вашего подтверждения.</p>
        </div>
      </div>

      <div className="panel chat">
        <div className="chat-list">
          <div className="panel-head">
            <h2>Чаты</h2>
            <button className="btn sm secondary" onClick={newChat} disabled={loading}>+ Новый</button>
          </div>
          <div className="chat-items">
            {chats.length === 0 && <div className="small muted" style={{ padding: '8px 10px' }}>Пока нет сохранённых чатов</div>}
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
                  aria-label={`Удалить чат «${c.title}»`}
                  onClick={(e) => { e.stopPropagation(); deleteChat(c); }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>

        <div
          className={`conv ${dragOver ? 'drag' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false); }}
          onDrop={onDrop}
        >
          <div className="msgs" ref={msgsRef}>
            {opening && <div className="typing">Загрузка чата…</div>}

            {!opening && messages.length === 0 && (
              <div className="empty">
                <h2>С чем помочь?</h2>
                <p className="muted">Напишите вопрос или выберите пример. Файл можно перетащить прямо сюда.</p>
                <div className="modes">
                  {EXAMPLES.map(([title, sub, qs]) => (
                    <div className="mode" key={title}>
                      <h3>{title}</h3>
                      <p>{sub}</p>
                      {qs.map((q) => <button key={q} className="chip" onClick={() => sendMessage(q)} disabled={busy}>{q}</button>)}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, idx) => (
              <div key={idx} className={`m ${m.role === 'user' ? 'me' : ''} ${m.isError ? 'err' : ''}`}>
                {m.role === 'assistant' && (
                  <div className="who"><span className="brand-mark">Б</span>Ассистент</div>
                )}
                {m.role === 'assistant' && !m.isError ? (
                  // Ответ модели в markdown. Сырой HTML react-markdown не выполняет: это безопасно
                  <div className="md body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="body" style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                )}
                {m.files && m.files.length > 0 && <div className="src">Файлы: {m.files.join(', ')}</div>}
                {m.trace && m.trace.length > 0 && <div className="src">Смотрел: {m.trace.map(toolRu).join(', ')}</div>}
                {m.pending_actions?.map((a) => (
                  <div className={`pend ${a.status === 'confirmed' ? 'done' : a.status === 'pending' || a.status === 'busy' ? '' : 'off'}`} key={a.id}>
                    <b>{a.summary}</b>
                    <div className="meta">
                      {a.status === 'pending'
                        ? `В учёт ничего не попадёт, пока вы не подтвердите. Действует до ${timeRu(a.expires_at)}.`
                        : STATUS_TEXT[a.status]}
                    </div>
                    {a.status === 'pending' && (
                      <div className="actions">
                        <button className="btn sm" onClick={() => handleAction(idx, a, 'confirm')}>Подтвердить</button>
                        <button className="btn sm secondary" onClick={() => handleAction(idx, a, 'reject')}>Отклонить</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
            {loading && <div className="typing">Ассистент считает по вашим данным…</div>}
            {uploading && <div className="typing">Загружаем файл…</div>}
          </div>

          <div className="composer">
            {attachments.length > 0 && (
              <div className="attach-row">
                {attachments.map((f) => (
                  <button
                    key={f.file_id}
                    className="chip"
                    title="Не прикладывать к сообщению"
                    onClick={() => setAttachments((prev) => prev.filter((x) => x.file_id !== f.file_id))}
                  >
                    {f.filename} ✕
                  </button>
                ))}
              </div>
            )}

            <form className="comp-box" onSubmit={(e) => { e.preventDefault(); sendMessage(); }}>
              <input
                type="file"
                accept={ACCEPT}
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={(e) => uploadFile(e.target.files[0])}
              />
              <button
                type="button"
                className="btn ghost icon"
                title="Приложить файл"
                aria-label="Приложить файл"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7" /></svg>
              </button>
              <select
                value={contextCategory}
                onChange={(e) => setContextCategory(e.target.value)}
                title="Категория файла"
                aria-label="Категория файла"
              >
                <option>Все</option>
                <option>Налоги</option>
                <option>Продажи</option>
                <option>Право</option>
                <option>Склад</option>
              </select>
              <textarea
                rows={1}
                value={input}
                onChange={(e) => { setInput(e.target.value); autoGrow(e.target); }}
                placeholder={attachments.length ? 'Что сделать с файлом?' : 'Напишите вопрос'}
                aria-label="Сообщение"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
                }}
              />
              <button type="submit" className="btn" disabled={busy}>Отправить</button>
            </form>
            <div className="comp-hint">
              <span>Enter — отправить, Shift+Enter — новая строка</span>
              <span>{uploadedFile ? `Последний файл: ${uploadedFile}` : `Файлы: txt, csv, xlsx, docx, pdf до ${MAX_MB} МБ, не больше ${MAX_FILES}`}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
