// Сквозная проверка Chat.jsx против ЖИВОГО бэкенда: файл, вопрос, подтверждение, история чатов, изоляция пользователей.
// Перед запуском поднимите СВЕЖИЙ бэкенд В РЕЖИМЕ MOCK (тест создаёт клиента и опирается на демо-данные):
//   cd bizagent && DB_BACKEND=mock LLM_PROVIDER=mock uvicorn app.main:app --port 8000
// Затем здесь: npm run test:e2e
import React from 'react';
import { describe, it, expect, beforeAll, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within, cleanup, waitFor } from '@testing-library/react';
import { FormData as UFormData, fetch as ufetch } from 'undici';
import { Blob as NodeBlob } from 'node:buffer';
import Chat from '../src/components/Chat.jsx';

const seen = [];
beforeAll(() => {
  // jsdom-овский FormData Node-овский fetch не понимает: перекладываем в undici FormData
  globalThis.fetch = async (url, opts = {}) => {
    let body = opts.body;
    if (body instanceof window.FormData) {
      const fd = new UFormData();
      for (const [k, v] of body.entries()) {
        if (typeof v === 'string') fd.append(k, v);
        else {
          // jsdom File -> Node Blob (в jsdom нет File.text(), но есть FileReader)
          const buf = await new Promise((res, rej) => { const r = new window.FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsArrayBuffer(v); });
          fd.append(k, new NodeBlob([new Uint8Array(buf)]), v.name);
        }
      }
      body = fd;
    }
    seen.push({ url, method: opts.method || 'GET', body: typeof opts.body === 'string' ? JSON.parse(opts.body) : null });
    return ufetch(url, { ...opts, body });
  };
  Element.prototype.scrollIntoView = () => {};
  window.confirm = () => true; // «Удалить чат?» — да
});
beforeEach(() => localStorage.setItem('auth_token', 'demo-owner-uyut'));
afterEach(cleanup);

const T = { timeout: 5000 };
const type = (text) => fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
const send = () => fireEvent.click(screen.getByText('Отправить'));
const chatItems = () => [...document.querySelectorAll('.chat-item')];

describe('Chat.jsx + живой бэкенд', () => {
  it('файл → вопрос → подтверждение; чат сохраняется в списке', async () => {
    const { container } = render(<Chat />);
    await screen.findByText('Пока нет сохранённых чатов', {}, T);

    fireEvent.change(container.querySelector('input[type=file]'), {
      target: { files: [new File(['Товар;Выручка\nПлед флисовый;39,90\n'], 'sales.csv', { type: 'text/csv' })] },
    });
    await screen.findByText(/загружен .*Файл приложится к следующему сообщению/, {}, T);
    expect(screen.getByText('📎 sales.csv ×')).toBeTruthy();

    type('Что в файле?');
    send();
    await screen.findByText(/Плед флисовый;39,90/, {}, T);
    expect(screen.getByText('🔧 read_uploaded_file')).toBeTruthy();
    expect(seen.find((r) => r.url.endsWith('/agent/chat')).body.file_ids).toHaveLength(1);

    type('создай клиента Иван Петров');
    send();
    const card = (await screen.findByText('Создать клиента «Иван Петров»', {}, T)).closest('.pend');
    const chatReqs = seen.filter((r) => r.url.endsWith('/agent/chat'));
    expect(chatReqs[1].body.conversation_id).toMatch(/^[0-9a-f]{32}$/); // второй вопрос в том же чате
    fireEvent.click(within(card).getByText('Подтвердить'));
    await screen.findByText('Готово: Создать клиента «Иван Петров»', {}, T);
    expect(within(card).getByText('Подтверждено')).toBeTruthy();

    await waitFor(() => expect(chatItems().map((e) => e.querySelector('.t').firstChild.textContent)).toEqual(['Что в файле?']));
    expect(localStorage.getItem('chat_messages')).toBeNull(); // история больше не хранится в браузере
  });

  it('при открытии показывает последний чат с сохранёнными статусами; «Новый» не стирает старый', async () => {
    render(<Chat />);
    await screen.findByText('Готово: Создать клиента «Иван Петров»', {}, T); // история пришла с сервера
    expect(screen.getByText('Подтверждено')).toBeTruthy();
    expect(screen.queryByText('Подтвердить')).toBeNull();

    fireEvent.click(screen.getByText('+ Новый'));
    expect(screen.queryByText(/Иван Петров/)).toBeNull();
    type('Какие товары заканчиваются?');
    send();
    await screen.findAllByText(/Сковорода 26 см/, {}, T);
    await waitFor(() => expect(chatItems()).toHaveLength(2));
    expect(chatItems()[0].className).toContain('on'); // новый чат сверху и активен

    fireEvent.click(chatItems()[1]); // вернулись к старому
    await screen.findByText('Готово: Создать клиента «Иван Петров»', {}, T);
    expect(screen.queryByText(/Сковорода 26 см/)).toBeNull();
  });

  it('другой пользователь не видит чужие чаты', async () => {
    localStorage.setItem('auth_token', 'demo-manager-uyut');
    render(<Chat />);
    await screen.findByText('Пока нет сохранённых чатов', {}, T);
    expect(screen.queryByText(/Иван Петров/)).toBeNull();
  });

  it('удаление чата', async () => {
    render(<Chat />);
    await waitFor(() => expect(chatItems()).toHaveLength(2), T);
    fireEvent.click(chatItems()[0].querySelector('.x'));
    await waitFor(() => expect(chatItems()).toHaveLength(1), T);
  });

  it('ошибки бэкенда показываются пользователю', async () => {
    const { container } = render(<Chat />);
    fireEvent.change(container.querySelector('input[type=file]'), { target: { files: [new File(['MZ'], 'virus.exe')] } });
    await screen.findByText(/Не удалось загрузить «virus.exe»: Формат «.exe» не поддерживается/, {}, T);
  });
});
