document.addEventListener('DOMContentLoaded', async () => {
  const tokenInput = document.getElementById('pineal_token');
  const cidInput = document.getElementById('atlas_client_id');
  const statusDiv = document.getElementById('status');
  const saveBtn = document.getElementById('save-btn');

  const storedAll = await chrome.storage.local.get(['pineal_token', 'atlas_client_id']);
  if (storedAll.pineal_token) {
    tokenInput.value = storedAll.pineal_token;
  }
  if (!storedAll.atlas_client_id) {
    storedAll.atlas_client_id = 'ext_' + Math.random().toString(36).slice(2, 9);
    await chrome.storage.local.set({ atlas_client_id: storedAll.atlas_client_id });
  }
  cidInput.value = storedAll.atlas_client_id;

  saveBtn.addEventListener('click', async () => {
    const token = tokenInput.value.trim();
    const cid = cidInput.value.trim() || storedAll.atlas_client_id;
    await chrome.storage.local.set({ pineal_token: token, atlas_client_id: cid });
    statusDiv.innerText = '✓ Ayarlar kaydedildi!';
    setTimeout(() => {
      statusDiv.innerText = '';
    }, 2000);
  });
});
