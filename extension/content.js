// content.js — DOM Automation for M365 Copilot Web
// Responsibilities: Session ID extraction, Model Selection, Prompt Input, Send, Observe Response, Download

const SELECTORS = {
    newChatButton: 'a[aria-label="New chat"], button[aria-label="New chat"]',
    modelSelector: '#gptModeSwitcher, button[aria-label="Model Selector"]',
    chatInput: '#m365-chat-editor-target-element',
    sendButton: 'button[aria-label="Send"], button.fai-SendButton',
    // Indicators that response is fully complete
    responseDone: '[data-testid="copy-button"], button[aria-label="Copy"], button[aria-label="Like"], button[aria-label="Dislike"]',
};

const MODEL_MAPPING = {
    'auto':   ['Auto'],
    'quick':  ['Quick response'],
    'think':  ['Think deeper'],
    'gpt5.5': ['GPT', '5.5'],
    'gpt 5.5': ['GPT', '5.5'],
    'gpt5.6': ['GPT', '5.6'],
    'gpt 5.6': ['GPT', '5.6'],
    'sonnet': ['Anthropic', 'Sonnet'],
    'opus':   ['Anthropic', 'Opus'],
    'gpt':    ['OpenAI'],
};

// --- Utilities ---

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForElement(selector, timeoutMs = 15000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const el = document.querySelector(selector);
        if (el) return el;
        await sleep(500);
    }
    return null;
}

function sendStatus(status, message = '') {
    chrome.runtime.sendMessage({ type: 'STATUS_UPDATE', status, message });
}

function sendError(message, step) {
    chrome.runtime.sendMessage({ type: 'ERROR', message, step });
}

// --- Session ID ---

function extractAndReportSessionId() {
    const match = window.location.href.match(/\/conversation\/([0-9a-f-]{36})/i);
    if (match) {
        chrome.runtime.sendMessage({ type: 'SESSION_ID', id: match[1] });
    }
}

// --- Step 0: New Chat ---

async function clickNewChat() {
    const btn = await waitForElement(SELECTORS.newChatButton, 5000);
    if (btn) {
        btn.click();
        sendStatus('NEW_CHAT_CLICKED', 'Clicked New Chat');
        await sleep(1500);
    }
}

// --- Step 1: Model Selection ---

async function selectModel(modelName) {
    sendStatus('MODEL_SELECTION', `Selecting model: ${modelName}`);
    const modelBtn = await waitForElement(SELECTORS.modelSelector, 5000);
    if (!modelBtn) {
        sendStatus('MODEL_SKIPPED', 'Model selector not found');
        return;
    }

    modelBtn.click();
    await sleep(1000);

    const findMenuItem = (text) => {
        const items = Array.from(document.querySelectorAll(
            '.fai-CapabilityPickerMenuItem, [role="menuitem"], [role="option"]'
        ));
        return items.find(el => el.textContent.toLowerCase().includes(text.toLowerCase()));
    };

    const path = MODEL_MAPPING[modelName.toLowerCase()] || [modelName];
    let found = false;

    for (const step of path) {
        const item = findMenuItem(step);
        if (item) {
            item.click();
            await sleep(800);
            found = true;
        } else {
            break;
        }
    }

    if (!found) {
        // Close the menu if model not found
        modelBtn.click();
        sendStatus('MODEL_SKIPPED', `Model "${modelName}" not in menu, using current`);
        await sleep(500);
    } else {
        sendStatus('MODEL_SELECTED', `Model selected: ${modelName}`);
    }
}

// --- Step 2: Input Prompt ---

async function inputPrompt(fullPrompt) {
    sendStatus('PROMPT_FINDING', 'Finding chat input…');
    let editor = await waitForElement(SELECTORS.chatInput, 8000);
    if (!editor) {
        editor = await waitForElement('[contenteditable="true"]', 3000);
    }
    if (!editor) {
        sendError('Chat input not found', 'PROMPT_INPUT');
        return false;
    }

    editor.focus();
    await sleep(300);

    // Clear existing content
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    await sleep(200);

    // Insert text preserving newlines.
    // execCommand('insertText') strips \n in most contenteditable editors,
    // so we split by line and use insertParagraph between each line.
    const lines = fullPrompt.split('\n');
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].length > 0) {
            document.execCommand('insertText', false, lines[i]);
        }
        if (i < lines.length - 1) {
            document.execCommand('insertParagraph', false, null);
        }
    }

    await sleep(300);
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    editor.dispatchEvent(new Event('change', { bubbles: true }));
    sendStatus('PROMPT_ENTERED', 'Prompt entered');
    return true;
}

// --- Step 3: Send ---

async function clickSend() {
    await sleep(500);
    const btn = await waitForElement(SELECTORS.sendButton, 5000);
    if (!btn) {
        sendError('Send button not found', 'SEND');
        return false;
    }
    btn.click();
    sendStatus('PROMPT_SENT', 'Prompt sent');
    return true;
}

// --- Step 4: Observe Response ---

async function observeResponse() {
    sendStatus('WAITING_RESPONSE', 'Waiting for Copilot response…');

    return new Promise((resolve) => {
        let lastMutation = Date.now();
        let downloadFound = false;
        let settled = false;

        function cleanup() {
            observer.disconnect();
            clearInterval(checker);
            clearTimeout(hardTimeout);
        }

        function finish(result) {
            if (settled) return;
            settled = true;
            cleanup();
            resolve(result);
        }

        const observer = new MutationObserver(() => {
            lastMutation = Date.now();
            if (!downloadFound) {
                const dl = findDownloadLink();
                if (dl) {
                    downloadFound = true;
                    // Wait a moment for response text to fully render
                    setTimeout(() => {
                        const summary = extractResponseSummary();
                        if (summary) {
                            chrome.runtime.sendMessage({ type: 'RESPONSE_TEXT', text: summary });
                        }
                        finish(dl);
                    }, 2500);
                }
            }
        });

        observer.observe(document.body, { childList: true, subtree: true, characterData: true });

        // Check periodically for "response done" signals
        const checker = setInterval(() => {
            const elapsed = Date.now() - lastMutation;

            // Check if response-complete indicators are present
            const doneIndicator = document.querySelector(SELECTORS.responseDone);
            if (doneIndicator && elapsed > 2000 && !downloadFound) {
                const dl = findDownloadLink();
                if (dl) {
                    downloadFound = true;
                    const summary = extractResponseSummary();
                    if (summary) {
                        chrome.runtime.sendMessage({ type: 'RESPONSE_TEXT', text: summary });
                    }
                    finish(dl);
                } else if (elapsed > 8000) {
                    // Response done but no download link
                    const summary = extractResponseSummary();
                    if (summary) {
                        chrome.runtime.sendMessage({ type: 'RESPONSE_TEXT', text: summary });
                    }
                    finish(null);
                }
            }

            // Fallback: no mutations for 12s
            if (elapsed > 12000 && !downloadFound) {
                const dl = findDownloadLink();
                const summary = extractResponseSummary();
                if (summary) chrome.runtime.sendMessage({ type: 'RESPONSE_TEXT', text: summary });
                finish(dl);
            }
        }, 2000);

        // Hard timeout: 8 minutes
        const hardTimeout = setTimeout(() => finish(null), 480000);
    });
}

// --- Extract response text summary ---

function extractResponseSummary() {
    // Get the last assistant message block
    const blocks = document.querySelectorAll(
        '[data-testid*="message"], .message-content, [class*="response"], [class*="assistant"]'
    );
    if (blocks.length === 0) return '';

    const last = blocks[blocks.length - 1];
    const text = last.innerText || last.textContent || '';
    // Return first 1500 chars as summary
    return text.trim().slice(0, 1500);
}

// --- Find Download Link ---

/** Return true if URL looks like an actual downloadable file, not a page navigation URL */
function isDownloadableUrl(url) {
    if (!url) return false;
    if (url.startsWith('blob:')) return true;
    if (url.startsWith('data:')) return true;
    // Must have a file extension that suggests a download
    try {
        const u = new URL(url);
        const path = u.pathname.toLowerCase();
        // Reject if it's a copilot chat/conversation page URL
        if (u.hostname.includes('m365.cloud.microsoft') || u.hostname.includes('copilot.microsoft.com')) {
            if (path.includes('/chat') || path.includes('/conversation')) return false;
        }
        // Accept if path ends with a known file extension
        return /\.(zip|tar\.gz|tgz|gz|rar|7z|pdf|docx?|xlsx?)$/i.test(path);
    } catch {
        return false;
    }
}

function findDownloadLink() {
    // Priority 1: <a download> with .zip href — must be real file URL
    for (const a of document.querySelectorAll('a[download]')) {
        if (isDownloadableUrl(a.href)) {
            return { url: a.href, filename: a.download || 'output.zip' };
        }
    }

    // Priority 2: <a> with .zip in href
    for (const a of document.querySelectorAll('a[href*=".zip"]')) {
        if (isDownloadableUrl(a.href)) {
            return { url: a.href, filename: a.download || 'output.zip' };
        }
    }

    // Priority 3: blob: URL links
    for (const a of document.querySelectorAll('a[href^="blob:"]')) {
        if (a.href) return { url: a.href, filename: a.download || 'output.zip' };
    }

    // Priority 4: aria-label containing "Download" — validate URL
    for (const a of document.querySelectorAll('a[aria-label*="Download" i]')) {
        if (isDownloadableUrl(a.href)) {
            return { url: a.href, filename: a.download || 'output.zip' };
        }
    }

    // Priority 5: button with "Download" text that also suggests a zip/code/archive file.
    // We intentionally skip generic "Download" buttons (e.g. CSV export) to avoid downloading
    // non-zip files. Only click if the button context hints at a zip or source-code archive.
    const _zipHints = ['zip', 'source', 'code', 'archive', 'project', '.zip'];
    const buttons = Array.from(document.querySelectorAll('button'));
    const dlBtn = buttons.find(b => {
        const t = (b.textContent || '').toLowerCase().trim();
        const l = (b.getAttribute('aria-label') || '').toLowerCase();
        const isDownloadBtn = (t === 'download' || t.startsWith('download ') || l.includes('download'));
        if (!isDownloadBtn) return false;
        // Accept only if nearby context or label hints at zip/archive
        const ctx = (b.closest('[data-testid], .message-content, article, section')
            ?.textContent || '').toLowerCase();
        return _zipHints.some(h => l.includes(h) || t.includes(h) || ctx.includes(h));
    });
    if (dlBtn) {
        dlBtn.click();
        return { url: '__BUTTON_CLICKED__', filename: 'output.zip' };
    }

    return null;
}

// --- Main Task Executor ---

async function executeTask(taskData) {
    const { model, prompt, is_new_session } = taskData;

    if (is_new_session) {
        await clickNewChat();
    }
    
    if (model) {
        await selectModel(model);
    }
    
    const inputOk = await inputPrompt(prompt);
    if (!inputOk) return;

    const sendOk = await clickSend();
    if (!sendOk) return;

    // After send, extract and report session ID (URL may update)
    await sleep(2000);
    extractAndReportSessionId();

    const downloadData = await observeResponse();

    // Extract session ID again after response is complete because URL might update late
    extractAndReportSessionId();

    if (!downloadData) {
        // No download link — this is a normal text-only response.
        // RESPONSE_TEXT was already sent. Signal completion to Python CLI.
        chrome.runtime.sendMessage({ type: 'TASK_COMPLETE_NO_FILE' });
        return;
    }

    if (downloadData.url === '__BUTTON_CLICKED__') {
        sendStatus('DOWNLOADING', 'Clicked download button, waiting for browser…');
        return; // background.js download listener will catch it
    }

    sendStatus('DOWNLOADING', `Downloading: ${downloadData.url.substring(0, 60)}…`);

    try {
        if (downloadData.url.startsWith('blob:')) {
            const res = await fetch(downloadData.url);
            const blob = await res.blob();
            const reader = new FileReader();
            reader.onloadend = () => {
                chrome.runtime.sendMessage({
                    type: 'DOWNLOAD_FILE',
                    url: reader.result,
                    filename: `CopilotAgent/${downloadData.filename}`,
                });
            };
            reader.readAsDataURL(blob);
        } else {
            chrome.runtime.sendMessage({
                type: 'DOWNLOAD_FILE',
                url: downloadData.url,
                filename: `CopilotAgent/${downloadData.filename}`,
            });
        }
    } catch (e) {
        sendError(`Failed to download: ${e.message}`, 'DOWNLOAD');
    }
}

// --- Initialization ---

chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'EXECUTE_TASK') {
        sendStatus('TASK_RECEIVED', 'Executing task in current session…');
        executeTask(message.taskData);
    }
});

// Report session ID on load
extractAndReportSessionId();

// Pull pending task from background on page load
setTimeout(() => {
    chrome.runtime.sendMessage({ type: 'PAGE_READY_PULL_TASK' }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response?.hasTask) {
            sendStatus('TASK_RECEIVED', 'Pulled pending task…');
            executeTask(response.taskData);
        }
    });
}, 3000);
