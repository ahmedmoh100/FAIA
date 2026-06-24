// FAIA Web Interface - Exact Flutter App Copy
class FAIAWebApp {
    constructor() {
        // API Configuration - Use relative path (same host, different port handled by proxy or same origin)
        this.apiUrl = '';

        this.currentTheme = localStorage.getItem('faia-theme') || 'light';
        this.messages = [];
        this.isProcessing = false;
        this.authToken = localStorage.getItem('faia-auth-token') || null;
        this.username = localStorage.getItem('faia-username') || null;
        this.debounceTimer = null;
        this.isSending = false; // Guard against duplicate sends
        // Store uploaded file info for context
        this.lastUploadedFile = null;
        // ✅ FIX: Load session_id from localStorage as STRING
        const storedSessionId = localStorage.getItem('faia-session-id');
        this.sessionId = storedSessionId ? String(storedSessionId) : 'web_session';

        // Guest page-load flag - true on every fresh page load/refresh (in-memory, resets on every load)
        // First guest message sends this as true → backend clears memory → flag flips to false
        this.guestIsNewPageLoad = true;

        // Multi-session management
        this.sessions = []; // Array of chat sessions
        this.activeSessionId = null; // Current active session
        this.isGuest = !this.authToken; // Guest detection
        this.renameSessionId = null; // Session being renamed

        // Token usage tracking
        this.tokenInfo = {
            max_tokens: 0,
            used_tokens: 0,
            remaining_tokens: 0,
            usage_percentage: 0
        };

        // User profile information
        this.userProfile = {
            user_id: null,
            role: 'STUDENT',
            status: 'ACTIVE'
        };

        // Backward-compat: migrate tokens set by standalone login/register pages
        // Those pages use keys: 'authToken' and 'isLoggedIn'
        const legacyToken = localStorage.getItem('authToken');
        const legacyIsLoggedIn = localStorage.getItem('isLoggedIn');
        if (!this.authToken && legacyToken && legacyIsLoggedIn === 'true') {
            this.authToken = legacyToken;
            localStorage.setItem('faia-auth-token', this.authToken);
            // Update isGuest after token migration
            this.isGuest = false;
        }

        this.initializeElements();
        this.initializeEventListeners();
        this.applyTheme();

        // ✅ Database-only mode
        if (!this.isGuest) {
            // Logged in - load from database
            // Validate token before loading data
            this.validateAndLoadUserData();
        }
        // Guest users start with empty state - no localStorage

        // Ensure auth-dependent UI is correct on first load
        this.updateAuthUI();
        this.updateUserDisplay();

        // Initialize RAG button state (show for all users)
        if (this.ragToggleButton) {
            this.updateRAGButton();
        }
    }

    initializeElements() {
        // Main elements
        this.appContainer = document.querySelector('.app-container');
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.attachButton = document.getElementById('attachButton');
        this.fileInput = document.getElementById('fileInput');

        // Drawer elements
        this.menuButton = document.getElementById('menuButton');
        this.drawerOverlay = document.getElementById('drawerOverlay');
        this.drawer = document.getElementById('drawer');
        this.drawerClose = document.getElementById('drawerClose');

        // Drawer menu items
        this.loginButton = document.getElementById('loginButton');
        this.registerButton = document.getElementById('registerButton');
        this.themeToggleButton = document.getElementById('themeToggleButton');

        // Session management elements
        this.sessionsSection = document.getElementById('sessionsSection');
        this.sessionsList = document.getElementById('sessionsList');
        this.newChatButton = document.getElementById('newChatButton');
        this.userDisplay = document.getElementById('userDisplay');

        // Modals
        this.loginModal = document.getElementById('loginModal');
        this.registerModal = document.getElementById('registerModal');
        this.loginModalClose = document.getElementById('loginModalClose');
        this.registerModalClose = document.getElementById('registerModalClose');

        // Forms
        this.loginForm = document.getElementById('loginForm');
        this.registerForm = document.getElementById('registerForm');

        // Other elements
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.toast = document.getElementById('toast');
        this.toastTimeout = null; // Initialize toast timeout variable
        this.confirmDialog = document.getElementById('confirmDialog');

        // Remove cursor pointer from toast since we have a close button
        // The close button will handle dismissal

        // Toast close button - use event delegation for reliability
        document.addEventListener('click', (e) => {
            if (e.target.closest('.toast-close')) {
                e.preventDefault();
                e.stopPropagation();
                this.hideToast();
            }
        });
        this.logoImage = document.getElementById('logoImage');
        this.welcomeLogo = document.getElementById('welcomeLogo');
        this.themeIcon = document.getElementById('themeIcon');
        this.themeText = document.getElementById('themeText');

        // Rename modal elements
        this.renameModal = document.getElementById('renameModal');
        this.renameModalClose = document.getElementById('renameModalClose');
        this.renameInput = document.getElementById('renameInput');
        this.renameCancel = document.getElementById('renameCancel');
        this.renameSave = document.getElementById('renameSave');

        // Settings modal elements
        this.settingsButton = document.getElementById('settingsButton');
        this.settingsModal = document.getElementById('settingsModal');
        this.settingsModalClose = document.getElementById('settingsModalClose');
        this.settingsRegisterButton = document.getElementById('settingsRegisterButton');
        this.settingsLoginButton = document.getElementById('settingsLoginButton');

        this.deleteAllChatsButton = document.getElementById('deleteAllChatsButton');

        // New functionality elements
        this.searchChatInput = document.getElementById('searchChatInput');
        this.ragToggleButton = document.getElementById('ragToggleButton');
        this.guestAuthSection = document.getElementById('guestAuthSection');
        this.accountSection = document.getElementById('accountSection');
        this.guestSection = document.getElementById('guestSection');

        // File preview elements
        this.filePreviewContainer = document.getElementById('filePreviewContainer');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.fileIcon = document.getElementById('fileIcon');
        this.processingIndicator = document.getElementById('processingIndicator');
        this.readyIndicator = document.getElementById('readyIndicator');
        this.removeFileButton = document.getElementById('removeFileButton');

        // RAG state - default to FALSE for all users
        const ragSetting = localStorage.getItem('faia-rag-enabled');
        this.ragEnabled = ragSetting === 'true' ? true : false;

        // Check for missing elements
        this.checkRequiredElements();
    }

    checkRequiredElements() {
        const requiredElements = [
            'appContainer', 'welcomeScreen', 'chatMessages', 'messageInput',
            'sendButton', 'attachButton', 'fileInput', 'menuButton',
            'drawerOverlay', 'drawer', 'drawerClose'
        ];

        for (const elementName of requiredElements) {
            if (!this[elementName]) {
            }
        }
    }

    initializeEventListeners() {
        // Menu and drawer
        if (this.menuButton) this.menuButton.addEventListener('click', () => this.toggleDrawer());
        if (this.drawerOverlay) this.drawerOverlay.addEventListener('click', () => this.closeDrawer());
        if (this.drawerClose) this.drawerClose.addEventListener('click', () => this.closeDrawer());

        // Chat functionality
        if (this.sendButton) this.sendButton.addEventListener('click', () => this.sendMessage());
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        if (this.attachButton && this.fileInput) {
            this.attachButton.addEventListener('click', () => this.fileInput.click());
        }
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }

        // Drawer menu items
        if (this.loginButton) this.loginButton.addEventListener('click', () => this.showLoginModal());
        if (this.registerButton) this.registerButton.addEventListener('click', () => this.showRegisterModal());
        if (this.themeToggleButton) this.themeToggleButton.addEventListener('click', () => this.toggleTheme());

        // Session management
        if (this.newChatButton) this.newChatButton.addEventListener('click', () => this.createNewSession());

        // Logout button
        const logoutButton = document.getElementById('logoutButton');
        if (logoutButton) logoutButton.addEventListener('click', () => this.logout());

        // Modal controls
        if (this.loginModalClose) this.loginModalClose.addEventListener('click', () => this.hideLoginModal());
        if (this.registerModalClose) this.registerModalClose.addEventListener('click', () => this.hideRegisterModal());
        if (this.loginModal) {
            this.loginModal.addEventListener('click', (e) => {
                if (e.target === this.loginModal) this.hideLoginModal();
            });
        }
        if (this.registerModal) {
            this.registerModal.addEventListener('click', (e) => {
                if (e.target === this.registerModal) this.hideRegisterModal();
            });
        }

        // Forms
        if (this.loginForm) this.loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        if (this.registerForm) this.registerForm.addEventListener('submit', (e) => this.handleRegister(e));

        // Forgot Password
        const forgotPasswordLink = document.getElementById('forgotPasswordLink');
        const forgotPasswordModal = document.getElementById('forgotPasswordModal');
        const forgotPasswordModalClose = document.getElementById('forgotPasswordModalClose');
        const forgotPasswordCancel = document.getElementById('forgotPasswordCancel');
        const forgotPasswordForm = document.getElementById('forgotPasswordForm');

        if (forgotPasswordLink) forgotPasswordLink.addEventListener('click', (e) => {
            e.preventDefault();
            this.hideLoginModal();
            this.showForgotPasswordModal();
        });
        if (forgotPasswordModalClose) forgotPasswordModalClose.addEventListener('click', () => this.hideForgotPasswordModal());
        if (forgotPasswordCancel) forgotPasswordCancel.addEventListener('click', () => this.hideForgotPasswordModal());
        if (forgotPasswordForm) forgotPasswordForm.addEventListener('submit', (e) => this.handleForgotPassword(e));
        if (forgotPasswordModal) {
            forgotPasswordModal.addEventListener('click', (e) => {
                if (e.target === forgotPasswordModal) this.hideForgotPasswordModal();
            });
        }

        // Reset Password
        const resetPasswordModal = document.getElementById('resetPasswordModal');
        const resetPasswordModalClose = document.getElementById('resetPasswordModalClose');
        const resetPasswordForm = document.getElementById('resetPasswordForm');

        if (resetPasswordModalClose) resetPasswordModalClose.addEventListener('click', () => this.hideResetPasswordModal());
        if (resetPasswordForm) resetPasswordForm.addEventListener('submit', (e) => this.handleResetPassword(e));
        if (resetPasswordModal) {
            resetPasswordModal.addEventListener('click', (e) => {
                if (e.target === resetPasswordModal) this.hideResetPasswordModal();
            });
        }

        // Change Password
        const changePasswordButton = document.getElementById('changePasswordButton');
        const changePasswordModal = document.getElementById('changePasswordModal');
        const changePasswordModalClose = document.getElementById('changePasswordModalClose');
        const changePasswordCancel = document.getElementById('changePasswordCancel');
        const changePasswordForm = document.getElementById('changePasswordForm');

        if (changePasswordButton) changePasswordButton.addEventListener('click', () => this.showChangePasswordModal());
        if (changePasswordModalClose) changePasswordModalClose.addEventListener('click', () => this.hideChangePasswordModal());
        if (changePasswordCancel) changePasswordCancel.addEventListener('click', () => this.hideChangePasswordModal());
        if (changePasswordForm) changePasswordForm.addEventListener('submit', (e) => this.handleChangePassword(e));
        if (changePasswordModal) {
            changePasswordModal.addEventListener('click', (e) => {
                if (e.target === changePasswordModal) this.hideChangePasswordModal();
            });
        }

        // Check for reset token in URL
        this.checkResetToken();

        // Simple feedback system - no modal needed

        // Event delegation for feedback buttons (since they're added dynamically)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.feedback-btn')) {
                const button = e.target.closest('.feedback-btn');
                const messageId = button.getAttribute('data-message-id');

                // Allow toggle - no prevention of multiple clicks
                if (messageId && !isNaN(parseInt(messageId))) {
                    this.likeResponse(parseInt(messageId), button);
                } else {
                    // Fallback to most recent if ID is invalid
                    this.likeResponse(null, button);
                }
            }
        });

        // Confirm dialog
        const confirmCancel = document.getElementById('confirmCancel');
        const confirmOk = document.getElementById('confirmOk');
        if (confirmCancel) confirmCancel.addEventListener('click', () => this.hideConfirmDialog());
        if (confirmOk) confirmOk.addEventListener('click', () => this.confirmAction());

        // Rename modal
        if (this.renameModalClose) this.renameModalClose.addEventListener('click', () => this.hideRenameModal());
        if (this.renameCancel) this.renameCancel.addEventListener('click', () => this.hideRenameModal());
        if (this.renameSave) this.renameSave.addEventListener('click', () => this.saveRename());
        if (this.renameModal) {
            this.renameModal.addEventListener('click', (e) => {
                if (e.target === this.renameModal) this.hideRenameModal();
            });
        }

        // Settings modal
        if (this.settingsButton) this.settingsButton.addEventListener('click', () => this.showSettingsModal());
        if (this.settingsModalClose) this.settingsModalClose.addEventListener('click', () => this.hideSettingsModal());
        if (this.settingsRegisterButton) this.settingsRegisterButton.addEventListener('click', () => {
            this.hideSettingsModal();
            this.showRegisterModal();
        });
        if (this.settingsLoginButton) this.settingsLoginButton.addEventListener('click', () => {
            this.hideSettingsModal();
            this.showLoginModal();
        });

        if (this.deleteAllChatsButton) this.deleteAllChatsButton.addEventListener('click', () => this.deleteAllChats());
        if (this.settingsModal) {
            this.settingsModal.addEventListener('click', (e) => {
                if (e.target === this.settingsModal) this.hideSettingsModal();
            });
        }

        // Search chat functionality
        if (this.searchChatInput) {
            this.searchChatInput.addEventListener('input', (e) => this.filterSessions(e.target.value));
        }

        // RAG toggle functionality (for all users, but guests get login prompt)
        if (this.ragToggleButton) {
            this.ragToggleButton.addEventListener('click', () => this.toggleRAG());
            this.updateRAGButton();
        }

        // File preview functionality
        if (this.removeFileButton) {
            this.removeFileButton.addEventListener('click', () => this.removeFile());
        }
    }

    // Theme Management
    applyTheme() {
        this.appContainer.setAttribute('data-theme', this.currentTheme);

        // Update logo based on theme
        const logoPath = this.currentTheme === 'dark'
            ? '/static/images/faia-logo-dark.png'
            : '/static/images/faia-logo.png';

        if (this.logoImage) this.logoImage.src = logoPath;
        if (this.welcomeLogo) this.welcomeLogo.src = logoPath;

        // Update theme button
        if (this.themeIcon) {
            this.themeIcon.className = this.currentTheme === 'dark'
                ? 'fas fa-sun'
                : 'fas fa-moon';
        }
        if (this.themeText) {
            this.themeText.textContent = this.currentTheme === 'dark'
                ? 'Light Mode'
                : 'Dark Mode';
        }
    }

    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('faia-theme', this.currentTheme);
        this.applyTheme();
        this.closeDrawer();
        this.showToast('Theme switched to ' + (this.currentTheme === 'dark' ? 'Dark' : 'Light') + ' mode');
    }

    // Drawer Management
    toggleDrawer() {
        this.drawer.classList.toggle('show');
        this.drawerOverlay.classList.toggle('show');
    }

    closeDrawer() {
        this.drawer.classList.remove('show');
        this.drawerOverlay.classList.remove('show');
    }

    // Security functions
    sanitizeInput(text) {
        if (!text) return '';
        // HTML escape
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    validateInput(text) {
        if (!text) return { valid: false, message: 'Message cannot be empty' };
        if (text.length > 1000) return { valid: false, message: 'Message too long (max 1000 characters)' };
        // Check for potential XSS
        if (/<script|javascript:|on\w+=/i.test(text)) {
            return { valid: false, message: 'Invalid characters detected' };
        }
        return { valid: true, message: '' };
    }

    // Chat Functionality
    async sendMessage() {
        if (this.isSending) return; // Prevent duplicate sends
        const message = this.messageInput.value.trim();
        if (!message || this.isProcessing) return;

        // Validate input
        const validation = this.validateInput(message);
        if (!validation.valid) {
            this.showToast(validation.message, 'error');
            return;
        }

        // Cancel any existing debounce timer
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        // Set a debounce timer to prevent rapid-fire sending
        this.debounceTimer = setTimeout(async () => {
            this.isSending = true;
            // Flip new-page-load flag after first message (only matters for guests)
            const wasNewPageLoad = this.guestIsNewPageLoad;
            this.guestIsNewPageLoad = false;
            // Create session on first message for logged-in users (only if no session exists)
            if (!this.isGuest && !this.activeSessionId) {
                this.createNewSession(message);
            } else if (!this.isGuest && this.activeSessionId) {
                // Update session name with first message if it's still "New Chat"
                const activeSession = this.sessions.find(s => s.id === this.activeSessionId);
                if (activeSession && activeSession.name === 'New Chat' && activeSession.messages.length === 0) {
                    activeSession.name = message.length > 30 ? message.substring(0, 30) + '...' : message;
                    this.saveSessions();
                    this.updateSessionsUI();
                }
            }

            // Add user message - show file card if file is attached (first use only)
            let displayMessage = message;
            let fileCard = null;
            if (this.lastUploadedFile && this.lastUploadedFile.processed && !this.lastUploadedFile.used) {
                const sizeKB = this.lastUploadedFile.size ? Math.round(this.lastUploadedFile.size / 1024) : null;
                const sizeStr = sizeKB ? (sizeKB >= 1024 ? (sizeKB/1024).toFixed(1) + ' MB' : sizeKB + ' KB') : '';
                const ext = this.lastUploadedFile.filename.split('.').pop().toLowerCase();
                const icons = { pdf: 'fa-file-pdf', docx: 'fa-file-word', doc: 'fa-file-word', xlsx: 'fa-file-excel', xls: 'fa-file-excel', txt: 'fa-file-alt' };
                const icon = icons[ext] || 'fa-file';
                fileCard = { filename: this.lastUploadedFile.filename, sizeStr, icon };
            }
            this.addMessage(displayMessage, 'user', null, null, fileCard);
            this.messageInput.value = '';

            // Store the current prompt for feedback system
            this.currentPrompt = message;

            // Update session messages if logged in
            if (!this.isGuest && this.activeSessionId) {
                this.updateSessionMessages(this.activeSessionId, this.messages);
            }

            // Show a 'bot is typing...' bubble
            const typingId = Date.now() + 1;
            const typingMessage = {
                id: typingId,
                content: '...',
                sender: 'bot',
                timestamp: new Date()
            };
            this.messages.push(typingMessage);
            this.renderMessage(typingMessage);
            this.saveMessages();
            this.updateUI();
            try {
                const isLoggedIn = !!this.authToken;
                const model = 'qwen';  // Qwen model



                const headers = {
                    'Content-Type': 'application/json',
                    ...(isLoggedIn && { 'Authorization': `Bearer ${this.authToken}` })
                };
                // Prepare file context and enhance prompt if we have an uploaded file
                // ONE-TIME USE: Inject file context only once, then clear
                let fileContext = null;
                let enhancedPrompt = message;

                if (this.lastUploadedFile && this.lastUploadedFile.processed && !this.lastUploadedFile.used) {
                    fileContext = {
                        session_id: this.lastUploadedFile.sessionId,
                        filename: this.lastUploadedFile.filename
                    };

                    // Enhance the prompt to provide context about the file (ONE-TIME ONLY)
                    enhancedPrompt = this.enhancePromptWithFileContext(message, this.lastUploadedFile.filename);

                    // Mark as used and null out - file context is now saved in DB as SYSTEM message
                    this.lastUploadedFile.used = true;
                    // Hide preview bar
                    if (this.filePreviewContainer) this.filePreviewContainer.style.display = 'none';
                    this.lastUploadedFile = null;
                }

                // Get current chat_id from active session
                let chatId = null;
                if (!this.isGuest && this.activeSessionId) {
                    const activeSession = this.sessions.find(s => s.id === this.activeSessionId);
                    if (activeSession && activeSession.chatId) {
                        chatId = String(activeSession.chatId);  // ✅ FIX: Convert to string
                    }
                }

                const requestBody = {
                    prompt: enhancedPrompt,  // Use enhanced prompt with file context
                    model,
                    chat_id: chatId,  // Send chat_id to continue conversation
                    session_id: this.sessionId,  // ✅ FIX: Send actual session_id from login
                    file_context: fileContext,
                    use_rag: this.ragEnabled,  // Include RAG preference
                    guest_new_page_load: this.isGuest ? wasNewPageLoad : undefined  // Clear memory on refresh
                };



                const response = await this.callAPI(`${this.apiUrl}/chat`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(requestBody)
                });

                // Remove the typing bubble
                this.messages = this.messages.filter(m => m.id !== typingId);
                const typingEl = this.chatMessages.querySelector(`[data-message-id="${typingId}"]`);
                if (typingEl) typingEl.remove();
                this.saveMessages();
                this.updateUI();
                if (response.success) {
                    // Add bot message with original prompt for feedback
                    // Pass RAG sources if available, or file source if file is active
                    let ragSources = null;
                    if (response.sources && response.sources.length > 0) {
                        ragSources = response.sources;
                    } else if (this.lastUploadedFile && this.lastUploadedFile.filename) {
                        ragSources = [{ original_filename: this.lastUploadedFile.filename, page_number: null, is_file_upload: true }];
                    }
                    const botMessage = this.addMessage(response.response, 'bot', 'normal', ragSources);
                    if (botMessage && this.currentPrompt) {
                        botMessage.originalPrompt = this.currentPrompt;
                    }
                    this.scrollToBottom(150); // Delay to let bot message fully render



                    // Show guest warning if applicable
                    if (response.is_guest && response.message) {
                        this.showToast(response.message, 'info');
                    }

                    // Save chat_id to session for continuing conversation (registered users only)
                    if (!this.isGuest && this.activeSessionId && response.chat_id) {
                        const activeSession = this.sessions.find(s => s.id === this.activeSessionId);
                        if (activeSession) {
                            activeSession.chatId = response.chat_id;  // Always update chatId
                        }
                    }

                    // Update token info after successful message (registered users only)
                    if (!this.isGuest) {
                        setTimeout(() => this.loadTokenInfo(), 1000);
                    }
                } else {
                    // Handle specific error types
                    if (response.code === 429) {
                        // Token limit exceeded - guest or registered user
                        const msg = response.error || 'Token limit reached.';
                        this.addMessage('⚠️ ' + msg, 'bot', 'warning');
                        if (!this.isGuest) this.loadTokenInfo();
                    } else if (response.code === 400 && response.error.includes('moderation')) {
                        // Content moderation
                        this.addMessage('⚠️ Your message was flagged for review. Please ensure your content follows community guidelines.', 'bot', 'warning');
                    } else {
                        this.addMessage('Sorry, I encountered an error: ' + (response.error || 'Unknown error'), 'bot', 'error');
                    }
                }

                // Update session messages after bot response
                if (!this.isGuest && this.activeSessionId) {
                    this.updateSessionMessages(this.activeSessionId, this.messages);
                }
            } catch (error) {
                this.messages = this.messages.filter(m => m.id !== typingId);
                const typingEl = this.chatMessages.querySelector(`[data-message-id="${typingId}"]`);
                if (typingEl) typingEl.remove();
                this.saveMessages();
                this.updateUI();

                // Show time-aware message for guest token limit
                const errMsg = error.message || 'Unknown error';
                if (errMsg.includes('Guest token limit reached') || errMsg.includes('token limit')) {
                    this.addMessage('⚠️ ' + errMsg, 'bot', 'warning');
                } else {
                    this.addMessage('Sorry, I encountered an error: ' + errMsg, 'bot');
                }
                this.scrollToBottom(150);

                // Update session messages after error
                if (!this.isGuest && this.activeSessionId) {
                    this.updateSessionMessages(this.activeSessionId, this.messages);
                }
            } finally {
                this.isSending = false; // Always release the lock
            }
        }, 500); // 500ms debounce
    }

    addMessage(content, sender, type = 'normal', sources = null, fileCard = null) {
        const message = {
            id: Date.now(),
            content: content,
            sender: sender,
            timestamp: new Date(),
            type: type,
            sources: sources || null,
            fileCard: fileCard || null
        };

        this.messages.push(message);
        this.renderMessage(message);
        this.saveMessages();
        this.updateUI();
        return message;
    }

    renderMessage(message) {
        // Hide system messages (file context)
        if (message.sender === 'system' || (message.content && message.content.includes('[FILE_CONTEXT:'))) {
            return;
        }

        const messageElement = document.createElement('div');
        messageElement.className = `message ${message.sender} ${message.type || 'normal'}`;
        messageElement.dataset.messageId = message.id;
        messageElement.style.cssText = `
            display: flex;
            margin: 8px 0;
            align-items: flex-end;
            flex-direction: ${message.sender === 'user' ? 'row-reverse' : 'row'};
            gap: 8px;
        `;

        const isFileUpload = false;
        let displayContent = message.content;

        messageElement.innerHTML = `
            <div class="message-avatar" style="
                width: 32px;
                height: 32px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                background: ${message.sender === 'user' ? '#007bff' : '#6c757d'};
                color: white;
                font-size: 14px;
                flex-shrink: 0;
            ">
                <i class="fas ${message.sender === 'user' ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="message-content" style="
                max-width: 70%;
                display: flex;
                flex-direction: column;
                align-items: ${message.sender === 'user' ? 'flex-end' : 'flex-start'};
            ">
                <div class="message-bubble" style="
                    background: ${message.sender === 'user' ? '#007bff' : '#f8f9fa'};
                    color: ${message.sender === 'user' ? 'white' : '#333'};
                    padding: 12px 16px;
                    border-radius: 18px;
                    border-bottom-right-radius: ${message.sender === 'user' ? '4px' : '18px'};
                    border-bottom-left-radius: ${message.sender === 'user' ? '18px' : '4px'};
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    word-wrap: break-word;
                    line-height: 1.4;
                ">${message.fileCard ? `<div class="file-attachment-card"><i class="fas ${message.fileCard.icon} file-attach-icon"></i><div class="file-attach-info"><span class="file-attach-name">${message.fileCard.filename}</span>${message.fileCard.sizeStr ? `<span class="file-attach-size">${message.fileCard.sizeStr}</span>` : ''}</div></div>` : ''}${this.formatMessage(message.content)}</div>
                <div class="message-time" style="
                    font-size: 11px;
                    color: #6c757d;
                    margin-top: 4px;
                    padding: 0 4px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                ">
                    ${this.formatTime(message.timestamp)}
                    ${message.sender === 'bot' && !this.isGuest ? `
                        <button class="feedback-btn" data-message-id="${message.id}" style="
                            background: none;
                            border: none;
                            color: #6c757d;
                            cursor: pointer;
                            font-size: 10px;
                            padding: 2px 4px;
                            border-radius: 3px;
                            opacity: 0.7;
                        " title="Rate this response">
                            <i class="fas fa-thumbs-up"></i>
                        </button>
                    ` : ''}
                </div>
                ${message.sender === 'bot' && message.sources && message.sources.length > 0 ? `
                    <div style="
                        margin-top: 6px;
                        padding: 6px 10px;
                        background: rgba(0,123,255,0.07);
                        border-left: 3px solid #007bff;
                        border-radius: 4px;
                        font-size: 11px;
                        color: #555;
                    ">
                        <strong>${message.sources[0].is_file_upload ? 'From file:' : 'Sources:'}</strong>
                        ${[...new Map(message.sources.map(s => [s.original_filename || s.filename, s])).values()].map(s => {
                            const rawName = s.original_filename || s.filename || 'Course Material';
                            const name = rawName.replace(/^\d+_/, '').replace(/\.[^.]+$/, '');
                            const page = (s.page_number && s.page_number !== 'N/A' && s.page_number !== null) ? `, Page ${s.page_number}` : '';
                            return `<span style="margin-left:6px;background:#e8f0fe;padding:2px 6px;border-radius:3px;">${name}${page}</span>`;
                        }).join('')}
                    </div>
                ` : ''}
            </div>
        `;

        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();
    }

    formatMessage(content) {
        // Simple formatting for line breaks and basic HTML
        return content
            .trim()
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
    }

    formatTime(timestamp) {
        // Normalize timestamp to Date
        if (!(timestamp instanceof Date)) {
            try {
                timestamp = new Date(timestamp);
            } catch (_) {
                return '';
            }
        }
        // Always show real time - no "just now" or relative time
        const now = new Date();
        const isToday = timestamp.toDateString() === now.toDateString();
        if (isToday) {
            return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else {
            return timestamp.toLocaleDateString([], { day: '2-digit', month: '2-digit' })
                + ' ' + timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    scrollToBottom(delay = 0) {
        // Use setTimeout to ensure DOM has fully painted before scrolling
        setTimeout(() => {
            if (this.chatMessages) {
                this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
            }
        }, delay);
    }

    updateUI() {
        const hasMessages = this.messages.length > 0;
        this.welcomeScreen.style.display = hasMessages ? 'none' : 'flex';
        this.chatMessages.style.display = hasMessages ? 'flex' : 'none';
        this.updateFileContextIndicator();
    }

    async validateAndLoadUserData() {
        if (this.isGuest || !this.authToken) return;

        // Show loading state on welcome screen while fetching
        const subtitle = document.querySelector('.welcome-subtitle');
        if (subtitle) subtitle.textContent = 'Loading your chats...';

        try {
            // Restore session_id from localStorage (may have been lost on page reload)
            const storedSessionId = localStorage.getItem('faia-session-id');
            if (storedSessionId && this.sessionId === 'web_session') {
                this.sessionId = String(storedSessionId);
            }

            // First validate the token by trying to load token info
            await this.loadTokenInfo();

            // If token is valid, load the rest
            if (!this.isGuest && this.authToken) {
                await this.loadChatsFromDatabase();
                const files = await this.loadUserFiles();
            }
        } catch (error) {
            // Token validation failed, clear auth
            this.logout();
        } finally {
            // Restore subtitle regardless of outcome
            if (subtitle) subtitle.textContent = 'Your AI Assistant';
        }
    }

    async loadChatsFromDatabase() {
        if (this.isGuest || !this.authToken) {
            return;
        }

        try {
            const response = await fetch(`${this.apiUrl}/chat/history`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });

            // Handle 401 - invalid token (logout and reload page once)
            if (response.status === 401) {
                this.authToken = null;
                this.username = null;
                this.isGuest = true;
                localStorage.removeItem('faia-auth-token');
                localStorage.removeItem('faia-username');
                localStorage.removeItem('faia-session-id');
                this.showToast('Session expired - please login again', 'warning');
                setTimeout(() => window.location.reload(), 1000);
                return;
            }

            if (response.ok) {
                const data = await response.json();

                // Convert database format to frontend session format
                if (data.history && data.history.length > 0) {
                    this.sessions = this.convertDbChatsToSessions(data.history);

                    // ✅ FIX: Clear ALL localStorage to prevent caching issues
                    localStorage.removeItem('faia-sessions');
                    localStorage.removeItem('faia-active-session');
                    localStorage.removeItem('faia-messages');

                    // Clear any stale file upload state - file is already in DB as SYSTEM message
                    this.lastUploadedFile = null;
                    if (this.filePreviewContainer) this.filePreviewContainer.style.display = 'none';

                    this.updateSessionsUI();

                    // Always set active session to the most recent one (reset stale session from previous user)
                    if (this.sessions.length > 0) {
                        this.activeSessionId = this.sessions[0].id;
                        this.loadMessages();
                    }
                } else {
                    // ✅ FIX: Clear localStorage even when no history
                    localStorage.removeItem('faia-sessions');
                    localStorage.removeItem('faia-active-session');
                    localStorage.removeItem('faia-messages');
                    this.sessions = [];
                    this.activeSessionId = null;
                    this.messages = [];
                    this.updateSessionsUI();
                }
            } else {
                this.sessions = [];
                this.messages = [];
                this.updateSessionsUI();
            }
        } catch (error) {
            this.sessions = [];
            this.messages = [];
            this.updateSessionsUI();
        }
    }

    convertDbChatsToSessions(dbChats) {
        return dbChats.map(chat => {
            // Convert database messages to frontend format, filtering out system messages
            const messages = (chat.messages || [])
                .filter(msg => msg.sender.toLowerCase() !== 'system')  // Filter out system messages
                .map(msg => ({
                    id: `msg_${msg.message_id || Date.now()}_${Math.random()}`,  // Generate unique ID
                    sender: msg.sender.toLowerCase() === 'user' ? 'user' : 'bot',  // Case-insensitive check
                    content: msg.content,  // Changed from 'text' to 'content' to match renderMessage
                    timestamp: msg.created_at ? new Date(msg.created_at).getTime() : Date.now(),
                    tokens: msg.token_count || 0,
                    messageId: msg.message_id  // Store DB message ID for reporting
                }));

            return {
                id: `session_${chat.chat_id}`,
                name: chat.title || 'Untitled Chat',
                messages: messages,
                createdAt: chat.created_at,
                lastActivity: chat.updated_at || chat.created_at,
                chatId: chat.chat_id, // Store DB ID for reference
                fromDatabase: true // Mark as loaded from database
            };
        });
    }

    updateFileContextIndicator() {
        if (this.filePreviewContainer) {
            // Only show preview if file is attached AND not yet used
            if (this.lastUploadedFile && !this.lastUploadedFile.used) {
                this.filePreviewContainer.style.display = 'block';
            } else {
                this.filePreviewContainer.style.display = 'none';
                if (this.messageInput && !this.lastUploadedFile) {
                    this.messageInput.placeholder = 'Type your message...';
                }
            }
        }

        // Remove old floating indicator if it exists
        const oldIndicator = document.getElementById('fileContextIndicator');
        if (oldIndicator) {
            oldIndicator.remove();
        }
    }

    clearChat() {
        this.showConfirmDialog(
            'Clear Chat',
            'Are you sure you want to clear all messages?',
            () => {
                this.messages = [];
                this.chatMessages.innerHTML = '';
                this.saveMessages();
                this.updateUI();
                this.closeDrawer();
                this.showToast('Chat cleared');
            }
        );
    }

    // File Handling - New integrated approach
    async handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Check if user is logged in
        if (!this.authToken) {
            this.showToast('Sign up to use this feature', 'warning');
            // Clear the file input
            event.target.value = '';
            return;
        }

        // Show file preview immediately
        this.showFilePreview(file);

        // Start processing the file
        await this.processFile(file);

        // Clear the file input for next selection
        event.target.value = '';
    }

    showFilePreview(file) {
        if (this.fileName) this.fileName.textContent = file.name;
        if (this.fileSize) this.fileSize.textContent = this.formatFileSize(file.size);

        if (this.fileIcon) {
            const extension = file.name.split('.').pop().toLowerCase();
            const iconMap = {
                'pdf': 'fa-file-pdf',
                'doc': 'fa-file-word',
                'docx': 'fa-file-word',
                'txt': 'fa-file-alt',
                'jpg': 'fa-file-image',
                'jpeg': 'fa-file-image',
                'png': 'fa-file-image'
            };
            this.fileIcon.className = `fas ${iconMap[extension] || 'fa-file'} file-icon`;
        }

        if (this.processingIndicator) this.processingIndicator.style.display = 'flex';
        if (this.readyIndicator) this.readyIndicator.style.display = 'none';
        if (this.filePreviewContainer) this.filePreviewContainer.style.display = 'block';
        if (this.messageInput) this.messageInput.placeholder = `Ask about ${file.name}...`;
    }

    async processFile(file) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('file_type', 'study_material');
            formData.append('session_id', this.sessionId || 'web_session');

            // ✅ FIX: Send current chat_id if we're already in a chat
            if (!this.isGuest && this.activeSessionId) {
                const activeSession = this.sessions.find(s => s.id === this.activeSessionId);
                if (activeSession && activeSession.chatId) {
                    formData.append('chat_id', activeSession.chatId);
                }
            }

            // Add auth token to upload request
            const headers = {};
            if (this.authToken) {
                headers['Authorization'] = `Bearer ${this.authToken}`;
            }

            const response = await this.callAPI(`${this.apiUrl}/upload`, {
                method: 'POST',
                headers: headers,
                body: formData
            });

            if (response.success) {
                // Store uploaded file info for context
                this.lastUploadedFile = {
                    filename: file.name,
                    size: file.size,
                    sessionId: this.sessionId || 'web_session',
                    fileId: response.file?.file_id,
                    uploadedAt: new Date(),
                    processed: true
                };

                // Automatically disable RAG when file is uploaded
                if (this.ragEnabled) {
                    this.ragEnabled = false;
                    localStorage.setItem('faia-rag-enabled', 'false');
                    this.updateRAGButton();
                    this.showToast('RAG automatically disabled - Using uploaded file content instead of knowledge base', 'info');
                }

                // Handle chat_id properly - don't reload if already in a chat
                if (response.chat_id) {
                    if (response.created_new_chat) {
                        // New chat was created - add it to sessions without reloading
                        await this.loadChatsFromDatabase();
                        // Switch to the new chat session
                        const newSession = this.sessions.find(s => String(s.chatId) === String(response.chat_id));
                        if (newSession) {
                            this.activeSessionId = newSession.id;
                            this.updateSessionsUI();
                        }
                    } else {
                        // Using existing chat - just update the session
                        const activeSession = this.sessions.find(s => s.id === this.activeSessionId);
                        if (activeSession) {
                            activeSession.chatId = response.chat_id;
                        }
                    }
                }

                if (this.processingIndicator) this.processingIndicator.style.display = 'none';
                if (this.readyIndicator) this.readyIndicator.style.display = 'flex';
                
                // Hide box after 2 seconds
                setTimeout(() => {
                    if (this.filePreviewContainer) this.filePreviewContainer.style.display = 'none';
                }, 2000);

                this.showToast(`${file.name} is ready!`, 'success');
            } else {
                this.showFileError('Upload failed: ' + (response.error || 'Unknown error'));
            }
        } catch (error) {
            this.showFileError('Upload failed: ' + error.message);
        }
    }

    showFileError(message) {
        // Show error state
        if (this.processingIndicator) this.processingIndicator.style.display = 'none';
        if (this.readyIndicator) {
            this.readyIndicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
            this.readyIndicator.style.display = 'flex';
            this.readyIndicator.style.color = '#dc3545';
        }
        this.showToast(message, 'error');
    }

    removeFile() {
        // Clear file data
        this.lastUploadedFile = null;

        // Hide preview container
        if (this.filePreviewContainer) this.filePreviewContainer.style.display = 'none';

        // Reset placeholder text
        if (this.messageInput) {
            this.messageInput.placeholder = 'Type your message...';
        }

        // Update RAG button state (file is now removed, so RAG can be enabled again)
        this.updateRAGButton();

        this.showToast('File removed - RAG can now be enabled if desired', 'info');
    }

    enhancePromptWithFileContext(userPrompt, filename) {
        // Enhance the user's prompt to provide better context about the uploaded file
        const fileExtension = filename.split('.').pop().toLowerCase();
        let fileTypeDescription = 'document';

        switch (fileExtension) {
            case 'pdf':
                fileTypeDescription = 'PDF document';
                break;
            case 'doc':
            case 'docx':
                fileTypeDescription = 'Word document';
                break;
            case 'txt':
                fileTypeDescription = 'text file';
                break;
            case 'jpg':
            case 'jpeg':
            case 'png':
                fileTypeDescription = 'image';
                break;
        }

        // Check if user is asking about "it", "this", "the document", etc.
        const referenceWords = /\b(it|this|that|the document|the file|the pdf|the text)\b/i;

        if (referenceWords.test(userPrompt)) {
            // Replace ambiguous references with specific file reference
            return `Regarding the uploaded ${fileTypeDescription} "${filename}": ${userPrompt}`;
        } else {
            // Add context without being too intrusive
            return `[Context: User has uploaded ${fileTypeDescription} "${filename}"]\n\n${userPrompt}`;
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Authentication
    showLoginModal() {
        this.loginModal.classList.add('show');
        this.closeDrawer();
    }

    hideLoginModal() {
        this.loginModal.classList.remove('show');
    }

    showRegisterModal() {
        this.registerModal.classList.add('show');
        this.closeDrawer();
    }

    hideRegisterModal() {
        this.registerModal.classList.remove('show');
    }

    async handleLogin(event) {
        event.preventDefault();

        // If already logged in, just close modal and show current state
        if (this.authToken && this.username) {
            this.hideLoginModal();
            this.showToast(`Already logged in as ${this.username}`, 'info');
            return;
        }
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;
        try {
            const response = await this.callAPI(`${this.apiUrl}/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`
            });

            // Check if we got an access_token (successful login)
            if (response.access_token) {
                this.authToken = response.access_token;
                this.username = username; // Use the username from form
                this.isGuest = false; // Update guest status

                // ✅ FIX: Store session_id from login response as STRING
                if (response.session_id) {
                    this.sessionId = String(response.session_id);  // Convert to string
                    localStorage.setItem('faia-session-id', this.sessionId);
                }

                localStorage.setItem('faia-auth-token', this.authToken);
                localStorage.setItem('faia-username', this.username);



                // ✅ FIX: Clear guest data when logging in
                this.messages = [];
                this.sessions = [];
                this.activeSessionId = null;
                if (this.chatMessages) {
                    this.chatMessages.innerHTML = '';
                }

                this.hideLoginModal();
                this.showToast('Login successful!');

                // Load user data from database
                await this.loadTokenInfo();
                await this.loadChatsFromDatabase(); // Load from database instead of localStorage

                this.updateAuthUI();
                this.updateUserDisplay();
            } else {
                this.showToast('Login failed: ' + (response.detail || 'Unknown error'), 'error');
            }
        } catch (error) {
            this.showToast('Login failed: ' + error.message, 'error');
        }
    }

    validatePassword(password) {
        if (password.length < 8) return { valid: false, message: 'Password must be at least 8 characters' };
        if (!/[A-Z]/.test(password)) return { valid: false, message: 'Password must contain uppercase letter' };
        if (!/[a-z]/.test(password)) return { valid: false, message: 'Password must contain lowercase letter' };
        if (!/[0-9]/.test(password)) return { valid: false, message: 'Password must contain number' };
        return { valid: true, message: 'Strong password' };
    }

    validateUsername(username) {
        if (username.length < 3) return { valid: false, message: 'Username must be at least 3 characters' };
        if (!/^[a-zA-Z0-9_]+$/.test(username)) return { valid: false, message: 'Username can only contain letters, numbers, and underscores' };
        return { valid: true, message: 'Valid username' };
    }

    validateEmail(email) {
        if (!email) return { valid: true, message: 'Email is optional' };
        const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        if (!emailRegex.test(email)) return { valid: false, message: 'Invalid email format' };
        return { valid: true, message: 'Valid email' };
    }

    async handleRegister(event) {
        event.preventDefault();
        if (this.authToken && this.username) {
            this.showToast(`Already logged in as ${this.username}. Please log out to switch users.`, 'warning');
            return;
        }
        const username = document.getElementById('registerUsername').value.trim();
        const password = document.getElementById('registerPassword').value;
        const confirmPassword = document.getElementById('registerConfirmPassword').value;
        const email = document.getElementById('registerEmail').value.trim();

        if (password !== confirmPassword) {
            this.showToast('Passwords do not match', 'error');
            return;
        }

        // Validate inputs
        const usernameValidation = this.validateUsername(username);
        if (!usernameValidation.valid) {
            this.showToast(usernameValidation.message, 'error');
            return;
        }

        const passwordValidation = this.validatePassword(password);
        if (!passwordValidation.valid) {
            this.showToast(passwordValidation.message, 'error');
            return;
        }

        if (email) {
            const emailValidation = this.validateEmail(email);
            if (!emailValidation.valid) {
                this.showToast(emailValidation.message, 'error');
                return;
            }
        }
        try {
            const response = await this.callAPI(`${this.apiUrl}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}&email=${encodeURIComponent(email)}`
            });
            if (response.success) {
                // Do NOT auto-login on registration; ask user to login explicitly
                this.hideRegisterModal();
                this.showToast('Registration successful! Please log in to access full features.', 'info');
                // Ensure we remain in guest mode
                this.authToken = null;
                this.username = null;
                localStorage.removeItem('faia-auth-token');
                localStorage.removeItem('faia-username');
                this.updateAuthUI();
                this.updateUserDisplay();
                // Optionally open the login modal for convenience
                this.showLoginModal();
            } else {
                this.showToast('Registration failed: ' + response.detail, 'error');
            }
        } catch (error) {
            this.showToast('Registration failed: ' + error.message, 'error');
        }
    }

    // Forgot Password Modal
    showForgotPasswordModal() {
        const modal = document.getElementById('forgotPasswordModal');
        if (modal) {
            modal.classList.add('show');
            const emailInput = document.getElementById('forgotEmail');
            const successDiv = document.getElementById('forgotPasswordSuccess');
            if (emailInput) emailInput.value = '';
            if (successDiv) successDiv.style.display = 'none';
        }
    }

    hideForgotPasswordModal() {
        const modal = document.getElementById('forgotPasswordModal');
        if (modal) modal.classList.remove('show');
    }

    async handleForgotPassword(event) {
        event.preventDefault();
        const email = document.getElementById('forgotEmail').value.trim();

        if (!email) {
            this.showToast('Please enter your email address', 'error');
            return;
        }

        try {
            const response = await this.callAPI(`${this.apiUrl}/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });

            if (response.success) {
                const successDiv = document.getElementById('forgotPasswordSuccess');
                successDiv.style.display = 'block';
                document.getElementById('forgotPasswordForm').style.display = 'none';
                this.showToast('Request received. Admin will contact you shortly.', 'success');

                setTimeout(() => {
                    this.hideForgotPasswordModal();
                    document.getElementById('forgotPasswordForm').style.display = 'block';
                }, 10000); // 10 seconds to read the link
            } else {
                this.showToast('Failed to send reset link', 'error');
            }
        } catch (error) {
            this.showToast('Error: ' + error.message, 'error');
        }
    }

    // Reset Password Modal
    showResetPasswordModal() {
        const modal = document.getElementById('resetPasswordModal');
        if (modal) {
            modal.classList.add('show');
            const newPassInput = document.getElementById('resetNewPassword');
            const confirmInput = document.getElementById('resetConfirmPassword');
            if (newPassInput) newPassInput.value = '';
            if (confirmInput) confirmInput.value = '';
        }
    }

    hideResetPasswordModal() {
        const modal = document.getElementById('resetPasswordModal');
        if (modal) modal.classList.remove('show');
    }

    checkResetToken() {
        // Check if URL has reset token
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');

        if (token) {
            document.getElementById('resetToken').value = token;
            this.showResetPasswordModal();
        }
    }

    async handleResetPassword(event) {
        event.preventDefault();
        const token = document.getElementById('resetToken').value;
        const newPassword = document.getElementById('resetNewPassword').value;
        const confirmPassword = document.getElementById('resetConfirmPassword').value;

        if (newPassword !== confirmPassword) {
            this.showToast('Passwords do not match', 'error');
            return;
        }

        if (newPassword.length < 6) {
            this.showToast('Password must be at least 6 characters', 'error');
            return;
        }

        try {
            const response = await this.callAPI(`${this.apiUrl}/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, new_password: newPassword })
            });

            if (response.success) {
                this.showToast('Password reset successfully! You can now login.', 'success');
                this.hideResetPasswordModal();

                // Clear token from URL
                window.history.replaceState({}, document.title, window.location.pathname);

                // Show login modal
                setTimeout(() => this.showLoginModal(), 1000);
            } else {
                this.showToast(response.detail || 'Failed to reset password', 'error');
            }
        } catch (error) {
            this.showToast('Error: ' + error.message, 'error');
        }
    }

    // Change Password Modal
    showChangePasswordModal() {
        const modal = document.getElementById('changePasswordModal');
        if (modal) {
            modal.classList.add('show');
            const currentInput = document.getElementById('currentPassword');
            const newInput = document.getElementById('newPassword');
            const confirmInput = document.getElementById('confirmNewPassword');
            if (currentInput) currentInput.value = '';
            if (newInput) newInput.value = '';
            if (confirmInput) confirmInput.value = '';
            // Populate hidden username so browser knows which account this password belongs to
            const usernameHint = document.getElementById('changePasswordUsername');
            if (usernameHint && this.username) usernameHint.value = this.username;
        }
    }

    hideChangePasswordModal() {
        const modal = document.getElementById('changePasswordModal');
        if (modal) modal.classList.remove('show');
    }

    async handleChangePassword(event) {
        event.preventDefault();
        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmNewPassword').value;

        if (newPassword !== confirmPassword) {
            this.showToast('New passwords do not match', 'error');
            return;
        }

        if (newPassword.length < 6) {
            this.showToast('New password must be at least 6 characters', 'error');
            return;
        }

        if (currentPassword === newPassword) {
            this.showToast('New password must be different from current password', 'error');
            return;
        }

        try {
            const response = await this.callAPI(`${this.apiUrl}/change-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword
                })
            });

            if (response.success) {
                this.showToast('Password changed successfully!', 'success');
                this.hideChangePasswordModal();
            } else {
                this.showToast(response.detail || 'Failed to change password', 'error');
            }
        } catch (error) {
            this.showToast('Error: ' + error.message, 'error');
        }
    }

    // Toggle Like System
    async likeResponse(messageId, buttonElement) {
        if (this.isGuest) {
            this.showToast('Please login to like responses', 'warning');
            return;
        }

        let targetMessage = null;

        if (messageId) {
            // Try to find the specific message
            targetMessage = this.messages.find(m => m.id === messageId && m.sender === 'bot');
        }

        // Fallback to most recent bot message if specific message not found
        if (!targetMessage) {
            const botMessages = this.messages.filter(m => m.sender === 'bot');
            if (botMessages.length === 0) {
                this.showToast('No AI responses found to like', 'error');
                return;
            }
            targetMessage = botMessages[botMessages.length - 1];
        }

        // Check current state and toggle
        const isCurrentlyLiked = buttonElement.classList.contains('liked');
        const newLikedState = !isCurrentlyLiked;

        // Immediately update button appearance (optimistic UI)
        if (newLikedState) {
            // Liking the response
            buttonElement.classList.add('liked');
            buttonElement.style.color = '#007bff';
            buttonElement.style.opacity = '1';
            buttonElement.title = 'Response liked and cached! Click again to unlike.';
        } else {
            // Unliking the response
            buttonElement.classList.remove('liked');
            buttonElement.style.color = '#6c757d';
            buttonElement.style.opacity = '0.7';
            buttonElement.title = 'Like this response';
        }

        // Send feedback to backend
        try {
            const feedbackData = {
                prompt: targetMessage.originalPrompt || this.currentPrompt || 'Conversation context',
                response: targetMessage.content,
                is_helpful: newLikedState, // true = like/cache, false = unlike/remove
                feedback_notes: null
            };

            const response = await this.callAPI(`${this.apiUrl}/feedback`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(feedbackData)
            });

            if (response.success) {
                if (newLikedState) {
                    this.showToast('Response liked and cached for faster future answers!', 'success');
                } else {
                    this.showToast('Response unliked and removed from cache.', 'info');
                }
            } else {
                // Revert button if failed
                this.revertButtonState(buttonElement, isCurrentlyLiked);
                this.showToast('Failed to save feedback', 'error');
            }
        } catch (error) {
            // Revert button if failed
            this.revertButtonState(buttonElement, isCurrentlyLiked);
            this.showToast('Error: ' + error.message, 'error');
        }
    }

    revertButtonState(buttonElement, wasLiked) {
        if (wasLiked) {
            // Revert to liked state
            buttonElement.classList.add('liked');
            buttonElement.style.color = '#007bff';
            buttonElement.style.opacity = '1';
            buttonElement.title = 'Response liked and cached! Click again to unlike.';
        } else {
            // Revert to unliked state
            buttonElement.classList.remove('liked');
            buttonElement.style.color = '#6c757d';
            buttonElement.style.opacity = '0.7';
            buttonElement.title = 'Like this response';
        }
    }

    async logout() {
        // Call backend logout endpoint to end session
        if (this.authToken) {
            try {
                // ✅ FIX: Send session_id to properly end the session
                const body = this.sessionId && this.sessionId !== 'web_session'
                    ? JSON.stringify({ session_id: parseInt(this.sessionId) })
                    : null;

                await this.callAPI(`${this.apiUrl}/logout`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.authToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: body
                });
            } catch (error) {
                // Continue with local logout even if backend fails
            }
        }

        // Clear local data
        this.authToken = null;
        this.username = null;
        this.isGuest = true; // Update guest status
        this.sessions = [];
        this.activeSessionId = null;
        this.messages = [];
        this.lastUploadedFile = null;
        this.sessionId = 'web_session'; // ✅ FIX: Reset session_id

        // Reset token info
        this.tokenInfo = {
            max_tokens: 0,
            used_tokens: 0,
            remaining_tokens: 0,
            usage_percentage: 0
        };

        // Reset user profile
        this.userProfile = {
            user_id: null,
            role: 'STUDENT',
            status: 'ACTIVE'
        };

        localStorage.removeItem('faia-auth-token');
        localStorage.removeItem('faia-username');
        localStorage.removeItem('faia-sessions');
        localStorage.removeItem('faia-active-session');
        localStorage.removeItem('faia-session-id');
        localStorage.removeItem('faia-rag-enabled');
        // Clear legacy keys if they exist
        localStorage.removeItem('authToken');
        localStorage.removeItem('isLoggedIn');

        this.updateAuthUI();
        this.updateSessionsUI();
        this.updateUI();
        this.closeDrawer();
        this.showToast('Logged out successfully');
    }

    // Utility Functions
    setProcessing(processing) {
        this.isProcessing = processing;
        this.sendButton.disabled = processing;
        this.attachButton.disabled = processing;
        this.messageInput.disabled = processing;

        if (processing) {
            this.loadingOverlay.classList.add('show');
        } else {
            this.loadingOverlay.classList.remove('show');
        }
    }

    showToast(message, type = 'info') {
        if (!this.toast) return;

        const toastMessage = document.getElementById('toastMessage');
        const toastIcon = document.getElementById('toastIcon');

        if (!toastMessage) return;

        // Clear any existing timeout first
        if (this.toastTimeout) {
            clearTimeout(this.toastTimeout);
            this.toastTimeout = null;
        }

        // Hide current toast if showing
        this.toast.classList.remove('show');

        // Set message content
        toastMessage.textContent = message;

        // Set appropriate icon based on type
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };

        if (toastIcon) {
            toastIcon.className = icons[type] || icons.info;
        }

        // Reset classes and set new type
        this.toast.className = `toast toast-${type}`;

        // Small delay to ensure previous animation completes
        setTimeout(() => {
            if (this.toast) {
                this.toast.classList.add('show');

                // Set timeout to auto-hide
                this.toastTimeout = setTimeout(() => {
                    this.hideToast();
                }, 3000);
            }
        }, 50);
    }

    hideToast() {
        if (this.toast) {
            this.toast.classList.remove('show');
        }
        if (this.toastTimeout) {
            clearTimeout(this.toastTimeout);
            this.toastTimeout = null;
        }
    }

    // Debug function to test toast (can be called from browser console)
    testToast(type = 'info') {
        const messages = {
            info: 'This is an info message',
            success: 'This is a success message',
            error: 'This is an error message',
            warning: 'This is a warning message'
        };
        this.showToast(messages[type] || messages.info, type);
    }

    showConfirmDialog(title, message, onConfirm) {
        document.getElementById('confirmTitle').textContent = title;
        document.getElementById('confirmMessage').textContent = message;
        this.confirmDialog.classList.add('show');

        this.pendingConfirm = onConfirm;
    }

    hideConfirmDialog() {
        this.confirmDialog.classList.remove('show');
        this.pendingConfirm = null;
    }

    confirmAction() {
        if (this.pendingConfirm) {
            this.pendingConfirm();
        }
        this.hideConfirmDialog();
    }

    async callAPI(endpoint, options = {}) {
        const response = await fetch(endpoint, options);
        const data = await response.json();

        if (!response.ok) {

            // Handle 401 Unauthorized - invalid/expired token
            if (response.status === 401) {

                // Clear invalid token
                this.authToken = null;
                this.username = null;
                this.isGuest = true;

                localStorage.removeItem('faia-auth-token');
                localStorage.removeItem('faia-username');
                localStorage.removeItem('authToken');
                localStorage.removeItem('isLoggedIn');

                // Clear sessions since we're logged out
                this.sessions = [];
                this.activeSessionId = null;
                this.messages = [];
                localStorage.removeItem('faia-sessions');
                localStorage.removeItem('faia-active-session');

                // Update UI to show logged out state
                this.updateAuthUI();
                this.updateUserDisplay();
                this.updateSessionsUI();
                this.updateUI();

                // Show friendly toast message instead of blocking alert
                this.showToast('Your session has expired. Please login again.', 'warning');

                // Don't throw error, just return empty data
                return { error: 'Session expired', success: false };
            }

            // ✅ Better error message with details
            const errorMessage = data.detail || data.error || data.message || `HTTP ${response.status}`;
            throw new Error(errorMessage);
        }

        return data;
    }

    // Session Management - Database only, no localStorage
    loadSessions() {
        // Sessions are loaded from database via loadChatsFromDatabase()
    }

    saveSessions() {
        // Sessions are saved to database automatically
    }

    createNewSession(firstMessage = null) {
        if (this.isGuest) return;

        // Always create a new session immediately (don't wait for first message)
        const sessionId = 'session_' + Date.now();
        const sessionName = firstMessage ?
            (firstMessage.length > 30 ? firstMessage.substring(0, 30) + '...' : firstMessage) :
            'New Chat';

        const newSession = {
            id: sessionId,
            name: sessionName,
            messages: [],
            createdAt: new Date().toISOString(),
            lastActivity: new Date().toISOString(),
            chatId: null  // Will be set on first message
        };

        this.sessions.unshift(newSession); // Add to beginning
        this.activeSessionId = sessionId;
        this.messages = [];
        this.lastUploadedFile = null; // Clear file context for new session

        // Clear chat area
        if (this.chatMessages) {
            this.chatMessages.innerHTML = '';
        }

        this.saveSessions();
        this.updateSessionsUI();
        this.updateUI();
        this.closeDrawer();

        return sessionId;
    }

    switchToSession(sessionId) {
        if (this.isGuest) return;

        const session = this.sessions.find(s => s.id === sessionId);

        if (!session) {
            return;
        }

        this.activeSessionId = sessionId;
        this.messages = [...session.messages]; // Copy messages
        this.lastUploadedFile = null; // Clear file context when switching

        this.saveSessions();
        this.updateSessionsUI();

        // Re-render messages for the selected session
        if (this.chatMessages) {
            this.chatMessages.innerHTML = '';
            this.messages.forEach((msg, i) => {
                this.renderMessage(msg);
            });
            this.scrollToBottom();  // Scroll to bottom after switching sessions
        }

        this.updateUI();
        this.closeDrawer();
    }

    async deleteSession(sessionId) {
        if (this.isGuest) {
            return;
        }

        const session = this.sessions.find(s => s.id === sessionId);

        // If session has a chatId (backend chat), delete from backend
        if (session && session.chatId) {
            try {
                // Get current token info before deletion
                const tokensBefore = this.tokenInfo.used_tokens || 0;

                const response = await this.callAPI(`${this.apiUrl}/chat/${session.chatId}`, {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${this.authToken}`
                    }
                });

                if (response && response.success) {
                    // Refresh token info to get updated counts
                    await this.loadTokenInfo();

                    // Calculate tokens restored by comparing before and after
                    const tokensAfter = this.tokenInfo.used_tokens || 0;
                    const tokensRestored = Math.max(0, tokensBefore - tokensAfter);

                    // Check response for explicit token count first, then use calculated
                    const responseTokens = response.tokens_returned ||
                        response.tokensReturned ||
                        response.tokens_restored ||
                        response.restored_tokens;

                    const finalTokenCount = responseTokens !== undefined ? responseTokens : tokensRestored;

                    if (finalTokenCount > 0) {
                        this.showToast(`Chat deleted. ${finalTokenCount} tokens restored.`, 'success');
                    } else {
                        this.showToast('Chat deleted successfully.', 'success');
                    }
                } else if (response && response.error) {
                    this.showToast(`Error: ${response.error}`, 'error');
                } else {
                    this.showToast('Failed to delete chat from server', 'error');
                }
            } catch (error) {
                this.showToast(`Error: ${error.message}`, 'error');
            }
        } else {
            this.showToast('Chat deleted locally.', 'info');
        }

        // Remove from local sessions
        this.sessions = this.sessions.filter(s => s.id !== sessionId);

        // If deleting active session, switch to another or create new
        if (this.activeSessionId === sessionId) {
            if (this.sessions.length > 0) {
                this.switchToSession(this.sessions[0].id);
            } else {
                this.activeSessionId = null;
                this.messages = [];
                this.updateUI();
            }
        }

        this.saveSessions();
        this.updateSessionsUI();
        this.closeDrawer();
    }



    renameSession(sessionId) {
        if (this.isGuest) return;

        const session = this.sessions.find(s => s.id === sessionId);
        if (!session) return;

        this.renameSessionId = sessionId;
        this.renameInput.value = session.name;
        this.showRenameModal();
    }

    saveRename() {
        if (!this.renameSessionId) return;

        const newName = this.renameInput.value.trim();
        if (!newName) return;

        const session = this.sessions.find(s => s.id === this.renameSessionId);
        if (session) {
            session.name = newName;
            session.lastActivity = new Date().toISOString();
            this.saveSessions();
            this.updateSessionsUI();
        }

        this.hideRenameModal();
    }

    updateSessionsUI() {
        if (!this.sessionsList) return;

        this.sessionsList.innerHTML = '';

        this.sessions.forEach(session => {
            const sessionElement = document.createElement('div');
            sessionElement.className = `session-item ${session.id === this.activeSessionId ? 'active' : ''}`;
            sessionElement.innerHTML = `
                <div class="session-content" title="${session.name}">
                    <i class="fas fa-comment"></i>
                    <span class="session-name">${session.name}</span>
                </div>
                <div class="session-actions">
                    <button class="session-action-btn rename-btn" title="Rename chat">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="session-action-btn delete-btn" title="Delete chat">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;

            // Add click handlers using addEventListener (safer than inline onclick)
            const contentDiv = sessionElement.querySelector('.session-content');
            const renameBtn = sessionElement.querySelector('.rename-btn');
            const deleteBtn = sessionElement.querySelector('.delete-btn');

            contentDiv.addEventListener('click', () => {
                this.switchToSession(session.id);
            });

            renameBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent triggering session switch
                this.renameSession(session.id);
            });

            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent triggering session switch
                this.deleteSession(session.id);
            });

            this.sessionsList.appendChild(sessionElement);
        });
    }

    updateUserDisplay() {
        if (!this.userDisplay) return;

        if (this.isGuest) {
            this.userDisplay.textContent = 'Guest User';
        } else {
            this.userDisplay.textContent = this.username || 'Logged In User';
        }

        // Update token info display
        this.updateTokenDisplay();
    }

    async loadTokenInfo() {
        if (this.isGuest || !this.authToken) return;

        try {
            const response = await this.callAPI(`${this.apiUrl}/user/tokens`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json'
                }
            });

            // If response indicates error (like session expired), skip update
            if (response && response.error) {
                return;
            }

            if (response && !response.is_guest) {
                this.tokenInfo = {
                    max_tokens: response.max_tokens || 100000,
                    used_tokens: response.used_tokens || 0,
                    remaining_tokens: response.remaining_tokens || 100000,
                    usage_percentage: response.usage_percentage || 0
                };
                this.updateTokenDisplay();
            }
        } catch (error) {
        }
    }

    updateTokenDisplay() {
        const tokenInfo = document.getElementById('tokenInfo');
        const tokenUsage = document.getElementById('tokenUsage');
        const tokenProgress = document.getElementById('tokenProgress');

        if (!tokenInfo || !tokenUsage || !tokenProgress) return;

        if (this.isGuest || this.tokenInfo.max_tokens === 0) {
            tokenInfo.style.display = 'none';
            return;
        }

        tokenInfo.style.display = 'flex';
        tokenUsage.textContent = `${this.tokenInfo.used_tokens.toLocaleString()} / ${this.tokenInfo.max_tokens.toLocaleString()}`;
        tokenProgress.style.width = `${Math.min(this.tokenInfo.usage_percentage, 100)}%`;

        // Change color based on usage
        if (this.tokenInfo.usage_percentage > 90) {
            tokenProgress.style.background = 'var(--current-error)';
        } else if (this.tokenInfo.usage_percentage > 75) {
            tokenProgress.style.background = '#FFA500';
        } else {
            tokenProgress.style.background = 'var(--current-primary)';
        }
    }

    async loadUserFiles() {
        if (this.isGuest) return [];

        try {
            const response = await this.callAPI(`${this.apiUrl}/user/files`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json'
                }
            });

            return response.files || [];
        } catch (error) {
            return [];
        }
    }

    updateSessionMessages(sessionId, messages) {
        if (this.isGuest) return;

        const session = this.sessions.find(s => s.id === sessionId);
        if (session) {
            session.messages = [...messages];
            session.lastActivity = new Date().toISOString();
            this.saveSessions();
        }
    }

    updateAuthUI() {
        // Update UI based on auth status
        const isLoggedIn = !!this.authToken;

        // Update drawer auth buttons (only show for guests)
        if (this.loginButton) this.loginButton.style.display = isLoggedIn ? 'none' : 'flex';
        if (this.registerButton) this.registerButton.style.display = isLoggedIn ? 'none' : 'flex';

        // Show logout and change password buttons if logged in
        const logoutButton = document.getElementById('logoutButton');
        const changePasswordButton = document.getElementById('changePasswordButton');
        if (logoutButton) logoutButton.style.display = isLoggedIn ? 'flex' : 'none';
        if (changePasswordButton) changePasswordButton.style.display = isLoggedIn ? 'flex' : 'none';

        // Show/hide guest banner
        const guestBanner = document.getElementById('guestBanner');
        if (guestBanner) guestBanner.style.display = this.isGuest ? 'block' : 'none';

        // Guest register link handler
        const guestRegisterLink = document.getElementById('guestRegisterLink');
        if (guestRegisterLink) {
            guestRegisterLink.onclick = (e) => {
                e.preventDefault();
                this.showRegisterModal();
            };
        }

        // Show/hide guest auth section in drawer
        if (this.guestAuthSection) {
            this.guestAuthSection.style.display = isLoggedIn ? 'none' : 'block';
        }

        // Show/hide sessions section
        if (this.sessionsSection) {
            this.sessionsSection.style.display = isLoggedIn ? 'block' : 'none';
        }

        // Update guest status
        this.isGuest = !isLoggedIn;

        // Update RAG button state for current user type
        if (this.ragToggleButton) {
            this.ragToggleButton.style.display = 'flex';
            this.updateRAGButton();
        }

        this.updateUserDisplay();
        this.updateSettingsUI();
    }

    showRenameModal() {
        if (this.renameModal) {
            this.renameModal.classList.add('show');
        }
    }

    hideRenameModal() {
        if (this.renameModal) {
            this.renameModal.classList.remove('show');
        }
        this.renameSessionId = null;
        this.renameInput.value = '';
    }

    // Data Persistence
    saveMessages() {
        // Database-only mode - messages are saved to database automatically
        // No localStorage usage
    }

    loadMessages() {
        // Load messages from active session (in-memory)
        if (this.activeSessionId) {
            const session = this.sessions.find(s => s.id === this.activeSessionId);
            this.messages = session ? [...(session.messages || [])] : [];
            // Normalize timestamps
            this.messages.forEach(message => {
                if (!(message.timestamp instanceof Date)) {
                    message.timestamp = new Date(message.timestamp);
                }
            });
        } else {
            this.messages = [];
        }

        if (this.chatMessages) {
            this.chatMessages.innerHTML = '';
            this.messages.forEach(message => this.renderMessage(message));
            // Use setTimeout to scroll after DOM finishes painting all messages
            setTimeout(() => this.scrollToBottom(), 150);
        }
        this.updateUI();
    }

    // Settings Modal Management
    showSettingsModal() {
        if (this.settingsModal) {
            this.settingsModal.classList.add('show');
            this.updateSettingsUI();
        }
        this.closeDrawer();
    }

    hideSettingsModal() {
        if (this.settingsModal) {
            this.settingsModal.classList.remove('show');
        }
    }

    updateSettingsUI() {
        // Update settings modal based on auth status
        if (this.accountSection) {
            this.accountSection.style.display = this.isGuest ? 'none' : 'block';
        }
        if (this.guestSection) {
            this.guestSection.style.display = this.isGuest ? 'block' : 'none';
        }

        // Update auth section in drawer
        if (this.guestAuthSection) {
            this.guestAuthSection.style.display = this.isGuest ? 'block' : 'none';
        }

    }



    // RAG Toggle Functionality
    toggleRAG() {
        // Check if user is guest
        if (this.isGuest) {
            // Show login prompt for guests (same as file upload)
            this.showToast('Please register or log in to use RAG (Retrieval Augmented Generation) features', 'info');
            return;
        }

        // Check if file is uploaded - prevent RAG activation
        if (this.lastUploadedFile && !this.ragEnabled) {
            this.showToast('RAG cannot be enabled while a file is uploaded. Remove the file first to use RAG with knowledge base.', 'warning');
            return;
        }

        this.ragEnabled = !this.ragEnabled;
        localStorage.setItem('faia-rag-enabled', this.ragEnabled.toString());
        this.updateRAGButton();

        // Enhanced feedback with more information
        const status = this.ragEnabled ? 'enabled' : 'disabled';
        const description = this.ragEnabled
            ? 'RAG will use knowledge base to enhance responses'
            : 'RAG disabled - using model knowledge only';

        this.showToast(`RAG ${status} - ${description}`, 'info');
    }

    updateRAGButton() {
        if (!this.ragToggleButton) return;

        // For guests, always show as disabled with login prompt
        if (this.isGuest) {
            this.ragToggleButton.classList.add('disabled');
            this.ragToggleButton.style.background = 'linear-gradient(135deg, #6c757d, #5a6268)';
            this.ragToggleButton.title = 'RAG (Retrieval Augmented Generation)\nPlease register or log in to use this feature';
            this.ragToggleButton.innerHTML = '<i class="fas fa-brain"></i>';
            this.ragToggleButton.style.animation = 'none';
            this.ragToggleButton.style.display = 'flex'; // Ensure it's visible
            return;
        }

        // For logged-in users, show actual state
        const hasUploadedFile = this.lastUploadedFile && this.lastUploadedFile.processed;
        
        if (this.ragEnabled) {
            this.ragToggleButton.classList.remove('disabled');
            this.ragToggleButton.style.background = 'linear-gradient(135deg, #28a745, #20c997)';
            this.ragToggleButton.title = 'RAG Enabled - Retrieval Augmented Generation active\nClick to disable and use model knowledge only';

            // Add visual indicator
            this.ragToggleButton.innerHTML = '<i class="fas fa-brain"></i>';
        } else {
            this.ragToggleButton.classList.add('disabled');
            this.ragToggleButton.style.background = 'linear-gradient(135deg, #6c757d, #5a6268)';
            
            // Different tooltip based on whether file is uploaded
            if (hasUploadedFile) {
                this.ragToggleButton.title = 'RAG Disabled - Using uploaded file content\nRemove file to enable knowledge base retrieval';
            } else {
                this.ragToggleButton.title = 'RAG Disabled - Using model knowledge only\nClick to enable knowledge base retrieval';
            }

            // Add visual indicator
            this.ragToggleButton.innerHTML = '<i class="fas fa-brain"></i>';
        }

        // Add pulsing effect when enabled
        if (this.ragEnabled) {
            this.ragToggleButton.style.animation = 'pulse 2s infinite';
        } else {
            this.ragToggleButton.style.animation = 'none';
        }
    }

    // Search Chat Functionality
    filterSessions(searchTerm) {
        if (!this.sessionsList) return;

        const sessions = this.sessionsList.querySelectorAll('.session-item');
        const term = searchTerm.toLowerCase().trim();

        sessions.forEach(sessionElement => {
            const sessionName = sessionElement.querySelector('.session-name');
            if (sessionName) {
                const name = sessionName.textContent.toLowerCase();
                const matches = name.includes(term);
                sessionElement.style.display = matches ? 'flex' : 'none';
            }
        });
    }



    // Delete All Chats Functionality
    async deleteAllChats() {
        if (this.isGuest) {
            this.showToast('Please login to delete chat history', 'warning');
            return;
        }

        this.showConfirmDialog(
            'Complete Reset & Fresh Start',
            'This will completely reset your account: delete ALL chats, clear uploaded files, end all sessions, and fully restore your token quota. You\'ll get a completely fresh start. This action cannot be undone. Continue?',
            async () => {
                try {
                    const response = await this.callAPI(`${this.apiUrl}/chat/history`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${this.authToken}`
                        }
                    });

                    if (response.success) {
                        // COMPREHENSIVE LOCAL CLEANUP
                        this.sessions = [];
                        this.activeSessionId = null;
                        this.messages = [];
                        this.lastUploadedFile = null;
                        this.currentPrompt = null;

                        // Reset session ID to default
                        this.sessionId = 'web_session';

                        // Clear any cached data
                        if (typeof (Storage) !== "undefined") {
                            // Clear any session-specific data but keep auth
                            const authToken = localStorage.getItem('faia-auth-token');
                            const username = localStorage.getItem('faia-username');

                            // Clear session data
                            localStorage.removeItem('faia-session-id');
                            localStorage.removeItem('faia-messages');
                            localStorage.removeItem('faia-sessions');

                            // Restore auth data
                            if (authToken) localStorage.setItem('faia-auth-token', authToken);
                            if (username) localStorage.setItem('faia-username', username);
                        }

                        // Clear UI completely
                        if (this.chatMessages) {
                            this.chatMessages.innerHTML = '';
                        }

                        // Show welcome screen
                        if (this.welcomeScreen) {
                            this.welcomeScreen.style.display = 'flex';
                        }
                        if (this.chatMessages) {
                            this.chatMessages.style.display = 'none';
                        }

                        // Update all UI components
                        this.updateSessionsUI();
                        this.updateUI();

                        // Show comprehensive reset success message
                        const chatsDeleted = response.chats_deleted || 0;
                        const tokensRecovered = response.tokens_recovered || response.tokens_returned || 0;
                        const filesCleared = response.files_cleared || 0;
                        const sessionsEnded = response.sessions_ended || 0;

                        let message = `🎉 Complete reset successful! `;
                        let details = [];

                        if (chatsDeleted > 0) details.push(`${chatsDeleted} chat${chatsDeleted !== 1 ? 's' : ''} deleted`);
                        if (tokensRecovered > 0) details.push(`${tokensRecovered.toLocaleString()} tokens recovered`);
                        if (filesCleared > 0) details.push(`${filesCleared} file${filesCleared !== 1 ? 's' : ''} cleared`);
                        if (sessionsEnded > 0) details.push(`${sessionsEnded} session${sessionsEnded !== 1 ? 's' : ''} ended`);

                        if (details.length > 0) {
                            message += details.join(', ') + '. ';
                        }

                        message += 'Fresh start ready!';

                        this.showToast(message, 'success');

                        // Refresh token info to show restored tokens
                        if (tokensRecovered > 0) {
                            setTimeout(() => this.loadTokenInfo(), 1000);
                        }
                    } else {
                        this.showToast('Failed to delete chat history: ' + (response.error || response.detail || 'Unknown error'), 'error');
                    }
                } catch (error) {
                    this.showToast('Failed to delete chat history: ' + error.message, 'error');
                }
            }
        );
    }
}

// Initialize the app when DOM is loaded
let app;
document.addEventListener('DOMContentLoaded', () => {
    // Expose globally for inline onclick handlers
    window.app = new FAIAWebApp();
    app = window.app;
});
