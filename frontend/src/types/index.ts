// Health
export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  service: string
  version: string
  database?: string
}

// Auth
export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  code: string
}

/** 发送注册验证码的响应 */
export interface SendCodeResponse {
  sent: boolean
  expires_in: number
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface UserInfo {
  id: string
  tenant_id: string
  username: string
  email: string
  role: string
  is_active: boolean
}

// Review
export type ReviewPosition = 'buyer' | 'seller' | 'neutral'

export interface ReviewRequest {
  text: string
  with_human_review?: boolean
  position?: ReviewPosition
}

export type StepStatus = 'pending' | 'running' | 'done' | 'error'

export interface StepEvent {
  step: string
  status: StepStatus
  message: string
  started_at: string
  finished_at: string | null
}

export interface TaskResponse {
  review_id: string
  task_id: string
  status: string
  message: string
}

export interface ReviewResponse {
  review_id: string
  status: string
  contract_type: string
  position?: ReviewPosition
  clauses_count: number
  risk_summary: string
  overall_risk_level: string
  overall_compliance: string
  suggestions_count: number
  needs_human_review: boolean
  filename: string
  created_at: string
  updated_at: string
  current_step: string
  progress: number
  step_log: StepEvent[]
}

export interface ReviewHistoryItem {
  review_id: string
  status: string
  contract_type: string
  overall_risk_level: string
  overall_compliance: string
  needs_human_review: boolean
  risk_summary: string
  filename: string
  created_at: string
  updated_at: string
}

export interface ReviewHistoryResponse {
  total: number
  items: ReviewHistoryItem[]
}

export interface DetailedReview {
  review_id: string
  status: string
  contract_type: string
  position?: ReviewPosition
  filename: string
  created_at: string
  updated_at: string
  clauses: Clause[]
  risk_findings: RiskFinding[]
  risk_summary: string
  overall_risk_level: string
  risk_score: number
  compliance_findings: ComplianceFinding[]
  missing_clauses: string[]
  overall_compliance: string
  suggestions: Suggestion[]
  version_diff: string
  needs_human_review: boolean
  human_feedback: HumanFeedback | null
  errors: string[]
  current_step: string
  progress: number
  step_log: StepEvent[]
  // P0-3: 暴露降级状态
  warnings?: string[]
  degraded_steps?: string[]
  has_quality_issues?: boolean
}

export interface Clause {
  id: string
  title: string
  content: string
  category: string
  section_number: string
  entities: ContractEntity[]
}

export interface ContractEntity {
  entity_type: string
  value: string
  location: string
}

/** RAG 检索引用：批注审查时命中的知识库条文（可审计的"判断依据"补充） */
export interface RagRef {
  doc_title: string
  clause_title: string
  category: string
  score: number
  snippet: string
}

export interface RiskFinding {
  clause_id: string
  risk_level: string
  risk_type: string
  description: string
  buyer_impact: string
  seller_impact: string
  rationale: string
  source?: 'rule' | 'llm' | 'conflict' | string  // 004 迁移后由后端写入；老数据缺省，前端按 rationale 兜底推断
  rag_refs?: RagRef[]  // 旧卷宗无此字段，undefined 按无引用渲染
}

export interface ComplianceFinding {
  clause_id: string
  status: string
  regulation: string
  issue: string
  recommendation: string
  rag_refs?: RagRef[]
}

export interface Suggestion {
  clause_id: string
  original_text: string
  suggested_text: string
  reason: string
  priority: string
  rag_refs?: RagRef[]
}

export type DecisionType = 'approve' | 'reject' | 'modify'

export interface HumanFeedback {
  reviewer: string
  decision: 'approve' | 'reject' | 'modify'
  comments: string
  timestamp: string
  bad_clauses?: string[]
  missed_clauses?: string[]
  overall_rating?: number
  industry?: string                    // v2
  contract_type_hint?: string          // v2
  modified_suggestions?: Suggestion[]
}

// BadCase
export interface BadCaseItem {
  case_id: string
  review_id: string
  signal_type: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  timestamp: string
  judge_score?: number
  judge_rationale?: string
  state_warnings: string[]
  state_degraded_steps: string[]
  resolved: boolean
  resolution: string
  resolution_commit: string
}

export interface BadCaseListResponse {
  total: number
  items: BadCaseItem[]
}

export interface DiagnosticReport {
  review_id: string
  timestamp: string
  rules_result: any | null
  similar_feedback: any[]
  similar_bad_cases: any[]
  similar_good_signatures: any[]
  deep_analyses: any[]               // v2 新增
  hypothesis: string
  recommended_actions: string[]
  state_warnings: string[]
  state_degraded_steps: string[]
  judge_score: number | null
}

// Batch
export interface BatchReviewResponse {
  batch_id: string
  total: number
  completed: number
  failed: number
  status: string
  items: BatchReviewItem[]
}

export interface BatchReviewItem {
  review_id: string
  filename: string
  status: string
  error: string
}

// Rules
export interface Rule {
  id: string
  name: string
  description: string
  severity: string
  category: string
  action: string
  priority: number
  enabled: boolean
  condition: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface RuleStats {
  total: number
  enabled: number
  disabled: number
  by_severity: Record<string, number>
  by_category: Record<string, number>
}

// Templates
export interface Template {
  id: string
  name: string
  category: string
  description: string
  required_clauses: string[]
  enabled: boolean
  metadata: Record<string, unknown>
}

export interface TemplateCheckResult {
  template_id: string
  template_name: string
  matched: string[]
  missing: string[]
  extra: string[]
  score: number
}

// Metrics
export interface AppMetrics {
  uptime_seconds: number
  request_count: number
  review_count: number
  risk_distribution: Record<string, number>
}

// Regulations
export interface Regulation {
  id: string
  name: string
  article: string
  content: string
  category: string
  keywords: string[]
  description: string
}

export interface RegulationMatch {
  regulation_id: string
  regulation_name: string
  article: string
  content: string
  matched_keyword: string
  relevance: number
}

// Knowledge（RAG 知识库，admin/reviewer 可见；入库/删除仅 admin）
export interface KnowledgeStatus {
  rag_enabled: boolean
  deps_ok: boolean
  index_exists: boolean
  ready: boolean
  active_chunks: number
  total_chunks: number
  doc_count: number
  embedding_model: string
  index_model: string
  model_mismatch: boolean
  reason: string
}

export interface KnowledgeDoc {
  doc_id: string
  title: string
  filename: string
  category: string
  chunk_count: number
  source_type: 'upload' | 'text' | string
  uploaded_by: string
  uploaded_at: string
}

export interface KnowledgeListResponse {
  docs: KnowledgeDoc[]
  status: KnowledgeStatus
}

export interface RagReloadInfo {
  ready: boolean
  size: number
  reason: string
}

export interface KnowledgeWriteResult {
  doc_id: string
  chunk_count: number
  rag: RagReloadInfo
}

export interface KnowledgeDeleteResult {
  doc_id: string
  chunks_marked_deleted: number
  rag: RagReloadInfo
}

// Diff
export interface DiffResult {
  added: number
  removed: number
  changed: number
  unchanged: number
  items: DiffItem[]
  summary: string
}

export interface DiffItem {
  type: 'added' | 'removed' | 'changed' | 'unchanged'
  line: number
  content: string
  old_value?: string
  new_value?: string
}

// Negotiation
export interface NegotiationSession {
  session_id: string
  review_id: string
  status: string
  rounds: FeedbackRound[]
  current_round: number
  created_at: string
  updated_at: string
  final_decision?: string
}

export interface FeedbackRound {
  round_number: number
  reviewer: string
  decision: string
  comments: string
  modifications?: SuggestionModification[]
  timestamp: string
}

export interface SuggestionModification {
  suggestion_index: number
  original_text: string
  new_text: string
  reason: string
}

export interface NegotiationStats {
  total_sessions: number
  active_sessions: number
  completed: number
  rejected: number
  total_rounds: number
}
