// background.js — Service Worker
// Responsibilities: WebSocket ↔ Python CLI, chrome.downloads, tab navigation

let ws = null;
let copilotTabId = null;
const WS_URL = 'ws://localhost:8765';
const COPILOT_BASE_URL = 'https://m365.cloud.microsoft/chat';

// --- WebSocket Connection ---

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log('[CopilotAgent BG] Connected to Python CLI');
    };

    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        console.log('[CopilotAgent BG] Received:', data);

        if (data.action === 'START_TASK') {
            await handleStartTask(data);
        }
    };

    ws.onclose = () => {
        console.log('[CopilotAgent BG] WebSocket disconnected. Reconnecting in 5s...');
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error('[CopilotAgent BG] WebSocket error:', err);
        ws.close();
    };
}

function sendToServer(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
    } else {
        console.error('[CopilotAgent BG] WebSocket not connected');
    }
}

// --- Task Handling ---

let pendingTask = null;

async function handleStartTask(taskData) {
    pendingTask = taskData;
    sendToServer({ event: 'STATUS_UPDATE', status: 'NAVIGATING_NEW_CHAT', message: 'Navigating to new chat...' });

    const tabs = await chrome.tabs.query({ url: ['https://m365.cloud.microsoft/*', 'https://copilot.microsoft.com/*'] });

    if (tabs.length > 0) {
        copilotTabId = tabs[0].id;
        await chrome.tabs.update(copilotTabId, { url: COPILOT_BASE_URL, active: true });
        // Optional: reload to ensure content script runs fresh if SPA doesn't trigger it
        await chrome.tabs.reload(copilotTabId);
    } else {
        const tab = await chrome.tabs.create({ url: COPILOT_BASE_URL, active: true });
        copilotTabId = tab.id;
    }
    // We now rely on the content script to pull the task when it loads.
}

// --- Messages from Content Script ---

let activeDownloadId = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[CopilotAgent BG] Message from content script:', message);

    if (message.type === 'PAGE_READY_PULL_TASK') {
        if (pendingTask) {
            sendResponse({ hasTask: true, taskData: pendingTask });
            pendingTask = null; // consume it
            sendToServer({ event: 'STATUS_UPDATE', status: 'PAGE_READY', message: 'Copilot page loaded and task pulled' });
        } else {
            sendResponse({ hasTask: false });
        }
        return true;
    }

    if (message.type === 'DOWNLOAD_FILE') {
        // Content script found a download URL
        const downloadUrl = message.url;
        const filename = message.filename || 'CopilotAgent/output.zip';

        try {
            chrome.downloads.download({
                url: downloadUrl,
                filename: filename,
                conflictAction: 'overwrite'
            }, (downloadId) => {
                if (chrome.runtime.lastError) {
                    sendToServer({
                        event: 'ERROR',
                        status: 'ERROR',
                        message: `Download failed: ${chrome.runtime.lastError.message}`,
                        step: 'DOWNLOAD'
                    });
                } else {
                    activeDownloadId = downloadId;
                    console.log(`[CopilotAgent BG] Download started: ${downloadId}`);
                }
            });
        } catch (e) {
            console.error('[CopilotAgent BG] Synchronous download error:', e);
            sendToServer({
                event: 'ERROR',
                status: 'ERROR',
                message: `Download failed synchronously: ${e.message}`,
                step: 'DOWNLOAD'
            });
        }
    }

    if (message.type === 'STATUS_UPDATE') {
        sendToServer({ event: 'STATUS_UPDATE', status: message.status, message: message.message || '' });
    }

    if (message.type === 'ERROR') {
        sendToServer({ event: 'ERROR', status: 'ERROR', message: message.message, step: message.step });
    }
});

// --- Download Completion Listener ---

chrome.downloads.onChanged.addListener((delta) => {
    if (delta.id === activeDownloadId) {
        if (delta.state && delta.state.current === 'complete') {
            chrome.downloads.search({ id: delta.id }, (results) => {
                if (results.length > 0) {
                    const filepath = results[0].filename;
                    // Extract just the basename, handling both / and \
                    const filename = filepath.split('/').pop().split('\\').pop();
                    console.log(`[CopilotAgent BG] Download complete: ${filename}`);
                    sendToServer({
                        event: 'TASK_COMPLETE',
                        status: 'FILE_DOWNLOADED',
                        filename: filename,
                        filepath: filepath
                    });
                    activeDownloadId = null;
                }
            });
        }

        if (delta.state && delta.state.current === 'interrupted') {
            sendToServer({
                event: 'ERROR',
                status: 'ERROR',
                message: `Download interrupted: ${delta.error?.current || 'unknown'}`,
                step: 'DOWNLOAD'
            });
            activeDownloadId = null;
        }
    }
});

// --- Initialize ---
connectWebSocket();
console.log('[CopilotAgent BG] Background service worker initialized');
