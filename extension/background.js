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

async function handleStartTask(taskData) {
    // Step 1: Find or create Copilot tab
    sendToServer({ event: 'STATUS_UPDATE', status: 'NAVIGATING_NEW_CHAT', message: 'Navigating to new chat...' });

    const tabs = await chrome.tabs.query({ url: ['https://m365.cloud.microsoft/*', 'https://copilot.microsoft.com/*'] });

    if (tabs.length > 0) {
        copilotTabId = tabs[0].id;
        await chrome.tabs.update(copilotTabId, { url: COPILOT_BASE_URL, active: true });
    } else {
        const tab = await chrome.tabs.create({ url: COPILOT_BASE_URL, active: true });
        copilotTabId = tab.id;
    }

    // Step 2: Wait for page to load, then send task to content script
    chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo) {
        if (tabId === copilotTabId && changeInfo.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);

            // Small delay to let Copilot UI fully render
            setTimeout(() => {
                sendToServer({ event: 'STATUS_UPDATE', status: 'PAGE_READY', message: 'Copilot page loaded' });
                chrome.tabs.sendMessage(copilotTabId, {
                    type: 'EXECUTE_TASK',
                    ...taskData
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        console.error('[CopilotAgent BG] sendMessage error:', chrome.runtime.lastError.message);
                        sendToServer({ 
                            event: 'ERROR', 
                            status: 'ERROR', 
                            message: 'Không tìm thấy Content Script. Hãy thử Refresh (F5) tab Copilot trên trình duyệt rồi thử lại!', 
                            step: 'INJECTION' 
                        });
                    }
                });
            }, 3000);
        }
    });
}

// --- Messages from Content Script ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[CopilotAgent BG] Message from content script:', message);

    if (message.type === 'DOWNLOAD_FILE') {
        // Content script found a download URL
        const downloadUrl = message.url;
        const filename = message.filename || 'CopilotAgent/output.zip';

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
                console.log(`[CopilotAgent BG] Download started: ${downloadId}`);
            }
        });
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
    if (delta.state && delta.state.current === 'complete') {
        chrome.downloads.search({ id: delta.id }, (results) => {
            if (results.length > 0 && results[0].filename.includes('CopilotAgent')) {
                const filename = results[0].filename.split('/').pop();
                console.log(`[CopilotAgent BG] Download complete: ${filename}`);
                sendToServer({
                    event: 'TASK_COMPLETE',
                    status: 'FILE_DOWNLOADED',
                    filename: filename
                });
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
    }
});

// --- Initialize ---
connectWebSocket();
console.log('[CopilotAgent BG] Background service worker initialized');
