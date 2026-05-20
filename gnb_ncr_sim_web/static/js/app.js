const modalBackdrop = document.getElementById('modalBackdrop');
const sendForm = document.getElementById('sendForm');
const modalTitle = document.getElementById('modalTitle');
const closeModal = document.getElementById('closeModal');
const cancelBtn = document.getElementById('cancelBtn');
const refreshBtn = document.getElementById('refreshBtn');
const releaseAllBtn = document.getElementById('releaseAllBtn');
const messageLog = document.getElementById('messageLog');
const rulesList = document.getElementById('rulesList');
const toast = document.getElementById('toast');

let currentType = 'Periodic';
let toastTimer = null;
let latestState = null;
let releaseBusy = false;

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove('hidden');

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    toast.classList.add('hidden');
  }, 2200);
}

function getSubmitButton() {
  return sendForm.querySelector('button[type="submit"]');
}

function getModalStatusBox() {
  let box = document.getElementById('modalStatusBox');

  if (!box) {
    box = document.createElement('div');
    box.id = 'modalStatusBox';
    box.className = 'modal-status hidden';

    const footer = sendForm.querySelector('.modal-footer');
    sendForm.insertBefore(box, footer);
  }

  return box;
}

function setSendingState(isSending, message = '') {
  const submitBtn = getSubmitButton();
  const statusBox = getModalStatusBox();
  const formControls = sendForm.querySelectorAll('input, button');

  formControls.forEach((control) => {
    control.disabled = isSending;
  });

  if (closeModal) {
    closeModal.disabled = isSending;
  }

  if (cancelBtn) {
    cancelBtn.disabled = isSending;
  }

  if (submitBtn) {
    if (isSending) {
      submitBtn.dataset.originalText = submitBtn.textContent;
      submitBtn.innerHTML = '<span class="btn-spinner"></span> 發送中';
      submitBtn.classList.add('is-loading');
    } else {
      submitBtn.textContent = submitBtn.dataset.originalText || '發送';
      submitBtn.classList.remove('is-loading');
    }
  }

  if (isSending) {
    statusBox.innerHTML = `
      <div class="modal-status-spinner"></div>
      <div>
        <strong>正在透過 Telnet 發送指令</strong>
        <p>${escapeHtml(message || '等待 gNB 回應中，請勿重複送出。')}</p>
      </div>
    `;
    statusBox.classList.remove('hidden');
    modalBackdrop.classList.add('is-busy');
  } else {
    statusBox.classList.add('hidden');
    statusBox.innerHTML = '';
    modalBackdrop.classList.remove('is-busy');
  }
}

function setReleaseBusyState(isBusy, activeButton = null, busyText = '處理中') {
  releaseBusy = isBusy;

  const releaseButtons = document.querySelectorAll('.rule-release-btn');

  releaseButtons.forEach((button) => {
    button.disabled = isBusy;

    if (!isBusy) {
      button.textContent = button.dataset.originalText || 'Release';
      button.classList.remove('is-loading');
      return;
    }

    if (button === activeButton) {
      button.dataset.originalText = button.dataset.originalText || button.textContent;
      button.textContent = busyText;
      button.classList.add('is-loading');
    }
  });

  if (releaseAllBtn) {
    releaseAllBtn.disabled = isBusy;

    if (!isBusy) {
      releaseAllBtn.textContent = releaseAllBtn.dataset.originalText || 'Release All';
      releaseAllBtn.classList.remove('is-loading');
    } else if (activeButton === releaseAllBtn) {
      releaseAllBtn.dataset.originalText = releaseAllBtn.dataset.originalText || releaseAllBtn.textContent;
      releaseAllBtn.textContent = busyText;
      releaseAllBtn.classList.add('is-loading');
    }
  }
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
  if (modalBackdrop.classList.contains('is-busy')) {
    return;
  }

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
            <th>Action</th>
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
              <td>
                <button
                  type="button"
                  class="primary-btn rule-release-btn"
                  data-rule-id="${escapeHtml(rule.id ?? rule.params.resource_id)}"
                >
                  Release
                </button>
              </td>
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

  if (modalBackdrop.classList.contains('is-busy')) {
    return;
  }

  const payload = {
    type: currentType,
    params: collectParams(sendForm),
  };

  setSendingState(
    true,
    `準備送出 ${currentType} 指令，Rule ID #${payload.params.resource_id}`
  );

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

  } finally {
    setSendingState(false);
  }
}

async function releaseRule(ruleId, button) {
  if (releaseBusy) {
    return;
  }

  setReleaseBusyState(true, button, '釋放中');

  try {
    const response = await fetch('/api/release', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        rule_id: Number(ruleId),
      }),
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      const detail = result.telnet_result
        ? `${result.error}\n${result.telnet_result}`
        : (result.error || 'Release 失敗');

      showToast(detail);

      if (result.state) {
        applyState(result.state);
      }

      return;
    }

    applyState(result.state);
    showToast(`Rule #${ruleId} 已透過 telnet 送出 Release`);

  } catch (error) {
    console.error(error);
    showToast(`Release 失敗：${error.message}`);

  } finally {
    setReleaseBusyState(false);
  }
}

async function releaseAllRules() {
  if (releaseBusy) {
    return;
  }

  setReleaseBusyState(true, releaseAllBtn, '釋放中');

  try {
    const response = await fetch('/api/release_all', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({}),
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      const detail = result.telnet_result
        ? `${result.error}\n${result.telnet_result}`
        : (result.error || 'Release All 失敗');

      showToast(detail);

      if (result.state) {
        applyState(result.state);
      }

      return;
    }

    applyState(result.state);
    showToast('Release All 已透過 telnet 送到 gNB，規則列表已清空');

  } catch (error) {
    console.error(error);
    showToast(`Release All 失敗：${error.message}`);

  } finally {
    setReleaseBusyState(false);
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

if (releaseAllBtn) {
  releaseAllBtn.addEventListener('click', releaseAllRules);
}

rulesList.addEventListener('click', (event) => {
  const button = event.target.closest('.rule-release-btn');

  if (!button) {
    return;
  }

  releaseRule(button.dataset.ruleId, button);
});

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