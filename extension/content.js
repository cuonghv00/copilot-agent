// content.js — DOM Automation for M365 Copilot Web
// Responsibilities: Model Selection → Prompt Input → Send → Observe Response → Find Download

const SELECTORS = {
    modelSelector: '#gptModeSwitcher, button[aria-label="Model Selector"]',
    chatInput: '#m365-chat-editor-target-element',
    sendButton: 'button[aria-label="Send"], button.fai-SendButton',
    temporaryChat: 'button[aria-label="Temporary chat"]',
};

const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

// --- Utility Functions ---

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

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

// --- Step 1: Select Model ---

async function selectModel(modelName) {
    const modelBtn = await waitForElement(SELECTORS.modelSelector);
    if (!modelBtn) {
        sendError('Model Selector button not found', 'MODEL_SELECTION');
        return false;
    }

    modelBtn.click();
    await sleep(1000);

    // Find the menu item matching the model name
    const menuItems = Array.from(document.querySelectorAll(
        '[role="menuitem"], [role="option"], [role="menuitemradio"]'
    ));
    const target = menuItems.find(item =>
        item.textContent.toLowerCase().includes(modelName.toLowerCase())
    );

    if (target) {
        target.click();
        sendStatus('MODEL_SELECTED', `Selected model: ${modelName}`);
        await sleep(500);
        return true;
    } else {
        // Close the menu by clicking elsewhere
        modelBtn.click();
        sendStatus('MODEL_SELECTED', `Model "${modelName}" not found in menu, using default`);
        await sleep(500);
        return true;  // Continue with default model
    }
}

// --- Step 2: Input Prompt ---

async function inputPrompt(fullPrompt) {
    const editor = await waitForElement(SELECTORS.chatInput);
    if (!editor) {
        sendError('Chat input element not found', 'PROMPT_INPUT');
        return false;
    }

    editor.focus();
    await sleep(300);

    // Clear existing content
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    await sleep(200);

    // Insert text using execCommand for Fluent UI React compatibility
    document.execCommand('insertText', false, fullPrompt);
    await sleep(300);

    // Dispatch events to ensure React state updates
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    editor.dispatchEvent(new Event('change', { bubbles: true }));

    sendStatus('PROMPT_ENTERED', 'Prompt typed into chat input');
    return true;
}

// --- Step 3: Click Send ---

async function clickSend() {
    // Wait a moment for the Send button to become active
    await sleep(500);
    const sendBtn = await waitForElement(SELECTORS.sendButton);
    if (!sendBtn) {
        sendError('Send button not found', 'SEND');
        return false;
    }

    sendBtn.click();
    sendStatus('PROMPT_SENT', 'Prompt sent to Copilot');
    return true;
}

// --- Step 4: Observe Response & Find Download ---

async function observeResponse() {
    sendStatus('WAITING_RESPONSE', 'Waiting for Copilot to generate response...');

    return new Promise((resolve) => {
        let lastMutationTime = Date.now();
        let checkInterval = null;
        let downloadFound = false;

        const observer = new MutationObserver((mutations) => {
            lastMutationTime = Date.now();

            // Check for download links in new content
            if (!downloadFound) {
                const downloadLink = findDownloadLink();
                if (downloadLink) {
                    downloadFound = true;
                    // Wait a bit more to ensure response is fully complete
                    setTimeout(() => {
                        cleanup();
                        resolve(downloadLink);
                    }, 3000);
                }
            }
        });

        observer.observe(document.body, { childList: true, subtree: true, characterData: true });

        // Periodically check if response has stopped generating
        checkInterval = setInterval(() => {
            const elapsed = Date.now() - lastMutationTime;

            // If no mutations for 10 seconds, response is likely complete
            if (elapsed > 10000 && !downloadFound) {
                const downloadLink = findDownloadLink();
                if (downloadLink) {
                    downloadFound = true;
                    cleanup();
                    resolve(downloadLink);
                } else {
                    // Response finished but no download link found
                    cleanup();
                    resolve(null);
                }
            }
        }, 2000);

        // Timeout after 5 minutes
        const timeout = setTimeout(() => {
            if (!downloadFound) {
                cleanup();
                resolve(null);
            }
        }, 300000);

        function cleanup() {
            observer.disconnect();
            clearInterval(checkInterval);
            clearTimeout(timeout);
        }
    });
}

function findDownloadLink() {
    // Strategy 1: Look for <a> tags with download attribute
    const downloadAnchors = document.querySelectorAll('a[download]');
    for (const a of downloadAnchors) {
        if (a.href) return a.href;
    }

    // Strategy 2: Look for links to zip files
    const zipLinks = document.querySelectorAll('a[href*=".zip"]');
    for (const a of zipLinks) {
        if (a.href) return a.href;
    }

    // Strategy 3: Look for buttons with download-related text
    const buttons = Array.from(document.querySelectorAll('button'));
    const downloadBtn = buttons.find(b => {
        const text = (b.textContent || '').toLowerCase();
        const label = (b.getAttribute('aria-label') || '').toLowerCase();
        return text.includes('download') || label.includes('download');
    });
    if (downloadBtn) {
        // Click the download button and let the browser handle it
        downloadBtn.click();
        return '__CLICKED_DOWNLOAD_BUTTON__';
    }

    return null;
}

// --- Main Task Executor ---

async function executeTask(taskData) {
    const { model, prompt, system_instruction, onedrive_link } = taskData;

    // Build full prompt
    const fullPrompt = [
        system_instruction || '',
        '',
        `Link OneDrive chứa mã nguồn: ${onedrive_link}`,
        '',
        `YÊU CẦU: ${prompt}`,
        '',
        'QUY ĐỊNH KẾT QUẢ: Sau khi hoàn thành, hãy tạo file nén (.zip) chứa toàn bộ các file đã được chỉnh sửa và cung cấp link/nút TẢI VỀ cho file này.'
    ].join('\n');

    // Step 1: Select model
    if (model) {
        const modelOk = await selectModel(model);
        if (!modelOk) return;
    }

    // Step 2: Input prompt
    const inputOk = await inputPrompt(fullPrompt);
    if (!inputOk) return;

    // Step 3: Click Send
    const sendOk = await clickSend();
    if (!sendOk) return;

    // Step 4: Observe response and find download link
    const downloadUrl = await observeResponse();

    if (downloadUrl && downloadUrl !== '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', `Found download URL: ${downloadUrl}`);
        chrome.runtime.sendMessage({
            type: 'DOWNLOAD_FILE',
            url: downloadUrl,
            filename: 'CopilotAgent/output.zip'
        });
    } else if (downloadUrl === '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', 'Clicked download button, waiting for browser to handle...');
        // The browser download will be caught by background.js download listener
    } else {
        sendError('No download link found in Copilot response', 'DOWNLOAD_DETECTION');
    }
}

// --- Message Listener ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'EXECUTE_TASK') {
        console.log('[CopilotAgent CS] Received task:', message);
        executeTask(message);
    }
});

console.log('[CopilotAgent CS] Content script loaded on', window.location.href);
