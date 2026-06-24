// IMMEDIATE ROLE CHECK - Run before anything else
(function () {
  const token = localStorage.getItem('ADMIN_TOKEN');  // Use consistent key
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.role === 'PROFESSOR') {

        window.userRole = 'PROFESSOR';
        // Set a flag that other code can check
        window.isProfessor = true;
      }
    } catch (e) {

    }
  }
})();

const routeRoot = document.getElementById('routeRoot');
const loginView = document.getElementById('loginView');
const appView = document.getElementById('appView');
const loginBtn = document.getElementById('loginBtn');
const tokenInput = document.getElementById('tokenInput');
const loginMsg = document.getElementById('loginMsg');
const logoutBtn = document.getElementById('logoutBtn');

function toast(msg) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.remove(); }, 2400);
}

// Custom confirmation modal
function showConfirm(title, message, onConfirm, onCancel = null) {
  const modal = document.getElementById('confirmModal');
  const titleEl = document.getElementById('confirmTitle');
  const messageEl = document.getElementById('confirmMessage');
  const okBtn = document.getElementById('confirmOk');
  const cancelBtn = document.getElementById('confirmCancel');

  titleEl.textContent = title;
  messageEl.textContent = message;

  // Remove any existing event listeners
  const newOkBtn = okBtn.cloneNode(true);
  const newCancelBtn = cancelBtn.cloneNode(true);
  okBtn.parentNode.replaceChild(newOkBtn, okBtn);
  cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

  // Add new event listeners
  newOkBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (onConfirm) onConfirm();
  });

  newCancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (onCancel) onCancel();
  });

  // Close on outside click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none';
      if (onCancel) onCancel();
    }
  });

  // Show modal
  modal.style.display = 'block';
}

// Custom input modal
function showInput(title, message, label, placeholder = '', type = 'text', helpText = '', onConfirm, onCancel = null) {
  const modal = document.getElementById('inputModal');
  const titleEl = document.getElementById('inputTitle');
  const messageEl = document.getElementById('inputMessage');
  const labelEl = document.getElementById('inputLabel');
  const inputEl = document.getElementById('inputField');
  const helpEl = document.getElementById('inputHelp');
  const okBtn = document.getElementById('inputOk');
  const cancelBtn = document.getElementById('inputCancel');

  titleEl.textContent = title;
  messageEl.textContent = message;
  labelEl.textContent = label;
  inputEl.placeholder = placeholder;
  inputEl.type = type;
  inputEl.value = '';
  helpEl.textContent = helpText;

  // Remove any existing event listeners
  const newOkBtn = okBtn.cloneNode(true);
  const newCancelBtn = cancelBtn.cloneNode(true);
  okBtn.parentNode.replaceChild(newOkBtn, okBtn);
  cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

  // Add new event listeners
  newOkBtn.addEventListener('click', () => {
    const value = inputEl.value.trim();
    modal.style.display = 'none';
    if (onConfirm) onConfirm(value);
  });

  newCancelBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    if (onCancel) onCancel();
  });

  // Handle Enter key
  inputEl.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const value = inputEl.value.trim();
      modal.style.display = 'none';
      if (onConfirm) onConfirm(value);
    }
  });

  // Handle Escape key
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      modal.style.display = 'none';
      if (onCancel) onCancel();
    }
  });

  // Close on outside click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none';
      if (onCancel) onCancel();
    }
  });

  // Show modal and focus input
  modal.style.display = 'block';
  setTimeout(() => inputEl.focus(), 100);
}

// JSON syntax highlighting function (VS Code style)
function syntaxHighlight(json) {
  if (typeof json !== "string") {
    json = JSON.stringify(json, null, 2);
  }

  json = json.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
    let cls = 'number';
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = 'key';
      } else {
        cls = 'string';
      }
    } else if (/true|false/.test(match)) {
      cls = 'bool';
    } else if (/null/.test(match)) {
      cls = 'null';
    }
    return '<span class="' + cls + '">' + match + '</span>';
  });
}

let currentRoute = null;

function render(route) {


  // Always clear content first to prevent caching issues
  routeRoot.innerHTML = '';
  currentRoute = route;

  // Update active navigation (use setTimeout to ensure updateActiveNav is defined)
  setTimeout(() => {
    if (typeof updateActiveNav === 'function') {
      updateActiveNav();
    }
  }, 50);

  switch (route) {
    case '#/users':
      fetch('/pages/users.html').then(r => r.text()).then(html => {
        routeRoot.innerHTML = html;
        if (window.initUsersPage) window.initUsersPage();
      });
      break;
    case '#/sessions':
      fetch('/pages/sessions.html').then(r => r.text()).then(html => {
        routeRoot.innerHTML = html;

        if (window.initSessionsPage) window.initSessionsPage();
      });
      break;
    case '#/audit':
      fetch('/pages/audit.html').then(r => r.text()).then(html => {
        routeRoot.innerHTML = html;
        if (window.initAuditPage) window.initAuditPage();
      });
      break;
    case '#/system':
      fetch('/pages/system.html').then(r => r.text()).then(html => {
        routeRoot.innerHTML = html;
        if (window.initSystemPage) window.initSystemPage();
      });
      break;
    case '#/overview':
    default:
      routeRoot.innerHTML = `
        <div class="dashboard-grid">
          <div class="card dashboard-card">
            <div class="card-header">
              <h3><i class="fas fa-heartbeat card-icon"></i> System Health</h3>
            </div>
            <div class="health-status" id="healthStatus">
              <div class="loading-spinner">Loading system status...</div>
            </div>
          </div>
          <div class="card dashboard-card">
            <div class="card-header">
              <h3><i class="fas fa-user-shield card-icon"></i> Admin Profile</h3>
            </div>
            <div class="admin-profile" id="adminProfile">
              <div class="loading-spinner">Loading profile...</div>
            </div>
          </div>
          <div class="card dashboard-card">
            <div class="card-header">
              <h3><i class="fas fa-chart-pie card-icon"></i> Session Statistics</h3>
            </div>
            <div class="chart-container">
              <canvas id="sessionChart" width="300" height="200"></canvas>
            </div>
          </div>
        </div>
        
        <!-- Wide User Distribution Card -->
        <div class="card dashboard-card wide-card">
          <div class="card-header">
            <h3><i class="fas fa-chart-line card-icon"></i> User Distribution</h3>
          </div>
          <div class="user-stats-overview" id="userStatsOverview">
            <div class="loading-spinner">Loading user statistics...</div>
          </div>
          <div class="chart-container">
            <canvas id="userChart" width="300" height="200"></canvas>
          </div>
        </div>
      `;

      // Wait for AdminApi to be available before making calls
      function loadDashboard() {
        if (typeof AdminApi === 'undefined') {
          setTimeout(loadDashboard, 100);
          return;
        }

        // Load enhanced health status
        AdminApi.apiGet('/admin/health').then(d => {
          const healthStatus = document.getElementById('healthStatus');
          if (!healthStatus) return; // Element not found, skip

          const dbConnected = d.database && d.database.connected;

          healthStatus.innerHTML = `
            <div class="status-grid">
              <div class="status-item">
                <div class="status-icon ${d.status === 'ok' ? 'status-ok' : 'status-error'}">
                  <i class="fas fa-${d.status === 'ok' ? 'check-circle' : 'exclamation-triangle'}"></i>
                </div>
                <div class="status-info">
                  <div class="status-label">API Status</div>
                  <div class="status-value">${d.status.toUpperCase()}</div>
                </div>
              </div>
              
              <div class="status-item">
                <div class="status-icon ${dbConnected ? 'status-ok' : 'status-error'}">
                  <i class="fas fa-database"></i>
                </div>
                <div class="status-info">
                  <div class="status-label">Database</div>
                  <div class="status-value">${dbConnected ? 'Connected' : 'Disconnected'}</div>
                  ${dbConnected ? `<div class="status-detail">${d.database.table_count} tables</div>` : ''}
                </div>
              </div>
              
              <div class="status-item">
                <div class="status-icon status-info">
                  <i class="fas fa-clock"></i>
                </div>
                <div class="status-info">
                  <div class="status-label">Service</div>
                  <div class="status-value">${d.service}</div>
                  <div class="status-detail">v${d.version}</div>
                </div>
              </div>
              
              <div class="status-item">
                <div class="status-icon status-info">
                  <i class="fas fa-server"></i>
                </div>
                <div class="status-info">
                  <div class="status-label">Database Host</div>
                  <div class="status-value">${dbConnected ? d.database.host : 'N/A'}</div>
                  ${dbConnected ? `<div class="status-detail">${d.database.database}</div>` : ''}
                </div>
              </div>
            </div>
          `;
        }).catch(e => {
          const healthStatus = document.getElementById('healthStatus');
          if (healthStatus) {
            healthStatus.innerHTML = `
              <div class="error-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load health status</p>
                <small>${e.message}</small>
              </div>
            `;
          }
        });

        // Load enhanced admin profile
        AdminApi.apiGet('/admin/me').then(d => {
          const adminProfile = document.getElementById('adminProfile');
          if (!adminProfile) return; // Element not found, skip

          adminProfile.innerHTML = `
            <div class="profile-header">
              <div class="profile-avatar">
                <i class="fas fa-user-shield"></i>
              </div>
              <div class="profile-info">
                <div class="profile-name">${d.username}</div>
                <div class="profile-role">
                  <span class="badge ${d.role.toLowerCase() === 'admin' ? 'ok' : 'warn'}">${d.role}</span>
                </div>
              </div>
            </div>
            
            <div class="profile-stats">
              <div class="stat-item">
                <div class="stat-icon">
                  <i class="fas fa-key"></i>
                </div>
                <div class="stat-info">
                  <div class="stat-label">User ID</div>
                  <div class="stat-value">${d.id}</div>
                </div>
              </div>
              
              <div class="stat-item">
                <div class="stat-icon">
                  <i class="fas fa-shield-alt"></i>
                </div>
                <div class="stat-info">
                  <div class="stat-label">Access Level</div>
                  <div class="stat-value">Full Admin</div>
                </div>
              </div>
              
              <div class="stat-item">
                <div class="stat-icon">
                  <i class="fas fa-clock"></i>
                </div>
                <div class="stat-info">
                  <div class="stat-label">Session</div>
                  <div class="stat-value">Active</div>
                </div>
              </div>
            </div>
          `;
        }).catch(e => {
          const adminProfile = document.getElementById('adminProfile');
          if (adminProfile) {
            adminProfile.innerHTML = `
              <div class="error-state">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Failed to load profile</p>
                <small>${e.message}</small>
              </div>
            `;
          }
        });
      }

      loadDashboard();

      // Initialize charts after a short delay to ensure DOM is ready
      setTimeout(() => {
        // Only initialize charts if we're actually on the dashboard
        if (document.getElementById('sessionChart') && document.getElementById('userChart')) {
          initCharts();
        }
      }, 500);
      break;
  }
}

function refreshAuthUI() {
  // Wait for AdminApi to be available
  if (typeof AdminApi === 'undefined') {
    setTimeout(refreshAuthUI, 100);
    return;
  }

  const hasToken = !!AdminApi.getToken();
  // Use setProperty with important to override inline styles
  loginView.style.setProperty('display', hasToken ? 'none' : 'block', 'important');
  appView.style.setProperty('display', hasToken ? 'block' : 'none', 'important');
  logoutBtn.style.display = hasToken ? 'inline-flex' : 'none';

  if (hasToken) {
    // Apply role-based UI BEFORE rendering
    if (window.applyRoleBasedUI && window.userRole) {

      window.applyRoleBasedUI(window.userRole);
    }

    // Force re-render by clearing content and route tracking
    routeRoot.innerHTML = '';
    window.currentRoute = null; // Reset to allow re-render

    // Set default route based on role
    let hash = location.hash || '#/overview';

    // Just render the current hash, don't redirect
    // (Redirects are handled by immediate role check in index.html)
    render(hash);

    // Update navigation after render
    setTimeout(() => {
      if (typeof updateActiveNav === 'function') {
        updateActiveNav();
      }
    }, 100);
  } else {
    // Not logged in - clear any rendered content
    routeRoot.innerHTML = '';
    window.currentRoute = null;
  }
}

loginBtn.addEventListener('click', async () => {
  const usernameInput = document.getElementById('usernameInput');
  const passwordInput = document.getElementById('passwordInput');

  const username = usernameInput ? usernameInput.value.trim() : '';
  const password = passwordInput ? passwordInput.value.trim() : '';

  if (!username || !password) {
    loginMsg.textContent = 'Please enter username and password';
    return;
  }

  // Wait for AdminApi to be available
  if (typeof AdminApi === 'undefined') {
    loginMsg.textContent = 'Loading... please wait';
    setTimeout(() => {
      loginBtn.click();
    }, 100);
    return;
  }

  // Add loading state to login button
  loginBtn.classList.add('loading');
  loginBtn.disabled = true;
  loginMsg.textContent = '';

  // Show loader
  if (window.Loader) {
    window.Loader.show('Logging in...', 'Authenticating your credentials');
  }

  try {
    // Call login endpoint
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${AdminApi.API_BASE}/admin/login`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();

    // Save token
    AdminApi.setToken(data.access_token);

    // Apply role-based UI if function exists
    if (window.applyRoleBasedUI && data.role) {

      window.applyRoleBasedUI(data.role);
    }

    // Clear inputs
    if (usernameInput) usernameInput.value = '';
    if (passwordInput) passwordInput.value = '';

    if (window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => {
        window.Loader.hide();
        refreshAuthUI();
        if (window.showToast) {
          window.showToast(`Welcome, ${data.username}!`, 'success');
        } else {
          toast(`Welcome, ${data.username}!`);
        }
      }, 500);
    } else {
      refreshAuthUI();
      toast(`Welcome, ${data.username}!`);
    }

  } catch (error) {

    loginMsg.textContent = error.message || 'Login failed';
    loginMsg.style.color = 'var(--danger)';

    if (window.Loader) {
      window.Loader.hide();
    }
  } finally {
    // Remove loading state
    loginBtn.classList.remove('loading');
    loginBtn.disabled = false;
  }
});

logoutBtn.addEventListener('click', () => {
  showConfirm(
    'Logout Confirmation',
    'Are you sure you want to logout? You will need to login again to access the admin panel.',
    () => {
      // User confirmed logout
      localStorage.removeItem('ADMIN_TOKEN');
      window.userRole = null;
      // Clear content
      routeRoot.innerHTML = '';
      // Show login view (force override any inline styles)
      loginView.style.setProperty('display', 'block', 'important');
      appView.style.setProperty('display', 'none', 'important');
      logoutBtn.style.display = 'none';
      // Clear any input fields
      const usernameInput = document.getElementById('usernameInput');
      const passwordInput = document.getElementById('passwordInput');
      if (usernameInput) usernameInput.value = '';
      if (passwordInput) passwordInput.value = '';
      loginMsg.textContent = '';

      // Reset the current route to force a clean state
      window.currentRoute = null;
      location.hash = '';

      // Refresh the authentication UI to ensure proper state
      setTimeout(() => {
        refreshAuthUI();
      }, 100);

      toast('Logged out successfully');
    }
  );
});

// Update active navigation link
function updateActiveNav() {
  // Determine current page from hash or pathname
  let currentHash = location.hash || '#/overview';

  // If no hash but we're on a specific page, derive hash from pathname
  if (!location.hash && location.pathname.includes('/pages/')) {
    const pageName = location.pathname.split('/pages/')[1].replace('.html', '');
    currentHash = `#/${pageName}`;
  }

  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href') === currentHash) {
      link.classList.add('active');
    }
  });
}

window.addEventListener('hashchange', () => {
  updateActiveNav();
  refreshAuthUI();
});

refreshAuthUI();
updateActiveNav();

// Chart initialization functions
function initCharts() {
  // Prevent multiple simultaneous chart initializations
  if (window.chartsInitializing) {

    return;
  }

  window.chartsInitializing = true;

  // Destroy existing charts before creating new ones
  destroyExistingCharts();

  // Add a small delay to ensure canvas recreation is complete
  setTimeout(() => {
    initSessionChart();
    initUserChart();
    window.chartsInitializing = false;
  }, 100);
}

function destroyExistingCharts() {
  // Destroy all existing Chart.js instances
  if (window.activeCharts) {
    window.activeCharts.forEach((chart, id) => {
      try {
        chart.destroy();

      } catch (e) {

      }
    });
    window.activeCharts.clear();
  }

  // Also destroy any charts that might be registered globally
  if (window.Chart && window.Chart.instances) {
    Object.keys(window.Chart.instances).forEach(key => {
      try {
        window.Chart.instances[key].destroy();
      } catch (e) {

      }
    });
  }

  // Completely recreate canvas elements to avoid Chart.js conflicts
  recreateCanvas('sessionChart');
  recreateCanvas('userChart');
}

function recreateCanvas(canvasId) {
  const existingCanvas = document.getElementById(canvasId);
  if (existingCanvas) {
    const parent = existingCanvas.parentNode;
    const newCanvas = document.createElement('canvas');
    newCanvas.id = canvasId;
    newCanvas.width = existingCanvas.width;
    newCanvas.height = existingCanvas.height;

    // Copy any classes or attributes
    newCanvas.className = existingCanvas.className;

    // Replace the old canvas with the new one
    parent.replaceChild(newCanvas, existingCanvas);

  }
}

function initSessionChart() {
  const ctx = document.getElementById('sessionChart');
  if (!ctx) {
    console.warn('Session chart canvas not found');
    return;
  }

  // Ensure we have a clean canvas context
  try {
    const context = ctx.getContext('2d');
    if (!context) {
      console.error('Could not get 2D context for session chart');
      return;
    }
  } catch (e) {
    console.error('Error getting session chart context:', e);
    return;
  }

  // Get session data from API with better error handling
  AdminApi.apiGet('/admin/sessions').then(sessions => {

    const activeSessions = sessions.filter(s => !s.logout_time).length;
    const completedSessions = sessions.filter(s => s.logout_time).length;

    // Add data source indicator
    const isRealData = sessions.length > 0;

    const sessionChart = new Chart(ctx, {
      type: 'pie',
      data: {
        labels: ['Active Sessions', 'Completed Sessions'],
        datasets: [{
          data: [activeSessions, completedSessions],
          backgroundColor: [
            '#4CAF50', // Green for active
            '#2196F3'  // Blue for completed
          ],
          borderColor: '#1a1a1a',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#ffffff',
              padding: 15
            }
          },
          tooltip: {
            callbacks: {
              label: function (context) {
                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                const percentage = ((context.parsed / total) * 100).toFixed(1);
                return `${context.label}: ${context.parsed} (${percentage}%)`;
              }
            }
          }
        }
      }
    });

    // Store chart reference for cleanup
    if (!window.activeCharts) window.activeCharts = new Map();
    window.activeCharts.set('sessionChart', sessionChart);

    // Update card header with data source
    const cardHeader = ctx.closest('.card').querySelector('.card-header h3');
    if (cardHeader) {
      cardHeader.innerHTML = `<i class="fas fa-chart-pie card-icon"></i> Session Statistics ${isRealData ? '<span class="badge ok" style="font-size: 10px; margin-left: 8px;">LIVE</span>' : '<span class="badge warn" style="font-size: 10px; margin-left: 8px;">DEMO</span>'}`;
    }

  }).catch(e => {
    // Fallback with sample data if API fails
    const sessionChart = new Chart(ctx, {
      type: 'pie',
      data: {
        labels: ['Active Sessions', 'Completed Sessions'],
        datasets: [{
          data: [12, 28],
          backgroundColor: ['#4CAF50', '#2196F3'],
          borderColor: '#1a1a1a',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#ffffff',
              padding: 15
            }
          }
        }
      }
    });

    // Store chart reference for cleanup
    if (!window.activeCharts) window.activeCharts = new Map();
    window.activeCharts.set('sessionChart', sessionChart);
  });
}

function initUserChart() {
  const ctx = document.getElementById('userChart');
  if (!ctx) return;

  // Get user data from API with database connection indicator
  AdminApi.apiGet('/admin/users').then(users => {

    const students = users.filter(u => u.role === 'STUDENT').length;
    const professors = users.filter(u => u.role === 'PROFESSOR').length;
    const admins = users.filter(u => u.role === 'ADMIN').length;

    // Check if this is real database data
    const isRealData = users.length > 0 && users[0].id;

    // Calculate percentages
    const totalUsers = students + professors + admins;
    const studentPercent = totalUsers > 0 ? ((students / totalUsers) * 100).toFixed(1) : 0;
    const professorPercent = totalUsers > 0 ? ((professors / totalUsers) * 100).toFixed(1) : 0;
    const adminPercent = totalUsers > 0 ? ((admins / totalUsers) * 100).toFixed(1) : 0;

    // Update the stats overview
    const statsOverview = document.getElementById('userStatsOverview');
    if (statsOverview) {
      statsOverview.innerHTML = `
        <div class="stats-grid">
          <div class="stat-card student-stat">
            <div class="stat-icon">
              <i class="fas fa-graduation-cap"></i>
            </div>
            <div class="stat-content">
              <div class="stat-number">${students}</div>
              <div class="stat-label">Students</div>
              <div class="stat-percentage">${studentPercent}%</div>
            </div>
          </div>
          
          <div class="stat-card professor-stat">
            <div class="stat-icon">
              <i class="fas fa-chalkboard-teacher"></i>
            </div>
            <div class="stat-content">
              <div class="stat-number">${professors}</div>
              <div class="stat-label">Professors</div>
              <div class="stat-percentage">${professorPercent}%</div>
            </div>
          </div>
          
          <div class="stat-card admin-stat">
            <div class="stat-icon">
              <i class="fas fa-user-shield"></i>
            </div>
            <div class="stat-content">
              <div class="stat-number">${admins}</div>
              <div class="stat-label">Admins</div>
              <div class="stat-percentage">${adminPercent}%</div>
            </div>
          </div>
        </div>
        
        <div class="total-users">
          <span class="total-label">Total Users:</span>
          <span class="total-number">${totalUsers}</span>
        </div>
      `;
    }

    const userChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Students', 'Professors', 'Admins'],
        datasets: [{
          label: 'Number of Users',
          data: [students, professors, admins],
          backgroundColor: [
            '#58a6ff', // Blue for students - matches icon color
            '#3fb950', // Green for professors - matches icon color
            '#d29922'  // Orange for admins - matches icon color
          ],
          borderColor: '#1a1a1a',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              color: '#ffffff',
              stepSize: 1
            },
            grid: {
              color: '#333333'
            }
          },
          x: {
            ticks: {
              color: '#ffffff'
            },
            grid: {
              color: '#333333'
            }
          }
        },
        plugins: {
          legend: {
            display: false  // Hide legend since we have beautiful stats cards above
          }
        }
      }
    });

    // Store chart reference for cleanup
    if (!window.activeCharts) window.activeCharts = new Map();
    window.activeCharts.set('userChart', userChart);

    // Update card header with data source
    const cardHeader = ctx.closest('.card').querySelector('.card-header h3');
    if (cardHeader) {
      cardHeader.innerHTML = `<i class="fas fa-chart-line card-icon"></i> User Distribution ${isRealData ? '<span class="badge ok" style="font-size: 10px; margin-left: 8px;">DATABASE</span>' : '<span class="badge warn" style="font-size: 10px; margin-left: 8px;">DEMO</span>'}`;
    }

  }).catch(e => {
    // Fallback with sample data if API fails
    const userChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['Students', 'Professors', 'Admins'],
        datasets: [{
          label: 'Number of Users',
          data: [8, 2, 3],
          backgroundColor: ['#58a6ff', '#3fb950', '#d29922'],
          borderColor: '#1a1a1a',
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              color: '#ffffff',
              stepSize: 1
            },
            grid: {
              color: '#333333'
            }
          },
          x: {
            ticks: {
              color: '#ffffff'
            },
            grid: {
              color: '#333333'
            }
          }
        },
        plugins: {
          legend: {
            display: false  // Hide legend for fallback chart too
          }
        }
      }
    });

    // Store chart reference for cleanup
    if (!window.activeCharts) window.activeCharts = new Map();
    window.activeCharts.set('userChart', userChart);

    // Update card header to show error
    const cardHeader = ctx.closest('.card').querySelector('.card-header h3');
    if (cardHeader) {
      cardHeader.innerHTML = `<i class="fas fa-chart-line card-icon"></i> User Distribution <span class="badge danger" style="font-size: 10px; margin-left: 8px;">ERROR</span>`;
    }
  });
}


