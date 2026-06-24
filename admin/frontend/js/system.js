// System Page JavaScript

// Ensure toast function is available globally
if (typeof window.toast === 'undefined') {
  window.toast = function(msg) {
    // Fallback toast implementation
    const el = document.createElement('div');
    el.className = 'toast toast-show';
    el.textContent = msg;
    el.style.cssText = `
      position: fixed;
      right: 24px;
      bottom: 24px;
      background: var(--card);
      color: var(--text);
      padding: 16px 20px;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
      z-index: 9999;
      font-weight: 500;
    `;
    document.body.appendChild(el);
    setTimeout(() => { 
      if (el.parentNode) el.parentNode.removeChild(el); 
    }, 3000);
  };
}

async function initSystemPage() {
  // Initialize tabs
  initTabs();
  
  // Initialize each tab's functionality with delays to ensure DOM readiness
  setTimeout(() => {
    initHealthCheck();
    initBackupRestore();
    initTokenization();
    initResourceMonitor();
  }, 200);
}

// ── Live Resource Monitor ──────────────────────────────────
let resourceInterval = null;

function getBarClass(percent) {
  if (percent >= 80) return 'danger';
  if (percent >= 50) return 'warn';
  return '';
}

function getResourceStatus(percent, thresholds) {
  if (percent >= thresholds.danger) return { text: 'Critical', color: '#e74c3c' };
  if (percent >= thresholds.warn)   return { text: 'High',     color: '#f39c12' };
  return                                   { text: 'Normal',   color: '#27ae60' };
}

async function refreshResourceMonitor() {
  try {
    const data = await AdminApi.apiGet('/admin/system/resources');

    const cpu    = Math.round(data.cpu_usage    || 0);
    const memory = Math.round(data.memory_usage || 0);
    const disk   = Math.round(data.disk_usage   || 0);
    const diskFree = data.disk_free !== undefined ? data.disk_free + ' GB free' : '';

    function setBar(id, percent) {
      const el = document.getElementById(id);
      if (el) { el.style.width = percent + '%'; el.className = 'resource-bar-fill ' + getBarClass(percent); }
    }
    function setVal(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
    function setSt(id, percent, thresholds, extra) {
      const el = document.getElementById(id);
      if (!el) return;
      const s = getResourceStatus(percent, thresholds);
      el.textContent = s.text + (extra ? ' — ' + extra : '');
      el.style.color = s.color;
    }

    setBar('cpu-bar', cpu);      setVal('cpu-value', cpu + '%');      setSt('cpu-status',    cpu,    {warn:50, danger:80}, '');
    setBar('memory-bar', memory); setVal('memory-value', memory + '%'); setSt('memory-status', memory, {warn:60, danger:85}, '');
    setBar('disk-bar', disk);    setVal('disk-value', disk + '%');    setSt('disk-status',   disk,   {warn:70, danger:90}, diskFree);

    const lastUp = document.getElementById('resource-last-updated');
    if (lastUp) lastUp.textContent = 'Last updated: ' + new Date().toLocaleTimeString();

  } catch (e) {
    console.error('Resource monitor error:', e);
  }
}

function initResourceMonitor() {
  refreshResourceMonitor();
  if (resourceInterval) clearInterval(resourceInterval);
  resourceInterval = setInterval(refreshResourceMonitor, 5000);

  // Stop when leaving health tab
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.getAttribute('data-tab') === 'health') {
        if (!resourceInterval) resourceInterval = setInterval(refreshResourceMonitor, 5000);
        refreshResourceMonitor();
      } else {
        if (resourceInterval) { clearInterval(resourceInterval); resourceInterval = null; }
      }
    });
  });
}

function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      
      // Remove active class from all tabs and panels
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.remove('active'));
      
      // Add active class to clicked tab and corresponding panel
      btn.classList.add('active');
      document.getElementById(`${targetTab}-tab`).classList.add('active');
      
      // Trigger tab-specific refresh
      switch(targetTab) {
        case 'health':
          refreshHealthCheck();
          break;
        case 'backup':
          refreshBackupHistory();
          break;
        case 'tokenization':
          refreshTokenization();
          break;
      }
    });
  });
}

// Health Check Tab
function initHealthCheck() {
  const btn = document.getElementById('refresh-health');
  if (!btn) return; // guard if system.html not mounted yet
  btn.addEventListener('click', refreshHealthCheck);
  refreshHealthCheck();
}

async function refreshHealthCheck() {
  try {
    // Get system health data
    const healthData = await AdminApi.apiGet('/admin/system/health');
    
    // Update enhanced health status (same as dashboard)
    const healthStatus = document.getElementById('healthStatus');
    if (healthStatus) {
      healthStatus.innerHTML = `
        <div class="status-grid">
          <div class="status-item">
            <div class="status-icon status-ok">
              <i class="fas fa-server"></i>
            </div>
            <div class="status-info">
              <div class="status-label">Server Status</div>
              <div class="status-value">Online</div>
              <div class="status-detail">Uptime: ${healthData.uptime || 'Unknown'}</div>
            </div>
          </div>
          
          <div class="status-item">
            <div class="status-icon ${healthData.database ? 'status-ok' : 'status-error'}">
              <i class="fas fa-database"></i>
            </div>
            <div class="status-info">
              <div class="status-label">Database</div>
              <div class="status-value">${healthData.database ? 'Connected' : 'Disconnected'}</div>
              <div class="status-detail">${healthData.database ? 'All systems operational' : 'Connection failed'}</div>
            </div>
          </div>
          
          <div class="status-item">
            <div class="status-icon ${healthData.ai_model ? 'status-ok' : 'status-error'}">
              <i class="fas fa-robot"></i>
            </div>
            <div class="status-info">
              <div class="status-label">AI Model</div>
              <div class="status-value">${healthData.ai_model ? 'Active' : 'Inactive'}</div>
              <div class="status-detail">${healthData.ai_model ? 'Ready for requests' : 'Model unavailable'}</div>
            </div>
          </div>
          
          <div class="status-item">
            <div class="status-icon status-info">
              <i class="fas fa-hdd"></i>
            </div>
            <div class="status-info">
              <div class="status-label">Disk Usage</div>
              <div class="status-value" style="color: ${(healthData.system_load || 0) > 90 ? 'var(--danger)' : 'var(--ok)'}">
                ${healthData.disk_usage !== undefined ? healthData.disk_usage + '%' : 'N/A'}
              </div>
              <div class="status-detail">${healthData.disk_free !== undefined ? healthData.disk_free + ' GB free' : 'Check system'}</div>
            </div>
          </div>
        </div>
      `;
    }
    
    // Update system statistics
    const systemStats = document.getElementById('systemStats');
    if (systemStats) {
      systemStats.innerHTML = `
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-number">${healthData.total_users || 0}</span>
            <span class="stat-label">Total Users</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">${healthData.active_sessions || 0}</span>
            <span class="stat-label">Active Sessions</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">${healthData.total_files || 0}</span>
            <span class="stat-label">Total Files</span>
          </div>
          <div class="stat-item">
            <span class="stat-number">${healthData.system_load || 0}%</span>
            <span class="stat-label">System Load</span>
          </div>
        </div>
      `;
    }
    
    // Update detailed health information
    const detailedHealth = document.getElementById('detailedHealth');
    if (detailedHealth) {
      detailedHealth.innerHTML = `
        <div class="detailed-health-grid">
          <div class="health-section">
            <h4><i class="fas fa-server"></i> Server Information</h4>
            <div class="health-details">
              <div class="health-detail">
                <span class="detail-label">Uptime:</span>
                <span class="detail-value">${healthData.uptime || 'Unknown'}</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">Load Average:</span>
                <span class="detail-value">${healthData.system_load || 0}%</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">API Response Time:</span>
                <span class="detail-value">${healthData.api_response_time || 0}ms</span>
              </div>
            </div>
          </div>
          
          <div class="health-section">
            <h4><i class="fas fa-database"></i> Database Status</h4>
            <div class="health-details">
              <div class="health-detail">
                <span class="detail-label">Connection:</span>
                <span class="detail-value ${healthData.database ? 'status-ok' : 'status-error'}">${healthData.database ? 'Connected' : 'Disconnected'}</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">Total Users:</span>
                <span class="detail-value">${healthData.total_users || 0}</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">Total Files:</span>
                <span class="detail-value">${healthData.total_files || 0}</span>
              </div>
            </div>
          </div>
          
          <div class="health-section">
            <h4><i class="fas fa-robot"></i> AI Services</h4>
            <div class="health-details">
              <div class="health-detail">
                <span class="detail-label">Model Status:</span>
                <span class="detail-value ${healthData.ai_model ? 'status-ok' : 'status-error'}">${healthData.ai_model ? 'Active' : 'Inactive'}</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">Active Sessions:</span>
                <span class="detail-value">${healthData.active_sessions || 0}</span>
              </div>
              <div class="health-detail">
                <span class="detail-label">Service Health:</span>
                <span class="detail-value status-ok">Operational</span>
              </div>
            </div>
          </div>
        </div>
      `;
    }
    
    // Update overall health badge
    const overallBadge = document.getElementById('overall-health-badge');
    if (overallBadge) {
      const isHealthy = healthData.database && healthData.ai_model;
      overallBadge.className = `badge ${isHealthy ? 'ok pulse' : 'warn'}`;
      overallBadge.textContent = isHealthy ? 'HEALTHY' : 'ISSUES DETECTED';
    }
    
  } catch (error) {
    console.error('Health check error:', error);
    toast('Failed to refresh health check: ' + error.message);
    
    // Show error state
    const healthStatus = document.getElementById('healthStatus');
    if (healthStatus) {
      healthStatus.innerHTML = `
        <div class="error-state">
          <i class="fas fa-exclamation-triangle"></i>
          <p>Failed to load health status</p>
          <small>${error.message}</small>
        </div>
      `;
    }
    
    const overallBadge = document.getElementById('overall-health-badge');
    if (overallBadge) {
      overallBadge.className = 'badge danger';
      overallBadge.textContent = 'ERROR';
    }
  }
}

// Backup & Restore Tab
function initBackupRestore() {
  const createBackupBtn = document.getElementById('create-backup');
  const selectBackupBtn = document.getElementById('select-backup');
  const backupFileInput = document.getElementById('backup-file');
  const restoreBackupBtn = document.getElementById('restore-backup');
  
  if (!createBackupBtn || !selectBackupBtn || !backupFileInput || !restoreBackupBtn) {
    console.warn('Backup & Restore elements not found, skipping initialization');
    return;
  }
  
  createBackupBtn.addEventListener('click', createBackup);
  selectBackupBtn.addEventListener('click', () => {
    backupFileInput.click();
  });
  backupFileInput.addEventListener('change', handleBackupFileSelect);
  restoreBackupBtn.addEventListener('click', restoreBackup);
  
  refreshBackupHistory();
}

async function createBackup() {
  const btn = document.getElementById('create-backup');
  const status = document.getElementById('backup-status');
  
  // Add loading state to button
  btn.classList.add('loading');
  btn.disabled = true;
  status.textContent = 'Preparing backup...';
  
  // Show loader with backup-specific messaging
  if (window.Loader) {
    window.Loader.show('Creating backup...', 'Collecting database, files, and configurations');
  }
  
  try {
    // Update loader message during process
    if (window.Loader) {
      setTimeout(() => window.Loader.updateMessage('Compressing data...', 'Creating downloadable backup file'), 1000);
      setTimeout(() => window.Loader.updateMessage('Almost ready...', 'Finalizing backup archive'), 2000);
    }
    
    const response = await fetch(`${AdminApi.API_BASE}/admin/system/backup`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${AdminApi.getToken() || 'demo:admin'}`
      }
    });
    
    if (!response.ok) {
      throw new Error('Backup creation failed');
    }
    
    // Get the file blob and download it
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backup_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    // Complete the progress
    if (window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => {
        window.Loader.hide();
        if (window.showToast) {
          window.showToast('Backup created and downloaded successfully!', 'success');
        } else {
          toast('Backup created and downloaded');
        }
      }, 500);
    } else {
      toast('Backup created and downloaded');
    }
    
    status.innerHTML = `<i class="fas fa-check-circle" style="color: var(--ok);"></i> Backup created and downloaded`;
    refreshBackupHistory();
    
  } catch (error) {
    console.error('Backup error:', error);
    
    // Hide loader and show error
    if (window.Loader) {
      window.Loader.hide();
    }
    
    if (window.showToast) {
      window.showToast('Backup failed: ' + error.message, 'error');
    }
    
    status.innerHTML = '<i class="fas fa-times-circle" style="color: var(--danger);"></i> Backup failed: ' + error.message;
  } finally {
    // Remove loading state
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

function handleBackupFileSelect(event) {
  const file = event.target.files[0];
  if (file) {
    document.getElementById('selected-file').textContent = file.name;
    document.getElementById('restore-backup').disabled = false;
  }
}

async function restoreBackup() {
  const fileInput = document.getElementById('backup-file');
  const btn = document.getElementById('restore-backup');
  const status = document.getElementById('restore-status');
  
  if (!fileInput.files[0]) {
    if (window.showToast) {
      window.showToast('Please select a backup file first', 'warning');
    } else {
      toast('Please select a backup file first');
    }
    return;
  }
  
  if (!confirm('WARNING: This will restore the entire system from backup. Are you sure?')) {
    return;
  }
  
  // Add loading state to button
  btn.classList.add('loading');
  btn.disabled = true;
  status.textContent = 'Preparing restore...';
  
  // Show loader with restore-specific messaging
  if (window.Loader) {
    window.Loader.show('Restoring system...', 'Uploading and processing backup file');
  }
  
  try {
    const formData = new FormData();
    formData.append('backup_file', fileInput.files[0]);
    
    // Update loader messages during restore process
    if (window.Loader) {
      setTimeout(() => window.Loader.updateMessage('Extracting backup...', 'Processing uploaded backup file'), 1000);
      setTimeout(() => window.Loader.updateMessage('Restoring database...', 'Importing database from backup'), 2500);
      setTimeout(() => window.Loader.updateMessage('Restoring files...', 'Copying files from backup'), 4000);
      setTimeout(() => window.Loader.updateMessage('Finalizing...', 'Completing system restore'), 5500);
    }
    
    const response = await fetch(`${AdminApi.API_BASE}/admin/backup/restore`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${AdminApi.getToken() || 'demo:admin'}`
      },
      body: formData
    });
    
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.error || 'Restore failed');
    }
    
    // Complete the progress
    if (window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => {
        window.Loader.hide();
        if (window.showToast) {
          window.showToast('System restored successfully! Please refresh the page.', 'success');
        } else {
          toast('System restored successfully');
        }
      }, 500);
    } else {
      toast('System restored successfully');
    }
    
    status.innerHTML = '<i class="fas fa-check-circle" style="color: var(--ok);"></i> System restored successfully';
    
  } catch (error) {
    console.error('Restore error:', error);
    
    // Hide loader and show error
    if (window.Loader) {
      window.Loader.hide();
    }
    
    if (window.showToast) {
      window.showToast('Restore failed: ' + error.message, 'error');
    }
    
    status.innerHTML = '<i class="fas fa-times-circle" style="color: var(--danger);"></i> Restore failed: ' + error.message;
  } finally {
    // Remove loading state
    btn.classList.remove('loading');
    btn.disabled = false;
  }
}

async function refreshBackupHistory() {
  const tbody = document.getElementById('backup-history-tbody');
  
  // Show loading skeleton
  if (tbody) {
    tbody.innerHTML = `
      <tr class="table-loading-row">
        <td><div class="loading-placeholder long"></div></td>
        <td><div class="loading-placeholder medium"></div></td>
        <td><div class="loading-placeholder short"></div></td>
        <td><div class="loading-placeholder short"></div></td>
        <td><div class="loading-placeholder medium"></div></td>
      </tr>
      <tr class="table-loading-row">
        <td><div class="loading-placeholder medium"></div></td>
        <td><div class="loading-placeholder long"></div></td>
        <td><div class="loading-placeholder short"></div></td>
        <td><div class="loading-placeholder short"></div></td>
        <td><div class="loading-placeholder medium"></div></td>
      </tr>
    `;
  }
  
  try {
    const data = await AdminApi.apiGet('/admin/backup/history', true, 'Loading backup history...');
    const backups = data.backups || [];
    
    if (!tbody) return;
    
    if (backups.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="empty-content"><i class="fas fa-archive"></i><p>No backups found</p><small>Create your first backup to see it here</small></div></td></tr>';
      return;
    }
    
    tbody.innerHTML = backups.map(backup => `
      <tr>
        <td>${backup.name}</td>
        <td>${new Date(backup.created_at).toLocaleString()}</td>
        <td>${backup.size_mb} MB</td>
        <td><span class="badge ok">Available</span></td>
        <td>
          <button class="btn sm secondary" title="Backup file saved locally"><i class="fas fa-check-circle"></i> Saved</button>
        </td>
      </tr>
    `).join('');
    
  } catch (error) {
    console.error('Backup history error:', error);
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="5" class="error-state"><div class="error-content"><i class="fas fa-exclamation-triangle"></i><p>Error loading backup history</p><small>' + error.message + '</small></div></td></tr>';
    }
  }
}

// Load and display current token limits
async function loadCurrentLimits() {
  try {
    const limitData = await AdminApi.apiGet('/admin/tokens/limits');
    
    // Update displayed values
    const globalDisplay = document.getElementById('current-global-limit');
    const studentDisplay = document.getElementById('current-student-limit');
    const guestDisplay = document.getElementById('current-guest-limit');
    
    if (globalDisplay) globalDisplay.textContent = (limitData.global_limit || 0).toLocaleString() + ' tokens';
    if (studentDisplay) studentDisplay.textContent = (limitData.student_limit || 0).toLocaleString() + ' tokens';
    if (guestDisplay) guestDisplay.textContent = (limitData.guest_limit || 0).toLocaleString() + ' tokens';
  } catch (error) {
    console.error('Failed to load current limits:', error);
  }
}

// Tokenization Tab
function initTokenization() {
  // Load current limits on page load
  loadCurrentLimits();
  
  // Add a small delay to ensure DOM is fully ready
  setTimeout(() => {
    // Only check for elements that exist in the simplified tokenization tab
    const saveGlobalLimitBtn = document.getElementById('save-global-limit');
    
    if (!saveGlobalLimitBtn) {
      console.warn('Tokenization elements not found, retrying in 1 second...');
      setTimeout(initTokenization, 1000);
      return;
    }
    
    saveGlobalLimitBtn.addEventListener('click', saveGlobalLimit);
    
    // Add student and guest token limit handlers
    const saveStudentLimitBtn = document.getElementById('save-student-limit');
    if (saveStudentLimitBtn) {
      saveStudentLimitBtn.addEventListener('click', saveStudentLimit);
    }
    
    const saveGuestLimitBtn = document.getElementById('save-guest-limit');
    if (saveGuestLimitBtn) {
      saveGuestLimitBtn.addEventListener('click', saveGuestLimit);
    }
    
    // Optional elements - only add listeners if they exist
    const searchUsersBtn = document.getElementById('search-users');
    if (searchUsersBtn) {
      searchUsersBtn.addEventListener('click', searchUsers);
    }
    
    const refreshTokensBtn = document.getElementById('refresh-tokens');
    if (refreshTokensBtn) {
      refreshTokensBtn.addEventListener('click', refreshTokenization);
    }
    
    const refreshAnalyticsBtn = document.getElementById('refresh-analytics');
    if (refreshAnalyticsBtn) {
      refreshAnalyticsBtn.addEventListener('click', refreshAnalytics);
    }
    
    // Add event listener for analytics period change
    const analyticsPeriodSelect = document.getElementById('analytics-period');
    if (analyticsPeriodSelect) {
      analyticsPeriodSelect.addEventListener('change', refreshAnalytics);
    }
    
    refreshTokenization();
    
    // Also refresh analytics initially if the button exists
    if (refreshAnalyticsBtn) {
      refreshAnalytics();
    }
  }, 100);
}

async function saveGlobalLimit() {
  const limit = document.getElementById('global-limit').value;
  const status = document.getElementById('global-limit-status');
  
  if (!limit || isNaN(limit)) {
    toast('Please enter a valid token limit');
    return;
  }
  
  try {
    await AdminApi.apiPut('/admin/tokens/global', { max_tokens: parseInt(limit) });
    status.innerHTML = '<i class="fas fa-check-circle" style="color: var(--success);"></i> Global limit updated successfully';
    
    // Clear the input field
    document.getElementById('global-limit').value = '';
    
    // Reload displayed limits
    await loadCurrentLimits();
    
    toast('Global token limit updated');
  } catch (error) {
    console.error('Save global limit error:', error);
    status.innerHTML = '<i class="fas fa-times-circle" style="color: var(--danger);"></i> Failed to save limit: ' + error.message;
  }
}

async function saveStudentLimit() {
  const limit = document.getElementById('student-token-limit').value;
  const status = document.getElementById('student-limit-status');
  
  if (!limit || isNaN(limit)) {
    toast('Please enter a valid student token limit');
    return;
  }
  
  try {
    await AdminApi.apiPut('/admin/tokens/student', { max_tokens: parseInt(limit) });
    status.innerHTML = '<i class="fas fa-check-circle" style="color: var(--success);"></i> All students updated';
    document.getElementById('student-token-limit').value = '';
    await loadCurrentLimits();
    toast('Student limit updated');
  } catch (error) {
    console.error('Save student limit error:', error);
    status.innerHTML = '<i class="fas fa-times-circle" style="color: var(--danger);"></i> Failed: ' + error.message;
  }
}

async function saveGuestLimit() {
  const limit = document.getElementById('guest-token-limit').value;
  const status = document.getElementById('guest-limit-status');
  
  if (!limit || isNaN(limit)) {
    toast('Please enter a valid guest token limit');
    return;
  }
  
  try {
    await AdminApi.apiPut('/admin/tokens/guest', { max_tokens: parseInt(limit) });
    status.innerHTML = '<i class="fas fa-check-circle" style="color: var(--success);"></i> Guest limit updated to ' + parseInt(limit).toLocaleString() + ' tokens';
    
    // Clear the input field
    document.getElementById('guest-token-limit').value = '';
    
    // Reload displayed limits
    await loadCurrentLimits();
    
    toast('Guest limit updated to ' + parseInt(limit).toLocaleString() + ' tokens');
  } catch (error) {
    console.error('Save guest limit error:', error);
    status.innerHTML = '<i class="fas fa-times-circle" style="color: var(--danger);"></i> Failed to save limit: ' + error.message;
  }
}



async function refreshTokenization() {
  try {
    await loadCurrentLimits();
  } catch (error) {
    console.error('Tokenization refresh error:', error);
  }
}


// Export initSystemPage for use by the router
window.initSystemPage = initSystemPage;

