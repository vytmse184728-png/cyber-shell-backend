const PREVIEW_CHAR_LIMIT = 1200;
const PREVIEW_LINE_LIMIT = 18;

const state = {
  sessions: [],
  selectedSessionId: null,
  selectedConversationId: null,
  timelineItems: [],
  nextCursor: null,
  hasMoreOlder: true,
  isLoadingOlder: false,
  isInitialTimelineLoading: false,
  isChatLoading: false,
  socket: null,
  subscribedSessionId: null,
  expandedEventId: null,
};

const sessionList = document.getElementById('sessionList');
const refreshSessionsBtn = document.getElementById('refreshSessions');
const sessionSummary = document.getElementById('sessionSummary');
const sessionTitle = document.getElementById('sessionTitle');
const sessionMeta = document.getElementById('sessionMeta');
const eventStream = document.getElementById('eventStream');
const eventStreamItems = document.getElementById('eventStreamItems');
const streamTopLoader = document.getElementById('streamTopLoader');
const chatThread = document.getElementById('chatThread');
const newChatBtn = document.getElementById('newChatBtn');
const chatForm = document.getElementById('chatForm');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const sendButtonLabel = document.getElementById('sendButtonLabel');
const chatLoadingNote = document.getElementById('chatLoadingNote');
const eventModal = document.getElementById('eventModal');
const closeEventModalBtn = document.getElementById('closeEventModal');
const eventModalMeta = document.getElementById('eventModalMeta');
const eventModalCommand = document.getElementById('eventModalCommand');
const eventModalOutput = document.getElementById('eventModalOutput');

const STORAGE_KEY = 'cyber-shell-ui-state-v2';
const PENDING_MESSAGE_ID = 'pendingAssistantMessage';

function persistUiState() {
  const snapshot = {
    selectedSessionId: state.selectedSessionId,
    selectedConversationId: state.selectedConversationId,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}

function restoreUiState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const snapshot = JSON.parse(raw);
    state.selectedSessionId = snapshot.selectedSessionId || null;
    state.selectedConversationId = snapshot.selectedConversationId || null;
  } catch (_err) {
    // ignore broken local state
  }
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDate(isoString) {
  if (!isoString) return 'Unknown time';
  const date = new Date(isoString);
  return Number.isNaN(date.getTime()) ? isoString : date.toLocaleString();
}

function formatRelativeTime(isoString) {
  if (!isoString) return 'Unknown';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  const diffMs = date.getTime() - Date.now();
  const absMs = Math.abs(diffMs);
  const units = [
    ['day', 24 * 60 * 60 * 1000],
    ['hour', 60 * 60 * 1000],
    ['minute', 60 * 1000],
    ['second', 1000],
  ];
  for (const [unit, ms] of units) {
    if (absMs >= ms || unit === 'second') {
      const value = Math.round(diffMs / ms);
      if (typeof Intl !== 'undefined' && typeof Intl.RelativeTimeFormat === 'function') {
        return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(value, unit);
      }
      return value < 0 ? `${Math.abs(value)} ${unit}${Math.abs(value) === 1 ? '' : 's'} ago` : `in ${value} ${unit}${value === 1 ? '' : 's'}`;
    }
  }
  return formatDate(isoString);
}

function renderInlineMarkdown(value) {
  let text = escapeHtml(value || '');
  const codeTokens = [];

  text = text.replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@INLINE_CODE_${codeTokens.length}@@`;
    codeTokens.push(`<code>${code}</code>`);
    return token;
  });

  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    const href = String(url || '').trim();
    if (!/^https?:\/\//i.test(href) && !/^mailto:/i.test(href)) {
      return `${label} (${escapeHtml(url)})`;
    }
    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  codeTokens.forEach((token, index) => {
    text = text.replace(`@@INLINE_CODE_${index}@@`, token);
  });

  return text;
}

function renderMarkdown(markdown) {
  const source = String(markdown || '').replace(/\r\n?/g, '\n').trim();
  if (!source) return '';

  const codeBlocks = [];
  const withPlaceholders = source.replace(/```([a-zA-Z0-9_-]+)?\n?([\s\S]*?)```/g, (_, lang = '', code = '') => {
    const languageAttr = lang ? ` data-language="${escapeHtml(lang)}"` : '';
    const html = `<pre class="md-code"><code${languageAttr}>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`;
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`;
    codeBlocks.push(html);
    return token;
  });

  const blocks = withPlaceholders.split(/\n\s*\n/).map(block => block.trim()).filter(Boolean);

  const renderBlock = (block) => {
    const codeMatch = block.match(/^@@CODE_BLOCK_(\d+)@@$/);
    if (codeMatch) {
      return codeBlocks[Number(codeMatch[1])] || '';
    }
    const headingMatch = block.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      return `<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`;
    }
    const lines = block.split('\n');
    if (lines.every(line => /^\s*[-*+]\s+/.test(line))) {
      return `<ul>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^\s*[-*+]\s+/, ''))}</li>`).join('')}</ul>`;
    }
    if (lines.every(line => /^\s*\d+\.\s+/.test(line))) {
      return `<ol>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^\s*\d+\.\s+/, ''))}</li>`).join('')}</ol>`;
    }
    return `<p>${lines.map(line => renderInlineMarkdown(line)).join('<br>')}</p>`;
  };

  return blocks.map(renderBlock).join('');
}

function isLongContent(value) {
  const text = String(value || '');
  if (!text) return false;
  return text.length > PREVIEW_CHAR_LIMIT || text.split('\n').length > PREVIEW_LINE_LIMIT;
}

function truncateContent(value) {
  const text = String(value || '');
  if (!text) return '';

  const lines = text.split('\n');
  let truncated = lines.slice(0, PREVIEW_LINE_LIMIT).join('\n');
  if (truncated.length > PREVIEW_CHAR_LIMIT) {
    truncated = truncated.slice(0, PREVIEW_CHAR_LIMIT);
  }
  truncated = truncated.trimEnd();

  if (truncated.length < text.length) {
    truncated += '\n...';
  }
  return truncated;
}

function previewContent(value) {
  return isLongContent(value) ? truncateContent(value) : String(value || '');
}

function inferPromptSymbol(item) {
  const cwd = String(item?.cwd || '').trim().toLowerCase();
  const cmd = String(item?.cmd || '').trim().toLowerCase();
  if (cwd.startsWith('/root') || cmd.startsWith('sudo ')) {
    return '#';
  }
  return '$';
}

function renderPromptLine(item, commandText) {
  const promptSymbol = inferPromptSymbol(item);
  return `
    <div class="timeline-command-line" title="${escapeHtml(String(item.cmd || ''))}">
      <span class="timeline-command-prompt">${promptSymbol}</span>
      <span class="timeline-command-text">${escapeHtml(commandText)}</span>
    </div>
  `;
}

function getEventById(eventId) {
  return state.timelineItems.find(item => String(item.id) === String(eventId)) || null;
}

function openEventModal(eventId) {
  const item = getEventById(eventId);
  if (!item || !eventModal) return;

  state.expandedEventId = item.id;
  eventModalMeta.textContent = `${formatDate(item.finished_at)} · seq ${item.seq} · exit ${item.exit_code}`;
  eventModalCommand.innerHTML = renderPromptLine(item, String(item.cmd || ''));
  eventModalOutput.textContent = String(item.output || '');
  eventModal.classList.remove('hidden');
  eventModal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
}

function closeEventModal() {
  if (!eventModal) return;
  state.expandedEventId = null;
  eventModal.classList.add('hidden');
  eventModal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
}

function renderSessions() {
  if (sessionSummary) {
    sessionSummary.textContent = `${state.sessions.length} session${state.sessions.length === 1 ? '' : 's'}`;
  }

  if (!state.sessions.length) {
    sessionList.innerHTML = '<div class="empty-state">No sessions found.</div>';
    return;
  }

  sessionList.innerHTML = state.sessions.map(item => {
    const isFailed = Number(item.failed_count || 0) > 0;
    const fullDate = formatDate(item.last_seen_at);
    const relativeDate = formatRelativeTime(item.last_seen_at);
    const statusBadge = isFailed
      ? `<span class="session-status-text fail">${item.failed_count} fail</span>`
      : '';
    return `
      <button class="session-card ${item.session_id === state.selectedSessionId ? 'active' : ''}" data-session-id="${escapeHtml(item.session_id)}" title="${escapeHtml(item.session_id)} · ${escapeHtml(fullDate)}">
        <div class="session-compact-top">
          <div class="session-title-wrap">
            <span class="session-title">${escapeHtml(item.session_id)}</span>
          </div>
          ${statusBadge}
        </div>
        <div class="session-compact-meta">
          <span class="session-host">${escapeHtml(item.hostname || 'Unknown host')}</span>
          <span class="session-updated" title="${escapeHtml(fullDate)}">${escapeHtml(relativeDate)}</span>
        </div>
        <div class="session-compact-footer">
          <span class="session-stats">${Number(item.event_count || 0)} events</span>
        </div>
      </button>
    `;
  }).join('');

  sessionList.querySelectorAll('.session-card').forEach(card => {
    card.addEventListener('click', () => selectSession(card.dataset.sessionId));
  });
}

async function loadSessions() {
  const res = await fetch('/api/sessions');
  state.sessions = await res.json();

  if (!state.selectedSessionId && state.sessions.length) {
    state.selectedSessionId = state.sessions[0].session_id;
  }
  if (state.selectedSessionId && !state.sessions.some(item => item.session_id === state.selectedSessionId)) {
    state.selectedSessionId = state.sessions[0]?.session_id || null;
  }

  renderSessions();
  persistUiState();

  if (state.selectedSessionId) {
    await Promise.all([loadTimeline(true), loadConversations()]);
  } else {
    sessionTitle.textContent = 'Choose a session';
    sessionMeta.textContent = '';
    eventStreamItems.innerHTML = '<div class="empty-state">No session selected.</div>';
    chatThread.innerHTML = '';
  }
}

async function selectSession(sessionId) {
  if (!sessionId || sessionId === state.selectedSessionId) return;
  state.selectedSessionId = sessionId;
  renderSessions();
  subscribeToSelectedSession();
  await Promise.all([loadTimeline(true), loadConversations()]);
}

function resetTimelineState() {
  state.timelineItems = [];
  state.nextCursor = null;
  state.hasMoreOlder = true;
  state.isLoadingOlder = false;
}

function timelineEventItem(item) {
  const metadataJson = item.metadata && Object.keys(item.metadata).length
    ? `<pre class="timeline-meta-block">${escapeHtml(JSON.stringify(item.metadata, null, 2))}</pre>`
    : '<div class="timeline-meta-block timeline-meta-empty">No metadata</div>';
  const hasLongContent = isLongContent(item.cmd) || isLongContent(item.output);
  const previewCommand = previewContent(item.cmd || '');
  const previewOutput = previewContent(item.output || '');

  return `
    <article class="timeline-event" data-event-id="${item.id}">
      <div class="timeline-event-top">
        <div>
          <div class="timeline-event-time">${escapeHtml(formatDate(item.finished_at))}</div>
          <div class="timeline-event-sub">seq ${escapeHtml(item.seq)} · exit ${escapeHtml(item.exit_code)} · ${escapeHtml(item.cwd || '')}</div>
        </div>
      </div>
      ${renderPromptLine(item, previewCommand)}
      <pre class="timeline-output">${escapeHtml(previewOutput)}</pre>
      ${hasLongContent ? `
        <div class="timeline-actions">
          <button type="button" class="secondary event-expand-btn" data-event-id="${item.id}">View more</button>
        </div>
      ` : ''}
      <details class="timeline-details">
        <summary>Metadata</summary>
        ${metadataJson}
      </details>
    </article>
  `;
}

function renderTimeline() {
  if (!state.timelineItems.length) {
    eventStreamItems.innerHTML = '<div class="empty-state">No events found for this session.</div>';
    return;
  }
  eventStreamItems.innerHTML = state.timelineItems.map(timelineEventItem).join('');
}

function prependTimelineItems(items) {
  if (!Array.isArray(items) || !items.length) return;
  const known = new Set(state.timelineItems.map(item => item.id));
  const fresh = items.filter(item => !known.has(item.id));
  if (!fresh.length) return;
  state.timelineItems = [...fresh, ...state.timelineItems];
  renderTimeline();
}

function appendTimelineItems(items) {
  if (!Array.isArray(items) || !items.length) return;
  const known = new Set(state.timelineItems.map(item => item.id));
  const fresh = items.filter(item => !known.has(item.id));
  if (!fresh.length) return;
  state.timelineItems = [...state.timelineItems, ...fresh];
  renderTimeline();
}

function isNearBottom(container) {
  return container.scrollHeight - (container.scrollTop + container.clientHeight) < 120;
}

async function loadTimeline(initial = false) {
  if (!state.selectedSessionId) return;

  if (initial) {
    resetTimelineState();
    state.isInitialTimelineLoading = true;
    eventStreamItems.innerHTML = '<div class="empty-state">Loading latest events…</div>';
    sessionTitle.textContent = state.selectedSessionId;
    const selected = state.sessions.find(item => item.session_id === state.selectedSessionId);
    sessionMeta.textContent = selected
      ? `${selected.hostname || 'Unknown host'} · ${selected.event_count || 0} events · ${selected.failed_count || 0} failures`
      : '';
  }

  const params = new URLSearchParams({ limit: '20' });
  if (!initial && state.nextCursor) {
    params.set('before_finished_at', state.nextCursor.before_finished_at);
    params.set('before_id', String(state.nextCursor.before_id));
  }

  const res = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/events?${params.toString()}`);
  const data = await res.json();

  if (initial) {
    state.timelineItems = Array.isArray(data.items) ? data.items : [];
    state.nextCursor = data.next_cursor;
    state.hasMoreOlder = Boolean(data.has_more);
    renderTimeline();
    requestAnimationFrame(() => {
      eventStream.scrollTop = eventStream.scrollHeight;
    });
    subscribeToSelectedSession();
    state.isInitialTimelineLoading = false;
    return;
  }

  prependTimelineItems(data.items || []);
  state.nextCursor = data.next_cursor;
  state.hasMoreOlder = Boolean(data.has_more);
}

async function loadOlderEvents() {
  if (!state.selectedSessionId || !state.hasMoreOlder || state.isLoadingOlder) return;
  state.isLoadingOlder = true;
  streamTopLoader.classList.remove('hidden');
  const previousHeight = eventStream.scrollHeight;
  await loadTimeline(false);
  requestAnimationFrame(() => {
    const newHeight = eventStream.scrollHeight;
    eventStream.scrollTop += newHeight - previousHeight;
    streamTopLoader.classList.add('hidden');
    state.isLoadingOlder = false;
  });
}

function renderMessages(messages) {
  if (!messages.length) {
    chatThread.innerHTML = '<div class="empty-state">This conversation is empty.</div>';
    return;
  }
  chatThread.innerHTML = messages.map(msg => {
    const tools = Array.isArray(msg.tool_trace) && msg.tool_trace.length
      ? `<div class="message-tools">Tools: ${escapeHtml(msg.tool_trace.map(item => item.tool).join(', '))}</div>`
      : '';
    const bodyHtml = msg.role === 'assistant' ? renderMarkdown(msg.body) : escapeHtml(msg.body);
    const bodyClass = msg.role === 'assistant' ? 'message-body markdown-body' : 'message-body plain-body';
    return `
      <article class="message ${msg.role}">
        <div class="message-top">
          <strong>${msg.role === 'user' ? 'You' : 'Assistant'}</strong>
          <span class="message-time">${formatDate(msg.created_at)}</span>
        </div>
        <div class="${bodyClass}">${bodyHtml}</div>
        ${tools}
      </article>
    `;
  }).join('');
  chatThread.scrollTop = chatThread.scrollHeight;
}

async function loadConversations() {
  if (!state.selectedSessionId) return;
  const res = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/conversations`);
  const conversations = await res.json();

  if (!Array.isArray(conversations) || !conversations.length) {
    state.selectedConversationId = null;
    chatThread.innerHTML = '<div class="empty-state">Ask a question to start the first chat.</div>';
    persistUiState();
    return;
  }

  if (!state.selectedConversationId || !conversations.some(item => item.id === state.selectedConversationId)) {
    state.selectedConversationId = conversations[0].id;
    persistUiState();
  }

  await loadConversationMessages();
}

async function loadConversationMessages() {
  if (!state.selectedConversationId) {
    chatThread.innerHTML = '<div class="empty-state">Ask about the selected session.</div>';
    return;
  }
  const res = await fetch(`/api/conversations/${state.selectedConversationId}/messages`);
  const data = await res.json();
  renderMessages(data.messages || []);
}

function showChatError(error) {
  chatThread.innerHTML = `<div class="empty-state">${escapeHtml(String(error))}</div>`;
}

function setChatLoading(isLoading) {
  state.isChatLoading = isLoading;
  chatForm.classList.toggle('loading', isLoading);
  sendButton.disabled = isLoading;
  newChatBtn.disabled = isLoading;
  messageInput.disabled = isLoading;
  sendButtonLabel.textContent = isLoading ? 'Thinking…' : 'Send';
  chatLoadingNote.textContent = isLoading ? 'Assistant is working…' : '';
}

function appendPendingAssistant() {
  removePendingAssistant();
  chatThread.insertAdjacentHTML('beforeend', `
    <article class="message assistant pending" id="${PENDING_MESSAGE_ID}">
      <div class="message-top"><strong>Assistant</strong><span class="message-time">now</span></div>
      <div class="typing-indicator" aria-label="Assistant is thinking">
        <span></span><span></span><span></span>
      </div>
    </article>
  `);
  chatThread.scrollTop = chatThread.scrollHeight;
}

function removePendingAssistant() {
  const pending = document.getElementById(PENDING_MESSAGE_ID);
  if (pending) pending.remove();
}

function appendAssistantError(message) {
  removePendingAssistant();
  chatThread.insertAdjacentHTML('beforeend', `
    <article class="message assistant error">
      <div class="message-top"><strong>Assistant</strong><span class="message-time">now</span></div>
      <div class="message-body plain-body">${escapeHtml(message)}</div>
    </article>
  `);
  chatThread.scrollTop = chatThread.scrollHeight;
}

function upsertSessionCard(payload) {
  const index = state.sessions.findIndex(item => item.session_id === payload.session_id);
  if (index >= 0) {
    state.sessions[index] = { ...state.sessions[index], ...payload };
  } else {
    state.sessions.unshift(payload);
  }
  state.sessions.sort((a, b) => new Date(b.last_seen_at || 0).getTime() - new Date(a.last_seen_at || 0).getTime());
}

function initSocket() {
  if (typeof io === 'undefined') {
    console.error('Socket.IO client not loaded');
    return;
  }

  state.socket = io({
    transports: ['websocket', 'polling'],
    reconnection: true,
  });

  state.socket.on('connect', () => {
    console.log('socket connected', state.socket.id);
    subscribeToSelectedSession();
  });

  state.socket.on('connect_error', (err) => {
    console.error('socket connect_error', err);
  });

  state.socket.on('terminal_event', (payload) => {
    if (!payload || payload.session_id !== state.selectedSessionId || !payload.event) {
      return;
    }

    const shouldStick = isNearBottom(eventStream);
    appendTimelineItems([payload.event]);

    if (shouldStick) {
      requestAnimationFrame(() => {
        eventStream.scrollTop = eventStream.scrollHeight;
      });
    }
  });

  state.socket.on('session_updated', (payload) => {
    if (!payload || !payload.session_id) return;
    upsertSessionCard(payload);
    renderSessions();
  });
}

function subscribeToSelectedSession() {
  if (!state.socket) return;
  if (state.subscribedSessionId && state.subscribedSessionId !== state.selectedSessionId) {
    state.socket.emit('unsubscribe_session', { session_id: state.subscribedSessionId });
  }
  if (state.selectedSessionId) {
    state.socket.emit('subscribe_session', { session_id: state.selectedSessionId });
  }
  state.subscribedSessionId = state.selectedSessionId;
}

refreshSessionsBtn.addEventListener('click', () => {
  loadSessions().catch(showChatError);
});

eventStream.addEventListener('scroll', () => {
  if (eventStream.scrollTop < 120) {
    loadOlderEvents().catch(showChatError);
  }
});

eventStreamItems.addEventListener('click', (event) => {
  const expandButton = event.target.closest('.event-expand-btn');
  if (!expandButton) return;
  openEventModal(expandButton.dataset.eventId);
});

if (eventModal) {
  eventModal.addEventListener('click', (event) => {
    if (event.target.matches('[data-modal-close="true"]')) {
      closeEventModal();
    }
  });
}

if (closeEventModalBtn) {
  closeEventModalBtn.addEventListener('click', closeEventModal);
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && eventModal && !eventModal.classList.contains('hidden')) {
    closeEventModal();
  }
});

newChatBtn.addEventListener('click', async () => {
  if (!state.selectedSessionId || state.isChatLoading) return;
  const res = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'New chat' }),
  });
  const data = await res.json();
  state.selectedConversationId = data.id;
  persistUiState();
  await loadConversationMessages();
  messageInput.focus();
});

messageInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  if (typeof chatForm.requestSubmit === 'function') {
    chatForm.requestSubmit();
  } else {
    chatForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
});

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || !state.selectedSessionId || state.isChatLoading) {
    return;
  }

  chatThread.insertAdjacentHTML('beforeend', `
    <article class="message user">
      <div class="message-top"><strong>You</strong><span class="message-time">now</span></div>
      <div class="message-body plain-body">${escapeHtml(message)}</div>
    </article>
  `);
  chatThread.scrollTop = chatThread.scrollHeight;
  messageInput.value = '';
  appendPendingAssistant();
  setChatLoading(true);

  try {
    if (!state.selectedConversationId) {
      const createRes = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: message }),
      });
      const createData = await createRes.json();
      if (!createRes.ok) {
        throw new Error(createData.error || 'failed to create conversation');
      }
      state.selectedConversationId = createData.id;
      persistUiState();
    }

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: state.selectedSessionId,
        conversation_id: state.selectedConversationId,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'unknown error');
    }

    state.selectedConversationId = data.conversation_id || state.selectedConversationId;
    persistUiState();
    await loadConversationMessages();
  } catch (error) {
    appendAssistantError(`Error: ${error.message || String(error)}`);
  } finally {
    setChatLoading(false);
    removePendingAssistant();
    messageInput.focus();
  }
});

restoreUiState();
initSocket();
loadSessions().catch(showChatError);
