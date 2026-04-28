const modalBackdrop = document.getElementById('modalBackdrop');
const sendForm = document.getElementById('sendForm');
const modalTitle = document.getElementById('modalTitle');
const closeModal = document.getElementById('closeModal');
const cancelBtn = document.getElementById('cancelBtn');
const refreshBtn = document.getElementById('refreshBtn');
const messageLog = document.getElementById('messageLog');
const rulesList = document.getElementById('rulesList');
const toast = document.getElementById('toast');

let currentType = 'Periodic';
let toastTimer = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add('hidden'), 2200);
}

function openModal(type) {
  currentType = type;
  modalTitle.textContent = `發送 ${type} 訊息`;
  modalBackdrop.classList.remove('hidden');
}

function hideModal() {
  modalBackdrop.classList.add('hidden');
}

function collectParams(form) {
  const data = new FormData(form);
  const params = {};
  for (const [key, value] of data.entries()) {
    params[key] = Number(value);
  }
  return params;
}

function paramsToText(params) {
  return [
    `resource_id=${params.resource_id}`,
    `rsrc_id=${params.rsrc_id}`,
    `beam=${params.beam}`,
    `slotPeriod=${params.slotPeriod}`,
    `slotOffset=${params.slotOffset}`,
    `symbol_offset=${params.symbol_offset}`,
    `duration_in_symbols=${params.duration_in_symbols}`,
    `ref_scs=${params.ref_scs}`,
  ].join('  ');
}

function renderRules(rules) {
  if (!rules.length) {
    rulesList.className = 'rules-list empty';
    rulesList.textContent = '尚無規則';
    return;
  }

  rulesList.className = 'rules-list';
  rulesList.innerHTML = `
    <div class="rules-table-wrap">
      <table class="rules-table">
        <thead>
          <tr>
            <th>Rule ID</th>
            <th>Type</th>
            <th>Rsrc</th>
            <th>Beam</th>
            <th>Period</th>
            <th>Offset</th>
            <th>Symbol</th>
            <th>Duration</th>
            <th>Ref SCS</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${rules.map((rule) => `
            <tr>
              <td>#${rule.id}</td>
              <td><span class="rule-type">${rule.type}</span></td>
              <td>${rule.params.rsrc_id}</td>
              <td>${rule.params.beam}</td>
              <td>${rule.params.slotPeriod}</td>
              <td>${rule.params.slotOffset}</td>
              <td>${rule.params.symbol_offset}</td>
              <td>${rule.params.duration_in_symbols}</td>
              <td>${rule.params.ref_scs}</td>
              <td><span class="rule-status">${rule.status}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderMessages(messages) {
  if (!messages.length) {
    messageLog.className = 'message-log empty';
    messageLog.textContent = '尚未發送訊息';
    return;
  }

  messageLog.className = 'message-log';
  messageLog.innerHTML = messages.map((message) => `
    <div class="log-item">
      <div>
        <div class="log-type">${message.type}</div>
        <small>${message.time}</small>
      </div>
      <div class="log-detail">${message.from} → ${message.to}<br>${paramsToText(message.params)}</div>
      <div class="log-status">${message.status}</div>
    </div>
  `).join('');
}

async function loadState() {
  const response = await fetch('/api/state');
  const state = await response.json();
  document.getElementById('gnbStatus').textContent = state.nodes.gnb.status;
  document.getElementById('ncrStatus').textContent = state.nodes.ncr.status;
  renderMessages(state.messages || []);
  renderRules(state.rules || []);
}

async function sendMessage(event) {
  event.preventDefault();

  const payload = {
    type: currentType,
    params: collectParams(sendForm),
  };

  const response = await fetch('/api/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const result = await response.json();
  if (!response.ok || !result.ok) {
    showToast(result.error || '發送失敗');
    return;
  }

  renderMessages(result.state.messages || []);
  renderRules(result.state.rules || []);
  hideModal();
  showToast(`${currentType} 已送達 NCR，規則已寫入列表`);
}

function refreshAll() {
  loadState().catch(() => showToast('載入狀態失敗'));
}

document.querySelectorAll('.send-btn').forEach((button) => {
  button.addEventListener('click', () => openModal(button.dataset.type));
});

closeModal.addEventListener('click', hideModal);
cancelBtn.addEventListener('click', hideModal);
refreshBtn.addEventListener('click', refreshAll);
sendForm.addEventListener('submit', sendMessage);
modalBackdrop.addEventListener('click', (event) => {
  if (event.target === modalBackdrop) hideModal();
});

refreshAll();
