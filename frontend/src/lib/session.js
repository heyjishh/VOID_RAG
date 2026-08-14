import { authApi } from './api.js'

const TOKEN_KEY = 'juryai.token'
const USER_KEY = 'juryai.user'

function saveToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch (e) {}
}

export function getSession() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY)) || null
  } catch {
    return null
  }
}

function persist(entry) {
  if (!entry?.user) return
  saveToken(entry.token)
  localStorage.setItem(USER_KEY, JSON.stringify(entry.user))
}

export async function sendOtp(payload) {
  return authApi.sendOtp(payload)
}

export async function verifyOtp(payload) {
  const result = await authApi.verifyOtp(payload)
  if (result?.user && result?.token) persist(result)
  return result
}

export async function register(payload) {
  const result = await authApi.register(payload)
  if (result?.user && result?.token) persist(result)
  return result
}

export async function login(payload) {
  const result = await authApi.login(payload)
  if (result?.user && result?.token) persist(result)
  return result
}

export async function forgot(payload) {
  return authApi.forgot(payload)
}

export async function reset(payload) {
  const result = await authApi.reset(payload)
  if (result?.user && result?.token) persist(result)
  return result
}

export async function logout() {
  try {
    await authApi.logout(getToken())
  } catch (e) {}
  saveToken(null)
  localStorage.removeItem(USER_KEY)
}

export function getDisplayName(user) {
  return user?.name || user?.email?.split('@')[0] || user?.phone?.slice(-4) || 'Researcher'
}

function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || null
  } catch {
    return null
  }
}