# MCP Tools Complete Documentation

Generated: 2026-04-14

---

## Table of Contents
1. [n8n-mcp](#1-n8n-mcp)
2. [grafana-mcp](#2-grafana-mcp)
3. [firecrawl](#3-firecrawl)
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

## 1. n8n-mcp

**Purpose:** Complete n8n workflow management, node configuration, validation, and deployment.

### Tools

#### tools_documentation
- **Description:** Meta-documentation tool. Returns docs for any n8n MCP tool or guide.
- **Parameters:**
  - `topic` (optional, string): Tool name or guide topic (e.g., "search_nodes", "javascript_code_node_guide")
  - `depth` (optional, string): "essentials" (default) or "full"
- **When to use:** Starting point for discovering n8n MCP capabilities.

#### n8n_health_check
- **Description:** Check n8n instance health, API connectivity, version status, performance metrics.
- **Parameters:**
  - `mode` (optional, string): "status" (default) or "diagnostic"
  - `verbose` (optional, boolean): Include extra details in diagnostic mode
- **When to use:** Verify n8n instance is running and accessible before any operations.

#### n8n_audit_instance
- **Description:** Security audit combining n8n built-in audit with deep workflow scanning (hardcoded secrets, unauthenticated webhooks, error handling gaps, data retention).
- **Parameters:**
  - `categories` (optional, array): ["credentials", "database", "nodes", "instance", "filesystem"]
  - `customChecks` (optional, array): ["hardcoded_secrets", "unauthenticated_webhooks", "error_handling", "data_retention"]
  - `daysAbandonedWorkflow` (optional, number): Days threshold for abandoned workflow detection (default: 90)
  - `includeCustomScan` (optional, boolean): Run deep workflow scanning (default: true)
- **When to use:** Security review, compliance checks, pre-deployment audits.

#### search_nodes
- **Description:** Text search across 800+ node names and descriptions. Returns most relevant nodes first.
- **Parameters:**
  - `query` (required, string): Keyword like "webhook", "database"
  - `limit` (optional, number): Max results (default: 20)
  - `source` (optional, string): "all" (default), "core", "community", "verified"
  - `includeExamples` (optional, boolean): Include real-world config examples from templates (default: false)
  - `includeOperations` (optional, boolean): Include resource/operation tree per node (default: false)
  - `mode` (optional, string): "OR" (any word, default), "AND" (all words), "FUZZY" (typo-tolerant)
- **When to use:** Finding the right node for a task, discovering available integrations.

#### get_node
- **Description:** Unified node information with progressive detail levels and multiple modes.
- **Parameters:**
  - `nodeType` (required, string): e.g., "nodes-base.httpRequest"
  - `mode` (optional, string): "info" (default), "docs", "search_properties", "versions", "compare", "breaking", "migrations"
  - `detail` (optional, string): "minimal", "standard" (default), "full"
  - `propertyQuery` (optional, string): Search term for property search mode
  - `maxPropertyResults` (optional, number): Max results for property search (default: 20)
  - `includeTypeInfo` (optional, boolean): Include type structure metadata (default: false)
  - `includeExamples` (optional, boolean): Include real-world examples (default: false)
  - `fromVersion` (optional, string): Source version for compare/breaking/migrations
  - `toVersion` (optional, string): Target version for compare mode
- **When to use:** Understanding node configuration, finding specific properties, version migration.

#### validate_node
- **Description:** Validate n8n node configuration for correctness.
- **Parameters:**
  - `nodeType` (required, string): e.g., "nodes-base.slack"
  - `config` (required, object): Configuration object to validate
  - `mode` (optional, string): "full" (default) or "minimal"
  - `profile` (optional, string): "ai-friendly" (default), "minimal", "runtime", "strict"
- **When to use:** Before creating/updating nodes, debugging configuration issues.

#### validate_workflow
- **Description:** Full workflow validation: structure, connections, expressions, AI tools.
- **Parameters:**
  - `workflow` (required, object): {nodes: [array], connections: {object}}
  - `options` (optional, object):
    - `validateNodes` (boolean, default: true)
    - `validateConnections` (boolean, default: true)
    - `validateExpressions` (boolean, default: true)
    - `profile` (string): "minimal", "runtime" (default), "ai-friendly", "strict"
- **When to use:** Before deploying workflows, debugging execution errors.

#### get_template
- **Description:** Get workflow template by ID from n8n.io.
- **Parameters:**
  - `templateId` (required, number): Template ID
  - `mode` (optional, string): "full" (default), "nodes_only", "structure"
- **When to use:** Retrieving specific template for deployment.

#### search_templates
- **Description:** Search 2,700+ workflow templates with multiple modes.
- **Parameters:**
  - `searchMode` (optional, string): "keyword" (default), "by_nodes", "by_task", "by_metadata", "patterns"
  - `query` (optional, string): Keyword for searchMode="keyword"
  - `nodeTypes` (optional, array): Node types for searchMode="by_nodes"
  - `task` (optional, string): Task type for searchMode="by_task" (ai_automation, data_sync, webhook_processing, etc.)
  - `limit` (optional, number): Max results (default: 20, max: 100)
  - `offset` (optional, number): Pagination offset (default: 0)
  - `fields` (optional, array): Fields to include in response
  - `category`, `complexity`, `targetAudience`, `requiredService`, `minSetupMinutes`, `maxSetupMinutes` (optional): For searchMode="by_metadata"
- **When to use:** Finding starter templates, discovering workflow patterns.

#### n8n_create_workflow
- **Description:** Create a new workflow (inactive by default).
- **Parameters:**
  - `name` (required, string): Workflow name
  - `nodes` (required, array): Array of node objects (each with id, name, type, typeVersion, position, parameters)
  - `connections` (required, object): Workflow connections object
  - `settings` (optional, object): Workflow settings (executionOrder, timezone, error handling, etc.)
  - `projectId` (optional, string): Project ID (enterprise feature)
- **When to use:** Building new workflows programmatically.

#### n8n_get_workflow
- **Description:** Get workflow by ID with configurable detail level.
- **Parameters:**
  - `id` (required, string): Workflow ID
  - `mode` (optional, string): "full" (default), "details", "structure", "minimal"
- **When to use:** Reading workflow configuration, checking workflow state.

#### n8n_update_full_workflow
- **Description:** Full workflow update (requires complete nodes and connections).
- **Parameters:**
  - `id` (required, string): Workflow ID
  - `name` (optional, string): New workflow name
  - `nodes` (optional, array): Complete array of workflow nodes
  - `connections` (optional, object): Complete connections object
  - `settings` (optional, object): Workflow settings
- **When to use:** Complete workflow replacement. For incremental changes, use n8n_update_partial_workflow.

#### n8n_update_partial_workflow
- **Description:** Update workflow incrementally with diff operations.
- **Parameters:**
  - `id` (required, string): Workflow ID
  - `operations` (required, array): Array of diff operations (addNode, removeNode, updateNode, patchNodeField, moveNode, enable/disableNode, addConnection, removeConnection, rewireConnection, cleanStaleConnections, replaceConnections, updateSettings, updateName, add/removeTag, activateWorkflow, deactivateWorkflow, transferWorkflow)
  - `continueOnError` (optional, boolean): Apply valid operations even if some fail (default: false)
  - `validateOnly` (optional, boolean): Only validate without applying (default: false)
- **When to use:** Making targeted changes to existing workflows without full replacement.

#### n8n_delete_workflow
- **Description:** Permanently delete a workflow (cannot be undone).
- **Parameters:**
  - `id` (required, string): Workflow ID
- **When to use:** Removing unused or test workflows.

#### n8n_list_workflows
- **Description:** List workflows with minimal metadata (no nodes/connections).
- **Parameters:**
  - `active` (optional, boolean): Filter by active status
  - `limit` (optional, number): Max results (1-100, default: 100)
  - `cursor` (optional, string): Pagination cursor
  - `tags` (optional, array): Filter by tags
  - `projectId` (optional, string): Filter by project ID
  - `excludePinnedData` (optional, boolean, default: true)
- **When to use:** Inventory workflows, find specific workflow by name/tags.

#### n8n_validate_workflow
- **Description:** Validate workflow from n8n instance by ID.
- **Parameters:**
  - `id` (required, string): Workflow ID
  - `options` (optional, object): validateNodes, validateConnections, validateExpressions, profile
- **When to use:** Checking workflow health before execution or deployment.

#### n8n_autofix_workflow
- **Description:** Automatically fix common workflow validation errors.
- **Parameters:**
  - `id` (required, string): Workflow ID
  - `applyFixes` (optional, boolean): Apply fixes to workflow (default: false - preview mode)
  - `confidenceThreshold` (optional, string): "high", "medium" (default), "low"
  - `maxFixes` (optional, number): Maximum fixes (default: 50)
  - `fixTypes` (optional, array): Specific fix types to apply
- **When to use:** Quick fixes for expression formats, typeVersions, connection issues.

#### n8n_test_workflow
- **Description:** Test/trigger workflow execution (webhook/form/chat triggers).
- **Parameters:**
  - `workflowId` (required, string): Workflow ID
  - `triggerType` (optional, string): "webhook", "form", "chat" (auto-detected)
  - `data` (optional, object): Input data/payload
  - `waitForResponse` (optional, boolean, default: true)
  - `httpMethod` (optional, string): "GET", "POST", "PUT", "DELETE"
  - `webhookPath` (optional, string): Override webhook path
  - `message` (optional, string): Chat message
  - `sessionId` (optional, string): Chat session ID
  - `headers` (optional, object): Custom HTTP headers
  - `timeout` (optional, number): Timeout in ms (default: 120000)
- **When to use:** Testing workflows, triggering webhook-based workflows.

#### n8n_executions
- **Description:** Manage workflow executions (get details, list, delete).
- **Parameters:**
  - `action` (required, string): "get", "list", "delete"
  - `id` (optional, string): Execution ID (required for get/delete)
  - `workflowId` (optional, string): Filter by workflow ID (for list)
  - `mode` (optional, string): "preview", "summary" (default), "filtered", "full", "error"
  - `status` (optional, string): "success", "error", "waiting" (for list)
  - `limit`, `cursor` (optional): Pagination (for list)
  - `includeData` (optional, boolean, default: false, for list)
  - Many optional parameters for detailed control
- **When to use:** Debugging executions, monitoring workflow runs, cleaning up execution history.

#### n8n_workflow_versions
- **Description:** Manage workflow version history, rollback, and cleanup.
- **Parameters:**
  - `mode` (required, string): "list", "get", "rollback", "delete", "prune", "truncate"
  - `workflowId` (optional, string): Workflow ID (required for most modes)
  - `versionId` (optional, number): Version ID (required for get/delete)
  - `limit` (optional, number, default: 10): For list mode
  - `maxVersions` (optional, number, default: 10): For prune mode
  - `validateBefore` (optional, boolean, default: true): For rollback
  - `confirmTruncate` (optional, boolean, default: false): Required for truncate
- **When to use:** Rolling back bad changes, version history audit, cleanup.

#### n8n_deploy_template
- **Description:** Deploy template from n8n.io directly to n8n instance.
- **Parameters:**
  - `templateId` (required, number): Template ID from n8n.io
  - `name` (optional, string): Custom workflow name
  - `autoFix` (optional, boolean, default: true): Auto-apply fixes after deployment
  - `autoUpgradeVersions` (optional, boolean, default: true): Upgrade node typeVersions
  - `stripCredentials` (optional, boolean, default: true): Remove credential references
- **When to use:** Quick deployment of community templates.

#### n8n_manage_datatable
- **Description:** Manage n8n data tables and rows.
- **Parameters:**
  - `action` (required, string): "createTable", "listTables", "getTable", "updateTable", "deleteTable", "getRows", "insertRows", "updateRows", "upsertRows", "deleteRows"
  - `tableId` (optional, string): Data table ID (required for most actions)
  - `name` (optional, string): Table name
  - `columns` (optional, array): Column definitions (for createTable)
  - `data` (optional, object/array): Row data
  - `filter` (optional, object): Filter criteria
  - `limit`, `cursor` (optional): Pagination
  - `dryRun` (optional, boolean): Preview without applying
- **When to use:** Managing persistent data storage in n8n.

#### n8n_generate_workflow
- **Description:** Generate workflow from natural language using AI.
- **Parameters:**
  - `description` (required, string): Workflow description with triggers, services, logic
  - `deploy_id` (optional, string): Proposal ID to deploy
  - `confirm_deploy` (optional, boolean): Deploy previously generated workflow
  - `skip_cache` (optional, boolean): Generate fresh workflow from scratch
- **When to use:** AI-assisted workflow creation from requirements.

#### n8n_manage_credentials
- **Description:** CRUD operations for n8n credentials.
- **Parameters:**
  - `action` (required, string): "list", "get", "create", "update", "delete", "getSchema"
  - `id` (optional, string): Credential ID (required for get/update/delete)
  - `name` (optional, string): Credential name (required for create)
  - `type` (optional, string): Credential type (required for create/getSchema)
  - `data` (optional, object): Credential data fields
- **When to use:** Managing API keys, OAuth tokens, connection credentials.

### Common Patterns
1. **Discovery → Configuration → Validation → Deployment:** search_nodes → get_node → validate_node → n8n_create_workflow → validate_workflow → n8n_update_partial_workflow (activate)
2. **Template Deployment:** search_templates → get_template → n8n_deploy_template → n8n_autofix_workflow
3. **Workflow Debugging:** n8n_get_workflow → n8n_validate_workflow → n8n_executions (get error details) → n8n_autofix_workflow

---

## 2. grafana-mcp

**Purpose:** Grafana dashboard management, alerting, data querying (Prometheus/Loki/Pyroscope/Tempo), incident management, and OnCall operations.

### Dashboard Tools

#### get_dashboard_by_uid
- **Description:** Retrieve complete dashboard JSON including panels, variables, settings.
- **Parameters:** `uid` (required, string)
- **Warning:** Large dashboards can consume significant context window.

#### get_dashboard_summary
- **Description:** Compact dashboard summary (title, panel count, types, variables, metadata).
- **Parameters:** `uid` (required, string)
- **When to use:** Quick overview without full JSON overhead.

#### get_dashboard_property
- **Description:** Get specific dashboard parts using JSONPath expressions.
- **Parameters:** `uid` (required, string), `jsonPath` (required, string)
- **Common paths:** `$.title`, `$.panels[*].title`, `$.panels[0]`, `$.templating.list`, `$.annotations.list`

#### get_dashboard_panel_queries
- **Description:** Retrieve panel queries from a dashboard (all datasource types supported).
- **Parameters:** `uid` (required, string), `panelId` (optional, integer), `variables` (optional, object)

#### search_dashboards
- **Description:** Search dashboards by query string.
- **Parameters:** `query` (optional, string), `limit` (optional, number, default: 50), `page` (optional, number, default: 1)

#### search_folders
- **Description:** Search folders by query string.
- **Parameters:** `query` (optional, string)

#### update_dashboard
- **Description:** Create or update dashboard. Two modes: full JSON or patch operations.
- **Parameters:** `dashboard` (optional, object), `uid` (optional, string), `operations` (optional, array), `folderUid` (optional, string), `message` (optional, string), `overwrite` (optional, boolean)

#### create_folder
- **Description:** Create Grafana folder.
- **Parameters:** `title` (required, string), `uid` (optional, string), `parentUid` (optional, string)

#### get_panel_image
- **Description:** Render dashboard panel as PNG image.
- **Parameters:** `dashboardUid` (required, string), `panelId` (optional, integer), `timeRange` (optional, object), `width`/`height` (optional, integers), `theme` (optional, string: "light"|"dark"), `scale` (optional, integer: 1-3), `variables` (optional, object)

### Datasource Tools

#### list_datasources
- **Description:** List all configured datasources.
- **Parameters:** `type` (optional, string), `limit` (optional, number, default: 50), `offset` (optional, number, default: 0)

#### get_datasource
- **Description:** Get detailed datasource info by UID or name.
- **Parameters:** `uid` (optional, string), `name` (optional, string)

### Prometheus Tools

#### list_prometheus_metric_names
- **Description:** List metric names in PromQL-compatible datasource.
- **Parameters:** `datasourceUid` (required, string), `regex` (optional, string), `limit` (optional, number, default: 10), `page` (optional, number, default: 1), `projectName` (optional, string)

#### list_prometheus_label_values
- **Description:** Get values for a specific label name.
- **Parameters:** `datasourceUid` (required, string), `labelName` (required, string), `matches` (optional, array), `startRfc3339`/`endRfc3339` (optional, strings), `limit` (optional, number, default: 100), `projectName` (optional, string)

#### list_prometheus_label_names
- **Description:** List label names in PromQL datasource.
- **Parameters:** `datasourceUid` (required, string), `matches` (optional, array), `startRfc3339`/`endRfc3339` (optional), `limit` (optional, number, default: 100), `projectName` (optional, string)

#### list_prometheus_metric_metadata
- **Description:** List Prometheus metric metadata (experimental).
- **Parameters:** `datasourceUid` (required, string), `metric` (optional, string), `limit` (optional, number, default: 10), `limitPerMetric` (optional, number), `projectName` (optional, string)

#### query_prometheus
- **Description:** Query PromQL-compatible datasource.
- **Parameters:** `datasourceUid` (required, string), `expr` (required, string), `endTime` (required, string), `startTime` (optional, string), `queryType` (optional, string: "range"|"instant"), `stepSeconds` (optional, integer), `projectName` (optional, string)

#### query_prometheus_histogram
- **Description:** Query histogram percentiles.
- **Parameters:** `datasourceUid` (required, string), `metric` (required, string), `percentile` (required, number), `labels` (optional, string), `startTime`/`endTime` (optional, strings), `stepSeconds` (optional, number, default: 60), `rateInterval` (optional, string, default: "5m"), `projectName` (optional, string)

### Loki Tools

#### list_loki_label_names
- **Description:** List all label names in Loki logs.
- **Parameters:** `datasourceUid` (required, string), `startRfc3339`/`endRfc3339` (optional, strings)

#### list_loki_label_values
- **Description:** Get label values in Loki.
- **Parameters:** `datasourceUid` (required, string), `labelName` (required, string), `startRfc3339`/`endRfc3339` (optional, strings)

#### query_loki_logs
- **Description:** Execute LogQL query against Loki.
- **Parameters:** `datasourceUid` (required, string), `logql` (required, string), `limit` (optional, number, default: 10), `direction` (optional, string: "forward"|"backward"), `startRfc3339`/`endRfc3339` (optional, strings), `queryType` (optional, string: "range"|"instant"), `stepSeconds` (optional, integer)

#### query_loki_stats
- **Description:** Get statistics about log streams.
- **Parameters:** `datasourceUid` (required, string), `logql` (required, string - label selector only), `startRfc3339`/`endRfc3339` (optional, strings)

#### query_loki_patterns
- **Description:** Retrieve detected log patterns from Loki.
- **Parameters:** `datasourceUid` (required, string), `logql` (required, string - stream selector), `startRfc3339`/`endRfc3339` (optional, strings), `step` (optional, string)

### Pyroscope Tools

#### list_pyroscope_profile_types
- **Description:** List available profile types in Pyroscope.
- **Parameters:** `data_source_uid` (required, string), `start_rfc_3339`/`end_rfc_3339` (optional, strings)

#### list_pyroscope_label_names
- **Description:** List label names in Pyroscope profiles.
- **Parameters:** `data_source_uid` (required, string), `matchers` (optional, string), `start_rfc_3339`/`end_rfc_3339` (optional, strings)

#### list_pyroscope_label_values
- **Description:** Get label values in Pyroscope.
- **Parameters:** `data_source_uid` (required, string), `name` (required, string), `matchers` (optional, string), `start_rfc_3339`/`end_rfc_3339` (optional, strings)

#### query_pyroscope
- **Description:** Query Pyroscope for profiles and/or metrics.
- **Parameters:** `data_source_uid` (required, string), `profile_type` (required, string), `query_type` (optional, string: "profile"|"metrics"|"both" (default)), `matchers` (optional, string), `start_rfc_3339`/`end_rfc_3339` (optional, strings), `step` (optional, number), `group_by` (optional, array), `max_node_depth` (optional, number, default: 100)

### Alerting Tools

#### alerting_manage_rules
- **Description:** Manage Grafana alert rules (CRUD + list + versions).
- **Parameters:** `operation` (required, string): "list", "get", "versions", "create", "update", "delete", plus many optional parameters for rule configuration (title, condition, data, labels, annotations, folder_uid, rule_group, states, etc.)

#### alerting_manage_routing
- **Description:** Manage notification policies, contact points, time intervals.
- **Parameters:** `operation` (required, string): "get_notification_policies", "get_contact_points", "get_contact_point", "get_time_intervals", "get_time_interval", plus optional filter parameters

#### list_alert_groups
- **Description:** List alert groups from Grafana OnCall.
- **Parameters:** `state` (optional, string: "new"|"acknowledged"|"resolved"|"silenced"), `integrationId`, `routeId`, `teamId`, `name`, `labels`, `startedAt`, `id`, `page` (all optional)

#### get_alert_group
- **Description:** Get specific alert group details.
- **Parameters:** `alertGroupId` (required, string)

### Incident Management

#### list_incidents
- **Description:** List Grafana incidents.
- **Parameters:** `status` (optional, string: "active"|"resolved"), `limit` (optional, number, default: 10), `drill` (optional, boolean)

#### get_incident
- **Description:** Get single incident by ID.
- **Parameters:** `id` (required, string)

#### create_incident
- **Description:** Create new Grafana incident.
- **Parameters:** `title` (required, string), `severity` (required, string), `roomPrefix` (required, string), `status` (optional, string), `isDrill` (optional, boolean), `labels` (optional, array), `attachCaption`/`attachUrl` (optional, strings)

#### add_activity_to_incident
- **Description:** Add note to incident timeline.
- **Parameters:** `incidentId` (required, string), `body` (required, string), `eventTime` (optional, string)

### OnCall Management

#### list_oncall_teams
- **Description:** List teams in Grafana OnCall.
- **Parameters:** `page` (optional, number)

#### list_oncall_users
- **Description:** List OnCall users.
- **Parameters:** `userId` (optional, string), `username` (optional, string), `page` (optional, number)

#### list_oncall_schedules
- **Description:** List OnCall schedules.
- **Parameters:** `scheduleId` (optional, string), `teamId` (optional, string), `page` (optional, number)

#### get_oncall_shift
- **Description:** Get OnCall shift details.
- **Parameters:** `shiftId` (required, string)

#### get_current_oncall_users
- **Description:** Get users currently on-call for a schedule.
- **Parameters:** `scheduleId` (required, string)

### Sift Investigation

#### list_sift_investigations
- **Description:** List Sift investigations.
- **Parameters:** `limit` (optional, number, default: 10)

#### get_sift_investigation
- **Description:** Get Sift investigation by UUID.
- **Parameters:** `id` (required, string)

#### get_sift_analysis
- **Description:** Get specific analysis from investigation.
- **Parameters:** `investigationId` (required, string), `analysisId` (required, string)

#### find_error_pattern_logs
- **Description:** Search Loki logs for elevated error patterns.
- **Parameters:** `name` (required, string), `labels` (required, object), `start`/`end` (optional, datetime strings)

#### find_slow_requests
- **Description:** Search Tempo for slow requests.
- **Parameters:** `name` (required, string), `labels` (required, object), `start`/`end` (optional, datetime strings)

### Annotations

#### get_annotations
- **Description:** Fetch Grafana annotations with filters.
- **Parameters:** `DashboardUID`, `PanelID`, `Tags`, `From`/`To` (epoch ms), `Limit`, `Type`, `MatchAny`, `AlertUID`, `UserID`, `DashboardID`, `AlertID` (all optional)

#### get_annotation_tags
- **Description:** Get annotation tags with optional filtering.
- **Parameters:** `tag` (optional, string), `limit` (optional, string)

#### create_annotation
- **Description:** Create new annotation.
- **Parameters:** `dashboardUID` (optional, string), `panelId` (optional, integer), `time`/`timeEnd` (optional, integers), `text` (optional, string), `tags` (optional, array), `format` (optional, string: "graphite"), `what`/`when`/`graphiteData`/`data` (optional)

#### update_annotation
- **Description:** Update annotation by ID.
- **Parameters:** `id` (required, integer), `text` (optional, string), `time`/`timeEnd` (optional, integers), `tags` (optional, array), `data` (optional, object)

### Other

#### generate_deeplink
- **Description:** Generate deeplink URLs for Grafana resources.
- **Parameters:** `resourceType` (required, string: "dashboard"|"panel"|"explore"), `dashboardUid` (optional, string), `panelId` (optional, integer), `datasourceUid` (optional, string), `queries` (optional, array), `timeRange` (optional, object), `queryParams` (optional, object)

#### get_assertions
- **Description:** Get assertion summary for an entity.
- **Parameters:** `startTime`/`endTime` (required, datetime strings), `entityType`/`entityName`/`env`/`site`/`namespace` (all optional, strings)

### Common Patterns
1. **Metric Discovery:** list_prometheus_metric_names → list_prometheus_label_values → query_prometheus
2. **Log Investigation:** list_loki_label_names → list_loki_label_values → query_loki_logs → find_error_pattern_logs
3. **Dashboard Analysis:** search_dashboards → get_dashboard_summary → get_dashboard_panel_queries
4. **Alert Debugging:** alerting_manage_rules (list with states) → alerting_manage_routing → list_alert_groups

---

## 3. firecrawl

**Purpose:** Web scraping, crawling, search, and autonomous browser automation.

### Scraping Tools

#### firecrawl_scrape
- **Description:** Scrape content from a single URL with advanced options. Fastest and most reliable scraper.
- **Parameters:**
  - `url` (required, string): URL to scrape
  - `formats` (optional, array): ["markdown", "html", "rawHtml", "screenshot", "links", "summary", "changeTracking", "branding", "json"]
  - `onlyMainContent` (optional, boolean): Exclude navigation/footers
  - `jsonOptions` (optional, object): {prompt: string, schema: object} for structured extraction
  - `waitFor` (optional, number): Milliseconds to wait for JS rendering
  - `actions` (optional, array): Click, fill, wait, scroll, screenshot, etc.
  - `screenshotOptions`, `includeTags`, `excludeTags`, `skipTlsVerification`, `mobile`, `location`, `proxy`, `maxAge`, `removeBase64Images`, `zeroDataRetention`, `parsers`, `pdfOptions` (all optional)
- **When to use:** Single page content extraction, structured data extraction.
- **Key pattern:** Use JSON format with schema for specific data points; markdown for full page content.

#### firecrawl_map
- **Description:** Discover all indexed URLs on a site.
- **Parameters:**
  - `url` (required, string)
  - `search` (optional, string): Filter URLs by search term
  - `limit` (optional, number)
  - `includeSubdomains` (optional, boolean)
  - `ignoreQueryParameters` (optional, boolean)
  - `sitemap` (optional, string): "include"|"skip"|"only"
- **When to use:** Finding specific pages on a site before scraping.

#### firecrawl_crawl
- **Description:** Start a crawl job across multiple pages.
- **Parameters:**
  - `url` (required, string)
  - `limit` (optional, number): Max pages
  - `maxDiscoveryDepth` (optional, number): Max crawl depth
  - `scrapeOptions` (optional, object): Format, filters
  - `allowExternalLinks`, `allowSubdomains`, `deduplicateSimilarURLs`, `ignoreQueryParameters` (optional, boolean)
  - `maxConcurrency` (optional, number)
  - `delay` (optional, number): Delay between requests
  - `excludePaths`, `includePaths` (optional, arrays)
  - `sitemap` (optional, string), `webhook` (optional, string), `prompt` (optional, string)
- **When to use:** Comprehensive site extraction. Returns operation ID for status checking.

####