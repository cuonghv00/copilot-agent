// background.js — Service Worker
// Responsibilities: WebSocket ↔ Python CLI, chrome.downloads, tab navigation, session resume

let ws = null;
let copilotTabId = null;
const WS_URL = 'ws://localhost:8765';
const COPILOT_BASE_URL = 'https://m365.cloud.microsoft/chat';

// --- WebSocket Connection ---

let reconnectDelay = 5000;
const MAX_RECONNECT_DELAY = 30000;

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log('[CopilotAgent BG] Connected to Python CLI');
        reconnectDelay = 5000; // reset on success
    };

    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        if (data.action === 'START_TASK') {
            await handleStartTask(data);
        }
    };

    ws.onclose = () => {
        console.log(`[CopilotAgent BG] Disconnected. Reconnecting in ${reconnectDelay/1000}s…`);
        setTimeout(() => {
            reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
            connectWebSocket();
        }, reconnectDelay);
    };

    ws.onerror = () => {
        // ERR_CONNECTION_REFUSED is expected when agent.py is not running yet.
        // onclose will handle reconnection automatically.
        console.log('[CopilotAgent BG] Connection failed (agent.py not running?). Will retry…');
    };
}

function sendToServer(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
    }
}

// --- Session Persistence ---

async function saveTabId(tabId) {
    copilotTabId = tabId;
    await chrome.storage.session.set({ copilotTabId: tabId });
}

async function loadTabId() {
    const result = await chrome.storage.session.get('copilotTabId');
    copilotTabId = result.copilotTabId || null;
    return copilotTabId;
}

// --- Task Handling ---

let pendingTask = null;

async function handleStartTask(taskData) {
    const isNewSession = taskData.is_new_session;
    const lastSessionId = taskData.last_session_id;
    pendingTask = taskData;

    // Find existing Copilot tab
    const tabs = await chrome.tabs.query({
        url: ['https://m365.cloud.microsoft/*', 'https://copilot.microsoft.com/*']
    });

    if (isNewSession) {
        sendToServer({ event: 'STATUS_UPDATE', status: 'NAVIGATING_NEW_CHAT', message: 'Opening new chat…' });

        if (tabs.length > 0) {
            copilotTabId = tabs[0].id;
            await chrome.tabs.update(copilotTabId, { url: COPILOT_BASE_URL, active: true });
        } else {
            const tab = await chrome.tabs.create({ url: COPILOT_BASE_URL, active: true });
            copilotTabId = tab.id;
        }
        await saveTabId(copilotTabId);

    } else {
        // Resume: navigate to saved conversation URL if we have an ID
        const resumeUrl = lastSessionId
            ? `${COPILOT_BASE_URL}/conversation/${lastSessionId}`
            : null;

        sendToServer({ event: 'STATUS_UPDATE', status: 'CONTINUING_CHAT', message: 'Resuming session…' });

        if (tabs.length > 0) {
            copilotTabId = tabs[0].id;
            if (resumeUrl) {
                // Navigate to exact conversation URL
                const currentTab = await chrome.tabs.get(copilotTabId);
                if (!currentTab.url.includes(lastSessionId)) {
                    await chrome.tabs.update(copilotTabId, { url: resumeUrl, active: true });
                    // Wait for content script to load and pull the task
                } else {
                    // Already on the right page, send directly
                    chrome.tabs.sendMessage(copilotTabId, { type: 'EXECUTE_TASK', taskData });
                }
            } else {
                chrome.tabs.sendMessage(copilotTabId, { type: 'EXECUTE_TASK', taskData });
            }
        } else {
            sendToServer({
                event: 'ERROR', status: 'ERROR', step: 'FIND_TAB',
                message: 'No Copilot tab open. Type /new to start a new session.'
            });
        }
    }
}

// --- Messages from Content Script ---

let activeDownloadId = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

    if (message.type === 'PAGE_READY_PULL_TASK') {
        if (pendingTask) {
            sendResponse({ hasTask: true, taskData: pendingTask });
            pendingTask = null;
            sendToServer({ event: 'STATUS_UPDATE', status: 'PAGE_READY', message: 'Page loaded, task started' });
        } else {
            sendResponse({ hasTask: false });
        }
        return true;
    }

    if (message.type === 'SESSION_ID') {
        // Forward conversation ID to CLI
        sendToServer({ event: 'SESSION_ID', id: message.id });
        return;
    }

    if (message.type === 'RESPONSE_TEXT') {
        // Forward Copilot response summary to CLI for display
        sendToServer({ event: 'RESPONSE_TEXT', text: message.text });
        return;
    }

    if (message.type === 'DOWNLOAD_FILE') {
        const downloadUrl = message.url;
        const filename = message.filename || 'CopilotAgent/output.zip';
        chrome.downloads.download(
            { url: downloadUrl, filename, conflictAction: 'overwrite' },
            (downloadId) => {
                if (chrome.runtime.lastError) {
                    sendToServer({
                        event: 'ERROR', status: 'ERROR', step: 'DOWNLOAD',
                        message: `Download failed: ${chrome.runtime.lastError.message}`
                    });
                } else {
                    activeDownloadId = downloadId;
                }
            }
        );
        return;
    }

    if (message.type === 'STATUS_UPDATE') {
        sendToServer({ event: 'STATUS_UPDATE', status: message.status, message: message.message || '' });
        return;
    }

    if (message.type === 'ERROR') {
        sendToServer({ event: 'ERROR', status: 'ERROR', message: message.message, step: message.step });
        return;
    }

    if (message.type === 'TASK_COMPLETE_NO_FILE') {
        // Text-only response — no file download. Signal CLI to stop waiting.
        sendToServer({ event: 'TASK_COMPLETE', status: 'NO_FILE' });
        return;
    }

});

// --- Download Completion ---

chrome.downloads.onChanged.addListener((delta) => {
    if (delta.id !== activeDownloadId) return;

    if (delta.state?.current === 'complete') {
        chrome.downloads.search({ id: delta.id }, (results) => {
            if (results.length > 0) {
                const filepath = results[0].filename;
                const filename = filepath.split('/').pop().split('\\').pop();
                sendToServer({
                    event: 'TASK_COMPLETE',
                    status: 'FILE_DOWNLOADED',
                    filename,
                    filepath,
                });
                activeDownloadId = null;
            }
        });
    }

    if (delta.state?.current === 'interrupted') {
        sendToServer({
            event: 'ERROR', status: 'ERROR', step: 'DOWNLOAD',
            message: `Download interrupted: ${delta.error?.current || 'unknown'}`
        });
        activeDownloadId = null;
    }
});

// --- Init ---
connectWebSocket();
