document.addEventListener('DOMContentLoaded', async () => {
  const tokenInput = document.getElementById('pineal_token');
  const statusDiv = document.getElementById('status');
  const saveBtn = document.getElementById('save-btn');

  const stored = await chrome.storage.local.get(['pineal_token']);
  if (stored.pineal_token) {
    tokenInput.value = stored.pineal_token;
  }

  saveBtn.addEventListener('click', async () => {
    const token = tokenInput.value.trim();
    await chrome.storage.local.set({ pineal_token: token });
    statusDiv.innerText = '✓ Ayarlar kaydedildi!';
    setTimeout(() => {
      statusDiv.innerText = '';
    }, 2000);
  });
});
