const state = {
  sessions: [],
  selectedSessionId: null,
  selectedConversationId: null,
  selectedLab: 'all',
  sessionFilter: '',
  eventSearch: '',
  eventPage: 1,
  pageSize: 5,
  currentEvents: [],
  selectedEventId: null,
  eventPageCount: 1,
  eventTotal: 0,
};

const sessionList = document.getElementById('sessionList');
const refreshSessionsBtn = document.getElementById('refreshSessions');
const labFilter = document.getElementById('labFilter');
const sessionTitle = document.getElementById('sessionTitle');
const sessionMeta = document.getElementById('sessionMeta');
const overviewChips = document.getElementById('overviewChips');
const labTabs = document.getElementById('labTabs');
const eventSearch = document.getElementById('eventSearch');
const pageSizeSelect = document.getElementById('pageSizeSelect');
const eventList = document.getElementById('eventList');
const eventDetailPanel = document.getElementById('eventDetailPanel');
const paginationBar = document.getElementById('paginationBar');
const paginationInfo = document.getElementById('paginationInfo');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const chatThread = document.getElementById('chatThread');
const newChatBtn = document.getElementById('newChatBtn');
const chatForm = document.getElementById('chatForm');
const messageInput = document.getElementById('messageInput');

const STORAGE_KEY = 'cyber-shell-ui-state';

function persistUiState() {
  const snapshot = {
    selectedSessionId: state.selectedSessionId,
    selectedConversationId: state.selectedConversationId,
    selectedLab: state.selectedLab,
    sessionFilter: state.sessionFilter,
    pageSize: state.pageSize,
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
    state.selectedLab = snapshot.selectedLab || 'all';
    state.sessionFilter = snapshot.sessionFilter || '';
    state.pageSize = Number(snapshot.pageSize || 12);
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

function badgeClass(lab) {
  return `badge ${lab || 'other'}`;
}

function safeHref(url) {
  const value = String(url || '').trim();
  if (/^https?:\/\//i.test(value) || /^mailto:/i.test(value)) {
    return value;
  }
  return null;
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
    const href = safeHref(url);
    if (!href) {
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

    if (/^(-{3,}|\*{3,})$/.test(block)) {
      return '<hr>';
    }

    const lines = block.split('\n');
    if (lines.every(line => /^\s*[-*+]\s+/.test(line))) {
      return `<ul>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^\s*[-*+]\s+/, ''))}</li>`).join('')}</ul>`;
    }

    if (lines.every(line => /^\s*\d+\.\s+/.test(line))) {
      return `<ol>${lines.map(line => `<li>${renderInlineMarkdown(line.replace(/^\s*\d+\.\s+/, ''))}</li>`).join('')}</ol>`;
    }

    if (lines.every(line => /^>\s?/.test(line))) {
      const inner = lines.map(line => line.replace(/^>\s?/, '')).join('\n');
      return `<blockquote>${renderMarkdown(inner)}</blockquote>`;
    }

    return `<p>${lines.map(line => renderInlineMarkdown(line)).join('<br>')}</p>`;
  };

  return blocks.map(renderBlock).join('');
}

function renderSessions() {
  const filtered = !state.sessionFilter
    ? state.sessions
    : state.sessions.filter(item => item.labs.includes(state.sessionFilter));

  if (!filtered.length) {
    sessionList.innerHTML = '<div class="empty-state">No sessions match the current filter.</div>';
    return;
  }

  sessionList.innerHTML = filtered.map(item => `
    <button class="session-card ${item.session_id === state.selectedSessionId ? 'active' : ''}" data-session-id="${escapeHtml(item.session_id)}">
      <div class="session-head">
        <div>
          <div class="session-title">${escapeHtml(item.session_id)}</div>
          <div class="session-host">${escapeHtml(item.hostname)} · ${formatDate(item.last_seen_at)}</div>
        </div>
        <span class="status-badge ${item.failed_count > 0 ? 'fail' : 'ok'}">${item.failed_count > 0 ? `${item.failed_count} fail` : 'clean'}</span>
      </div>
      <div class="badge-row mt-10">
        ${item.labs.map(lab => `<span class="${badgeClass(lab)}">${escapeHtml(lab.replace('-web', '').toUpperCase())}</span>`).join('')}
        <span class="overview-pill">${item.event_count} events</span>
        <span class="overview-pill">${item.conversation_count} chats</span>
      </div>
      <div class="conversation-preview mt-10">${escapeHtml(item.last_output_summary || 'No recent output preview.')}</div>
      ${item.top_findings && item.top_findings.length ? `<div class="finding-row mt-10">${item.top_findings.map(f => `<span class="finding">${escapeHtml(f)}</span>`).join('')}</div>` : ''}
    </button>
  `).join('');

  sessionList.querySelectorAll('.session-card').forEach(card => {
    card.addEventListener('click', () => selectSession(card.dataset.sessionId));
  });
}

async function loadSessions() {
  const query = state.sessionFilter ? `?lab=${encodeURIComponent(state.sessionFilter)}` : '';
  const res = await fetch(`/api/sessions${query}`);
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
    await Promise.all([loadOverview(), loadEvents(), loadConversations()]);
  } else {
    sessionTitle.textContent = 'Choose a session';
    sessionMeta.textContent = '';
    overviewChips.innerHTML = '';
    eventList.innerHTML = '<div class="empty-state">No session selected.</div>';
    eventDetailPanel.innerHTML = '<div class="detail-empty">Open an event to inspect the full command, metadata, and output without stretching the page.</div>';
    chatThread.innerHTML = '';
  }
}

async function selectSession(sessionId) {
  state.selectedSessionId = sessionId;
  state.selectedConversationId = null;
  state.eventPage = 1;
  state.selectedEventId = null;
  renderSessions();
  persistUiState();
  await Promise.all([loadOverview(), loadEvents(), loadConversations()]);
}

async function loadOverview() {
  if (!state.selectedSessionId) return;
  const res = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/overview`);
  const data = await res.json();
  sessionTitle.textContent = `${data.session_id} · ${data.hostname}`;
  sessionMeta.textContent = `${data.event_count} recent events · ${data.failed_count} failures · latest command: ${data.latest_command || 'n/a'}`;
  overviewChips.innerHTML = [
    ...(data.labs || []).map(item => `<span class="${badgeClass(item.lab)}">${escapeHtml(item.label)} ${item.count}</span>`),
    ...(data.findings || []).slice(0, 4).map(item => `<span class="finding">${escapeHtml(item.key)} ${item.count}</span>`),
  ].join('');
}

function eventListItem(item) {
  return `
    <button class="event-list-item ${item.id === state.selectedEventId ? 'active' : ''}" data-event-id="${item.id}">
      <div class="event-top">
        <div>
          <div class="meta-badges">
            <span class="${badgeClass(item.lab)}">${escapeHtml(item.lab_label)}</span>
            <span class="status-badge ${item.exit_code === 0 ? 'ok' : 'fail'}">exit ${item.exit_code}</span>
            <span class="overview-pill">seq ${item.seq}</span>
          </div>
          <div class="event-meta mt-8">${formatDate(item.finished_at)}</div>
        </div>
      </div>
      <div class="event-command-line">${escapeHtml(item.cmd)}</div>
      <div class="conversation-preview mt-10">${escapeHtml(item.output_summary || item.output_preview || '')}</div>
      ${Array.isArray(item.findings) && item.findings.length ? `<div class="finding-row mt-10">${item.findings.map(f => `<span class="finding">${escapeHtml(f)}</span>`).join('')}</div>` : ''}
    </button>
  `;
}

function renderEventDetail(item) {
  const metadata = item.metadata && Object.keys(item.metadata).length
    ? `<pre>${escapeHtml(JSON.stringify(item.metadata, null, 2))}</pre>`
    : '<div class="detail-empty small">No metadata attached to this event.</div>';

  eventDetailPanel.innerHTML = `
    <div class="detail-header">
      <div>
        <div class="meta-badges">
          <span class="${badgeClass(item.lab)}">${escapeHtml(item.lab_label)}</span>
          <span class="status-badge ${item.exit_code === 0 ? 'ok' : 'fail'}">exit ${item.exit_code}</span>
          <span class="overview-pill">seq ${item.seq}</span>
          <span class="overview-pill">${escapeHtml(item.shell || 'shell')}</span>
        </div>
        <div class="event-meta mt-8">${formatDate(item.finished_at)} · ${escapeHtml(item.cwd || '')}</div>
      </div>
    </div>

    <div class="command-block mt-12">
      <div class="block-label">Command</div>
      <pre>${escapeHtml(item.cmd)}</pre>
    </div>

    <div class="command-block mt-12">
      <div class="block-label">Full output</div>
      <pre>${escapeHtml(item.output_full || item.output_preview || '')}</pre>
    </div>

    <div class="command-block mt-12">
      <div class="block-label">Metadata</div>
      ${metadata}
    </div>
  `;
}

async function openEvent(eventId) {
  if (!eventId) return;
  state.selectedEventId = Number(eventId);
  renderEvents(state.currentEvents);
  eventDetailPanel.innerHTML = '<div class="detail-empty">Loading event detail…</div>';
  const res = await fetch(`/api/events/${eventId}`);
  const data = await res.json();
  if (!res.ok) {
    eventDetailPanel.innerHTML = `<div class="detail-empty">${escapeHtml(data.error || 'Failed to load event detail.')}</div>`;
    return;
  }
  renderEventDetail(data);
}

function renderEvents(events) {
  if (!events.length) {
    eventList.innerHTML = '<div class="empty-state">No events match the current filters.</div>';
    eventDetailPanel.innerHTML = '<div class="detail-empty">No event detail to show for the current filters.</div>';
    return;
  }

  eventList.innerHTML = events.map(eventListItem).join('');
  eventList.querySelectorAll('.event-list-item').forEach(button => {
    button.addEventListener('click', () => openEvent(button.dataset.eventId).catch(showChatError));
  });
}

function updatePagination() {
  paginationInfo.textContent = `Page ${state.eventPage} / ${state.eventPageCount} · ${state.eventTotal} events`;
  prevPageBtn.disabled = state.eventPage <= 1;
  nextPageBtn.disabled = state.eventPage >= state.eventPageCount;
}

async function loadEvents() {
  if (!state.selectedSessionId) return;
  const params = new URLSearchParams({
    page: String(state.eventPage),
    page_size: String(state.pageSize),
  });
  if (state.selectedLab && state.selectedLab !== 'all') params.set('lab', state.selectedLab);
  if (state.eventSearch) params.set('search', state.eventSearch);
  const res = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/events?${params.toString()}`);
  const data = await res.json();
  state.currentEvents = Array.isArray(data.items) ? data.items : [];
  state.eventPage = data.page || 1;
  state.eventPageCount = data.page_count || 1;
  state.eventTotal = data.total || 0;
  updatePagination();

  if (state.currentEvents.length) {
    const availableIds = state.currentEvents.map(item => item.id);
    if (!state.selectedEventId || !availableIds.includes(state.selectedEventId)) {
      state.selectedEventId = state.currentEvents[0].id;
    }
    renderEvents(state.currentEvents);
    await openEvent(state.selectedEventId);
  } else {
    state.selectedEventId = null;
    renderEvents([]);
  }
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
    const bodyHtml = msg.role === 'assistant'
      ? renderMarkdown(msg.body)
      : escapeHtml(msg.body);
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

refreshSessionsBtn.addEventListener('click', () => {
  loadSessions().catch(showChatError);
});

labFilter.addEventListener('change', () => {
  state.sessionFilter = labFilter.value;
  persistUiState();
  loadSessions().catch(showChatError);
});

labTabs.querySelectorAll('.chip').forEach(button => {
  button.addEventListener('click', () => {
    state.selectedLab = button.dataset.lab;
    state.eventPage = 1;
    persistUiState();
    labTabs.querySelectorAll('.chip').forEach(item => item.classList.toggle('active', item === button));
    loadEvents().catch(showChatError);
  });
});

eventSearch.addEventListener('input', () => {
  state.eventSearch = eventSearch.value.trim();
  state.eventPage = 1;
  loadEvents().catch(showChatError);
});

pageSizeSelect.addEventListener('change', () => {
  state.pageSize = Number(pageSizeSelect.value || 5);
  state.eventPage = 1;
  persistUiState();
  loadEvents().catch(showChatError);
});

prevPageBtn.addEventListener('click', () => {
  if (state.eventPage <= 1) return;
  state.eventPage -= 1;
  loadEvents().catch(showChatError);
});

nextPageBtn.addEventListener('click', () => {
  if (state.eventPage >= state.eventPageCount) return;
  state.eventPage += 1;
  loadEvents().catch(showChatError);
});

newChatBtn.addEventListener('click', async () => {
  if (!state.selectedSessionId) return;
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

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || !state.selectedSessionId) {
    return;
  }

  if (!state.selectedConversationId) {
    const createRes = await fetch(`/api/sessions/${encodeURIComponent(state.selectedSessionId)}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: message }),
    });
    const createData = await createRes.json();
    state.selectedConversationId = createData.id;
    persistUiState();
  }

  chatThread.insertAdjacentHTML('beforeend', `
    <article class="message user">
      <div class="message-top"><strong>You</strong><span class="message-time">now</span></div>
      <div class="message-body plain-body">${escapeHtml(message)}</div>
    </article>
  `);
  chatThread.scrollTop = chatThread.scrollHeight;
  messageInput.value = '';

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
    showChatError(`Error: ${data.error || 'unknown error'}`);
    return;
  }

  state.selectedConversationId = data.conversation_id || state.selectedConversationId;
  persistUiState();
  await loadConversationMessages();
});

restoreUiState();
labFilter.value = state.sessionFilter;
pageSizeSelect.value = String(state.pageSize);
const activeChip = labTabs.querySelector(`[data-lab="${state.selectedLab}"]`);
if (activeChip) {
  labTabs.querySelectorAll('.chip').forEach(item => item.classList.toggle('active', item === activeChip));
}

loadSessions().catch(showChatError);
