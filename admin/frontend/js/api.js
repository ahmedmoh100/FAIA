const API_BASE = window.ADMIN_API_BASE || (localStorage.getItem('ADMIN_API_BASE') || 'http://localhost:8001');

function setToken(token) {
  localStorage.setItem('ADMIN_TOKEN', token);
}

function getToken() {
  return localStorage.getItem('ADMIN_TOKEN');
}

async function apiGet(path, showLoader = false, loaderMessage = null) {
  if (showLoader && window.Loader) {
    window.Loader.show(loaderMessage || 'Fetching data...', 'Please wait while we retrieve the information');
  }
  
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Authorization': `Bearer ${getToken() || ''}`
      }
    });
    if (res.status === 401) {
      localStorage.removeItem('ADMIN_TOKEN');
      window.location.reload();
      throw new Error('Session expired. Please log in again.');
    }
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    
    if (showLoader && window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => window.Loader.hide(), 300);
    }
    
    return data;
  } catch (error) {
    if (showLoader && window.Loader) {
      window.Loader.hide();
    }
    throw error;
  }
}

async function apiGetText(path, showLoader = false, loaderMessage = null) {
  if (showLoader && window.Loader) {
    window.Loader.show(loaderMessage || 'Fetching data...', 'Please wait while we retrieve the information');
  }
  
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Authorization': `Bearer ${getToken() || ''}`
      }
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.text();
    
    if (showLoader && window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => window.Loader.hide(), 300);
    }
    
    return data;
  } catch (error) {
    if (showLoader && window.Loader) {
      window.Loader.hide();
    }
    throw error;
  }
}

async function apiPost(path, body, showLoader = false, loaderMessage = null) {
  if (showLoader && window.Loader) {
    window.Loader.show(loaderMessage || 'Processing...', 'Please wait while we process your request');
  }
  
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken() || ''}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body || {})
    });
    if (res.status === 401) {
      localStorage.removeItem('ADMIN_TOKEN');
      window.location.reload();
      throw new Error('Session expired. Please log in again.');
    }
    if (!res.ok) throw new Error(await res.text());
    
    if (showLoader && window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => window.Loader.hide(), 300);
    }
    
    try { return await res.json(); } catch { return {}; }
  } catch (error) {
    if (showLoader && window.Loader) {
      window.Loader.hide();
    }
    throw error;
  }
}

async function apiPut(path, body, showLoader = false, loaderMessage = null) {
  if (showLoader && window.Loader) {
    window.Loader.show(loaderMessage || 'Updating...', 'Please wait while we save your changes');
  }
  
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${getToken() || ''}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body || {})
    });
    if (res.status === 401) {
      localStorage.removeItem('ADMIN_TOKEN');
      window.location.reload();
      throw new Error('Session expired. Please log in again.');
    }
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    
    if (showLoader && window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => window.Loader.hide(), 300);
    }
    
    return data;
  } catch (error) {
    if (showLoader && window.Loader) {
      window.Loader.hide();
    }
    throw error;
  }
}

async function apiDelete(path, showLoader = false, loaderMessage = null) {
  if (showLoader && window.Loader) {
    window.Loader.show(loaderMessage || 'Deleting...', 'Please wait while we remove the item');
  }
  
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${getToken() || ''}`
      }
    });
    if (res.status === 401) {
      localStorage.removeItem('ADMIN_TOKEN');
      window.location.reload();
      throw new Error('Session expired. Please log in again.');
    }
    if (!res.ok) throw new Error(await res.text());
    
    if (showLoader && window.Loader) {
      window.Loader.setProgress(100);
      setTimeout(() => window.Loader.hide(), 300);
    }
    
    try { return await res.json(); } catch { return {}; }
  } catch (error) {
    if (showLoader && window.Loader) {
      window.Loader.hide();
    }
    throw error;
  }
}

window.AdminApi = { API_BASE, setToken, getToken, apiGet, apiGetText, apiPost, apiPut, apiDelete };


