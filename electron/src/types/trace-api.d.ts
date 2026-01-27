/**
 * Type definitions for the Trace API exposed by preload.js
 */

export interface BackendStatus {
  version: string;
  running: boolean;
  uptime_seconds: number;
  python_version: string;
}

export interface PythonAPI {
  /** Check if Python backend is ready */
  isReady(): Promise<boolean>;

  /** Ping the Python backend */
  ping(): Promise<string>;

  /** Get Python backend status */
  getStatus(): Promise<BackendStatus>;

  /** Generic call to Python backend */
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T>;
}

/** Permission types */
export type PermissionType = 'screen_recording' | 'accessibility' | 'location';

/** Permission status */
export type PermissionStatusType = 'granted' | 'denied' | 'not_determined' | 'restricted';

/** State of a single permission */
export interface PermissionState {
  permission: PermissionType;
  status: PermissionStatusType;
  required: boolean;
  can_request: boolean;
}

/** State of all permissions */
export interface AllPermissionsState {
  screen_recording: PermissionState;
  accessibility: PermissionState;
  location: PermissionState;
  all_granted: boolean;
  requires_restart: boolean;
}

/** Instructions for granting a permission */
export interface PermissionInstructions {
  title: string;
  description: string;
  steps: string[];
  system_preferences_url: string;
  requires_restart: boolean;
}

/** Permission API methods */
export interface PermissionsAPI {
  /** Check all permissions */
  checkAll(): Promise<AllPermissionsState>;

  /** Check a specific permission */
  check(permission: PermissionType): Promise<PermissionState>;

  /** Get instructions for granting a permission */
  getInstructions(permission: PermissionType): Promise<PermissionInstructions>;

  /** Open system settings for a permission */
  openSettings(permission: PermissionType): Promise<{ success: boolean }>;

  /** Request accessibility permission (triggers system prompt) */
  requestAccessibility(): Promise<{ success: boolean }>;

  /** Request location permission (triggers system prompt) */
  requestLocation(): Promise<{ success: boolean }>;
}

/** Citation from a note */
export interface Citation {
  note_id: string;
  note_path: string;
  quote: string;
  timestamp: string;
}

/** v0.8.0: Unified citation for both notes and web sources */
export interface UnifiedCitation {
  id: string;  // Citation number (e.g., "1", "2")
  type: 'note' | 'web';
  label: string;

  // Note-specific fields
  note_id?: string;
  note_type?: 'hourly' | 'daily';
  timestamp?: string;
  note_content?: string;  // Snippet for popup preview

  // Web-specific fields
  url?: string;
  title?: string;
  snippet?: string;
  accessed_at?: string;
}

/** Note match from search */
export interface NoteMatch {
  note_id: string;
  path: string;
  title: string;
  timestamp: string;
  similarity: number;
  summary: string;
  entities: Array<{ name: string; type: string }>;
}

/** Related entity from graph expansion */
export interface RelatedEntity {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  edge_type: string;
  weight: number;
  source_entity_id: string;
  source_entity_name: string;
  direction: 'to' | 'from';
}

/** Aggregate item (e.g., most used app) */
export interface AggregateItem {
  key: string;
  key_type: string;
  value: number;
  period_type: string;
  period_start: string;
  period_end: string;
}

/** Time filter parsed from query */
export interface TimeFilter {
  start: string;
  end: string;
  description: string;
}

/** Follow-up question from chat */
export interface FollowUpQuestion {
  question: string;
  category: string;
}

/** Chat response */
export interface ChatResponse {
  answer: string;
  citations: Citation[];
  notes: NoteMatch[];
  time_filter: TimeFilter | null;
  related_entities: RelatedEntity[];
  aggregates: AggregateItem[];
  query_type: string;
  confidence: number;
  processing_time_ms: number;
  follow_up?: FollowUpQuestion | null;
  // v0.8.0: Unified citations with inline [N] markers
  unified_citations?: UnifiedCitation[];
  web_citations?: Array<{ title: string; url: string; snippet: string }>;
}

/** Chat query options */
export interface ChatQueryOptions {
  timeFilter?: string;
  includeGraphExpansion?: boolean;
  includeAggregates?: boolean;
  maxResults?: number;
}

/** Chat API methods */
export interface ChatAPI {
  /** Send a query and get a response */
  query(query: string, options?: ChatQueryOptions): Promise<ChatResponse>;
}

/** App usage statistics */
export interface AppUsage {
  appName: string;
  bundleId: string;
  totalMinutes: number;
  sessionCount: number;
  percentage: number;
}

/** Topic usage statistics */
export interface TopicUsage {
  topic: string;
  entityType: string;
  noteCount: number;
  mentionStrength: number;
}

/** Activity trend data point */
export interface ActivityTrend {
  date: string;
  eventCount: number;
  uniqueApps: number;
}

/** Heatmap cell */
export interface HeatmapCell {
  hour: number;
  dayOfWeek: number;
  activityCount: number;
}

/** Productivity summary */
export interface ProductivitySummary {
  success: boolean;
  totalMinutes: number;
  totalHours: number;
  uniqueApps: number;
  notesGenerated: number;
  entitiesExtracted: number;
  mostProductiveHour: number | null;
  daysAnalyzed: number;
}

/** Dashboard data response */
export interface DashboardData {
  success: boolean;
  summary: ProductivitySummary;
  appUsage: AppUsage[];
  topicUsage: TopicUsage[];
  activityTrend: ActivityTrend[];
  activityHeatmap: HeatmapCell[];
  error?: string;
}

/** Dashboard API methods */
export interface DashboardAPI {
  /** Get all dashboard data */
  getData(daysBack?: number): Promise<DashboardData>;

  /** Get productivity summary */
  getSummary(daysBack?: number): Promise<ProductivitySummary>;

  /** Get app usage statistics */
  getAppUsage(daysBack?: number, limit?: number): Promise<{ success: boolean; apps: AppUsage[] }>;

  /** Get topic usage statistics */
  getTopicUsage(daysBack?: number, limit?: number): Promise<{ success: boolean; topics: TopicUsage[] }>;

  /** Get activity trend */
  getActivityTrend(daysBack?: number): Promise<{ success: boolean; trend: ActivityTrend[] }>;

  /** Get activity heatmap */
  getHeatmap(daysBack?: number): Promise<{ success: boolean; heatmap: HeatmapCell[] }>;
}

/** Weekly comparison data */
export interface WeeklyComparison {
  hoursChange: number;
  hoursChangePercent: number;
  appsChange: number;
  notesChange: number;
}

/** Weekly digest data */
export interface WeeklyDigest {
  success: boolean;
  weekStart: string;
  weekEnd: string;
  totalHours: number;
  uniqueApps: number;
  notesGenerated: number;
  topApps: Array<{ appName: string; bundleId: string; minutes: number }>;
  topTopics: Array<{ topic: string; entityType: string; noteCount: number }>;
  productivityScore: number;
  highlights: string[];
  comparison: WeeklyComparison;
  error?: string;
}

/** Digest notification result */
export interface DigestNotificationResult {
  success: boolean;
  digest?: WeeklyDigest;
  notificationSent?: boolean;
  error?: string;
}

/** Weekly digest API methods */
export interface DigestAPI {
  /** Get current week digest */
  getCurrent(): Promise<WeeklyDigest>;

  /** Get digest for a specific week offset (0=current, 1=last week, etc.) */
  getWeek(weekOffset?: number): Promise<WeeklyDigest>;

  /** Send digest notification */
  sendNotification(weekOffset?: number): Promise<DigestNotificationResult>;

  /** Get digest history for multiple weeks */
  getHistory(weeks?: number): Promise<{ success: boolean; digests: WeeklyDigest[] }>;
}

/** Note listing item */
export interface NoteListItem {
  note_id: string;
  type: 'hourly' | 'daily';
  path: string;
  date: string;
}

/** Note content */
export interface NoteContent {
  content: string;
  path: string;
}

/** Notes list options */
export interface NotesListOptions {
  startDate?: string;
  endDate?: string;
  limit?: number;
}

/** Notes API methods */
export interface NotesAPI {
  /** Read a specific note by ID */
  read(noteId: string): Promise<NoteContent>;

  /** List available notes */
  list(options?: NotesListOptions): Promise<{ notes: NoteListItem[] }>;
}

/** Application settings */
export interface AppSettings {
  data_dir: string;
  notes_dir: string;
  db_path: string;
  cache_dir: string;
  has_api_key: boolean;
}

/** User profile settings */
export interface UserProfile {
  name: string;
  age: string;
  interests: string;
  languages: string;
  additional_info: string;
}

/** All settings with full configuration and metadata */
export interface AllSettings {
  config: {
    appearance: { show_in_dock: boolean; launch_at_login: boolean };
    capture: {
      summarization_interval_minutes: number;
      daily_revision_hour: number;
      blocked_apps: string[];
      blocked_domains: string[];
      power_saving_enabled?: boolean;
      power_saving_mode?: 'off' | 'automatic' | 'always_on';
      power_saving_threshold?: number;
      power_saving_interval?: number;
      dedup_threshold?: number;
      jpeg_quality?: number;
    };
    models?: {
      triage: string;
      hourly: string;
      daily: string;
      chat: string;
    };
    notifications: { weekly_digest_enabled: boolean; weekly_digest_day: string };
    shortcuts: { open_trace: string; enabled?: boolean };
    data: { retention_months: number | null };
    api_key: string | null;
    user_profile?: UserProfile;
    updates?: {
      check_on_launch: boolean;
      check_periodically: boolean;
      check_interval_hours: number;
      skipped_versions: string[];
      last_check_timestamp: number | null;
      remind_later_until: number | null;
    };
  };
  options: {
    summarization_intervals: number[];
    daily_revision_hours: number[];
    weekly_digest_days: string[];
    retention_months: (number | null)[];
  };
  has_api_key: boolean;
  paths: {
    data_dir: string;
    notes_dir: string;
    db_path: string;
    cache_dir: string;
  };
}

/** Settings API methods */
export interface SettingsAPI {
  /** Get current settings */
  get(): Promise<AppSettings>;

  /** Get a specific setting value by key path */
  get(key: string): Promise<unknown>;

  /** Get all settings with metadata */
  getAll(): Promise<AllSettings>;

  /** Set a single setting value by key path */
  set(key: string, value: unknown): Promise<{ success: boolean }>;

  /** Set a single setting value by key path */
  setValue(key: string, value: unknown): Promise<{ success: boolean }>;

  /** Get the stored API key */
  getApiKey(): Promise<{ api_key: string | null; has_api_key: boolean }>;

  /** Set API key */
  setApiKey(apiKey: string): Promise<{ success: boolean }>;

  /** Validate API key against OpenAI API */
  validateApiKey(apiKey?: string): Promise<{ valid: boolean; error: string | null }>;

  /** Get summary of data that would be deleted by a reset */
  getDataSummary(): Promise<{
    notes_count: number;
    notes_size_bytes: number;
    database_exists: boolean;
    tables_with_data: { table: string; count: number }[];
    memory_exists: boolean;
    cache_size_bytes: number;
  }>;

  /** Reset all data (notes, database, memory, cache) - DESTRUCTIVE */
  resetAllData(): Promise<{
    success: boolean;
    notes_deleted: boolean;
    database_cleared: boolean;
    memory_cleared: boolean;
    cache_cleared: boolean;
    errors: string[];
  }>;
}

/** Appearance settings */
export interface AppearanceSettings {
  showInDock: boolean;
  launchAtLogin: boolean;
}

/** Appearance API methods */
export interface AppearanceAPI {
  /** Get current appearance settings */
  get(): Promise<AppearanceSettings>;

  /** Set dock visibility (macOS) */
  setDockVisibility(showInDock: boolean): Promise<void>;

  /** Set launch at login */
  setLaunchAtLogin(launchAtLogin: boolean): Promise<void>;
}

/** Window control methods */
export interface WindowAPI {
  /** Minimize window */
  minimize(): Promise<void>;

  /** Maximize/unmaximize window */
  maximize(): Promise<void>;

  /** Close window */
  close(): Promise<void>;
}

/** Shortcut names */
export type ShortcutName = 'toggleWindow' | 'quickCapture';

/** Shortcut bindings */
export interface ShortcutBindings {
  toggleWindow: string;
  quickCapture: string;
}

/** Shortcut set result */
export interface ShortcutSetResult {
  success: boolean;
  shortcut?: string;
  accelerator?: string;
  error?: string;
}

/** Global shortcuts API */
export interface ShortcutsAPI {
  /** Get current shortcut bindings */
  get(): Promise<ShortcutBindings>;

  /** Set a shortcut binding */
  set(name: ShortcutName, accelerator: string): Promise<ShortcutSetResult>;

  /** Reset shortcuts to defaults */
  reset(): Promise<ShortcutBindings>;

  /** Enable or disable global shortcuts */
  setEnabled(enabled: boolean): Promise<{ success: boolean; enabled: boolean }>;

  /** Check if global shortcuts are enabled */
  isEnabled(): Promise<{ enabled: boolean }>;

  /** Listen for quick capture shortcut events */
  onQuickCapture(callback: () => void): () => void;
}

/** Tray menu event listeners */
export interface TrayAPI {
  /** Listen for open note events from tray menu */
  onOpenNote(callback: (noteId: string) => void): () => void;

  /** Listen for open graph events from tray menu */
  onOpenGraph(callback: () => void): () => void;

  /** Listen for open settings events from tray menu */
  onOpenSettings(callback: () => void): () => void;
}

/** Graph node for visualization */
export interface GraphNode {
  id: string;
  label: string;
  type: string;
  noteCount: number;
  edgeCount: number;
}

/** Graph edge for visualization */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

/** Graph data response */
export interface GraphDataResponse {
  success: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeCount: number;
  edgeCount: number;
  error?: string;
}

/** Entity type with count */
export interface EntityTypeCount {
  type: string;
  count: number;
}

/** Entity types response */
export interface EntityTypesResponse {
  success: boolean;
  types: EntityTypeCount[];
  error?: string;
}

/** Related entity in details view */
export interface RelatedEntityInfo {
  id: string;
  direction: 'incoming' | 'outgoing';
  edgeType: string;
  weight: number;
  name: string;
  type: string;
}

/** Note reference in entity details */
export interface EntityNoteRef {
  noteId: string;
  path: string;
  timestamp: string;
  summary: string;
  strength: number;
}

/** Entity details response */
export interface EntityDetailsResponse {
  success: boolean;
  entity?: {
    id: string;
    type: string;
    name: string;
    aliases: string[];
  };
  related?: RelatedEntityInfo[];
  notes?: EntityNoteRef[];
  error?: string;
}

/** Graph data options */
export interface GraphDataOptions {
  daysBack?: number;
  entityTypes?: string[];
  minEdgeWeight?: number;
  limit?: number;
}

/** Graph API methods */
export interface GraphAPI {
  /** Get graph data for visualization */
  getData(options?: GraphDataOptions): Promise<GraphDataResponse>;

  /** Get entity types with counts */
  getEntityTypes(): Promise<EntityTypesResponse>;

  /** Get entity details */
  getEntityDetails(entityId: string): Promise<EntityDetailsResponse>;
}

/** Blocklist entry */
export interface BlocklistEntry {
  blocklist_id: string;
  block_type: 'app' | 'domain';
  pattern: string;
  display_name: string | null;
  enabled: boolean;
  block_screenshots: boolean;
  block_events: boolean;
  created_ts: string;
  updated_ts: string;
}

/** Blocklist API response */
export interface BlocklistListResponse {
  success: boolean;
  entries: BlocklistEntry[];
  count: number;
}

/** Blocklist add response */
export interface BlocklistAddResponse {
  success: boolean;
  entry?: BlocklistEntry;
  error?: string;
}

/** Blocklist operation response */
export interface BlocklistOperationResponse {
  success: boolean;
  removed?: boolean;
  updated?: boolean;
  added?: number;
  error?: string;
}

/** Blocklist check response */
export interface BlocklistCheckResponse {
  success: boolean;
  blocked: boolean;
  reason: string | null;
  error?: string;
}

/** Export summary */
export interface ExportSummary {
  success: boolean;
  notes_in_db: number;
  markdown_files: number;
  entities: number;
  edges: number;
  aggregates: number;
  estimated_markdown_size_bytes: number;
  error?: string;
}

/** Export result */
export interface ExportResult {
  success: boolean;
  format?: string;
  notes_count?: number;
  entities_count?: number;
  edges_count?: number;
  export_path?: string;
  export_size_bytes?: number;
  export_time_seconds?: number;
  canceled?: boolean;
  error?: string;
}

/** Export API methods */
export interface ExportAPI {
  /** Get summary of exportable data */
  summary(): Promise<ExportSummary>;

  /** Export to JSON format */
  toJson(outputPath: string): Promise<ExportResult>;

  /** Export to Markdown directory */
  toMarkdown(outputPath: string): Promise<ExportResult>;

  /** Export to ZIP archive */
  toArchive(outputPath: string): Promise<ExportResult>;

  /** Show save dialog and export to archive */
  saveArchive(): Promise<ExportResult>;
}

/** Spotlight indexing status */
export interface SpotlightStatus {
  success: boolean;
  indexed: boolean;
  notes_count: number;
  directory: string;
  excluded?: boolean;
  error?: string;
}

/** Spotlight reindex result */
export interface SpotlightReindexResult {
  success: boolean;
  total: number;
  errors: number;
  error?: string;
}

/** Spotlight index note options */
export interface SpotlightIndexNoteOptions {
  title?: string;
  summary?: string;
  entities?: string[];
}

/** Spotlight API methods */
export interface SpotlightAPI {
  /** Get Spotlight indexing status */
  status(): Promise<SpotlightStatus>;

  /** Reindex all notes for Spotlight */
  reindex(): Promise<SpotlightReindexResult>;

  /** Index a single note for Spotlight */
  indexNote(notePath: string, options?: SpotlightIndexNoteOptions): Promise<{ success: boolean }>;

  /** Trigger Spotlight to reindex using mdimport */
  triggerReindex(): Promise<{ success: boolean }>;
}

/** Detected pattern data */
export interface PatternData {
  [key: string]: unknown;
}

/** Detected pattern */
export interface Pattern {
  patternType: string;
  description: string;
  confidence: number;
  data: PatternData;
}

/** All patterns response */
export interface AllPatternsResponse {
  success: boolean;
  patterns: Pattern[];
  patternCount: number;
  daysAnalyzed: number;
  error?: string;
}

/** Patterns by type response */
export interface PatternsResponse {
  success: boolean;
  patterns: Pattern[];
  error?: string;
}

/** Insights summary response */
export interface InsightsSummaryResponse {
  success: boolean;
  insights: string[];
  totalPatterns: number;
  error?: string;
}

/** Pattern detection API methods */
export interface PatternsAPI {
  /** Get all detected patterns */
  getAll(daysBack?: number): Promise<AllPatternsResponse>;

  /** Get insights summary (top 3 patterns) */
  getSummary(daysBack?: number): Promise<InsightsSummaryResponse>;

  /** Get time of day patterns */
  getTimeOfDay(daysBack?: number): Promise<PatternsResponse>;

  /** Get day of week patterns */
  getDayOfWeek(daysBack?: number): Promise<PatternsResponse>;

  /** Get app usage patterns */
  getApps(daysBack?: number): Promise<PatternsResponse>;

  /** Get focus session patterns */
  getFocus(daysBack?: number): Promise<PatternsResponse>;
}

/** Blocklist API methods */
export interface BlocklistAPI {
  /** List all blocklist entries */
  list(includeDisabled?: boolean): Promise<BlocklistListResponse>;

  /** Add an app to the blocklist */
  addApp(
    bundleId: string,
    displayName?: string | null,
    blockScreenshots?: boolean,
    blockEvents?: boolean
  ): Promise<BlocklistAddResponse>;

  /** Add a domain to the blocklist */
  addDomain(
    domain: string,
    displayName?: string | null,
    blockScreenshots?: boolean,
    blockEvents?: boolean
  ): Promise<BlocklistAddResponse>;

  /** Remove an entry from the blocklist */
  remove(blocklistId: string): Promise<BlocklistOperationResponse>;

  /** Enable or disable a blocklist entry */
  setEnabled(blocklistId: string, enabled: boolean): Promise<BlocklistOperationResponse>;

  /** Initialize default blocklist entries */
  initDefaults(): Promise<BlocklistOperationResponse>;

  /** Check if an app or URL is blocked */
  check(bundleId?: string | null, url?: string | null): Promise<BlocklistCheckResponse>;
}

/** Installed application info */
export interface InstalledApp {
  name: string;
  bundleId: string;
  path: string;
}

/** Installed apps list response */
export interface InstalledAppsResponse {
  success: boolean;
  apps: InstalledApp[];
  error?: string;
}

/** Installed apps API methods */
export interface AppsAPI {
  /** List installed applications (macOS only) */
  list(): Promise<InstalledAppsResponse>;
}

/** Shell API methods */
export interface ShellAPI {
  /** Open external URL */
  openExternal(url: string): Promise<{ success: boolean }>;
}

/** Update asset (downloadable file) */
export interface UpdateAsset {
  name: string;
  downloadUrl: string;
  size: number;
  contentType?: string;
}

/** Update information */
export interface UpdateInfo {
  available: boolean;
  currentVersion: string;
  latestVersion: string;
  releaseUrl: string;
  releaseNotes: string;
  releaseName?: string;
  publishedAt: string;
  assets: UpdateAsset[];
  error?: string;
}

/** Update check result */
export interface UpdateCheckResult {
  checked: boolean;
  available?: boolean;
  skipped?: boolean;
  reason?: string;
  error?: string;
  currentVersion?: string;
  updateInfo?: UpdateInfo;
}

/** Update settings */
export interface UpdateSettings {
  check_on_launch: boolean;
  check_periodically: boolean;
  check_interval_hours: number;
  skipped_versions: string[];
  last_check_timestamp: number | null;
  remind_later_until: number | null;
}

/** Updates API methods */
export interface UpdatesAPI {
  /** Check for updates */
  check(options?: { silent?: boolean; force?: boolean }): Promise<UpdateCheckResult>;

  /** Get cached update info */
  getInfo(): Promise<UpdateInfo | null>;

  /** Open release page in browser */
  openReleasePage(url: string): Promise<{ success: boolean }>;

  /** Listen for update available events */
  onUpdateAvailable(callback: (info: UpdateInfo) => void): () => void;
}

/** User profile in memory */
export interface MemoryProfile {
  name?: string;
  age?: string;
  languages?: string;
  location?: string;
  occupation?: string;
}

/** User memory data */
export interface UserMemory {
  profile: MemoryProfile;
  interests: string[];
  preferences: string[];
  important_facts: string[];
  work_projects: string[];
  learned_patterns: string[];
  conversation_insights: string[];
}

/** Memory get response */
export interface MemoryGetResponse {
  success: boolean;
  memory: UserMemory;
}

/** Memory context response */
export interface MemoryContextResponse {
  success: boolean;
  context: string;
}

/** Memory raw response */
export interface MemoryRawResponse {
  success: boolean;
  content: string;
}

/** Memory operation response */
export interface MemoryOperationResponse {
  success: boolean;
  error?: string;
}

/** Memory learn response */
export interface MemoryLearnResponse {
  success: boolean;
  extracted: string[];
  error?: string;
}

/** Memory API methods */
export interface MemoryAPI {
  /** Get full user memory */
  get(): Promise<MemoryGetResponse>;

  /** Get memory context formatted for LLM */
  getContext(): Promise<MemoryContextResponse>;

  /** Get raw markdown content */
  getRaw(): Promise<MemoryRawResponse>;

  /** Update profile fields */
  updateProfile(profile: Partial<MemoryProfile>): Promise<MemoryOperationResponse>;

  /** Add an item to a section */
  addItem(section: string, item: string): Promise<MemoryOperationResponse>;

  /** Remove an item from a section */
  removeItem(section: string, item: string): Promise<MemoryOperationResponse>;

  /** Bulk update memory */
  bulkUpdate(updates: Partial<UserMemory>): Promise<MemoryOperationResponse>;

  /** Learn from a user's response to a follow-up question */
  learnFromResponse(question: string, answer: string, context?: string): Promise<MemoryLearnResponse>;

  /** Migrate profile from config to MEMORY.md */
  migrateFromConfig(): Promise<{ success: boolean; migrated: boolean; message: string }>;

  /** Check if memory is empty */
  isEmpty(): Promise<{ success: boolean; is_empty: boolean }>;
}

/** Onboarding mode */
export type OnboardingMode = 'initial' | 'update' | 'restart';

/** Onboarding start response */
export interface OnboardingStartResponse {
  success: boolean;
  message: string;
  phase: string;
  extracted: Record<string, unknown>;
  error?: string;
}

/** Onboarding chat params */
export interface OnboardingChatParams {
  phase: string;
  message: string;
  history: Array<{ role: 'assistant' | 'user'; content: string }>;
  extracted: Record<string, unknown>;
  mode: OnboardingMode;
}

/** Onboarding chat response */
export interface OnboardingChatResponse {
  success: boolean;
  response: string;
  phase: string;
  extracted: Record<string, unknown>;
  should_advance: boolean;
  completion_detected: boolean;
  is_ready_to_continue: boolean;
  error?: string;
}

/** Onboarding finalize params */
export interface OnboardingFinalizeParams {
  history: Array<{ role: 'assistant' | 'user'; content: string }>;
  extracted: Record<string, unknown>;
}

/** Onboarding finalize response */
export interface OnboardingFinalizeResponse {
  success: boolean;
  items_added: number;
  summary: string;
  error?: string;
}

/** Onboarding summary response */
export interface OnboardingSummaryResponse {
  success: boolean;
  summary: string;
  error?: string;
}

/** Onboarding API methods */
export interface OnboardingAPI {
  /** Start the onboarding conversation */
  start(mode?: OnboardingMode): Promise<OnboardingStartResponse>;

  /** Process a message in the onboarding conversation */
  chat(params: OnboardingChatParams): Promise<OnboardingChatResponse>;

  /** Finalize and save the onboarding to memory */
  finalize(params: OnboardingFinalizeParams): Promise<OnboardingFinalizeResponse>;

  /** Clear memory (for restart) */
  clear(): Promise<MemoryOperationResponse>;

  /** Get memory summary (for update mode) */
  getSummary(): Promise<OnboardingSummaryResponse>;
}

/** Conversation session */
export interface Conversation {
  conversation_id: string;
  title: string;
  created_ts: string;
  updated_ts: string;
  pinned: boolean;
  archived: boolean;
  title_generated_at?: string | null;
  message_count?: number;
  last_message_preview?: string;
}

/** Message metadata for assistant responses */
export interface MessageMetadata {
  citations: Citation[];
  notes: NoteMatch[];
  aggregates: AggregateItem[];
  confidence: number;
  query_type: string;
  processing_time_ms: number;
}

/** Message within a conversation */
export interface ConversationMessage {
  message_id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_ts: string;
  metadata?: MessageMetadata | null;
  token_count?: number | null;
}

/** Conversation list options */
export interface ConversationListOptions {
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
  searchQuery?: string;
}

/** Conversation list response */
export interface ConversationListResponse {
  conversations: Conversation[];
  total_count: number;
}

/** Conversation get options */
export interface ConversationGetOptions {
  messageLimit?: number;
  messageOffset?: number;
}

/** Conversation get response */
export interface ConversationGetResponse {
  conversation: Conversation;
  messages: ConversationMessage[];
  has_more: boolean;
}

/** Conversation send options */
export interface ConversationSendOptions {
  timeFilter?: string;
  includeGraphExpansion?: boolean;
  includeAggregates?: boolean;
  maxResults?: number;
}

/** Conversation send response */
export interface ConversationSendResponse {
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
  response: ChatResponse;
  title_updated: boolean;
  new_title?: string | null;
}

/** Conversations API methods */
export interface ConversationsAPI {
  /** List conversations with pagination */
  list(options?: ConversationListOptions): Promise<ConversationListResponse>;

  /** Create a new conversation */
  create(title?: string): Promise<{ conversation: Conversation }>;

  /** Get a conversation with its messages */
  get(conversationId: string, options?: ConversationGetOptions): Promise<ConversationGetResponse>;

  /** Update conversation metadata (title, pinned, archived) */
  update(
    conversationId: string,
    updates: { title?: string; pinned?: boolean; archived?: boolean }
  ): Promise<{ success: boolean; conversation: Conversation }>;

  /** Delete a conversation and all its messages */
  delete(conversationId: string): Promise<{ success: boolean }>;

  /** Send a message and get AI response */
  send(
    conversationId: string,
    query: string,
    options?: ConversationSendOptions
  ): Promise<ConversationSendResponse>;

  /** Generate or regenerate title for a conversation */
  generateTitle(conversationId: string, force?: boolean): Promise<{ title: string; generated: boolean }>;
}

export interface TraceAPI {
  /** Ping the Electron main process */
  ping(): Promise<string>;

  /** Current platform (darwin, win32, linux) */
  platform: string;

  /** Get app version */
  getVersion(): Promise<string>;

  /** Python backend methods */
  python: PythonAPI;

  /** Permission management */
  permissions: PermissionsAPI;

  /** Chat/query API */
  chat: ChatAPI;

  /** Dashboard API */
  dashboard: DashboardAPI;

  /** Weekly digest API */
  digest: DigestAPI;

  /** Pattern detection API */
  patterns: PatternsAPI;

  /** Notes API */
  notes: NotesAPI;

  /** Settings API */
  settings: SettingsAPI;

  /** Export API */
  export: ExportAPI;

  /** Graph API */
  graph: GraphAPI;

  /** Spotlight API */
  spotlight: SpotlightAPI;

  /** Blocklist API */
  blocklist: BlocklistAPI;

  /** Appearance API */
  appearance: AppearanceAPI;

  /** Window control */
  window: WindowAPI;

  /** Global shortcuts */
  shortcuts: ShortcutsAPI;

  /** Tray menu events */
  tray: TrayAPI;

  /** Shell utilities */
  shell: ShellAPI;

  /** Installed apps (macOS) */
  apps: AppsAPI;

  /** Auto-updates API */
  updates: UpdatesAPI;

  /** User memory API */
  memory: MemoryAPI;

  /** Onboarding chat API */
  onboarding: OnboardingAPI;

  /** Conversations API */
  conversations: ConversationsAPI;
}

declare global {
  interface Window {
    traceAPI: TraceAPI;
  }
}
