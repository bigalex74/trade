# Complete MCP Tools Documentation

Generated: 14 April 2026

---

## Table of Contents

1. [grafana-mcp](#1-grafana-mcp)
2. [firecrawl](#2-firecrawl)
3. [n8n-mcp](#3-n8n-mcp)
4. [lightrag-mcp](#4-lightrag-mcp)
5. [github](#5-github)
6. [filesystem](#6-filesystem)
7. [memory](#7-memory)
8. [context7](#8-context7)
9. [playwright](#9-playwright)
10. [docker](#10-docker)
11. [google-workspace](#11-google-workspace)
12. [postgresql](#12-postgresql)
13. [searxng](#13-searxng)
14. [puppeteer](#14-puppeteer)

---

## 1. grafana-mcp

### Overview
Grafana MCP server provides tools for managing Grafana dashboards, alerts, incidents, datasources, logs, traces, and profiles.

### Tools

#### Alerting & Rules
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `alerting_manage_rules` | Manage alert rules (list, get, create, update, delete, versions) | `operation` | `rule_uid`, `title`, `folder_uid`, `rule_group`, `condition`, `data`, `for`, `labels`, `annotations`, `no_data_state`, `exec_err_state`, `keep_firing_for`, `is_paused`, `notification_settings`, `record`, `org_id`, `disable_provenance`, `limit_alerts`, `search_rule_name`, `search_folder`, `states`, `rule_type`, `rule_limit`, `datasource_uid`, `matchers`, `label_selecters` |
| `alerting_manage_routing` | Manage notification policies, contact points, time intervals | `operation` | `contact_point_title`, `datasource_uid`, `limit`, `name`, `time_interval_name` |

**Operations for alerting_manage_rules:** `list`, `get`, `versions`, `create`, `update`, `delete`

**Operations for alerting_manage_routing:** `get_notification_policies`, `get_contact_points`, `get_contact_point`, `get_time_intervals`, `get_time_interval`

#### Dashboards
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_dashboard_by_uid` | Get complete dashboard JSON | `uid` | - |
| `get_dashboard_summary` | Get compact dashboard summary | `uid` | - |
| `get_dashboard_property` | Get specific dashboard parts via JSONPath | `uid`, `jsonPath` | - |
| `get_dashboard_panel_queries` | Get panel queries from dashboard | `uid` | `panelId`, `variables` |
| `update_dashboard` | Create or update dashboard | (one of: `dashboard` OR `uid`+`operations`) | `folderUid`, `message`, `overwrite`, `userId` |
| `search_dashboards` | Search dashboards by query | - | `query`, `limit`, `page` |

#### Panels
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_panel_image` | Render panel/dashboard as PNG | `dashboardUid` | `panelId`, `width`, `height`, `theme`, `scale`, `timeRange`, `variables`, `timeout` |
| `generate_deeplink` | Generate deeplink URLs | `resourceType` | `dashboardUid`, `panelId`, `datasourceUid`, `queries`, `timeRange`, `queryParams` |

#### Folders
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_folder` | Create Grafana folder | `title` | `uid`, `parentUid` |
| `search_folders` | Search folders | `query` | - |

#### Annotations
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_annotations` | Fetch annotations | - | `DashboardUID`, `PanelID`, `Tags`, `Type`, `From`, `To`, `Limit`, `AlertUID`, `AlertID`, `UserID`, `MatchAny` |
| `create_annotation` | Create annotation | - | `dashboardUID`, `dashboardId`, `panelId`, `text`, `time`, `timeEnd`, `tags`, `format`, `what`, `when`, `data`, `graphiteData` |
| `update_annotation` | Update annotation | - | `id`, `text`, `time`, `timeEnd`, `tags`, `data` |
| `get_annotation_tags` | Get annotation tags | - | `tag`, `limit` |

#### Datasources
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_datasources` | List all datasources | - | `type`, `limit`, `offset` |
| `get_datasource` | Get datasource details | (one of: `uid` OR `name`) | - |

#### Prometheus Queries
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_prometheus_metric_names` | Discover available metrics | `datasourceUid` | `regex`, `limit`, `page`, `projectName` |
| `list_prometheus_label_values` | Get label values for filtering | `datasourceUid`, `labelName` | `matches`, `startRfc3339`, `endRfc3339`, `limit`, `projectName` |
| `list_prometheus_label_names` | List label names | `datasourceUid` | `matches`, `startRfc3339`, `endRfc3339`, `limit`, `projectName` |
| `list_prometheus_metric_metadata` | List metric metadata | `datasourceUid` | `metric`, `limit`, `limitPerMetric`, `projectName` |
| `query_prometheus` | Execute PromQL query | `datasourceUid`, `expr`, `endTime` | `startTime`, `stepSeconds`, `queryType`, `projectName` |
| `query_prometheus_histogram` | Query histogram percentiles | `datasourceUid`, `metric`, `percentile` | `labels`, `startTime`, `endTime`, `stepSeconds`, `rateInterval`, `projectName` |

#### Loki Queries
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_loki_label_names` | List Loki label names | `datasourceUid` | `startRfc3339`, `endRfc3339` |
| `list_loki_label_values` | Get Loki label values | `datasourceUid`, `labelName` | `startRfc3339`, `endRfc3339` |
| `query_loki_logs` | Execute LogQL query | `datasourceUid`, `logql` | `startRfc3339`, `endRfc3339`, `limit`, `direction`, `queryType`, `stepSeconds` |
| `query_loki_stats` | Get log stream statistics | `datasourceUid`, `logql` | `startRfc3339`, `endRfc3339` |
| `query_loki_patterns` | Get detected log patterns | `datasourceUid`, `logql` | `startRfc3339`, `endRfc3339`, `step` |

#### Pyroscope (Profiling)
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_pyroscope_profile_types` | List available profile types | `data_source_uid` | `start_rfc_3339`, `end_rfc_3339` |
| `list_pyroscope_label_names` | List Pyroscope label names | `data_source_uid` | `matchers`, `start_rfc_3339`, `end_rfc_3339` |
| `list_pyroscope_label_values` | Get Pyroscope label values | `data_source_uid`, `name` | `matchers`, `start_rfc_3339`, `end_rfc_3339` |
| `query_pyroscope` | Query profiles/metrics | `data_source_uid`, `profile_type` | `matchers`, `start_rfc_3339`, `end_rfc_3339`, `query_type`, `group_by`, `step`, `max_node_depth` |

#### Incidents (Grafana OnCall)
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_incidents` | List incidents | - | `status`, `drill`, `limit` |
| `get_incident` | Get incident details | `id` | - |
| `create_incident` | Create new incident | `title`, `severity`, `roomPrefix` | `status`, `labels`, `attachUrl`, `attachCaption`, `isDrill` |
| `add_activity_to_incident` | Add note to incident timeline | `incidentId`, `body` | `eventTime` |

#### Alert Groups (OnCall)
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_alert_groups` | List alert groups | - | `id`, `routeId`, `integrationId`, `state`, `teamId`, `startedAt`, `labels`, `name`, `page` |
| `get_alert_group` | Get alert group details | `alertGroupId` | - |

#### OnCall Schedules & Users
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_oncall_teams` | List OnCall teams | - | `page` |
| `list_oncall_users` | List OnCall users | - | `userId`, `username`, `page` |
| `list_oncall_schedules` | List schedules | - | `scheduleId`, `teamId`, `page` |
| `get_oncall_shift` | Get shift details | `shiftId` | - |
| `get_current_oncall_users` | Get current on-call users | `scheduleId` | - |

#### Sift Investigations
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `list_sift_investigations` | List investigations | - | `limit` |
| `get_sift_investigation` | Get investigation details | `id` | - |
| `get_sift_analysis` | Get analysis from investigation | `investigationId`, `analysisId` | - |
| `find_error_pattern_logs` | Find elevated error patterns | `name`, `labels` | `start`, `end` |
| `find_slow_requests` | Find slow requests in Tempo | `name`, `labels` | `start`, `end` |

#### Assertions
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_assertions` | Get assertion summary | `startTime`, `endTime` | `entityType`, `entityName`, `env`, `site`, `namespace` |

**When to use:** Monitoring, alerting, incident management, log analysis, performance profiling, dashboard management, root cause analysis.

---

## 2. firecrawl

### Overview
Firecrawl provides web scraping, crawling, mapping, search, and browser automation tools.

### Tools

| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `firecrawl_scrape` | Scrape single URL content | `url` | `formats`, `onlyMainContent`, `includeTags`, `excludeTags`, `waitFor`, `maxAge`, `jsonOptions`, `screenshotOptions`, `mobile`, `skipTlsVerification`, `storeInCache`, `removeBase64Images`, `proxy`, `location`, `actions`, `parsers`, `pdfOptions`, `zeroDataRetention` |
| `firecrawl_map` | Discover URLs on a website | `url` | `search`, `limit`, `ignoreQueryParameters`, `includeSubdomains`, `sitemap` |
| `firecrawl_search` | Web search with optional extraction | `query` | `limit`, `sources`, `scrapeOptions`, `lang`, `country`, `location`, `tbs`, `filter`, `enterprise` |
| `firecrawl_crawl` | Start website crawl job | `url` | `limit`, `maxDiscoveryDepth`, `maxConcurrency`, `allowExternalLinks`, `allowSubdomains`, `deduplicateSimilarURLs`, `ignoreQueryParameters`, `includePaths`, `excludePaths`, `delay`, `webhook`, `webhookHeaders`, `prompt`, `scrapeOptions`, `sitemap` |
| `firecrawl_check_crawl_status` | Check crawl job status | `id` | - |
| `firecrawl_extract` | Extract structured data from pages | `urls` | `prompt`, `schema`, `allowExternalLinks`, `enableWebSearch`, `includeSubdomains` |
| `firecrawl_agent` | Autonomous web research agent | `prompt` | `urls`, `schema` |
| `firecrawl_agent_status` | Check agent job status | `id` | - |
| `firecrawl_browser_create` | Create CDP browser session | - | `ttl`, `activityTtl`, `streamWebView`, `profile` |
| `firecrawl_browser_execute` | Execute code in browser | `sessionId`, `code` | `language` |
| `firecrawl_browser_delete` | Destroy browser session | `sessionId` | - |
| `firecrawl_browser_list` | List browser sessions | - | `status` |

**Format Selection for firecrawl_scrape:**
- Use `formats: ["json"]` with `jsonOptions` for structured data extraction
- Use `formats: ["markdown"]` for full page content
- Use `formats: ["branding"]` for brand identity extraction

**Common Workflows:**
1. **Discover then scrape:** `firecrawl_map` -> `firecrawl_scrape` on specific URL
2. **Web research:** `firecrawl_search` -> `firecrawl_scrape` on relevant results
3. **Full site extraction:** `firecrawl_crawl` -> `firecrawl_check_crawl_status` until complete
4. **Autonomous research:** `firecrawl_agent` -> poll `firecrawl_agent_status` every 15-30s
5. **Browser automation:** `firecrawl_browser_create` -> `firecrawl_browser_execute` (multiple) -> `firecrawl_browser_delete`

**When to use:** Web scraping, data extraction, web research, crawling sites, browser automation, SPA content extraction.

---

## 3. n8n-mcp

### Overview
n8n MCP server provides comprehensive workflow automation tools for n8n.

### System & Health
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `n8n_health_check` | Check n8n instance health | - | `mode`, `verbose` |
| `n8n_audit_instance` | Security audit of instance | - | `categories`, `customChecks`, `includeCustomScan`, `daysAbandonedWorkflow` |

### Node Discovery & Configuration
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `search_nodes` | Search nodes by query | `query` | `limit`, `mode`, `includeExamples`, `includeOperations`, `source` |
| `get_node` | Get node info/docs | `nodeType` | `mode`, `detail`, `propertyQuery`, `maxPropertyResults`, `fromVersion`, `toVersion`, `includeExamples`, `includeTypeInfo` |
| `validate_node` | Validate node config | `nodeType`, `config` | `mode`, `profile` |
| `tools_documentation` | Get tool documentation | - | `topic`, `depth` |

### Templates
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `search_templates` | Search workflow templates | - | `query`, `searchMode`, `limit`, `offset`, `fields`, `nodeTypes`, `task`, `category`, `complexity`, `requiredService`, `targetAudience`, `minSetupMinutes`, `maxSetupMinutes` |
| `get_template` | Get template by ID | `templateId` | `mode` |
| `n8n_deploy_template` | Deploy template to instance | `templateId` | `name`, `autoFix`, `autoUpgradeVersions`, `stripCredentials` |

### Workflow CRUD
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `n8n_create_workflow` | Create workflow | `name`, `nodes`, `connections` | `settings`, `projectId` |
| `n8n_get_workflow` | Get workflow by ID | `id` | `mode` |
| `n8n_update_full_workflow` | Full workflow update | `id` | `name`, `nodes`, `connections`, `settings` |
| `n8n_update_partial_workflow` | Incremental update | `id`, `operations` | `validateOnly`, `continueOnError` |
| `n8n_delete_workflow` | Delete workflow | `id` | - |
| `n8n_list_workflows` | List workflows | - | `limit`, `cursor`, `active`, `tags`, `projectId`, `excludePinnedData` |

### Validation & Testing
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `validate_workflow` | Validate workflow structure | `workflow` | `options` |
| `n8n_validate_workflow` | Validate workflow by ID | `id` | `options` |
| `n8n_autofix_workflow` | Auto-fix validation errors | `id` | `applyFixes`, `confidenceThreshold`, `fixTypes`, `maxFixes` |
| `n8n_test_workflow` | Test/trigger workflow | `workflowId` | `triggerType`, `data`, `waitForResponse`, `webhookPath`, `httpMethod`, `message`, `sessionId`, `headers`, `timeout` |

### Execution Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `n8n_executions` | Manage executions | `action` | `id`, `mode`, `workflowId`, `status`, `limit`, `cursor`, `includeData`, `nodeNames`, `itemsLimit`, `errorItemsLimit`, `includeInputData`, `includeStackTrace`, `includeExecutionPath`, `fetchWorkflow` |
| `n8n_workflow_versions` | Manage versions | `mode` | `workflowId`, `versionId`, `limit`, `validateBefore`, `maxVersions`, `deleteAll`, `confirmTruncate` |

### Data & Credentials
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `n8n_manage_datatable` | Manage data tables | `action` | `name`, `tableId`, `columns`, `data`, `filter`, `search`, `limit`, `cursor`, `sortBy`, `returnData`, `returnType`, `dryRun` |
| `n8n_manage_credentials` | Manage credentials | `action` | `id`, `name`, `type`, `data` |

### AI Generation
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `n8n_generate_workflow` | Generate workflow from description | `description` | `deploy_id`, `skip_cache`, `confirm_deploy` |

**Partial Workflow Operations (18 types):**
- Node: `addNode`, `removeNode`, `updateNode`, `patchNodeField`, `moveNode`, `enableNode`, `disableNode`
- Connection: `addConnection`, `removeConnection`, `rewireConnection`, `cleanStaleConnections`, `replaceConnections`
- Metadata: `updateSettings`, `updateName`, `addTag`, `removeTag`
- Activation: `activateWorkflow`, `deactivateWorkflow`
- Project: `transferWorkflow`

**When to use:** Workflow creation, automation, node configuration, template deployment, instance management, security auditing.

---

## 4. lightrag-mcp

### Overview
LightRAG provides knowledge graph storage, document indexing, and semantic search capabilities.

### Document Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `insert_document` | Add text to storage | `text` | - |
| `insert_file` | Add document from file | `file_path` | - |
| `upload_document` | Upload and index file | `file_path` | - |
| `insert_batch` | Batch add documents from directory | `directory_path` | `recursive`, `depth`, `include_only`, `ignore_files`, `ignore_directories` |
| `get_documents` | List all uploaded documents | - | - |
| `scan_for_new_documents` | Scan /inputs for new docs | - | - |

### Pipeline & Health
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_pipeline_status` | Get processing status | - | - |
| `check_lightrag_health` | Check API status | - | - |

### Knowledge Graph
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_graph_labels` | Get entity/relationship types | - | - |
| `create_entities` | Create entities | `entities` | - |
| `edit_entities` | Edit entities | `entities` | - |
| `delete_by_entities` | Delete entities | `entity_names` | - |
| `delete_by_doc_ids` | Delete by document IDs | `doc_ids` | - |
| `create_relations` | Create relationships | `relations` | - |
| `edit_relations` | Edit relationships | `relations` | - |
| `merge_entities` | Merge entities | `source_entities`, `target_entity` | `merge_strategy` |

### Query
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `query_document` | Semantic search query | `query` | `mode`, `top_k`, `response_type`, `only_need_context`, `only_need_prompt`, `hl_keywords`, `ll_keywords`, `max_token_for_text_unit`, `max_token_for_local_context`, `max_token_for_global_context`, `history_turns` |

**Query Modes:** `mix`, `semantic`, `keyword`, `global`, `hybrid`, `local`, `naive`

**When to use:** Knowledge base management, semantic search, document indexing, graph-based knowledge storage, RAG applications.

---

## 5. github

### Overview
GitHub MCP server provides repository, issue, pull request, and file management tools.

### Repository Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_repository` | Create new repo | `name` | `description`, `private`, `autoInit` |
| `search_repositories` | Search repos | `query` | `page`, `perPage` |
| `fork_repository` | Fork a repository | `owner`, `repo` | `organization` |
| `create_branch` | Create new branch | `owner`, `repo`, `branch` | `from_branch` |

### File Operations
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `get_file_contents` | Get file/directory contents | `owner`, `repo`, `path` | `branch` |
| `create_or_update_file` | Create/update single file | `owner`, `repo`, `path`, `content`, `message`, `branch` | `sha` |
| `push_files` | Push multiple files | `owner`, `repo`, `branch`, `files`, `message` | - |

### Issues
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_issue` | Create new issue | `owner`, `repo`, `title` | `body`, `labels`, `assignees`, `milestone` |
| `list_issues` | List issues | `owner`, `repo` | `state`, `labels`, `sort`, `direction`, `since`, `page`, `per_page` |
| `get_issue` | Get issue details | `owner`, `repo`, `issue_number` | - |
| `update_issue` | Update issue | `owner`, `repo`, `issue_number` | `state`, `title`, `body`, `labels`, `assignees`, `milestone` |
| `add_issue_comment` | Add comment to issue | `owner`, `repo`, `issue_number`, `body` | - |
| `search_issues` | Search issues/PRs | `q` | `page`, `per_page`, `sort`, `order` |

### Pull Requests
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_pull_request` | Create PR | `owner`, `repo`, `title`, `head`, `base` | `body`, `draft`, `maintainer_can_modify` |
| `list_pull_requests` | List PRs | `owner`, `repo` | `state`, `head`, `base`, `sort`, `direction`, `page`, `per_page` |
| `get_pull_request` | Get PR details | `owner`, `repo`, `pull_number` | - |
| `get_pull_request_files` | Get changed files in PR | `owner`, `repo`, `pull_number` | - |
| `get_pull_request_status` | Get PR status checks | `owner`, `repo`, `pull_number` | - |
| `get_pull_request_comments` | Get PR review comments | `owner`, `repo`, `pull_number` | - |
| `get_pull_request_reviews` | Get PR reviews | `owner`, `repo`, `pull_number` | - |
| `create_pull_request_review` | Create PR review | `owner`, `repo`, `pull_number`, `body`, `event` | `commit_id`, `comments` |
| `merge_pull_request` | Merge PR | `owner`, `repo`, `pull_number` | `commit_title`, `commit_message`, `merge_method` |
| `update_pull_request_branch` | Update PR branch | `owner`, `repo`, `pull_number` | `expected_head_sha` |

### Search
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `search_code` | Search code | `q` | `page`, `per_page`, `order` |
| `search_users` | Search users | `q` | `page`, `per_page`, `sort`, `order` |
| `list_commits` | List commits | `owner`, `repo` | `sha`, `page`, `perPage` |

**When to use:** Repository management, code search, issue tracking, pull request workflows, file management, CI/CD integration.

---

## 6. filesystem

### Overview
Filesystem MCP server provides file and directory operations within allowed directories.

### File Operations
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `read_file` | Read file contents | `path` | `head`, `tail` |
| `read_text_file` | Read file as text | `path` | `head`, `tail` |
| `read_media_file` | Read image/audio file | `path` | - |
| `read_multiple_files` | Read multiple files | `paths` | - |
| `write_file` | Create/overwrite file | `path`, `content` | - |
| `edit_file` | Make line-based edits | `path`, `edits` | `dryRun` |

### Directory Operations
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_directory` | Create directory | `path` | - |
| `list_directory` | List directory contents | `path` | - |
| `list_directory_with_sizes` | List with sizes | `path` | `sortBy` |
| `directory_tree` | Get recursive tree view | `path` | `excludePatterns` |
| `list_allowed_directories` | List allowed directories | - | - |

### File Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `move_file` | Move/rename file | `source`, `destination` | - |
| `search_files` | Search files by pattern | `path`, `pattern` | `excludePatterns` |
| `get_file_info` | Get file metadata | `path` | - |

**When to use:** File reading/writing, directory management, file searching, code editing, project organization.

---

## 7. memory

### Overview
Memory MCP server provides a knowledge graph for storing and retrieving structured information.

### Entity Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_entities` | Create entities | `entities` | - |
| `add_observations` | Add observations to entities | `observations` | - |
| `delete_observations` | Delete observations | `deletions` | - |
| `delete_entities` | Delete entities | `entityNames` | - |

### Relation Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `create_relations` | Create relations | `relations` | - |
| `delete_relations` | Delete relations | `relations` | - |

### Query
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `read_graph` | Read entire graph | - | - |
| `search_nodes` | Search nodes by query | `query` | - |
| `open_nodes` | Get specific nodes | `names` | - |

**Entity Structure:** `{name: string, entityType: string, observations: string[]}`
**Relation Structure:** `{from: string, to: string, relationType: string}`

**When to use:** Persistent memory across sessions, knowledge storage, fact tracking, relationship mapping.

---

## 8. context7

### Overview
Context7 provides up-to-date library documentation and code examples.

### Tools
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `resolve-library-id` | Resolve library name to Context7 ID | `query`, `libraryName` | - |
| `query-docs` | Query library documentation | `libraryId`, `query` | - |

**Workflow:**
1. Call `resolve-library-id` with library name -> get library ID (e.g., `/vercel/next.js`)
2. Call `query-docs` with library ID and question -> get documentation

**When to use:** Library documentation lookup, API reference, code examples, framework setup guidance.

---

## 9. playwright

### Overview
Playwright MCP server provides browser automation and HTTP request tools.

### Browser Navigation
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_navigate` | Navigate to URL | `url` | `browserType`, `headless`, `width`, `height`, `waitUntil`, `timeout` |
| `playwright_go_back` | Navigate back | - | - |
| `playwright_go_forward` | Navigate forward | - | - |
| `playwright_close` | Close browser | - | - |
| `playwright_resize` | Resize viewport | - | `width`, `height`, `device`, `orientation` |
| `playwright_custom_user_agent` | Set custom user agent | `userAgent` | - |

### Page Interaction
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_click` | Click element | `selector` | - |
| `playwright_fill` | Fill input field | `selector`, `value` | - |
| `playwright_select` | Select from dropdown | `selector`, `value` | - |
| `playwright_hover` | Hover element | `selector` | - |
| `playwright_press_key` | Press keyboard key | `key` | `selector` |
| `playwright_drag` | Drag element | `sourceSelector`, `targetSelector` | - |
| `playwright_upload_file` | Upload file | `selector`, `filePath` | - |

### Iframe Interaction
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_iframe_click` | Click in iframe | `iframeSelector`, `selector` | - |
| `playwright_iframe_fill` | Fill in iframe | `iframeSelector`, `selector`, `value` | - |

### Page Content
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_screenshot` | Take screenshot | `name` | `selector`, `width`, `height`, `fullPage`, `savePng`, `storeBase64`, `downloadsDir` |
| `playwright_get_visible_text` | Get page text | - | - |
| `playwright_get_visible_html` | Get page HTML | - | `selector`, `cleanHtml`, `minify`, `maxLength`, `removeScripts`, `removeStyles`, `removeMeta`, `removeComments` |
| `playwright_evaluate` | Execute JavaScript | `script` | - |
| `playwright_console_logs` | Get console logs | - | `type`, `search`, `limit`, `clear` |

### Tab Management
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_click_and_switch_tab` | Click link, switch tab | `selector` | - |

### HTTP Requests
| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `playwright_get` | HTTP GET request | `url` | `headers`, `token` |
| `playwright_post` | HTTP POST request | `url`, `value` | `headers`, `token` |
| `playwright_put` | HTTP PUT request | `url`, `value` | `headers`, `token` |
| `playwright_patch` | HTTP PATCH request | `url`, `value` | `headers`, `token` |
| `playwright_delete` | HTTP DELETE request | `url` | `headers`, `token` |
| `playwright_expect_response` | Wait for HTTP response | `id`, `url` | - |
| `playwright_assert_response` | Assert HTTP response | `id` | `value` |

### PDF
| Tool | Description | Required Params | Optional