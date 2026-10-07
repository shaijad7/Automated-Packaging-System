export const API_BASE_URL = "http://localhost:8000/api";

export function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return sessionStorage.getItem("access_token");
  }
  return null;
}

export function setAuthToken(token: string) {
  if (typeof window !== "undefined") {
    sessionStorage.setItem("access_token", token);
  }
}

export function removeAuthToken() {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem("access_token");
  }
}

export async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers,
  });
  
  if (response.status === 401) {
    removeAuthToken();
    if (typeof window !== "undefined" && window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }
  
  return response;
}
