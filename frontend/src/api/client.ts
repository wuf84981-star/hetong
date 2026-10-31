import type {
  HealthResponse,
  LoginRequest,
  RegisterRequest,
  SendCodeResponse,
  TokenResponse,
  ReviewResponse,
  ReviewPosition,
  ReviewHistoryResponse,
  DetailedReview,
  BatchReviewResponse,
  HumanFeedback,
  Rule,
  RuleStats,
  Template,
  TemplateCheckResult,
  AppMetrics,
  Regulation,
  RegulationMatch,
  KnowledgeListResponse,
  KnowledgeWriteResult,
  KnowledgeDeleteResult,
  DiffResult,
  NegotiationSession,
  NegotiationStats,
  TaskResponse,
  BadCaseListResponse,
  DiagnosticReport,
} from '../types'

const BASE = ''

/** API 错误：带 HTTP 状态码，供调用方区分 401（需登录）与其他失败 */
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 清掉本地登录态并广播，让所有 useAuth 实例同步为访客 */
export function clearAuth() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('username')
  window.dispatchEvent(new Event('auth-changed'))
}

/** 401 软失败：不再整页跳转（那会绕过一切路由转场），交由此事件唤起登录层 */
function handleUnauthorized(): never {
  clearAuth()
  window.dispatchEvent(new Event('unauthorized'))
  throw new ApiError('请先登录', 401)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  })
  if (res.status === 401) handleUnauthorized()
  if (!res.ok) {
    const text = await res.text()
    // FastAPI 错误体是 {"detail": "..."}：优先透出那句中文人话，解析失败退回原文
    let message = text
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed?.detail === 'string') message = parsed.detail
    } catch {
      /* 非 JSON 响应体，保留原文 */
    }
    throw new ApiError(message, res.status)
  }
  return res.json()
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (res.status === 401) handleUnauthorized()
  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(`API error ${res.status}: ${text}`, res.status)
  }
  return res.json()
}

/** 带 Bearer 头的文件下载：报告类端点是直链 <a> 拿不到登录态，改走 fetch+blob */
async function downloadFile(path: string, filename: string): Promise<void> {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401) handleUnauthorized()
  if (!res.ok) throw new ApiError(`下载失败 ${res.status}`, res.status)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export const api = {
  // Health
  health: () => request<HealthResponse>('/api/v1/health'),

  // Auth
  login: (body: LoginRequest) =>
    request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  register: (body: RegisterRequest) =>
    request<{ id: string; username: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  sendRegisterCode: (email: string) =>
    request<SendCodeResponse>('/api/v1/auth/send-code', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  // Review
  createReview: (text: string, with_human_review = true, position: ReviewPosition = 'neutral') =>
    request<TaskResponse>('/api/v1/review?mode=async', {
      method: 'POST',
      body: JSON.stringify({ review_body: { text, with_human_review, position } }),
    }),
  uploadReview: (file: File, with_human_review = true, position: ReviewPosition = 'neutral') => {
    const form = new FormData()
    form.append('file', file)
    form.append('position', position)
    return upload<TaskResponse>(`/api/v1/review/upload?mode=async&with_human_review=${with_human_review}`, form)
  },
  batchReview: (files: File[], with_human_review = true, position: ReviewPosition = 'neutral') => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    form.append('position', position)
    return upload<BatchReviewResponse>(`/api/v1/review/batch?with_human_review=${with_human_review}`, form)
  },
  listReviews: (page = 1, pageSize = 20) =>
    request<ReviewHistoryResponse>(`/api/v1/reviews?page=${page}&page_size=${pageSize}`),
  getReview: (id: string) => request<DetailedReview>(`/api/v1/review/${id}`),
  submitFeedback: (id: string, body: HumanFeedback) =>
    request<{ message: string; status: string }>(`/api/v1/review/${id}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ feedback_body: body }),
    }),
  deleteReview: (id: string) =>
    request<{ message: string; review_id: string }>(`/api/v1/review/${id}`, { method: 'DELETE' }),
  rerunReview: (id: string, with_human_review = true) =>
    request<TaskResponse>(`/api/v1/review/${id}/rerun?mode=async&with_human_review=${with_human_review}`, {
      method: 'POST',
    }),
  reportUrl: (id: string) => `${BASE}/api/v1/review/${id}/report`,
  // 带鉴权头的下载（访客点击时由调用方先过 requireLogin 门）
  downloadReport: (id: string) => downloadFile(`/api/v1/review/${id}/report`, `report_${id}.pdf`),
  downloadWord: (id: string) => downloadFile(`/api/v1/review/${id}/word`, `report_${id}.docx`),
  downloadRedline: (id: string) => downloadFile(`/api/v1/review/${id}/redline`, `redline_${id}.docx`),

  // Rules
  listRules: (category?: string) =>
    request<{ total: number; rules: Rule[] }>(`/api/v1/rules${category ? `?category=${category}` : ''}`),
  getRule: (id: string) => request<Rule>(`/api/v1/rules/${id}`),
  createRule: (data: Partial<Rule>) =>
    request<Rule>('/api/v1/rules', { method: 'POST', body: JSON.stringify(data) }),
  updateRule: (id: string, data: Partial<Rule>) =>
    request<Rule>(`/api/v1/rules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRule: (id: string) =>
    request<{ message: string }>(`/api/v1/rules/${id}`, { method: 'DELETE' }),
  toggleRule: (id: string, enabled: boolean) =>
    request<{ message: string }>(`/api/v1/rules/${id}/toggle?enabled=${enabled}`, { method: 'PATCH' }),
  getRuleStats: () => request<RuleStats>('/api/v1/rules/stats'),
  reloadRules: () => request<{ count: number }>('/api/v1/rules/reload', { method: 'POST' }),

  // Templates
  listTemplates: (category?: string) =>
    request<{ total: number; templates: Template[] }>(`/api/v1/templates${category ? `?category=${category}` : ''}`),
  getTemplate: (id: string) => request<Template>(`/api/v1/templates/${id}`),
  createTemplate: (data: Partial<Template>) =>
    request<Template>('/api/v1/templates', { method: 'POST', body: JSON.stringify(data) }),
  deleteTemplate: (id: string) =>
    request<{ message: string }>(`/api/v1/templates/${id}`, { method: 'DELETE' }),
  checkTemplate: (template_id: string, clause_texts: string[]) =>
    request<TemplateCheckResult>('/api/v1/templates/check', {
      method: 'POST',
      body: JSON.stringify({ template_id, clause_texts }),
    }),

  // Metrics
  getMetrics: () => request<AppMetrics>('/api/v1/metrics'),

  // Regulations
  listRegulations: (category?: string) =>
    request<{ regulations: Regulation[] }>(`/api/v1/regulations${category ? `?category=${category}` : ''}`),
  getRegulation: (id: string) => request<Regulation>(`/api/v1/regulations/${id}`),
  matchRegulations: (text: string) =>
    request<{ matches: RegulationMatch[] }>('/api/v1/regulations/match', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // Knowledge（RAG 知识库：列表 admin/reviewer，入库/删除仅 admin）
  listKnowledge: () => request<KnowledgeListResponse>('/api/v1/knowledge'),
  uploadKnowledgeDoc: (file: File, category: string, title: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    form.append('title', title)
    return upload<KnowledgeWriteResult>('/api/v1/knowledge/upload', form)
  },
  createKnowledgeText: (title: string, category: string, content: string) =>
    request<KnowledgeWriteResult>('/api/v1/knowledge/text', {
      method: 'POST',
      body: JSON.stringify({ title, category, content }),
    }),
  deleteKnowledgeDoc: (docId: string) =>
    request<KnowledgeDeleteResult>(`/api/v1/knowledge/${docId}`, { method: 'DELETE' }),

  // Diff
  compareDiff: (oldText: string, newText: string) =>
    request<DiffResult>('/api/v1/diff', {
      method: 'POST',
      body: JSON.stringify({ old_text: oldText, new_text: newText }),
    }),

  // Negotiation
  listNegotiations: () => request<{ sessions: NegotiationSession[]; total: number }>('/api/v1/negotiation/list'),
  startNegotiation: (reviewId: string) =>
    request<NegotiationSession>('/api/v1/negotiation/start', {
      method: 'POST',
      body: JSON.stringify({ review_id: reviewId }),
    }),
  getNegotiation: (id: string) => request<NegotiationSession>(`/api/v1/negotiation/${id}`),
  submitNegotiationFeedback: (id: string, feedback: {
    reviewer: string;
    decision: string;
    comments: string;
    modifications?: { suggestion_index: number; original_text: string; new_text: string; reason: string }[];
  }) =>
    request<{ message: string }>(`/api/v1/negotiation/${id}/feedback`, {
      method: 'POST',
      body: JSON.stringify(feedback),
    }),
  completeNegotiation: (id: string) =>
    request<{ message: string }>(`/api/v1/negotiation/${id}/complete`, { method: 'POST' }),
  rejectNegotiation: (id: string, reason: string) =>
    request<{ message: string }>(`/api/v1/negotiation/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  getNegotiationStats: () => request<NegotiationStats>('/api/v1/negotiation/stats'),

  // Word Report
  wordReportUrl: (id: string) => `${BASE}/api/v1/review/${id}/word`,
  redlineUrl: (id: string) => `${BASE}/api/v1/review/${id}/redline`,

  // Feedback v2 + BadCase (Phase 3)
  submitFeedbackV2: (
    id: string,
    body: {
      reviewer: string;
      decision: 'approve' | 'reject' | 'modify';
      comments: string;
      bad_clauses?: string[];
      missed_clauses?: string[];
      overall_rating?: number;
      industry?: string;
      contract_type_hint?: string;
      timestamp: string;
    }
  ) =>
    request<{ message: string; status: string }>(`/api/v1/review/${id}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ feedback_body: body }),
    }),

  listBadCases: (min_severity = 'medium', limit = 50) =>
    request<BadCaseListResponse>(
      `/api/v1/bad-cases?min_severity=${min_severity}&limit=${limit}`
    ),

  diagnoseBadCase: (caseId: string) =>
    request<DiagnosticReport>(`/api/v1/diagnostics/bad-cases/${caseId}`),

  // 判分官对该卷的抽检结论（未抽检时后端返回 404，调用方静默处理）
  getReviewDiagnostics: (reviewId: string) =>
    request<DiagnosticReport>(`/api/v1/diagnostics/reviews/${reviewId}`),

  resolveBadCase: (caseId: string, commit: string, notes: string) =>
    request<{ case_id: string; resolved: boolean }>(
      `/api/v1/bad-cases/${caseId}/resolve`,
      {
        method: 'POST',
        body: JSON.stringify({ commit, notes }),
      }
    ),
}
