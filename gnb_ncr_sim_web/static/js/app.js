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
let latestState = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove('hidden');

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    toast.classList.add('hidden');
  }, 2200);
}

function getNextResourceId() {
  if (latestState && Number.isInteger(Number(latestState.next_resource_id))) {
    return Number(latestState.next_resource_id);
  }

  if (latestState && Array.isArray(latestState.rules)) {
    return latestState.rules.length + 1;
  }

  return 1;
}

function setResourceIdInput() {
  const input = sendForm.querySelector('input[name="resource_id"]');

  if (!input) {
    return;
  }

  input.value = getNextResourceId();
  input.readOnly = true;
  input.classList.add('readonly-input');
}

function openModal(type) {
  currentType = type;
  modalTitle.textContent = `發送 ${type} 訊息`;

  setResourceIdInput();

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

  params.resource_id = getNextResourceId();

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
  ].join(' ');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function updateNodeState(state) {
  const gnbStatus = document.getElementById('gnbStatus');
  const ncrStatus = document.getElementById('ncrStatus');
  const ncrUeId = document.getElementById('ncrUeId');

  if (state.nodes && state.nodes.gnb && gnbStatus) {
    gnbStatus.textContent = state.nodes.gnb.status || 'unknown';
  }

  if (state.nodes && state.nodes.ncr && ncrStatus) {
    ncrStatus.textContent = state.nodes.ncr.status || 'unknown';
  }

  if (state.nodes && state.nodes.ncr && ncrUeId) {
    const ueId = state.nodes.ncr.ue_id;

    if (ueId) {
      ncrUeId.textContent = ueId;
      ncrUeId.classList.add('has-value');
    } else {
      ncrUeId.textContent = 'waiting...';
      ncrUeId.classList.remove('has-value');
    }
  }
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
              <td>#${escapeHtml(rule.params.resource_id)}</td>
              <td><span class="rule-type">${escapeHtml(rule.type)}</span></td>
              <td>${escapeHtml(rule.params.rsrc_id)}</td>
              <td>${escapeHtml(rule.params.beam)}</td>
              <td>${escapeHtml(rule.params.slotPeriod)}</td>
              <td>${escapeHtml(rule.params.slotOffset)}</td>
              <td>${escapeHtml(rule.params.symbol_offset)}</td>
              <td>${escapeHtml(rule.params.duration_in_symbols)}</td>
              <td>${escapeHtml(rule.params.ref_scs)}</td>
              <td><span class="rule-status">${escapeHtml(rule.status)}</span></td>
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
      <div class="log-type">${escapeHtml(message.type)}</div>
      <div class="log-detail">
        <strong>${escapeHtml(message.time)}</strong><br>
        ${escapeHtml(message.from)} → ${escapeHtml(message.to)}<br>
        ${escapeHtml(paramsToText(message.params))}<br>
        <span class="telnet-command">TELNET: ${escapeHtml(message.telnet_command || '')}</span>
      </div>
      <div class="log-status">${escapeHtml(message.status)}</div>
    </div>
  `).join('');
}

function applyState(state) {
  latestState = state;

  updateNodeState(state);
  renderMessages(state.messages || []);
  renderRules(state.rules || []);

  setResourceIdInput();
}

async function loadState() {
  const response = await fetch('/api/state');

  if (!response.ok) {
    throw new Error(`state api failed: ${response.status}`);
  }

  const state = await response.json();

  applyState(state);
}

async function sendMessage(event) {
  event.preventDefault();

  const payload = {
    type: currentType,
    params: collectParams(sendForm),
  };

  let result = null;

  try {
    const response = await fetch('/api/send', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload),
    });

    result = await response.json();

    if (!response.ok || !result.ok) {
      const detail = result.telnet_result
        ? `${result.error}\n${result.telnet_result}`
        : (result.error || '發送失敗');

      showToast(detail);

      if (result.state) {
        applyState(result.state);
      }

      return;
    }

    applyState(result.state);

    hideModal();
    showToast(`${currentType} 已透過 telnet 送到 gNB，規則已寫入列表`);

  } catch (error) {
    console.error(error);
    showToast(`發送失敗：${error.message}`);
  }
}

function refreshAll() {
  loadState().catch((error) => {
    console.error(error);
    showToast('載入狀態失敗');
  });
}

document.querySelectorAll('.send-btn').forEach((button) => {
  button.addEventListener('click', () => openModal(button.dataset.type));
});

closeModal.addEventListener('click', hideModal);
cancelBtn.addEventListener('click', hideModal);
refreshBtn.addEventListener('click', refreshAll);

sendForm.addEventListener('submit', sendMessage);

modalBackdrop.addEventListener('click', (event) => {
  if (event.target === modalBackdrop) {
    hideModal();
  }
});

refreshAll();

setInterval(() => {
  loadState().catch((error) => {
    console.error(error);
  });
}, 2000);
