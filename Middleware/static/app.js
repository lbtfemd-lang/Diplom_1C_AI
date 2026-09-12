// 1C:Enterprise 8.5 Authentic Client Logic - Full Backend Sync
let authToken = sessionStorage.getItem('v8_auth_token') || null;
let currentUser = null;
try {
  currentUser = JSON.parse(sessionStorage.getItem('v8_user') || 'null');
} catch (e) {
  currentUser = null;
}

let currentTab = 'chat';
let isVoiceRecording = false;
let speechRecognizer = null;
let currentTheme = localStorage.getItem('v8_theme') || 'light';
let kanbanData = { todo: [], in_progress: [], review: [], done: [] };

// 1. Theme Management (1C 8.5 Light <-> 1C 8.5 Dark)
function applyTheme(theme) {
  currentTheme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  document.body.className = theme === 'dark' ? 'theme-dark' : 'theme-light';
  localStorage.setItem('v8_theme', theme);

  const iconSlot = document.getElementById('themeIconSlot');
  const label = document.getElementById('themeLabel');
  if (iconSlot && label) {
    if (theme === 'dark') {
      iconSlot.innerHTML = `
        <svg class="v8-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
        </svg>`;
      label.textContent = '1С 8.5 (Светлая)';
    } else {
      iconSlot.innerHTML = `
        <svg class="v8-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
        </svg>`;
      label.textContent = '1С 8.5 (Тёмная)';
    }
  }
}

function toggleTheme() {
  const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
  applyTheme(nextTheme);
}

// 2. Discrete Step-by-Step Scenario Pagination (Mobile)
function scrollScenarioPage(direction) {
  const el = document.getElementById('scenarioStrip');
  if (!el) return;
  const step = el.clientWidth;
  el.scrollBy({ left: direction * step, behavior: 'smooth' });
}

// 3. Mobile Drawer Navigation
function toggleMobileSidebar() {
  const sidebar = document.getElementById('taxiSidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (sidebar && backdrop) {
    const isOpen = sidebar.classList.toggle('open');
    backdrop.classList.toggle('open', isOpen);
  }
}

function closeMobileSidebar() {
  const sidebar = document.getElementById('taxiSidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  if (sidebar && backdrop) {
    sidebar.classList.remove('open');
    backdrop.classList.remove('open');
  }
}

// Toast Notifications
function show1CToast(message, isError = false) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `v8-toast ${isError ? 'error' : 'success'}`;
  toast.onclick = () => switchTab('kanban');
  toast.innerHTML = `
    <div class="v8-toast-icon">
      ${isError ? '✕' : '✓'}
    </div>
    <div style="flex:1;">
      <strong>1С:Уведомление</strong><br>
      <span>${escapeHtml(message)}</span>
    </div>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(12px)';
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// Startup
document.addEventListener('DOMContentLoaded', async () => {
  applyTheme(currentTheme);

  const isValid = await checkCurrentSession();
  if (!isValid) {
    // If no active valid session, auto-login as director for immediate ease or prompt
    openLoginModal(false);
  } else {
    updateUserPillUI();
    applyRolePermissions();
    await loadKanbanBoard();
    initGreetingMessage();
    setupSpeechRecognition();
  }

  const hashTab = (window.location.hash || '').replace('#', '').toLowerCase();
  if (['kanban', 'analytics', 'business', 'system', 'chat'].includes(hashTab)) {
    switchTab(hashTab);
  }

  window.addEventListener('hashchange', () => {
    const h = (window.location.hash || '').replace('#', '').toLowerCase();
    if (['kanban', 'analytics', 'business', 'system', 'chat'].includes(h)) {
      switchTab(h);
    }
  });

  // Background monitor refresh every 30s
  setInterval(() => {
    if (currentTab === 'analytics' && currentUser && ['director', 'cfo', 'admin'].includes(currentUser.role)) {
      loadFinancialMonitor();
    }
  }, 30000);
});

// Authentication & Session Management
async function checkCurrentSession() {
  if (!authToken) return false;
  try {
    const res = await fetch('/auth/me', {
      headers: { 'Authorization': `Bearer ${authToken}`, 'X-Auth-Token': authToken }
    });
    if (res.ok) {
      currentUser = await res.json();
      sessionStorage.setItem('v8_user', JSON.stringify(currentUser));
      return true;
    }
  } catch (e) {
    console.warn('Session verification error:', e);
  }
  return false;
}

function openLoginModal(canCancel = false) {
  const modal = document.getElementById('loginModal');
  const closeBtn = modal?.querySelector('.v8-dialog-titlebar button');
  const cancelBtn = modal?.querySelector('.v8-dialog-actions button:last-child');
  if (closeBtn) closeBtn.style.display = canCancel ? 'inline-flex' : 'none';
  if (cancelBtn) cancelBtn.style.display = canCancel ? 'inline-block' : 'none';
  if (modal) modal.style.display = 'flex';
  const err = document.getElementById('loginErrorMsg');
  if (err) err.style.display = 'none';
}

function closeLoginModal() {
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.display = 'none';
}

function quickFillLogin(username, password) {
  const u = document.getElementById('loginUsername');
  const p = document.getElementById('loginPassword');
  if (u) u.value = username;
  if (p) p.value = password;
  const f = document.getElementById('loginForm');
  if (f) {
    if (typeof f.requestSubmit === 'function') {
      f.requestSubmit();
    } else {
      handleLoginSubmit(new Event('submit'));
    }
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const username = document.getElementById('loginUsername')?.value.trim();
  const password = document.getElementById('loginPassword')?.value;
  const errBox = document.getElementById('loginErrorMsg');
  const submitBtn = document.getElementById('loginSubmitBtn');

  if (!username || !password) return;
  if (submitBtn) submitBtn.disabled = true;
  if (errBox) errBox.style.display = 'none';

  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Неверное имя пользователя или пароль');
    }
    const data = await res.json();
    authToken = data.access_token;
    currentUser = data.user;
    sessionStorage.setItem('v8_auth_token', authToken);
    sessionStorage.setItem('v8_user', JSON.stringify(currentUser));

    updateUserPillUI();
    applyRolePermissions();
    closeLoginModal();
    show1CToast(`Вы вошли как ${currentUser.full_name} (${currentUser.role})`);

    // Reload active tab or switch to requested hash tab
    const hashTab = (window.location.hash || '').replace('#', '').toLowerCase();
    if (['kanban', 'analytics', 'business', 'system', 'chat'].includes(hashTab)) {
      switchTab(hashTab);
    } else if (currentTab === 'analytics') {
      loadFinancialMonitor();
    } else if (currentTab === 'kanban') {
      loadKanbanBoard();
    }
  } catch (err) {
    if (errBox) {
      errBox.textContent = err.message;
      errBox.style.display = 'block';
    }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function updateUserPillUI() {
  if (!currentUser) return;
  const nameLabel = document.getElementById('userNameLabel');
  const roleBadge = document.getElementById('userRoleBadge');
  const avatar = document.getElementById('userAvatar');
  const ddFullName = document.getElementById('dropdownFullName');
  const ddDept = document.getElementById('dropdownDept');

  const shortName = currentUser.full_name.split(' ').slice(0, 2).join(' ') || currentUser.username;
  if (nameLabel) nameLabel.textContent = shortName;
  if (roleBadge) roleBadge.textContent = currentUser.role;
  if (avatar) avatar.textContent = (currentUser.full_name[0] || currentUser.username[0] || 'U').toUpperCase();
  if (ddFullName) ddFullName.textContent = currentUser.full_name;
  if (ddDept) ddDept.textContent = `${currentUser.department_name || 'Подразделение'} (${currentUser.role})`;
}

function applyRolePermissions() {
  if (!currentUser) return;
  const role = currentUser.role;
  const isExecutive = ['director', 'cfo', 'admin'].includes(role);

  const tabAnalytics = document.getElementById('tabAnalytics');
  if (tabAnalytics) {
    if (!isExecutive) {
      tabAnalytics.style.opacity = '0.5';
      tabAnalytics.title = 'Доступно только Директору и CFO';
    } else {
      tabAnalytics.style.opacity = '1.0';
      tabAnalytics.title = '';
    }
  }
}

function toggleUserDropdown() {
  const dd = document.getElementById('userDropdown');
  if (!dd) return;
  dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
}

function logout() {
  authToken = null;
  currentUser = null;
  sessionStorage.removeItem('v8_auth_token');
  sessionStorage.removeItem('v8_user');
  const dd = document.getElementById('userDropdown');
  if (dd) dd.style.display = 'none';
  openLoginModal(false);
}

// Close dropdown when clicking outside
window.addEventListener('click', (e) => {
  const container = document.getElementById('userPillContainer');
  const dd = document.getElementById('userDropdown');
  if (dd && container && !container.contains(e.target)) {
    dd.style.display = 'none';
  }
});

// 4. Open Tabs Navigation (NO CROSSES)
function switchTab(tabKey) {
  currentTab = tabKey;
  closeMobileSidebar();
  if (history.replaceState && window.location.hash !== '#' + tabKey) {
    history.replaceState(null, null, '#' + tabKey);
  }
  document.querySelectorAll('.v8-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.v8-view').forEach(v => v.classList.remove('active'));

  if (tabKey === 'chat') {
    document.getElementById('tabChat')?.classList.add('active');
    document.getElementById('viewChat')?.classList.add('active');
  } else if (tabKey === 'kanban') {
    document.getElementById('tabKanban')?.classList.add('active');
    document.getElementById('viewKanban')?.classList.add('active');
    loadKanbanBoard();
  } else if (tabKey === 'analytics') {
    document.getElementById('tabAnalytics')?.classList.add('active');
    document.getElementById('viewAnalytics')?.classList.add('active');
    loadFinancialMonitor();
  } else if (tabKey === 'business') {
    document.getElementById('tabBusiness')?.classList.add('active');
    document.getElementById('viewBusiness')?.classList.add('active');
  } else if (tabKey === 'system') {
    document.getElementById('tabSystem')?.classList.add('active');
    document.getElementById('viewSystem')?.classList.add('active');
  }
}

// 5. Financial Monitor Live Loading & Auto-Refresh
async function loadFinancialMonitor() {
  const isExecutive = currentUser && ['director', 'cfo', 'admin'].includes(currentUser.role);
  if (!isExecutive) {
    const monitorTs = document.getElementById('monitorTimestamp');
    if (monitorTs) {
      monitorTs.className = 'v8-badge danger';
      monitorTs.textContent = '⛔ Доступ ограничен политикой 1С:УНФ (роль: ' + (currentUser ? currentUser.role : 'гость') + ')';
    }
    show1CToast('Раздел финансовых показателей доступен только Генеральному директору и CFO', true);
    return;
  }

  try {
    const res = await fetch('/analytics/monitor', {
      headers: { 'Authorization': `Bearer ${authToken}`, 'X-Auth-Token': authToken || '' }
    });
    if (res.ok) {
      const data = await res.json();
      renderFinancialMonitor(data);
    } else if (res.status === 403) {
      show1CToast('Недостаточно прав для просмотра финансовых регистров 1С', true);
    }
  } catch (err) {
    console.warn('Financial monitor fetch fallback:', err);
  }
}

function renderFinancialMonitor(data) {
  if (!data || !data.kpi) return;
  const kpi = data.kpi;
  const kpiCash = document.getElementById('kpiCash');
  const kpiGap = document.getElementById('kpiGap');
  const kpiOrders = document.getElementById('kpiOrders');
  const kpiStock = document.getElementById('kpiStock');
  const monitorTimestamp = document.getElementById('monitorTimestamp');

  if (kpiCash) kpiCash.textContent = formatCurrency(kpi.cash_balance) + ' ₽';
  if (kpiGap) kpiGap.textContent = formatCurrency(kpi.cash_gap) + ' ₽';
  if (kpiOrders) kpiOrders.textContent = formatCurrency(kpi.stalled_orders_amount) + ' ₽';
  if (kpiStock) kpiStock.textContent = formatCurrency(kpi.dead_stock_amount) + ' ₽';
  if (monitorTimestamp) monitorTimestamp.textContent = 'Обновлено: ' + data.timestamp + (data.is_mock_data ? ' (демонстрационные данные)' : ' (синхронизированный снимок)');
}

function formatCurrency(val) {
  return Number(val || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

function refreshCurrentView() {
  if (currentTab === 'kanban') {
    loadKanbanBoard();
  } else if (currentTab === 'analytics') {
    loadFinancialMonitor();
  } else if (currentTab === 'system') {
    checkInfrastructureStatus();
  } else {
    sendQuickPrompt('Какова текущая сводка по ключевым цифрам?');
  }
}

async function checkInfrastructureStatus() {
  const btn = document.getElementById('checkStatusBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = 'Проверка...';
  }
  try {
    const res = await fetch('/health');
    const data = await res.json();
    show1CToast(`Диагностика: Службы активны. База 1С: ${data.db || 'ok'}, ИИ: ${data.llm || 'готов'}`);
  } catch (e) {
    show1CToast('Служба Middleware недоступна', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="v8-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
        <span>Диагностика связи</span>
      `;
    }
  }
}

// 6. Interactions with 1C Objects
function open1CObjectInBrowser(objectType, id) {
  const url = `http://localhost:8081/unf#e1cib/data/${encodeURIComponent(objectType)}?ref=${encodeURIComponent(id)}`;
  window.open(url, '_blank');
}

function open1CDocument(docType) {
  if (docType === 'ЗаказПокупателя') {
    sendQuickPrompt('Покажи зависшие и сорванные заказы');
  } else if (docType === 'ПлатежноеПоручение') {
    sendQuickPrompt('Кому и сколько мы должны денег?');
  }
}

function open1CSection(sectionName) {
  closeMobileSidebar();
  if (sectionName === 'CRM') {
    sendQuickPrompt('Покажи спящих клиентов без заказов');
  } else if (sectionName === 'Склад') {
    sendQuickPrompt('Какие неликвиды лежат на складе?');
  } else if (sectionName === 'Деньги') {
    sendQuickPrompt('Будет ли кассовый разрыв на этой неделе?');
  } else if (sectionName === 'Продажи') {
    sendQuickPrompt('Покажи зависшие и сорванные заказы');
  } else if (sectionName === 'Закупки') {
    sendQuickPrompt('У кого дешевле купить кабель?');
  } else {
    switchTab('chat');
  }
}

async function query1CODataDirect(entityName) {
  switchTab('chat');
  if (entityName === 'Контрагенты') {
    sendQuickPrompt('Кто нам должен деньги?');
  } else if (entityName === 'Заказы') {
    sendQuickPrompt('Покажи зависшие и сорванные заказы');
  } else if (entityName === 'Остатки') {
    sendQuickPrompt('Какие неликвиды лежат на складе?');
  }
}

// 7. Greeting Message
function initGreetingMessage() {
  const viewport = document.getElementById('chatViewport');
  if (viewport && viewport.children.length === 0) {
    appendBotMessage(
      'Здравствуйте! Я интеллектуальный ассистент руководителя в системе **«1С:Управление нашей фирмой 3.0»**.\n\n' +
      'Я помогаю подготовить запросы к 1С и поставить задачи. В учебном веб-стенде показаны демонстрационные примеры. Работа с регистрами и документами требует настроенного подключения и прав пользователя 1С.',
      'greeting',
      null
    );
  }
}

// 8. Chat Interaction
async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  appendUserMessage(text);
  input.value = '';
  input.style.height = 'auto';

  const typingId = showTypingIndicator();

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': authToken || ''
      },
      body: JSON.stringify({
        messages: [{ role: 'user', text: text }]
      })
    });

    removeTypingIndicator(typingId);

    if (res.ok) {
      const data = await res.json();
      appendBotMessage(data.text, data.action, data.data);
    } else {
      handle1CFallback(text);
    }
  } catch (err) {
    removeTypingIndicator(typingId);
    handle1CFallback(text);
  }
}

function handle1CFallback(text) {
  appendBotMessage(
    'Запрос не выполнен: сервер недоступен или отклонил обращение. Проверьте подключение и авторизацию. Данные и действия не сформированы.',
    'access_denied',
    null
  );
}

function sendQuickPrompt(promptText) {
  switchTab('chat');
  document.getElementById('chatInput').value = promptText;
  sendChatMessage();
}

function handleInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 80) + 'px';
}

function appendUserMessage(text) {
  const viewport = document.getElementById('chatViewport');
  if (!viewport) return;
  const row = document.createElement('div');
  row.className = 'v8-msg user';
  row.innerHTML = `
    <div class="v8-msg-avatar">ВЫ</div>
    <div class="v8-msg-body">${escapeHtml(text)}</div>
  `;
  viewport.appendChild(row);
  viewport.scrollTop = viewport.scrollHeight;
}

function showTypingIndicator() {
  const viewport = document.getElementById('chatViewport');
  if (!viewport) return null;
  const id = 'typing_' + Date.now();
  const row = document.createElement('div');
  row.className = 'v8-msg bot';
  row.id = id;
  row.innerHTML = `
    <div class="v8-msg-avatar">1С</div>
    <div class="v8-msg-body" style="color:var(--text-dim);font-style:italic;">
      Обработка запроса...
    </div>
  `;
  viewport.appendChild(row);
  viewport.scrollTop = viewport.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  if (!id) return;
  const el = document.getElementById(id);
  if (el) el.remove();
}

// 9. Bot Message & Authentic 1C Tables
function appendBotMessage(text, action, data) {
  const viewport = document.getElementById('chatViewport');
  if (!viewport) return;
  const row = document.createElement('div');
  row.className = 'v8-msg bot';

  let widgetHtml = '';
  if (action === 'cash_gap_forecast') {
    widgetHtml = render1CCashGapWidget(data);
  } else if (action === 'audit_stalled_orders') {
    widgetHtml = render1CStalledOrdersWidget(data);
  } else if (action === 'get_dead_stock') {
    widgetHtml = render1CDeadStockWidget(data);
  } else if (action === 'get_creditors') {
    widgetHtml = render1CCreditorsWidget(data);
  } else if (action === 'dormant_clients_winback') {
    widgetHtml = render1CDormantClientsWidget(data);
  } else if (action === 'supplier_price_comparison') {
    widgetHtml = render1CSupplierPriceWidget(data);
  } else if (action === 'get_debtors') {
    widgetHtml = render1CDebtorsWidget(data);
  }

  if (data && data.task_id) {
    widgetHtml += `
      <div style="margin-top:8px;">
        <button class="v8-btn v8-btn-primary" onclick="switchTab('kanban')">
          Открыть задачу №${data.task_id} на Канбан-доске →
        </button>
      </div>
    `;
  }

  const formattedText = formatMarkdown(text);

  row.innerHTML = `
    <div class="v8-msg-avatar">1С</div>
    <div class="v8-msg-body">
      <div>${formattedText}</div>
      ${widgetHtml}
    </div>
  `;
  viewport.appendChild(row);
  viewport.scrollTop = viewport.scrollHeight;
}

function render1CCashGapWidget(data) {
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Платёжный календарь (1С:УНФ, 7 дней)
      </div>
      <table class="v8-grid-table">
        <tbody>
          <tr>
            <td>Текущий остаток денежных средств (Банк + Касса)</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-green-text);">69 825 848 ₽</td>
          </tr>
          <tr>
            <td>Ожидаемые поступления от покупателей</td>
            <td class="text-right">0.00 ₽</td>
          </tr>
          <tr>
            <td>Плановые платежи поставщикам к списанию</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-red-text);">2 757 870 ₽</td>
          </tr>
          <tr style="background:var(--bg-selected);">
            <td><strong>Итоговый чистый запас ликвидности</strong></td>
            <td class="text-right" style="font-weight:700;color:var(--badge-green-text);">+67 067 978 ₽</td>
          </tr>
        </tbody>
      </table>
      <div style="padding:6px 10px;background:var(--bg-subtle);display:flex;gap:6px;justify-content:flex-end;">
        <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Контроль графика платежей', 'Проконтролировать график оплат поставщикам на неделю.', 'medium', this)">
          Поставить задачу в Канбан
        </button>
      </div>
    </div>
  `;
}

function render1CStalledOrdersWidget(data) {
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Заказы покупателей с просрочкой отгрузки (> 3 дней)
      </div>
      <table class="v8-grid-table">
        <thead>
          <tr>
            <th>Номер документа</th>
            <th>Покупатель</th>
            <th class="text-right">Сумма заказа</th>
            <th>Просрочка</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Заказ № 00000003</strong></td>
            <td>ООО "АльфаТрейд"</td>
            <td class="text-right" style="font-weight:700;">128 500.00 ₽</td>
            <td><span class="v8-badge danger">12 дней</span></td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Срыв заказа №00000003 (АльфаТрейд)', 'Срочно выяснить задержку отгрузки кабеля 128 500 ₽ у начальника склада.', 'high', this)">
                В работу
              </button>
            </td>
          </tr>
          <tr>
            <td><strong>Заказ № 00000007</strong></td>
            <td>ИП Смирнов В.А.</td>
            <td class="text-right" style="font-weight:700;">46 200.00 ₽</td>
            <td><span class="v8-badge warning">6 дней</span></td>
            <td>
              <button class="v8-btn" onclick="createKanbanTaskDirect('Срыв заказа №00000007 (Смирнов)', 'Задержка отгрузки 6 дней. Проверить комплектацию.', 'medium', this)">
                В работу
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function render1CDeadStockWidget(data) {
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Залежалая номенклатура на складах (> 90 дней без движения)
      </div>
      <table class="v8-grid-table">
        <thead>
          <tr>
            <th>Артикул</th>
            <th>Номенклатура</th>
            <th class="text-right">Остаток</th>
            <th class="text-right">Заморожено</th>
            <th class="text-right">Дней покоя</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>КБ-325</td>
            <td><strong>Кабель силовой ВВГнг-LS 3x2.5</strong></td>
            <td class="text-right">1 200 м</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-yellow-text);">96 000 ₽</td>
            <td class="text-right">142 дн.</td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Уценка: Кабель ВВГнг-LS', 'Запустить уценку 15% для оптовых покупателей.', 'medium', this)">
                Уценить 15%
              </button>
            </td>
          </tr>
          <tr>
            <td>СВ-LED36</td>
            <td><strong>Светильник светодиодный LED 36W</strong></td>
            <td class="text-right">85 шт</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-yellow-text);">72 250 ₽</td>
            <td class="text-right">118 дн.</td>
            <td>
              <button class="v8-btn" onclick="createKanbanTaskDirect('Уценка: Светильники LED 36W', 'Сформировать спецпредложение оптовикам.', 'medium', this)">
                В промо
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function render1CCreditorsWidget(data) {
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Кредиторская задолженность перед поставщиками (1С:УНФ)
      </div>
      <table class="v8-grid-table">
        <thead>
          <tr>
            <th>Поставщик</th>
            <th>Договор</th>
            <th class="text-right">Сумма долга</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>ООО "КабельСнабСервис"</strong></td>
            <td>Договор поставки № 12</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-red-text);">1 420 500.00 ₽</td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Оплата: КабельСнабСервис', 'Платеж 1 420 500 ₽ по договору №12', 'high', this)">
                Создать платёж
              </button>
            </td>
          </tr>
          <tr>
            <td><strong>ЗАО "Световые Системы"</strong></td>
            <td>Основной договор</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-red-text);">890 370.28 ₽</td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Оплата: Световые Системы', 'Платеж 890 370.28 ₽', 'medium', this)">
                Создать платёж
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function render1CDormantClientsWidget(data) {
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Спящие постоянные клиенты (>45 дней без заказов)
      </div>
      <table class="v8-grid-table">
        <thead>
          <tr>
            <th>Клиент</th>
            <th class="text-right">Накопленный LTV</th>
            <th>Без заказов</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>ООО "СтройКомплект"</strong></td>
            <td class="text-right" style="font-weight:700;">845 000 ₽</td>
            <td><span class="v8-badge warning">68 дней</span></td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Возврат: СтройКомплект', 'Связаться с ЛПР (LTV 845 000 ₽), предложить скидку 7%.', 'high', this)">
                Поручить возврат
              </button>
            </td>
          </tr>
          <tr>
            <td><strong>ИП Петров К.М.</strong></td>
            <td class="text-right" style="font-weight:700;">312 000 ₽</td>
            <td><span class="v8-badge warning">52 дня</span></td>
            <td>
              <button class="v8-btn" onclick="createKanbanTaskDirect('Возврат: ИП Петров', 'Запросить новые потребности в материалах.', 'medium', this)">
                Поручить возврат
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function render1CSupplierPriceWidget(data) {
  const item = data && data.item_name ? data.item_name : 'Кабель силовой ВВГнг-LS 3x2.5';
  return `
    <div style="margin-top:8px;border:1px solid var(--border);border-radius:3px;overflow:hidden;background:var(--bg-card);">
      <div style="padding:6px 10px;background:var(--bg-toolbar);border-bottom:1px solid var(--border-light);font-weight:700;font-size:12px;">
        Регистр цен поставщиков: «${escapeHtml(item)}»
      </div>
      <table class="v8-grid-table">
        <thead>
          <tr>
            <th>Поставщик</th>
            <th class="text-right">Цена закупки</th>
            <th>Статус цены</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>ООО "КабельОптТорг"</strong></td>
            <td class="text-right" style="font-weight:700;color:var(--badge-green-text);">78.50 ₽ / м</td>
            <td><span class="v8-badge success">Минимальная</span></td>
            <td>
              <button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Заказ: КабельОптТорг', 'Сформировать заказ по минимальной цене 78.50 ₽/м', 'medium', this)">
                Заказать
              </button>
            </td>
          </tr>
          <tr>
            <td>ООО "ЭлектроКабель"</td>
            <td class="text-right" style="font-weight:700;color:var(--badge-red-text);">94.20 ₽ / м</td>
            <td><span class="v8-badge danger">+20.0% переплата</span></td>
            <td>—</td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}

function render1CDebtorsWidget(data) {
  return `
    <div style="margin-top:8px;padding:8px 12px;background:var(--badge-green-bg);border:1px solid var(--badge-green-border);border-radius:3px;font-size:12.5px;color:var(--badge-green-text);font-weight:600;">
      В базе 1С:УНФ просроченная дебиторская задолженность отсутствует. Все текущие отгрузки закрыты платежами.
    </div>
  `;
}

// 10. Kanban Board Live Sync with Backend SQLite
async function loadKanbanBoard() {
  try {
    const res = await fetch('/kanban/board', {
      headers: { 'X-Auth-Token': authToken || '' }
    });
    if (res.ok) {
      const data = await res.json();
      const grouped = { todo: [], in_progress: [], review: [], done: [] };
      if (Array.isArray(data.tasks)) {
        data.tasks.forEach(t => {
          const col = t.column || 'todo';
          if (!grouped[col]) grouped[col] = [];
          grouped[col].push(t);
        });
        // Sort each column with newest task on top
        for (const colKey of Object.keys(grouped)) {
          grouped[colKey].sort((a, b) => Number(b.id) - Number(a.id));
        }
      }
      kanbanData = grouped;
    }
  } catch (err) {
    console.warn('Kanban fetch error:', err);
  }
  renderKanbanBoard();
}

let currentKanbanFilter = 'all';
function filterKanban(filterType) {
  currentKanbanFilter = filterType;
  renderKanbanBoard();
}

function renderKanbanBoard() {
  const container = document.getElementById('kanbanBoard');
  if (!container) return;
  container.innerHTML = '';

  const columnsConfig = [
    { key: 'todo', title: 'К выполнению', badgeClass: 'info' },
    { key: 'in_progress', title: 'В работе', badgeClass: 'warning' },
    { key: 'review', title: 'На проверке', badgeClass: 'danger' },
    { key: 'done', title: 'Завершено', badgeClass: 'success' }
  ];

  columnsConfig.forEach(col => {
    let tasks = kanbanData[col.key] || [];
    if (currentKanbanFilter === 'high') {
      tasks = tasks.filter(t => t.priority === 'high' || t.priority === 'urgent');
    } else if (currentKanbanFilter === 'in_progress') {
      tasks = tasks.filter(t => t.column === 'in_progress');
    }

    const colDiv = document.createElement('div');
    colDiv.className = 'v8-kanban-column';
    colDiv.innerHTML = `
      <div class="v8-col-titlebar">
        <span>${col.title}</span>
        <span class="v8-badge ${col.badgeClass}">${tasks.length}</span>
      </div>
      <div class="v8-tasks-scroll" id="col_${col.key}" ondragover="handleDragOver(event)" ondrop="handleDrop(event, '${col.key}')">
        ${tasks.map(t => renderTaskCard(t)).join('')}
      </div>
    `;
    container.appendChild(colDiv);
  });

  // Update total badge if exists
  const totalTasks = (kanbanData.todo?.length || 0) + (kanbanData.in_progress?.length || 0) + (kanbanData.review?.length || 0) + (kanbanData.done?.length || 0);
  const allBtn = document.querySelector(".v8-toolbar button[onclick=\"filterKanban('all')\"]");
  if (allBtn) {
    allBtn.textContent = `Все (${totalTasks})`;
  }
}

function renderTaskCard(t) {
  const badgeClass = (t.priority === 'high' || t.priority === 'urgent') ? 'danger' : t.priority === 'low' ? 'info' : 'warning';
  const prioText = (t.priority === 'high' || t.priority === 'urgent') ? 'Срочно' : t.priority === 'low' ? 'План' : 'Обычная';
  const nextCol = t.column === 'todo' ? 'in_progress' : t.column === 'in_progress' ? 'review' : t.column === 'review' ? 'done' : null;
  const nextBtn = nextCol ? `<button class="v8-btn" style="height:19px;padding:0 6px;font-size:10px;" onclick="moveTaskNext(${t.id}, '${nextCol}')">В ${getColName(nextCol)} →</button>` : '<span style="color:var(--badge-green-text);font-weight:700;">Готово</span>';

  return `
    <div class="v8-task-item" draggable="true" ondragstart="handleDragStart(event, ${t.id})">
      <div class="v8-task-item-head">
        <span class="v8-badge ${badgeClass}">${prioText}</span>
        <span style="font-size:10.5px;color:var(--text-dim);">#${t.id} • ${escapeHtml(t.source || '1С')}</span>
      </div>
      <div class="v8-task-item-title">${escapeHtml(t.title)}</div>
      ${t.description ? `<div class="v8-task-item-desc">${escapeHtml(t.description)}</div>` : ''}
      <div class="v8-task-item-foot">
        <span>${escapeHtml(t.assignee || 'Абдулов (директор)')}</span>
        ${nextBtn}
      </div>
    </div>
  `;
}

function getColName(col) {
  if (col === 'in_progress') return 'работу';
  if (col === 'review') return 'проверку';
  if (col === 'done') return 'архив';
  return 'следующую';
}

// Drag & Drop
let draggedTaskId = null;
function handleDragStart(e, taskId) {
  draggedTaskId = taskId;
  e.dataTransfer.setData('text/plain', String(taskId));
}

function handleDragOver(e) {
  e.preventDefault();
}

async function handleDrop(e, targetColumn) {
  e.preventDefault();
  if (!draggedTaskId) return;

  await moveTaskToColumn(draggedTaskId, targetColumn);
  draggedTaskId = null;
}

async function moveTaskNext(taskId, targetColumn) {
  await moveTaskToColumn(taskId, targetColumn);
}

async function moveTaskToColumn(taskId, targetColumn) {
  const numericId = parseInt(taskId, 10);
  let foundTask = null;
  for (const colKey of Object.keys(kanbanData)) {
    const idx = kanbanData[colKey].findIndex(t => Number(t.id) === numericId);
    if (idx !== -1) {
      foundTask = kanbanData[colKey].splice(idx, 1)[0];
      break;
    }
  }

  if (foundTask) {
    foundTask.column = targetColumn;
    if (!kanbanData[targetColumn]) kanbanData[targetColumn] = [];
    kanbanData[targetColumn].unshift(foundTask);
    renderKanbanBoard();
  }

  try {
    await fetch('/kanban/tasks/move', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': authToken || ''
      },
      body: JSON.stringify({ task_id: numericId, column: targetColumn })
    });
  } catch (err) {
    console.warn('Kanban move sync:', err);
  }
}

// 11. Modal Task Dialog (Native Backend Persistence)
function openNewTaskModal() {
  const modal = document.getElementById('taskModal');
  if (modal) modal.style.display = 'flex';
}

function closeTaskModal() {
  const modal = document.getElementById('taskModal');
  if (modal) modal.style.display = 'none';
  const form = document.getElementById('newTaskForm');
  if (form) form.reset();
}

async function handleCreateTask(e) {
  e.preventDefault();
  const title = document.getElementById('taskTitle').value.trim();
  const desc = document.getElementById('taskDesc').value.trim();
  const priority = document.getElementById('taskPriority').value;
  const column = document.getElementById('taskColumn').value;

  if (!title) return;

  const payload = {
    title,
    description: desc,
    priority,
    column,
    source: 'web',
    assignee: 'Абдулов (директор)'
  };

  try {
    const res = await fetch('/kanban/tasks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': authToken || ''
      },
      body: JSON.stringify(payload)
    });

    closeTaskModal();

    if (res.ok) {
      const created = await res.json();
      if (!kanbanData[column]) kanbanData[column] = [];
      kanbanData[column].unshift(created);
      renderKanbanBoard();
      show1CToast(`Задача №${created.id}: «${title}» добавлена.`);
    } else {
      console.error('Task creation failed:', await res.text());
    }
  } catch (err) {
    console.error('Task save local:', err);
  }
}

// Direct Task Creation from 1C Operational Widgets & Scenario Buttons
async function createKanbanTaskDirect(title, desc, priority, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.dataset.origText = btnEl.innerHTML;
    btnEl.innerHTML = 'Запись...';
  }

  const payload = {
    title: title,
    description: desc || '',
    priority: priority || 'medium',
    column: 'todo',
    source: '1c',
    assignee: 'Абдулов (директор)'
  };

  try {
    const res = await fetch('/kanban/tasks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': authToken || ''
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const created = await res.json();
      if (!kanbanData['todo']) kanbanData['todo'] = [];
      kanbanData['todo'].unshift(created);
      renderKanbanBoard();

      if (btnEl) {
        btnEl.innerHTML = '✓ В Канбане';
        btnEl.classList.add('v8-btn-success');
        setTimeout(() => {
          btnEl.disabled = false;
          btnEl.innerHTML = btnEl.dataset.origText;
          btnEl.classList.remove('v8-btn-success');
        }, 3000);
      }

      show1CToast(`Задача №${created.id}: ${title}`);

      appendBotMessage(
        `Создана задача в 1С:\n\n**«${title}»** (Задача №${created.id})\n_${desc}_\n\nЗадача сохранена в базе 1С:УНФ и доступна на Канбан-доске.`,
        null,
        { task_id: created.id }
      );
      return created;
    } else {
      const errText = await res.text();
      console.error('Task create error:', res.status, errText);
      show1CToast(`Ошибка создания задачи: ${res.status}`, true);
      if (btnEl) {
        btnEl.disabled = false;
        btnEl.innerHTML = btnEl.dataset.origText;
      }
    }
  } catch (err) {
    console.error('Direct task sync error:', err);
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = btnEl.dataset.origText;
    }
  }
}

// 12. Voice Input
function setupSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) return;

  speechRecognizer = new SpeechRec();
  speechRecognizer.lang = 'ru-RU';
  speechRecognizer.continuous = false;
  speechRecognizer.interimResults = false;

  speechRecognizer.onstart = () => {
    isVoiceRecording = true;
    const btn = document.getElementById('voiceBtn');
    if (btn) btn.style.background = 'var(--badge-red-bg)';
  };

  speechRecognizer.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    const input = document.getElementById('chatInput');
    if (input) {
      input.value = transcript;
      sendChatMessage();
    }
  };

  speechRecognizer.onerror = () => stopVoiceInput();
  speechRecognizer.onend = () => stopVoiceInput();
}

function toggleVoiceInput() {
  if (!speechRecognizer) {
    alert('Голосовой ввод не поддерживается данным браузером. Используйте Google Chrome или Яндекс Браузер.');
    return;
  }
  if (isVoiceRecording) {
    speechRecognizer.stop();
  } else {
    try {
      speechRecognizer.start();
    } catch (e) {
      console.warn('Voice start failed:', e);
    }
  }
}

function stopVoiceInput() {
  isVoiceRecording = false;
  const btn = document.getElementById('voiceBtn');
  if (btn) btn.style.background = '';
}

// 13. Helpers
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatMarkdown(text) {
  if (!text) return '';
  let out = escapeHtml(text);
  out = out.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/_(.*?)_/g, '<em>$1</em>');
  out = out.replace(/\n/g, '<br>');
  return out;
}

// 14. Omnichannel Gateway (Telegram, VK, Email) Testing Logic
async function checkIntegrationsStatus() {
  const btn = document.getElementById('checkIntegrationsBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = 'Проверка...';
  }
  try {
    const res = await fetch('/integrations/status');
    const data = await res.json();
    const ch = data.channels || {};
    
    // Telegram
    const tgBadge = document.getElementById('tgBadge');
    if (tgBadge && ch.telegram) {
      tgBadge.className = 'v8-badge success';
      tgBadge.textContent = ch.telegram.configured ? '● Активен (Live)' : '● Активен (Sandbox 25+)';
    }
    
    // VK
    const vkBadge = document.getElementById('vkBadge');
    if (vkBadge && ch.vk) {
      vkBadge.className = 'v8-badge success';
      vkBadge.textContent = ch.vk.configured ? '● Активен (Live)' : '● Активен (Sandbox)';
    }

    // Email
    const emailBadge = document.getElementById('emailBadge');
    if (emailBadge && ch.email) {
      emailBadge.className = 'v8-badge success';
      emailBadge.textContent = ch.email.configured ? '● SMTP подключен' : `● Робот (Outbox: ${ch.email.outbox_count})`;
    }

    show1CToast('Каналы Telegram, VK и Email активны');
  } catch (e) {
    show1CToast('Ошибка проверки каналов интеграции', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="v8-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
        </svg>
        <span>Статус каналов</span>
      `;
    }
  }
}

function setOmniPreset(type, val) {
  const select = document.getElementById('omniChannelSelect');
  const input = document.getElementById('omniCommandInput');
  if (!select || !input) return;

  if (type === 'telegram') {
    select.value = 'telegram';
    input.value = val;
  } else if (type === 'vk') {
    select.value = 'vk';
    input.value = val;
  } else if (type === 'email_order') {
    select.value = 'email';
    input.value = 'Заказ: Кабель ВВГнг-LS 3х2.5 — 50м, Автоматический выключатель — 10 шт для ООО "АльфаМарт"';
  } else if (type === 'email_digest') {
    select.value = 'email';
    input.value = '/digest';
  }
}

async function sendOmnichannelTest() {
  const select = document.getElementById('omniChannelSelect');
  const input = document.getElementById('omniCommandInput');
  const out = document.getElementById('omniConsoleOutput');
  const btn = document.getElementById('omniSendBtn');

  const channel = select ? select.value : 'telegram';
  const text = input ? input.value.trim() : '';

  if (!text) {
    if (out) out.textContent = '⚠️ Введите команду или текст для отправки в шлюз.';
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Обработка...';
  }
  if (out) {
    out.textContent = `[${new Date().toLocaleTimeString()}] 🚀 Отправка запроса в канал [${channel.toUpperCase()}]...\nВходные данные: ${text}\n`;
  }

  try {
    let res;
    if (channel === 'telegram') {
      res = await fetch('/integrations/telegram/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, user_name: 'Абдулов (директор)' })
      });
      const data = await res.json();
      const msgs = data.messages || [];
      let replyText = msgs.map(m => m.text).join('\n---\n') || 'Сообщение обработано.';
      out.textContent += `\n[${new Date().toLocaleTimeString()}] 📱 Ответ Telegram Bot:\n${replyText}`;
      show1CToast('Telegram: ответ получен');
    } else if (channel === 'vk') {
      res = await fetch('/integrations/vk/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, user_id: 123456 })
      });
      const data = await res.json();
      const msgs = data.messages || [];
      let replyText = msgs.map(m => m.text).join('\n---\n') || 'Команда обработана сообществом ВК.';
      out.textContent += `\n[${new Date().toLocaleTimeString()}] 🌐 Ответ ВКонтакте:\n${replyText}`;
      show1CToast('VK: ответ получен');
    } else if (channel === 'email') {
      if (text === '/digest' || text.toLowerCase().includes('дайджест')) {
        res = await fetch('/integrations/email/digest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recipient: 'b67292451@gmail.com' })
        });
        const data = await res.json();
        out.textContent += `\n[${new Date().toLocaleTimeString()}] ✉️ Утренний дайджест руководителя сформирован!\nОтправлен на: b67292451@gmail.com\nСтатус доставки: ${data.delivery}\nID письма в Outbox: #${data.email_id}`;
        show1CToast('Дайджест отправлен на b67292451@gmail.com');
      } else {
        res = await fetch('/integrations/email/incoming', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sender: 'b67292451@gmail.com',
            subject: text.slice(0, 50),
            body: text
          })
        });
        const data = await res.json();
        out.textContent += `\n[${new Date().toLocaleTimeString()}] ✉️ Почтовый робот принял заявку!\nСоздана задача Канбан: #${data.task_id} («${data.task_title}»)\nОтправитель: ${data.sender}\nАвтоответ клиенту отправлен в Outbox.\nРезюме ИИ: ${data.ai_summary || 'Заявка принята'}`;
        show1CToast(`Email-to-Order: Задача #${data.task_id} в Канбане!`);
        loadKanbanBoard();
      }
    }
  } catch (err) {
    if (out) out.textContent += `\n❌ Ошибка шлюза: ${err.message}`;
    show1CToast('Ошибка отправки в шлюз', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Отправить в шлюз';
    }
  }
}

async function openEmailOutboxModal() {
  const modal = document.getElementById('emailOutboxModal');
  const container = document.getElementById('emailOutboxList');
  if (modal) modal.style.display = 'flex';
  if (container) container.innerHTML = '<div style="color:var(--v8-text-muted);padding:10px;">Загрузка писем...</div>';

  try {
    const res = await fetch('/integrations/email/outbox');
    const data = await res.json();
    const outbox = data.outbox || [];

    if (!container) return;

    if (outbox.length === 0) {
      container.innerHTML = '<div style="color:var(--v8-text-muted);padding:20px;text-align:center;">Почтовый ящик пуст. Отправьте дайджест или заявку в шлюзе.</div>';
      return;
    }

    container.innerHTML = outbox.map(em => `
      <div style="background:var(--v8-bg-card);border:1px solid var(--v8-border);border-radius:6px;padding:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <strong style="font-size:13px;color:var(--v8-text-main);">${escapeHtml(em.subject)}</strong>
          <span class="v8-badge ${em.type === 'critical_alert' ? 'danger' : 'info'}">${escapeHtml(em.type)}</span>
        </div>
        <div style="font-size:11px;color:var(--v8-text-muted);margin-bottom:8px;">
          Получатель: <strong>${escapeHtml(em.to)}</strong> • Время: ${escapeHtml(em.timestamp)} • Доставка: <em>${escapeHtml(em.delivery)}</em>
        </div>
        ${em.html_body ? `
          <div style="background:#ffffff;border:1px solid #cbd5e1;border-radius:4px;padding:8px;margin-top:6px;max-height:220px;overflow-y:auto;">
            ${em.html_body}
          </div>
        ` : `
          <pre style="background:var(--v8-bg-main);border:1px solid var(--v8-border-subtle);border-radius:4px;padding:8px;font-size:11px;color:var(--v8-text-main);white-space:pre-wrap;font-family:monospace;max-height:140px;overflow-y:auto;">${escapeHtml(em.body)}</pre>
        `}
      </div>
    `).join('');
  } catch (e) {
    if (container) container.innerHTML = '<div style="color:red;padding:10px;">Ошибка загрузки почтового ящика.</div>';
  }
}

function closeEmailOutboxModal() {
  const modal = document.getElementById('emailOutboxModal');
  if (modal) modal.style.display = 'none';
}

// ===========================================================================
// 15. RUSSIAN BUSINESS MODULES (115-ФЗ, MARGIN, DEBT, STOCK, OCR)
// ===========================================================================

function getAuthHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (authToken) {
    h['Authorization'] = `Bearer ${authToken}`;
    h['X-Auth-Token'] = authToken;
  }
  return h;
}

// 1. Switch Active Business Sub-Tool Panel
function switchBizTool(toolId) {
  const panels = {
    compliance: document.getElementById('bizToolCompliance'),
    margin: document.getElementById('bizToolMargin'),
    debt: document.getElementById('bizToolDebt'),
    stock: document.getElementById('bizToolStock'),
    ocr: document.getElementById('bizToolOcr')
  };

  Object.keys(panels).forEach(key => {
    if (panels[key]) {
      panels[key].style.display = (key === toolId) ? 'block' : 'none';
    }
  });

  const buttons = document.getElementById('bizNavButtons')?.querySelectorAll('button') || [];
  buttons.forEach(btn => {
    const isCurrent = btn.getAttribute('onclick')?.includes(toolId);
    btn.className = isCurrent ? 'v8-btn v8-btn-primary' : 'v8-btn';
  });
}

// 2. 115-ФЗ: Counterparty Check by INN
async function runCounterpartyCheck() {
  const inn = document.getElementById('bizInnInput')?.value.trim();
  const isMassDir = document.getElementById('bizMassDirector')?.checked || false;
  const isMassAddr = document.getElementById('bizMassAddress')?.checked || false;
  const resBox = document.getElementById('bizCounterpartyResult');

  if (!inn) {
    show1CToast('Введите ИНН контрагента (10 или 12 цифр)', true);
    return;
  }

  if (resBox) {
    resBox.style.display = 'block';
    resBox.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Проверка по базам ФНС, ЕГРЮЛ и Росфинмониторинга...</div>';
  }

  try {
    const res = await fetch('/business/compliance/check-counterparty', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        inn: inn,
        is_mass_director: isMassDir,
        is_mass_address: isMassAddr
      })
    });

    if (res.status === 401 || res.status === 403) {
      const err = await res.json().catch(() => ({}));
      if (resBox) {
        resBox.innerHTML = `<div style="color:#b91c1c;">⛔ Доступ запрещен (${res.status}): ${escapeHtml(err.detail || 'Недостаточно прав')}</div>`;
      }
      show1CToast('Недостаточно прав для проверки контрагентов', true);
      return;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка при проверке контрагента');
    }

    const data = await res.json();
    const badgeClass = data.risk_level === 'LOW' ? 'success' : (data.risk_level === 'CRITICAL' || data.risk_level === 'HIGH' ? 'danger' : 'warning');

    let stopFactorsHtml = '';
    if (data.stop_factors && data.stop_factors.length > 0) {
      stopFactorsHtml = `
        <div style="margin-top:8px;padding:6px 8px;background:#fee2e2;border:1px solid #f87171;border-radius:4px;color:#991b1b;">
          <strong>Стоп-факторы:</strong>
          <ul style="margin:4px 0 0 16px;padding:0;">
            ${data.stop_factors.map(sf => `<li>${escapeHtml(sf)}</li>`).join('')}
          </ul>
        </div>`;
    }

    let warningsHtml = '';
    if (data.warnings && data.warnings.length > 0) {
      warningsHtml = `
        <div style="margin-top:8px;padding:6px 8px;background:#fef3c7;border:1px solid #fcd34d;border-radius:4px;color:#92400e;">
          <strong>Предупреждения:</strong>
          <ul style="margin:4px 0 0 16px;padding:0;">
            ${data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
          </ul>
        </div>`;
    }

    let recsHtml = '';
    if (data.recommendations && data.recommendations.length > 0) {
      recsHtml = `
        <div style="margin-top:8px;font-size:11px;color:var(--text-main);">
          <strong>Рекомендации службы безопасности:</strong>
          <ul style="margin:4px 0 0 16px;padding:0;">
            ${data.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
          </ul>
        </div>`;
    }

    if (resBox) {
      resBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:6px;margin-bottom:8px;">
          <div>
            <strong style="font-size:13px;">${escapeHtml(data.name || 'Организация')}</strong>
            <span style="font-size:11px;color:var(--text-dim);margin-left:6px;">(${escapeHtml(data.entity_type)})</span>
          </div>
          <span class="v8-badge ${badgeClass}" style="font-weight:700;">
            Уровень риска: ${escapeHtml(data.risk_level)} (${data.risk_score}/100)
          </span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
          <div>Контрольная сумма ИНН: <strong>${data.is_inn_valid ? '✓ Корректна' : '✕ Ошибка контрольных цифр'}</strong></div>
          <div>Заключение договора: <strong>${data.can_conclude_contract ? '<span style="color:#16a34a;">✓ Разрешено</span>' : '<span style="color:#dc2626;">⛔ Запрещено (Блокировка)</span>'}</strong></div>
        </div>
        ${stopFactorsHtml}
        ${warningsHtml}
        ${recsHtml}
      `;
    }
    show1CToast(`Проверка ИНН ${inn}: риск ${data.risk_level} (${data.risk_score} б.)`);
  } catch (err) {
    if (resBox) resBox.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}

// 3. 115-ФЗ: Payment Purpose & AML Audit
async function runPaymentAudit() {
  const amount = parseFloat(document.getElementById('bizPayAmount')?.value || '0');
  const purpose = document.getElementById('bizPayPurpose')?.value.trim();
  const isCash = document.getElementById('bizIsCash')?.checked || false;
  const resBox = document.getElementById('bizPaymentResult');

  if (!purpose || amount <= 0) {
    show1CToast('Укажите корректную сумму и назначение платежа', true);
    return;
  }

  if (resBox) {
    resBox.style.display = 'block';
    resBox.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Анализ семантики назначения по справочникам 115-ФЗ и критериям ЦБ 375-П...</div>';
  }

  try {
    const res = await fetch('/business/compliance/audit-payment', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        payer_inn: '7707083893',
        recipient_inn: '7724123456',
        amount: amount,
        payment_purpose: purpose,
        is_cash_withdrawal: isCash
      })
    });

    if (res.status === 401 || res.status === 403) {
      const err = await res.json().catch(() => ({}));
      if (resBox) resBox.innerHTML = `<div style="color:#b91c1c;">⛔ Доступ ограничен политикой безопасности: ${escapeHtml(err.detail || 'Доступно только Директору и CFO')}</div>`;
      show1CToast('Доступно только Директору и CFO', true);
      return;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка аудита платежа');
    }

    const data = await res.json();
    const badgeClass = data.is_compliant_115_fz ? 'success' : 'danger';

    let triggersHtml = '';
    if (data.triggers && data.triggers.length > 0) {
      triggersHtml = `
        <div style="margin-top:6px;padding:6px 8px;background:#fee2e2;border:1px solid #f87171;border-radius:4px;color:#991b1b;">
          <strong>Выявленные триггеры риска:</strong>
          <ul style="margin:4px 0 0 16px;padding:0;">
            ${data.triggers.map(t => `<li>${escapeHtml(t)}</li>`).join('')}
          </ul>
        </div>`;
    }

    let docsHtml = '';
    if (data.required_documents && data.required_documents.length > 0) {
      docsHtml = `
        <div style="margin-top:6px;padding:6px 8px;background:#fef3c7;border:1px solid #fcd34d;border-radius:4px;color:#92400e;font-size:11px;">
          <strong>Обязательный пакет документов для финмониторинга:</strong>
          <ul style="margin:4px 0 0 16px;padding:0;">
            ${data.required_documents.map(d => `<li>${escapeHtml(d)}</li>`).join('')}
          </ul>
        </div>`;
    }

    if (resBox) {
      resBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:6px;margin-bottom:8px;">
          <strong>Вердикт комплаенс:</strong>
          <span class="v8-badge ${badgeClass}" style="font-weight:700;">
            ${data.is_compliant_115_fz ? '✓ Платёж соответствует 115-ФЗ' : '⛔ Повышенный риск 115-ФЗ'}
          </span>
        </div>
        <div style="margin-bottom:6px;"><strong>Оценка:</strong> ${escapeHtml(data.verdict)}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;margin-bottom:6px;">
          <div>Обязательный контроль (≥1М ₽): <strong>${data.is_mandatory_control_threshold ? '<span style="color:#dc2626;">Да (сообщение в РФМ)</span>' : 'Нет'}</strong></div>
          <div>Признаки дробления: <strong>${data.is_splitting_detected ? '<span style="color:#dc2626;">Да (сумма близка к лимиту)</span>' : 'Нет'}</strong></div>
        </div>
        ${triggersHtml}
        ${docsHtml}
      `;
    }
    show1CToast(data.is_compliant_115_fz ? 'Платеж одобрен' : 'Платеж требует документов по 115-ФЗ', !data.is_compliant_115_fz);
  } catch (err) {
    if (resBox) resBox.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}

// 4. Margin Protection & Unit Economics Calculator
async function calculateDealMargin() {
  const client = document.getElementById('marginClient')?.value.trim() || 'Покупатель';
  const itemName = document.getElementById('marginItemName')?.value.trim() || 'Товар';
  const qty = parseFloat(document.getElementById('marginQty')?.value || '1');
  const cost = parseFloat(document.getElementById('marginCost')?.value || '0');
  const price = parseFloat(document.getElementById('marginPrice')?.value || '0');
  const discount = parseFloat(document.getElementById('marginDiscount')?.value || '0');
  const delay = parseInt(document.getElementById('marginDelay')?.value || '0', 10);
  const taxSystem = document.getElementById('marginTaxSystem')?.value || 'osno';
  const outBox = document.getElementById('marginCalculationOutput');

  if (qty <= 0 || cost <= 0 || price <= 0) {
    show1CToast('Заполните количество, себестоимость и цену', true);
    return;
  }

  if (outBox) {
    outBox.style.display = 'block';
    outBox.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Расчет юнит-экономики, ставки ЦБ 21% и налогов...</div>';
  }

  try {
    const res = await fetch('/business/margin/calculate-deal', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        customer_name: client,
        items: [{
          sku: 'KB-325',
          name: itemName,
          quantity: qty,
          purchase_price: cost,
          selling_price: price,
          discount_percent: discount
        }],
        tax_system: taxSystem,
        payment_delay_days: delay,
        auto_create_kanban_approval: true
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка расчета маржинальности');
    }

    const data = await res.json();
    const isApproved = data.is_approved;
    const badgeClass = isApproved ? 'success' : 'danger';

    let kanbanNotice = '';
    if (data.approval_task_id) {
      kanbanNotice = `
        <div style="margin-top:10px;padding:8px 10px;background:#fee2e2;border:1px solid #f87171;border-radius:4px;display:flex;align-items:center;justify-content:space-between;">
          <span style="color:#991b1b;font-weight:600;">
            📌 Создана задача в Канбан: #${data.approval_task_id} («Согласование скидки: ${escapeHtml(client)}»)
          </span>
          <button class="v8-btn v8-btn-primary" type="button" onclick="switchTab('kanban')">Открыть Канбан</button>
        </div>`;
    }

    if (outBox) {
      outBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:8px;margin-bottom:10px;">
          <div>
            <strong style="font-size:13px;">${escapeHtml(data.customer_name)}</strong>
            <div style="font-size:11px;color:var(--text-dim);">${escapeHtml(data.summary)}</div>
          </div>
          <span class="v8-badge ${badgeClass}" style="font-size:12px;font-weight:700;">
            ${isApproved ? '✓ Автосогласовано' : '⛔ Требуется согласование CFO'}
          </span>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:8px;margin-bottom:10px;">
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Выручка (с НДС)</div>
            <strong style="font-size:13px;">${formatCurrency(data.revenue_gross)} ₽</strong>
          </div>
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Себестоимость</div>
            <strong style="font-size:13px;">${formatCurrency(data.cost_goods_sold)} ₽</strong>
          </div>
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Налоги (НДС+прибыль/УСН)</div>
            <strong style="font-size:13px;">${formatCurrency(data.tax_amount)} ₽</strong>
          </div>
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Заморозка отсрочки (ЦБ 21%)</div>
            <strong style="font-size:13px;color:#dc2626;">-${formatCurrency(data.cost_of_capital_delay)} ₽</strong>
          </div>
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Чистая прибыль</div>
            <strong style="font-size:14px;color:${data.net_profit >= 0 ? '#16a34a' : '#dc2626'};">${formatCurrency(data.net_profit)} ₽</strong>
          </div>
          <div style="padding:6px 8px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Чистая рентабельность</div>
            <strong style="font-size:14px;color:${data.net_margin_percent >= 15 ? '#16a34a' : '#dc2626'};">${data.net_margin_percent.toFixed(1)}%</strong>
          </div>
        </div>
        ${kanbanNotice}
      `;
    }
    show1CToast(`Рентабельность сделки: ${data.net_margin_percent.toFixed(1)}% (${isApproved ? 'Одобрено' : 'Ниже порога 15%'})`);
  } catch (err) {
    if (outBox) outBox.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}

// 5. Debt Collection: Art 395 GK RF Penalty Only
async function calculatePenaltyOnly() {
  const debtor = document.getElementById('debtDebtor')?.value.trim();
  const debt = parseFloat(document.getElementById('debtAmount')?.value || '0');
  const dueDate = document.getElementById('debtDueDate')?.value;
  const outBox = document.getElementById('debtResultOutput');

  if (debt <= 0 || !dueDate) {
    show1CToast('Укажите сумму задолженности и срок оплаты', true);
    return;
  }

  if (outBox) {
    outBox.style.display = 'block';
    outBox.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Расчет процентов по периодам ключевых ставок ЦБ РФ...</div>';
  }

  try {
    const res = await fetch('/business/debt/calculate-penalty', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        debt_amount: debt,
        due_date: dueDate
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка расчета процентов');
    }

    const data = await res.json();
    let periodsTable = '';
    if (data.periods && data.periods.length > 0) {
      periodsTable = `
        <table class="v8-grid-table" style="margin-top:10px;">
          <thead>
            <tr>
              <th>Период просрочки</th>
              <th class="text-right">Дней</th>
              <th class="text-right">Ставка ЦБ</th>
              <th class="text-right">Дней в году</th>
              <th class="text-right">Пени (руб)</th>
            </tr>
          </thead>
          <tbody>
            ${data.periods.map(p => `
              <tr>
                <td>${escapeHtml(p.start_date)} — ${escapeHtml(p.end_date)}</td>
                <td class="text-right">${p.days}</td>
                <td class="text-right"><strong>${p.key_rate_percent}%</strong></td>
                <td class="text-right">${p.days_in_year}</td>
                <td class="text-right" style="font-weight:700;color:#dc2626;">${formatCurrency(p.penalty_rub)} ₽</td>
              </tr>
            `).join('')}
          </tbody>
        </table>`;
    }

    if (outBox) {
      outBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:6px;margin-bottom:8px;">
          <div>
            <strong>Расчет процентов по ст. 395 ГК РФ: ${escapeHtml(debtor || 'Должник')}</strong>
            <div style="font-size:11px;color:var(--text-dim);">${escapeHtml(data.formula_explanation)}</div>
          </div>
          <span class="v8-badge danger" style="font-size:13px;font-weight:700;">
            Итого пени: ${formatCurrency(data.total_penalty)} ₽
          </span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(140px, 1fr));gap:8px;margin-bottom:8px;">
          <div style="padding:6px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Основной долг</div>
            <strong>${formatCurrency(data.debt_amount)} ₽</strong>
          </div>
          <div style="padding:6px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Дней просрочки</div>
            <strong style="color:#dc2626;">${data.overdue_days} дн.</strong>
          </div>
          <div style="padding:6px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Действующая ставка ЦБ</div>
            <strong>${data.effective_key_rate_percent}%</strong>
          </div>
          <div style="padding:6px;background:var(--bg-main);border-radius:4px;">
            <div style="font-size:11px;color:var(--text-dim);">Всего к взысканию</div>
            <strong style="color:#dc2626;">${formatCurrency(data.debt_amount + data.total_penalty)} ₽</strong>
          </div>
        </div>
        ${periodsTable}
      `;
    }
    show1CToast(`Начислено пени: ${formatCurrency(data.total_penalty)} ₽ за ${data.overdue_days} дн.`);
  } catch (err) {
    if (outBox) outBox.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}

// 6. Debt Collection: Generate & Send Pre-Trial Claim
async function generateAndSendClaim() {
  const debtor = document.getElementById('debtDebtor')?.value.trim() || 'ООО «Контрагент»';
  const inn = document.getElementById('debtInn')?.value.trim() || '7707083893';
  const debt = parseFloat(document.getElementById('debtAmount')?.value || '0');
  const dueDate = document.getElementById('debtDueDate')?.value;
  const contract = document.getElementById('debtContract')?.value.trim() || 'Договор поставки';
  const email = document.getElementById('debtEmail')?.value.trim() || 'buh@alphatrade.ru';
  const outBox = document.getElementById('debtResultOutput');

  if (debt <= 0 || !dueDate) {
    show1CToast('Заполните параметры долга и срок оплаты', true);
    return;
  }

  if (outBox) {
    outBox.style.display = 'block';
    outBox.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Генерация юридического текста досудебной претензии и отправка в Outbox...</div>';
  }

  try {
    const res = await fetch('/business/debt/generate-claim', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        debtor_name: debtor,
        debtor_inn: inn,
        debtor_email: email,
        creditor_name: 'ООО «НейроТех Инновации»',
        contract_number: contract,
        contract_date: '2025-01-15',
        invoice_number: 'Счет № 41',
        invoice_date: '2026-01-10',
        principal_debt: debt,
        due_date: dueDate,
        payment_deadline_days: 10,
        arbitration_court_name: 'Арбитражный суд города Москвы',
        send_email_immediately: true
      })
    });

    if (res.status === 401 || res.status === 403) {
      const err = await res.json().catch(() => ({}));
      if (outBox) outBox.innerHTML = `<div style="color:#b91c1c;">⛔ Доступ запрещен: формирование претензий доступно только Руководству и Юристу/CFO</div>`;
      show1CToast('Формирование претензий доступно только Директору и CFO', true);
      return;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка генерации претензии');
    }

    const data = await res.json();
    if (outBox) {
      outBox.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border-color);padding-bottom:6px;margin-bottom:8px;">
          <div>
            <strong>Досудебная претензия № ${escapeHtml(data.claim_number)} от ${escapeHtml(data.claim_date)}</strong>
            <div style="font-size:11px;color:var(--text-dim);">Должник: ${escapeHtml(data.debtor_name)} (ИНН ${escapeHtml(data.debtor_inn)})</div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            <span class="v8-badge ${data.email_sent ? 'success' : 'warning'}">
              ${data.email_sent ? '✉️ Отправлено на ' + escapeHtml(email) : 'Черновик'}
            </span>
            <button class="v8-btn v8-btn-sm" type="button" onclick="copyClaimText()">Скопировать текст</button>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:6px;margin-bottom:8px;font-size:12px;">
          <div>Сумма долга: <strong>${formatCurrency(data.principal_debt)} ₽</strong></div>
          <div>Проценты ст. 395: <strong style="color:#dc2626;">+${formatCurrency(data.penalty_amount)} ₽</strong></div>
          <div>Итого по претензии: <strong style="color:#dc2626;font-size:13px;">${formatCurrency(data.total_claim_amount)} ₽</strong></div>
          <div>Просрочка: <strong>${data.overdue_days} дн.</strong></div>
        </div>

        <pre id="preTrialClaimTextPre" style="background:var(--bg-main);border:1px solid var(--border-color);border-radius:4px;padding:10px;font-size:11px;white-space:pre-wrap;max-height:240px;overflow-y:auto;font-family:monospace;">${escapeHtml(data.legal_claim_text)}</pre>
      `;
    }
    show1CToast(`Претензия №${data.claim_number} сформирована на сумму ${formatCurrency(data.total_claim_amount)} ₽`);
  } catch (err) {
    if (outBox) outBox.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}

function copyClaimText() {
  const pre = document.getElementById('preTrialClaimTextPre');
  if (pre) {
    navigator.clipboard.writeText(pre.textContent).then(() => {
      show1CToast('Текст досудебной претензии скопирован');
    });
  }
}

// 7. Smart Stock Rebalancing: ROP, EOQ, Dead Stock & 1C Purchase Order
let currentPurchaseOrderJson = null;

async function runStockRebalanceAnalysis() {
  const sumBox = document.getElementById('stockAnalysisSummary');
  const tbody = document.getElementById('stockAnalysisTbody');
  const poBox = document.getElementById('purchaseOrderBox');
  const poPre = document.getElementById('purchaseOrderJsonPre');

  if (sumBox) sumBox.innerHTML = '<span style="color:var(--text-dim);font-style:italic;">Расчет точек перезаказа (ROP), страховых запасов и партий Уилсона (EOQ)...</span>';

  const defaultStockData = [
    {
      sku: "КБ-325",
      name: "Кабель силовой ВВГнг-LS 3x2.5",
      current_stock: 250,
      daily_sales_avg: 50,
      daily_sales_std: 10,
      lead_time_days: 7,
      unit_cost: 80.0,
      order_fixed_cost: 1500.0,
      annual_holding_cost_rate: 0.25,
      days_without_sales: 0,
      supplier_name: "ООО «КабельСнабОпт»"
    },
    {
      sku: "ВА-47-29",
      name: "Выключатель автоматический ВА 47-29 1P 16A",
      current_stock: 40,
      daily_sales_avg: 15,
      daily_sales_std: 4,
      lead_time_days: 5,
      unit_cost: 185.0,
      order_fixed_cost: 1200.0,
      annual_holding_cost_rate: 0.25,
      days_without_sales: 0,
      supplier_name: "ЗАО «ЭлектроКомпонент»"
    },
    {
      sku: "СВ-LED36",
      name: "Светильник светодиодный LED 36W",
      current_stock: 85,
      daily_sales_avg: 0,
      daily_sales_std: 0,
      lead_time_days: 10,
      unit_cost: 850.0,
      order_fixed_cost: 1500.0,
      annual_holding_cost_rate: 0.25,
      days_without_sales: 118,
      supplier_name: "ЗАО «Световые Системы»"
    },
    {
      sku: "ТР-20М",
      name: "Труба гофрированная ПВХ d20 с протяжкой",
      current_stock: 1500,
      daily_sales_avg: 20,
      daily_sales_std: 5,
      lead_time_days: 3,
      unit_cost: 12.0,
      order_fixed_cost: 800.0,
      annual_holding_cost_rate: 0.25,
      days_without_sales: 0,
      supplier_name: "ООО «ПолимерТрейд»"
    }
  ];

  try {
    const res = await fetch('/business/stock/analyze-inventory', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        items: defaultStockData,
        service_level_z: 1.65,
        dead_stock_threshold_days: 90,
        generate_1c_order: true
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка анализа запасов');
    }

    const data = await res.json();
    currentPurchaseOrderJson = data.purchase_order_1c;

    if (sumBox) {
      sumBox.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <div>${escapeHtml(data.executive_summary)}</div>
          <div style="display:flex;gap:8px;">
            <span class="v8-badge danger">Дефицит: ${data.deficit_items_count} поз. (Заказ: ${formatCurrency(data.total_reorder_budget_rub)} ₽)</span>
            <span class="v8-badge warning">Неликвиды: ${data.dead_stock_items_count} поз. (Заморожено: ${formatCurrency(data.total_frozen_capital_rub)} ₽)</span>
          </div>
        </div>
      `;
    }

    if (tbody) {
      tbody.innerHTML = data.items.map(it => {
        let badge = '<span class="v8-badge success">Норма</span>';
        let actionBtn = '<span style="color:var(--text-dim);font-size:11px;">В норме</span>';

        if (it.status === 'DEFICIT') {
          badge = '<span class="v8-badge danger">Дефицит ROP</span>';
          actionBtn = `<button class="v8-btn v8-btn-primary" onclick="createKanbanTaskDirect('Заказ поставщику: ${escapeHtml(it.name)}', 'Заказать партию ${it.recommended_order_quantity} шт на сумму ${formatCurrency(it.estimated_purchase_cost)} ₽', 'high', this)">Заказать в 1С</button>`;
        } else if (it.status === 'DEAD_STOCK') {
          badge = '<span class="v8-badge warning">Неликвид >90 дн</span>';
          actionBtn = `<button class="v8-btn" onclick="createKanbanTaskDirect('Уценка неликвида: ${escapeHtml(it.name)}', 'Запустить уценку 15% или акцию для оптовиков (заморожено ${formatCurrency(it.frozen_capital_rub)} ₽)', 'medium', this)">Уценить 15%</button>`;
        } else if (it.status === 'SURPLUS') {
          badge = '<span class="v8-badge info">Избыток</span>';
          actionBtn = '<span style="color:var(--text-dim);font-size:11px;">Снизить закупки</span>';
        }

        return `
          <tr>
            <td>${badge}</td>
            <td><strong>${escapeHtml(it.sku)}</strong></td>
            <td>${escapeHtml(it.name)}</td>
            <td class="text-right">${it.current_stock}</td>
            <td class="text-right" style="font-weight:600;">${it.reorder_point_rop.toFixed(0)}</td>
            <td class="text-right">${it.economic_order_quantity_eoq.toFixed(0)}</td>
            <td class="text-right" style="font-weight:700;color:${it.recommended_order_quantity > 0 ? '#dc2626' : 'inherit'};">
              ${it.recommended_order_quantity > 0 ? it.recommended_order_quantity : '—'}
            </td>
            <td class="text-right" style="font-weight:700;">
              ${it.estimated_purchase_cost > 0 ? formatCurrency(it.estimated_purchase_cost) + ' ₽' : (it.frozen_capital_rub > 0 ? formatCurrency(it.frozen_capital_rub) + ' ₽' : '—')}
            </td>
            <td>${actionBtn}</td>
          </tr>
        `;
      }).join('');
    }

    if (poBox && currentPurchaseOrderJson) {
      poBox.style.display = 'block';
      if (poPre) poPre.textContent = JSON.stringify(currentPurchaseOrderJson, null, 2);
    }

    show1CToast(`Анализ завершен: ${data.deficit_items_count} поз. к заказу, ${data.dead_stock_items_count} неликвидов`);
  } catch (err) {
    if (sumBox) sumBox.innerHTML = `<span style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</span>`;
    show1CToast(err.message, true);
  }
}

function copyPurchaseOrderJson() {
  if (currentPurchaseOrderJson) {
    navigator.clipboard.writeText(JSON.stringify(currentPurchaseOrderJson, null, 2)).then(() => {
      show1CToast('JSON документа «ЗаказПоставщику» 1С скопирован');
    });
  }
}

// 8. Multimodal OCR: Sample Invoice Text & Parsing
function loadSampleInvoiceText() {
  const input = document.getElementById('ocrTextInput');
  if (input) {
    input.value = `Счет на оплату № 814 от 02 сентября 2026 г.
Поставщик: ООО "ЭлектроСнаб" ИНН 7724123456 КПП 772401001
Покупатель: ООО "НейроТех" ИНН 7707083893
Товары (работы, услуги):
1. Кабель силовой ВВГнг-LS 3x2.5 | 500 м | 80.00 руб | Сумма без НДС 40 000.00 | НДС 20% 8 000.00 | Всего 48 000.00 руб
2. Выключатель автоматический ВА 47-29 1P 16A | 40 шт | 185.00 руб | Сумма без НДС 7 400.00 | НДС 20% 1 480.00 | Всего 8 880.00 руб
Итого без НДС: 47 400.00 руб
В том числе НДС 20%: 9 480.00 руб
Всего к оплате с НДС: 56 880.00 руб`;
    show1CToast('Образец счёта с НДС 20% загружен');
  }
}

async function parseInvoiceOcr() {
  const text = document.getElementById('ocrTextInput')?.value.trim();
  const container = document.getElementById('ocrResultContainer');
  const headerInfo = document.getElementById('ocrHeaderInfo');
  const tbody = document.getElementById('ocrLinesTbody');

  if (!text) {
    show1CToast('Вставьте текст счёта или нажмите «Вставить образец»', true);
    return;
  }

  if (container) container.style.display = 'block';
  if (headerInfo) headerInfo.innerHTML = '<div style="color:var(--text-dim);font-style:italic;">Нечеткое распознавание (Fuzzy Levenshtein + Stemming) по справочнику номенклатуры 1С...</div>';

  try {
    const res = await fetch('/business/ocr/parse-invoice', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ raw_text: text, file_name: 'Счет_814.pdf' })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Ошибка обработки OCR документа');
    }

    const data = await res.json();
    const arithBadge = data.is_arithmetic_valid
      ? '<span class="v8-badge success">✓ Арифметика и НДС 20% верны</span>'
      : '<span class="v8-badge danger">✕ Ошибка расчёта НДС / суммы</span>';

    if (headerInfo) {
      headerInfo.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div>
            <strong style="font-size:13px;">Счёт № ${escapeHtml(data.invoice_number || 'б/н')} от ${escapeHtml(data.invoice_date || 'текущая дата')}</strong>
            <div style="font-size:11px;color:var(--text-dim);">
              Поставщик: <strong>${escapeHtml(data.supplier_name || 'Не указан')}</strong> (ИНН ${escapeHtml(data.supplier_inn || '—')}) • 
              Покупатель: ИНН ${escapeHtml(data.buyer_inn || '—')}
            </div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            ${arithBadge}
            <span class="v8-badge info">Всего с НДС: ${formatCurrency(data.total_amount)} ₽</span>
          </div>
        </div>
        <div style="font-size:11px;color:var(--text-main);">${escapeHtml(data.summary)}</div>
      `;
    }

    if (tbody) {
      tbody.innerHTML = data.lines.map(line => {
        const confPercent = Math.round(line.match_confidence * 100);
        const confClass = confPercent >= 80 ? 'success' : (confPercent >= 50 ? 'warning' : 'danger');

        return `
          <tr>
            <td>${line.line_number}</td>
            <td><strong>${escapeHtml(line.raw_name)}</strong></td>
            <td>
              ${line.matched_1c_name ? `
                <div style="font-weight:600;color:var(--text-main);">${escapeHtml(line.matched_1c_name)}</div>
                <small style="color:var(--text-dim);">Артикул: ${escapeHtml(line.matched_1c_sku || '—')}</small>
              ` : '<span style="color:#dc2626;">Не найдено в 1С</span>'}
            </td>
            <td class="text-right">
              <span class="v8-badge ${confClass}">${confPercent}%</span>
            </td>
            <td class="text-right">${line.quantity} ${escapeHtml(line.unit)}</td>
            <td class="text-right">${formatCurrency(line.unit_price)} ₽</td>
            <td class="text-right" style="font-weight:700;">${formatCurrency(line.line_total_amount)} ₽</td>
            <td>
              ${line.arithmetic_valid ? '<span style="color:#16a34a;">✓ ОК</span>' : `<span style="color:#dc2626;">✕ ${escapeHtml(line.discrepancy_note || 'Ошибка')}</span>`}
            </td>
          </tr>
        `;
      }).join('');
    }

    show1CToast(`Распознано позиций: ${data.lines.length}, сумма: ${formatCurrency(data.total_amount)} ₽`);
  } catch (err) {
    if (headerInfo) headerInfo.innerHTML = `<div style="color:#b91c1c;">Ошибка: ${escapeHtml(err.message)}</div>`;
    show1CToast(err.message, true);
  }
}
