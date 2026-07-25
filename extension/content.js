// content.js — DOM Automation for M365 Copilot Web
// Responsibilities: Model Selection → Prompt Input → Send → Observe Response → Find Download

const SELECTORS = {
    newChatButton: 'a[aria-label="New chat"], button[aria-label="New chat"]',
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

// --- Step 0: New Chat ---

async function clickNewChat() {
    sendStatus('NEW_CHAT', 'Looking for New Chat button...');
    const btn = await waitForElement(SELECTORS.newChatButton, 5000);
    if (btn) {
        btn.click();
        sendStatus('NEW_CHAT_CLICKED', 'Clicked New Chat button');
        await sleep(1000);
    } else {
        sendStatus('NEW_CHAT_SKIPPED', 'New Chat button not found, continuing...');
    }
}

const MODEL_MAPPING = {
    'auto': ['Auto'],
    'quick': ['Quick response'],
    'think': ['Think deeper'],
    'sonnet': ['Claude', 'Sonnet'],
    'opus': ['Claude', 'Opus'],
    'gpt5.5': ['GPT', '5.5'],
    'gpt5.6': ['GPT', '5.6']
};

async function selectModel(modelName) {
    sendStatus('MODEL_SELECTION', `Looking for model selector for ${modelName}...`);
    const modelBtn = await waitForElement(SELECTORS.modelSelector, 5000);
    if (!modelBtn) {
        sendStatus('MODEL_SKIPPED', 'Model selector not found, skipping model selection.');
        return true; // We don't fail, we just skip
    }

    modelBtn.click();
    await sleep(1000);

    const findMenuItem = (name) => {
        const items = Array.from(document.querySelectorAll('.fai-CapabilityPickerMenuItem, [role="menuitem"], [role="option"]'));
        return items.find(item => item.textContent.toLowerCase().includes(name.toLowerCase()));
    };

    const path = MODEL_MAPPING[modelName.toLowerCase()] || [modelName];
    let target = null;

    for (let i = 0; i < path.length; i++) {
        const step = path[i];
        target = findMenuItem(step);
        
        if (target) {
            target.click();
            await sleep(1000);
        } else {
            break;
        }
    }

    if (target) {
        sendStatus('MODEL_SELECTED', `Selected model: ${modelName}`);
        await sleep(500);
        return true;
    } else {
        modelBtn.click();
        sendStatus('MODEL_SKIPPED', `Model "${modelName}" not found in menu, continuing with current`);
        await sleep(500);
        return true;
    }
}

// --- Step 2: Input Prompt ---

async function inputPrompt(fullPrompt) {
    sendStatus('PROMPT_FINDING', 'Looking for chat input element...');
    const editor = await waitForElement(SELECTORS.chatInput, 5000);
    if (!editor) {
        // Fallback selector for generic textareas if M365 chat editor isn't found
        const fallbackEditor = await waitForElement('textarea, [contenteditable="true"]', 3000);
        if (!fallbackEditor) {
            sendError('Chat input element not found. UI may have changed.', 'PROMPT_INPUT');
            return false;
        }
        sendStatus('PROMPT_FINDING', 'Found fallback chat input element.');
        return await typeIntoEditor(fallbackEditor, fullPrompt);
    }
    return await typeIntoEditor(editor, fullPrompt);
}

async function typeIntoEditor(editor, fullPrompt) {
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
    sendStatus('SENDING', 'Looking for Send button...');
    await sleep(500);
    const sendBtn = await waitForElement(SELECTORS.sendButton, 5000);
    if (!sendBtn) {
        // Fallback: look for button containing "Submit" or "Send" SVG or aria-label
        const fallbackBtn = await waitForElement('button[title*="Submit"], button[aria-label*="Submit"], button svg', 3000);
        if (fallbackBtn) {
            let target = fallbackBtn.tagName === 'svg' ? fallbackBtn.closest('button') : fallbackBtn;
            if (target) {
                target.click();
                sendStatus('PROMPT_SENT', 'Prompt sent to Copilot via fallback button');
                return true;
            }
        }
        
        sendError('Send button not found. UI may have changed.', 'SEND');
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
        if (a.href) return { url: a.href, filename: a.download || 'output.zip' };
    }

    // Strategy 2: Look for links to zip files
    const zipLinks = document.querySelectorAll('a[href*=".zip"]');
    for (const a of zipLinks) {
        if (a.href) return { url: a.href, filename: a.download || 'output.zip' };
    }

    // Strategy 2.5: Look for links starting with "Download " in aria-label
    const downloadAria = document.querySelectorAll('a[aria-label^="Download " i], a[aria-label^="download " i]');
    for (const a of downloadAria) {
        if (a.href) return { url: a.href, filename: a.download || 'output.zip' };
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
        return { url: '__CLICKED_DOWNLOAD_BUTTON__', filename: 'output.zip' };
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

    // Step 0: Click New Chat to ensure a fresh session
    await clickNewChat();

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
    const downloadData = await observeResponse();

    if (downloadData && downloadData.url !== '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', `Found download URL: ${downloadData.url.substring(0, 50)}...`);
        
        try {
            if (downloadData.url.startsWith('blob:')) {
                sendStatus('DOWNLOADING', 'Fetching blob to convert to Base64...');
                const res = await fetch(downloadData.url);
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onloadend = () => {
                    try {
                        chrome.runtime.sendMessage({
                            type: 'DOWNLOAD_FILE',
                            url: reader.result,
                            filename: `CopilotAgent/${downloadData.filename}`
                        });
                        sendStatus('DOWNLOADING', 'Sent Base64 payload to background script.');
                    } catch (e) {
                        sendError(`Failed to send Base64 payload: ${e.message}`, 'DOWNLOAD');
                    }
                };
                reader.readAsDataURL(blob);
            } else {
                chrome.runtime.sendMessage({
                    type: 'DOWNLOAD_FILE',
                    url: downloadData.url,
                    filename: `CopilotAgent/${downloadData.filename}`
                });
            }
        } catch (e) {
            sendError(`Failed to fetch blob URL: ${e.message}`, 'DOWNLOAD');
        }
    } else if (downloadData && downloadData.url === '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', 'Clicked download button, waiting for browser to handle...');
        // The browser download will be caught by background.js download listener
    } else {
        sendError('No download link found in Copilot response', 'DOWNLOAD_DETECTION');
    }
}

// --- Initialization & Task Pulling ---

console.log('[CopilotAgent CS] Content script loaded on', window.location.href);

// Wait a bit for the SPA to render, then ask background script if there is a pending task
setTimeout(() => {
    chrome.runtime.sendMessage({ type: 'PAGE_READY_PULL_TASK' }, (response) => {
        if (chrome.runtime.lastError) {
            console.error('[CopilotAgent CS] Error pulling task:', chrome.runtime.lastError.message);
            return;
        }

        if (response && response.hasTask) {
            console.log('[CopilotAgent CS] Pulled task:', response.taskData);
            sendStatus('TASK_RECEIVED', 'Content script pulled task and is executing...');
            executeTask(response.taskData);
        }
    });
}, 3000);
