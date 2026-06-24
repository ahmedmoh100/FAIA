/**
 * Global Loader Management System
 * Provides beautiful animated loading states for the FAIA Admin interface
 */

class LoaderManager {
    constructor() {
        this.overlay = document.getElementById('globalLoader');
        this.loadingText = document.getElementById('loadingText');
        this.loadingSubtext = document.getElementById('loadingSubtext');
        this.progressBar = document.getElementById('progressBar');
        this.isVisible = false;
        this.currentProgress = 0;
        this.loadingMessages = [
            { text: 'Loading...', subtext: 'Please wait while we prepare your dashboard' },
            { text: 'Fetching data...', subtext: 'Retrieving the latest information' },
            { text: 'Processing...', subtext: 'Analyzing and organizing content' },
            { text: 'Almost ready...', subtext: 'Finalizing your experience' },
            { text: 'Connecting...', subtext: 'Establishing secure connection' },
            { text: 'Authenticating...', subtext: 'Verifying your credentials' },
            { text: 'Loading users...', subtext: 'Fetching user management data' },
            { text: 'Loading files...', subtext: 'Retrieving file system information' }
        ];
        this.messageIndex = 0;
        this.messageInterval = null;
        this.progressInterval = null;
    }

    /**
     * Show the global loader with optional custom message
     * @param {string} message - Custom loading message
     * @param {string} subtext - Custom subtext
     * @param {boolean} showProgress - Whether to show progress bar animation
     */
    show(message = null, subtext = null, showProgress = true) {
        if (this.isVisible) return;

        this.isVisible = true;
        this.currentProgress = 0;

        // Set custom message or use default
        if (message) {
            this.loadingText.textContent = message;
            this.loadingSubtext.textContent = subtext || 'Please wait...';
        } else {
            this.setRandomMessage();
        }

        // Reset progress bar
        this.progressBar.style.width = '0%';

        // Show overlay with animation
        this.overlay.classList.add('show');
        this.overlay.classList.remove('hide');

        // Start message rotation if no custom message
        if (!message) {
            this.startMessageRotation();
        }

        // Start progress animation if enabled
        if (showProgress) {
            this.startProgressAnimation();
        }
    }

    /**
     * Hide the global loader
     * @param {number} delay - Delay before hiding (ms)
     */
    hide(delay = 0) {
        setTimeout(() => {
            if (!this.isVisible) return;

            this.isVisible = false;

            // Stop intervals
            this.stopMessageRotation();
            this.stopProgressAnimation();

            // Hide overlay with animation
            this.overlay.classList.add('hide');
            this.overlay.classList.remove('show');

            // Reset after animation completes
            setTimeout(() => {
                this.currentProgress = 0;
                this.progressBar.style.width = '0%';
                this.messageIndex = 0;
            }, 300);
        }, delay);
    }

    /**
     * Update loading message
     * @param {string} message - New message
     * @param {string} subtext - New subtext
     */
    updateMessage(message, subtext = null) {
        if (!this.isVisible) return;

        this.loadingText.textContent = message;
        if (subtext) {
            this.loadingSubtext.textContent = subtext;
        }
    }

    /**
     * Set progress percentage
     * @param {number} percentage - Progress percentage (0-100)
     */
    setProgress(percentage) {
        if (!this.isVisible) return;

        this.currentProgress = Math.max(0, Math.min(100, percentage));
        this.progressBar.style.width = `${this.currentProgress}%`;
    }

    /**
     * Simulate progress animation
     * @param {number} duration - Duration in milliseconds
     * @param {Function} callback - Callback when complete
     */
    simulateProgress(duration = 3000, callback = null) {
        if (!this.isVisible) return;

        const steps = 50;
        const stepDuration = duration / steps;
        let currentStep = 0;

        const progressInterval = setInterval(() => {
            currentStep++;
            const progress = (currentStep / steps) * 100;
            this.setProgress(progress);

            if (currentStep >= steps) {
                clearInterval(progressInterval);
                if (callback) callback();
            }
        }, stepDuration);
    }

    /**
     * Start rotating loading messages
     */
    startMessageRotation() {
        this.stopMessageRotation(); // Clear any existing interval

        this.messageInterval = setInterval(() => {
            this.messageIndex = (this.messageIndex + 1) % this.loadingMessages.length;
            const message = this.loadingMessages[this.messageIndex];
            this.loadingText.textContent = message.text;
            this.loadingSubtext.textContent = message.subtext;
        }, 10000);
    }

    /**
     * Stop rotating loading messages
     */
    stopMessageRotation() {
        if (this.messageInterval) {
            clearInterval(this.messageInterval);
            this.messageInterval = null;
        }
    }

    /**
     * Start progress bar animation
     */
    startProgressAnimation() {
        this.stopProgressAnimation(); // Clear any existing interval

        let progress = 0;
        this.progressInterval = setInterval(() => {
            progress += Math.random() * 3;
            if (progress > 90) progress = 90; // Don't complete automatically
            this.setProgress(progress);
        }, 200);
    }

    /**
     * Stop progress bar animation
     */
    stopProgressAnimation() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }

    /**
     * Set a random loading message
     */
    setRandomMessage() {
        const message = this.loadingMessages[Math.floor(Math.random() * this.loadingMessages.length)];
        this.loadingText.textContent = message.text;
        this.loadingSubtext.textContent = message.subtext;
    }

    /**
     * Show loader for a specific page
     * @param {string} page - Page name
     */
    showForPage(page) {
        const pageMessages = {
            users: { text: 'Loading users...', subtext: 'Fetching user management data' },
            files: { text: 'Loading files...', subtext: 'Retrieving file system information' },
            audit: { text: 'Loading audit logs...', subtext: 'Preparing system audit information' },
            system: { text: 'Loading system info...', subtext: 'Gathering system diagnostics' },
            overview: { text: 'Loading dashboard...', subtext: 'Preparing your admin overview' }
        };

        const message = pageMessages[page] || pageMessages.overview;
        this.show(message.text, message.subtext);
    }

    /**
     * Show loader with custom duration and auto-hide
     * @param {number} duration - Duration in milliseconds
     * @param {string} message - Custom message
     * @param {string} subtext - Custom subtext
     */
    showTimed(duration = 2000, message = null, subtext = null) {
        this.show(message, subtext);
        this.simulateProgress(duration * 0.8, () => {
            this.setProgress(100);
            setTimeout(() => this.hide(), 200);
        });
    }
}

// Create global loader instance
window.Loader = new LoaderManager();

// Utility functions for easy access
window.showLoader = (message, subtext, showProgress) => window.Loader.show(message, subtext, showProgress);
window.hideLoader = (delay) => window.Loader.hide(delay);
window.updateLoader = (message, subtext) => window.Loader.updateMessage(message, subtext);
window.setLoaderProgress = (percentage) => window.Loader.setProgress(percentage);

// Auto-hide loader on page load if it's showing
document.addEventListener('DOMContentLoaded', () => {
    // Small delay to ensure smooth transition
    setTimeout(() => {
        if (window.Loader && window.Loader.isVisible) {
            window.Loader.hide();
        }
    }, 500);
});

// Show loader on page unload for navigation
window.addEventListener('beforeunload', () => {
    if (window.Loader) {
        window.Loader.show('Loading...', 'Navigating to new page');
    }
});