/**
 * Toast Notification System
 * Provides beautiful toast notifications that work with the loader system
 */

class ToastManager {
  constructor() {
    this.toasts = [];
    this.container = null;
    this.createContainer();
  }

  createContainer() {
    this.container = document.createElement('div');
    this.container.id = 'toast-container';
    this.container.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 12px;
      pointer-events: none;
    `;
    document.body.appendChild(this.container);
  }

  show(message, type = 'info', duration = 4000) {
    const toast = this.createToast(message, type);
    this.container.appendChild(toast);
    this.toasts.push(toast);

    // Animate in
    setTimeout(() => {
      toast.classList.add('toast-show');
    }, 10);

    // Auto remove
    setTimeout(() => {
      this.hide(toast);
    }, duration);

    return toast;
  }

  createToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icons = {
      success: 'fas fa-check-circle',
      error: 'fas fa-exclamation-circle',
      warning: 'fas fa-exclamation-triangle',
      info: 'fas fa-info-circle'
    };

    toast.innerHTML = `
      <i class="toast-icon ${icons[type] || icons.info}"></i>
      <span>${message}</span>
    `;

    // Make clickable to dismiss
    toast.style.pointerEvents = 'auto';
    toast.style.cursor = 'pointer';
    toast.onclick = () => this.hide(toast);

    return toast;
  }

  hide(toast) {
    if (!toast || !toast.parentNode) return;
    
    toast.classList.add('toast-exit');
    
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
      const index = this.toasts.indexOf(toast);
      if (index > -1) {
        this.toasts.splice(index, 1);
      }
    }, 300);
  }

  success(message, duration) {
    return this.show(message, 'success', duration);
  }

  error(message, duration) {
    return this.show(message, 'error', duration);
  }

  warning(message, duration) {
    return this.show(message, 'warning', duration);
  }

  info(message, duration) {
    return this.show(message, 'info', duration);
  }

  clear() {
    this.toasts.forEach(toast => this.hide(toast));
  }
}

// Create global toast instance
window.Toast = new ToastManager();

// Utility functions for easy access
window.showToast = (message, type, duration) => window.Toast.show(message, type, duration);
window.showSuccess = (message, duration) => window.Toast.success(message, duration);
window.showError = (message, duration) => window.Toast.error(message, duration);
window.showWarning = (message, duration) => window.Toast.warning(message, duration);
window.showInfo = (message, duration) => window.Toast.info(message, duration);