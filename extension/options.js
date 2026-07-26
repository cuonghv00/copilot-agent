// options.js — Copilot Agent Extension Settings

const DEFAULT_PORT = 8765;

async function loadSettings() {
    const { wsPort = DEFAULT_PORT } = await chrome.storage.local.get({ wsPort: DEFAULT_PORT });
    document.getElementById('wsPort').value = wsPort;
}

async function saveSettings() {
    const raw = document.getElementById('wsPort').value.trim();
    const port = parseInt(raw, 10);

    if (!raw || isNaN(port) || port < 1024 || port > 65535) {
        const status = document.getElementById('status');
        status.textContent = '⚠ Invalid port (must be 1024–65535)';
        status.style.color = '#f87171';
        status.classList.add('show');
        setTimeout(() => status.classList.remove('show'), 3000);
        return;
    }

    await chrome.storage.local.set({ wsPort: port });

    // Notify background to reconnect with new port
    chrome.runtime.sendMessage({ type: 'RECONNECT_WS' });

    const status = document.getElementById('status');
    status.textContent = '✓ Settings saved — reconnecting…';
    status.style.color = '#4ade80';
    status.classList.add('show');
    setTimeout(() => status.classList.remove('show'), 2500);
}

document.getElementById('saveBtn').addEventListener('click', saveSettings);
document.getElementById('wsPort').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') saveSettings();
});

loadSettings();
