/**
 * dnsdist Custom Lovelace Card
 *
 * Displays dnsdist counters and filtering rules in a dynamic layout.
 */
import { LitElement, html, nothing, PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { cardStyles } from './styles';
import type { DnsdistCardConfig, HomeAssistant, HassEntity, FilteringRule, DynamicRule } from './types';

// Import and register the editor
import './dnsdist-card-editor';

// Register card with Home Assistant custom card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'dnsdist-card',
  name: 'dnsdist Card',
  description: 'Display dnsdist DNS server metrics and filtering rules',
  preview: true,
});

@customElement('dnsdist-card')
export class DnsdistCard extends LitElement {
  static styles = cardStyles;

  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: DnsdistCardConfig;
  @state() private _expandedFilters: Set<string> = new Set();
  @state() private _expandedDynamic: Set<string> = new Set();
  @state() private _showZeroMatchDynamic = false;
  @state() private _showConfirm = false;
  @state() private _confirmAction: (() => void) | null = null;

  // Timer for updating dynamic rule countdowns
  private _countdownTimer?: ReturnType<typeof setInterval>;

  static getConfigElement() {
    return document.createElement('dnsdist-card-editor');
  }

  static getStubConfig() {
    return {
      entity_prefix: 'dnsdist',
      show_filters: true,
      show_dynamic_rules: true,
      show_actions: true,
    };
  }

  setConfig(config: DnsdistCardConfig) {
    // Don't throw during initial setup - let the editor handle validation
    this._config = {
      show_graphs: false,
      show_filters: true,
      show_dynamic_rules: true,
      show_actions: true,
      compact: false,
      ...config,
      // Ensure entity_prefix is at least an empty string
      entity_prefix: config.entity_prefix || '',
    };
  }

  protected updated(changedProps: PropertyValues) {
    super.updated(changedProps);
    if (this._config?.compact) {
      this.setAttribute('compact', '');
    } else {
      this.removeAttribute('compact');
    }
  }

  connectedCallback() {
    super.connectedCallback();
    // Start countdown timer for dynamic rules (updates every second)
    this._countdownTimer = setInterval(() => {
      // Only request update if we have expanded dynamic rules with active countdowns
      if (this._expandedDynamic.size > 0) {
        this.requestUpdate();
      }
    }, 1000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    // Clean up the countdown timer
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = undefined;
    }
  }

  /**
   * Entity ID mapping: the card uses friendly metric names that map to
   * HA entity IDs. HA generates entity_ids from device_name + friendly_name,
   * e.g., "dns1" + "Total Queries" -> "sensor.dns1_total_queries"
   */
  private static readonly METRIC_TO_ENTITY: Record<string, string[]> = {
    // Core metrics - try multiple patterns
    queries: ['total_queries', 'queries'],
    responses: ['responses'],
    drops: ['dropped_queries', 'drops'],
    rule_drop: ['rule_drops', 'rule_drop'],
    downstream_errors: ['downstream_send_errors', 'downstream_errors'],
    cache_hits: ['cache_hits'],
    cache_misses: ['cache_misses'],
    cache_hit_rate: ['cache_hit_rate', 'cachehit'],
    cpu: ['cpu_usage', 'cpu'],
    uptime: ['uptime'],
    req_per_hour: ['requests_per_hour_last_hour', 'req_per_hour'],
    req_per_day: ['requests_per_day_last_24h', 'req_per_day'],
    security_status: ['security_status'],
  };

  private _getEntityId(metric: string): string | undefined {
    const prefix = this._config.entity_prefix;
    const patterns = DnsdistCard.METRIC_TO_ENTITY[metric] || [metric];

    // Try different prefix variations to handle naming inconsistencies
    const prefixVariations = [
      prefix,
      `${prefix}_${prefix}`,  // doubled prefix (nsec -> nsec_nsec)
    ];

    for (const pfx of prefixVariations) {
      for (const pattern of patterns) {
        const entityId = `sensor.${pfx}_${pattern}`;
        if (this.hass?.states?.[entityId]) {
          return entityId;
        }
      }
    }
    // Return first pattern as fallback
    return `sensor.${prefix}_${patterns[0]}`;
  }

  private _getEntity(metric: string): HassEntity | undefined {
    const entityId = this._getEntityId(metric);
    return entityId ? this.hass?.states?.[entityId] : undefined;
  }

  private _getEntityValue(metric: string): string | number | null {
    const entity = this._getEntity(metric);
    if (!entity) return null;
    const state = entity.state;
    if (state === 'unavailable' || state === 'unknown') return null;
    return state;
  }

  private _getNumericValue(metric: string): number | null {
    const val = this._getEntityValue(metric);
    if (val === null) return null;
    const num = parseFloat(String(val));
    return isNaN(num) ? null : num;
  }

  private _formatNumber(num: number | null): string {
    if (num === null) return '-';
    if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
    if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
    return num.toLocaleString();
  }

  private _getSecurityStatus(): string {
    const val = this._getEntityValue('security_status');
    return val ? String(val).toLowerCase() : 'unknown';
  }

  private _getSecurityStatusClass(): string {
    const status = this._getSecurityStatus();
    if (status === 'ok' || status === 'secure') return 'status-ok';
    if (status === 'warning') return 'status-warning';
    if (status === 'critical') return 'status-critical';
    return 'status-unknown';
  }

  private _getSecurityLabel(): string {
    const entity = this._getEntity('security_status');
    return entity?.attributes?.status_label as string || this._getSecurityStatus().toUpperCase();
  }

  private _getUptimeDisplay(): string {
    const entity = this._getEntity('uptime');
    if (!entity) return '-';
    const human = entity.attributes?.human_readable as string;
    if (human) return human;

    const seconds = this._getNumericValue('uptime');
    if (seconds === null) return '-';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours.toString().padStart(2, '0')}h ${minutes.toString().padStart(2, '0')}m`;
  }

  private _getFilterEntities(): Array<{ entity: HassEntity; rule: FilteringRule }> {
    if (!this.hass?.states) return [];

    const prefix = this._config.entity_prefix;
    // Escape special regex characters in prefix
    const escapedPrefix = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Match various filter entity patterns, including doubled prefix:
    // - sensor.{prefix}_filter_{name}
    // - sensor.{prefix}_{prefix}_filter_{name} (doubled prefix)
    const filterPattern = new RegExp(
      `^sensor\\.(${escapedPrefix}_)?${escapedPrefix}[_\\s]?filter`,
      'i'
    );

    const filters: Array<{ entity: HassEntity; rule: FilteringRule }> = [];

    for (const entityId of Object.keys(this.hass.states)) {
      if (!entityId.startsWith('sensor.')) continue;

      const entity = this.hass.states[entityId];
      const friendlyName = entity.attributes?.friendly_name as string || '';

      // Method 1: Check by entity_id pattern (handles both prefix and doubled prefix)
      const matchesPattern = filterPattern.test(entityId);

      // Method 2: Check by friendly_name containing "Filter" and prefix
      const prefixForName = prefix.toLowerCase().replace(/_/g, ' ');
      const matchesFriendlyName = friendlyName.toLowerCase().includes(' filter ') &&
        (friendlyName.toLowerCase().startsWith(prefixForName) ||
         friendlyName.toLowerCase().startsWith(`${prefixForName} ${prefixForName}`));

      // Method 3: Check if it has filter-specific attributes (action, rule, enabled)
      const hasFilterAttrs = entity.attributes?.action !== undefined ||
        (entity.attributes?.rule !== undefined && entity.attributes?.enabled !== undefined);
      const matchesFilterAttrs = hasFilterAttrs &&
        (entityId.toLowerCase().includes(prefix.toLowerCase()) ||
         friendlyName.toLowerCase().includes(prefix.toLowerCase().replace(/_/g, ' ')));

      if (!matchesPattern && !matchesFriendlyName && !matchesFilterAttrs) continue;
      const matches = parseInt(entity.state, 10);

      const rule: FilteringRule = {
        matches: isNaN(matches) ? 0 : matches,
        id: entity.attributes?.id as number | undefined,
        uuid: entity.attributes?.uuid as string | undefined,
        name: this._extractRuleName(entity),
        action: entity.attributes?.action as string | undefined,
        rule: entity.attributes?.rule as string | undefined,
        type: entity.attributes?.type as string | undefined,
        enabled: entity.attributes?.enabled as boolean | undefined,
        bypass: entity.attributes?.bypass as boolean | undefined,
        sources: entity.attributes?.sources as Record<string, number> | undefined,
      };

      filters.push({ entity, rule });
    }

    // Sort by matches descending
    return filters.sort((a, b) => b.rule.matches - a.rule.matches);
  }

  private _extractRuleName(entity: HassEntity): string {
    // The entity name format is "{host} Filter {rule_name}"
    const friendlyName = entity.attributes?.friendly_name as string;
    if (friendlyName) {
      const match = friendlyName.match(/Filter (.+)$/);
      if (match) return match[1];
    }
    // Fallback: extract from entity_id
    const match = entity.entity_id.match(/_filter_(.+)$/);
    if (match) return match[1].replace(/_/g, ' ');
    return 'Unknown Rule';
  }

  private _toggleFilterExpand(entityId: string) {
    const expanded = new Set(this._expandedFilters);
    if (expanded.has(entityId)) {
      expanded.delete(entityId);
    } else {
      expanded.add(entityId);
    }
    this._expandedFilters = expanded;
  }

  private _getDynamicRuleEntities(): Array<{ entity: HassEntity; rule: DynamicRule }> {
    if (!this.hass?.states) return [];

    const prefix = this._config.entity_prefix;
    // Escape special regex characters in prefix
    const escapedPrefix = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Match various dynamic rule entity patterns:
    // - sensor.{prefix}_dynblock_{network}
    // - sensor.{prefix}_{prefix}_dynblock_{network} (doubled prefix)
    const dynblockPattern = new RegExp(
      `^sensor\\.(${escapedPrefix}_)?${escapedPrefix}[_\\s]?dynblock`,
      'i'
    );

    const rules: Array<{ entity: HassEntity; rule: DynamicRule }> = [];

    for (const entityId of Object.keys(this.hass.states)) {
      if (!entityId.startsWith('sensor.')) continue;

      const entity = this.hass.states[entityId];
      const friendlyName = entity.attributes?.friendly_name as string || '';

      // Method 1: Check by entity_id pattern
      const matchesPattern = dynblockPattern.test(entityId);

      // Method 2: Check by friendly_name containing "Dynblock"
      const prefixForName = prefix.toLowerCase().replace(/_/g, ' ');
      const matchesFriendlyName = friendlyName.toLowerCase().includes(' dynblock ') &&
        (friendlyName.toLowerCase().startsWith(prefixForName) ||
         friendlyName.toLowerCase().startsWith(`${prefixForName} ${prefixForName}`));

      // Method 3: Check if it has dynblock-specific attributes (network, reason, seconds)
      const hasDynblockAttrs = entity.attributes?.network !== undefined ||
        (entity.attributes?.reason !== undefined && entity.attributes?.seconds !== undefined);
      const matchesDynblockAttrs = hasDynblockAttrs &&
        (entityId.toLowerCase().includes(prefix.toLowerCase()) ||
         friendlyName.toLowerCase().includes(prefix.toLowerCase().replace(/_/g, ' ')));

      if (!matchesPattern && !matchesFriendlyName && !matchesDynblockAttrs) continue;

      // Skip entities with invalid/unavailable state
      if (entity.state === 'unknown' || entity.state === 'unavailable') continue;

      const blocks = parseInt(entity.state, 10);
      const seconds = entity.attributes?.seconds as number | undefined;
      const network = entity.attributes?.network as string | undefined;

      // Skip if missing essential dynblock attributes (stale entity)
      if (seconds === undefined || network === undefined) continue;

      // Calculate if the dynblock has expired based on elapsed time
      let isExpired = false;
      if (seconds <= 0) {
        isExpired = true;
      } else if (entity.last_updated) {
        const updatedTime = new Date(entity.last_updated).getTime();
        const elapsedSeconds = Math.floor((Date.now() - updatedTime) / 1000);
        if (seconds - elapsedSeconds <= 0) {
          isExpired = true;
        }
      }

      // Skip expired dynblocks
      if (isExpired) continue;

      const rule: DynamicRule = {
        blocks: isNaN(blocks) ? 0 : blocks,
        network: entity.attributes?.network as string | undefined,
        reason: entity.attributes?.reason as string | undefined,
        action: entity.attributes?.action as string | undefined,
        seconds: seconds,
        ebpf: entity.attributes?.ebpf as boolean | undefined,
        warning: entity.attributes?.warning as boolean | undefined,
        sources: entity.attributes?.sources as Record<string, number> | undefined,
        last_updated: entity.last_updated,
      };

      rules.push({ entity, rule });
    }

    // Filter out zero-match rules unless toggle is enabled
    const filteredRules = this._showZeroMatchDynamic
      ? rules
      : rules.filter(({ rule }) => rule.blocks > 0);

    // Sort by blocks descending
    return filteredRules.sort((a, b) => b.rule.blocks - a.rule.blocks);
  }

  private _extractDynamicRuleName(entity: HassEntity): string {
    // The entity name format is "{host} Dynblock {network}"
    const friendlyName = entity.attributes?.friendly_name as string;
    if (friendlyName) {
      const match = friendlyName.match(/Dynblock (.+)$/);
      if (match) return match[1];
    }
    // Try network attribute
    const network = entity.attributes?.network as string;
    if (network) return network;
    // Fallback: extract from entity_id
    const match = entity.entity_id.match(/_dynblock_(.+)$/);
    if (match) return match[1].replace(/_/g, '.');
    return 'Unknown';
  }

  private _toggleDynamicExpand(entityId: string) {
    const expanded = new Set(this._expandedDynamic);
    if (expanded.has(entityId)) {
      expanded.delete(entityId);
    } else {
      expanded.add(entityId);
    }
    this._expandedDynamic = expanded;
  }

  private _formatTimeRemaining(seconds: number | undefined, lastUpdated?: string): string {
    if (seconds === undefined || seconds <= 0) return '-';

    // Calculate elapsed time since last update to show real-time countdown
    let adjustedSeconds = seconds;
    if (lastUpdated) {
      const updatedTime = new Date(lastUpdated).getTime();
      const now = Date.now();
      const elapsedSeconds = Math.floor((now - updatedTime) / 1000);
      adjustedSeconds = Math.max(0, seconds - elapsedSeconds);
    }

    if (adjustedSeconds <= 0) return 'Expiring...';

    const mins = Math.floor(adjustedSeconds / 60);
    const secs = Math.floor(adjustedSeconds % 60);
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  }

  private _getActionClass(action: string | undefined): string {
    if (!action) return '';
    const lower = action.toLowerCase();
    if (lower.includes('drop') || lower.includes('refuse')) return 'drop';
    if (lower.includes('allow') || lower.includes('pool')) return 'allow';
    return '';
  }

  private async _clearCache() {
    const prefix = this._config.entity_prefix;
    const buttonEntity = `button.${prefix}_clear_cache`;

    if (this.hass.states[buttonEntity]) {
      await this.hass.callService('button', 'press', {
        entity_id: buttonEntity,
      });
    } else {
      // Fallback: call the dnsdist service directly
      await this.hass.callService('dnsdist', 'clear_cache', {
        host: prefix,
      });
    }
  }

  private _showClearCacheConfirm() {
    this._confirmAction = () => this._clearCache();
    this._showConfirm = true;
  }

  private _confirmDialogAction() {
    if (this._confirmAction) {
      this._confirmAction();
    }
    this._hideConfirm();
  }

  private _hideConfirm() {
    this._showConfirm = false;
    this._confirmAction = null;
  }

  private _toggleShowZeroMatchDynamic() {
    this._showZeroMatchDynamic = !this._showZeroMatchDynamic;
  }

  private _renderGaugeSvg(needleRotation: number, colors: string[]) {
    return html`
      <svg class="gauge-svg" viewBox="0 0 100 100">
        <path d="M 21.72 78.28 A 40 40 0 0 1 10.77 57.80" fill="none" stroke="${colors[0]}" stroke-width="8"/>
        <path d="M 10.77 57.80 A 40 40 0 0 1 13.04 34.69" fill="none" stroke="${colors[1]}" stroke-width="8"/>
        <path d="M 13.04 34.69 A 40 40 0 0 1 27.78 16.74" fill="none" stroke="${colors[2]}" stroke-width="8"/>
        <path d="M 27.78 16.74 A 40 40 0 0 1 50.00 10.00" fill="none" stroke="${colors[3]}" stroke-width="8"/>
        <path d="M 50.00 10.00 A 40 40 0 0 1 72.22 16.74" fill="none" stroke="${colors[4]}" stroke-width="8"/>
        <path d="M 72.22 16.74 A 40 40 0 0 1 86.96 34.69" fill="none" stroke="${colors[5]}" stroke-width="8"/>
        <path d="M 86.96 34.69 A 40 40 0 0 1 89.23 57.80" fill="none" stroke="${colors[6]}" stroke-width="8"/>
        <path d="M 89.23 57.80 A 40 40 0 0 1 78.28 78.28" fill="none" stroke="${colors[7]}" stroke-width="8"/>
        <g class="gauge-needle-group" style="transform: rotate(${needleRotation}deg); transform-origin: 50px 50px;">
          <line class="gauge-needle" x1="50" y1="50" x2="50" y2="16" />
        </g>
        <circle class="gauge-pivot" cx="50" cy="50" r="4" />
      </svg>
    `;
  }

  private _renderGaugeInfo(value: number | null, label: string, position: 'left' | 'right') {
    return html`
      <div class="gauge-info gauge-info-${position}">
        <div class="gauge-value">${value !== null ? `${value.toFixed(0)}%` : '-'}</div>
        <div class="gauge-label">${label}</div>
      </div>
    `;
  }

  private _renderGaugeGreenToRed(value: number | null, label: string, position: 'left' | 'right') {
    const pct = value !== null ? Math.min(100, Math.max(0, value)) : 0;
    const needleRotation = -135 + (pct / 100) * 270;
    const colors = ['#4caf50', '#8bc34a', '#cddc39', '#ffeb3b', '#ffc107', '#ff9800', '#ff5722', '#f44336'];

    return html`
      <div class="gauge">
        ${position === 'left' ? this._renderGaugeInfo(value, label, position) : ''}
        ${this._renderGaugeSvg(needleRotation, colors)}
        ${position === 'right' ? this._renderGaugeInfo(value, label, position) : ''}
      </div>
    `;
  }

  private _renderGaugeRedToGreen(value: number | null, label: string, position: 'left' | 'right') {
    const pct = value !== null ? Math.min(100, Math.max(0, value)) : 0;
    const needleRotation = -135 + (pct / 100) * 270;
    const colors = ['#f44336', '#ff5722', '#ff9800', '#ffc107', '#ffeb3b', '#cddc39', '#8bc34a', '#4caf50'];

    return html`
      <div class="gauge">
        ${position === 'left' ? this._renderGaugeInfo(value, label, position) : ''}
        ${this._renderGaugeSvg(needleRotation, colors)}
        ${position === 'right' ? this._renderGaugeInfo(value, label, position) : ''}
      </div>
    `;
  }

  private _renderCounterTile(label: string, metric: string, icon: string) {
    const value = this._getNumericValue(metric);
    return html`
      <div class="counter-tile">
        <ha-icon icon="${icon}"></ha-icon>
        <div class="counter-value">${this._formatNumber(value)}</div>
        <div class="counter-label">${label}</div>
      </div>
    `;
  }

  private _renderFilterItem(entityId: string, rule: FilteringRule) {
    const isExpanded = this._expandedFilters.has(entityId);

    return html`
      <div
        class="filter-item ${isExpanded ? 'expanded' : ''}"
        @click=${() => this._toggleFilterExpand(entityId)}
      >
        <div class="filter-main">
          <span class="filter-name">${rule.name || 'Unnamed Rule'}</span>
          ${rule.action
            ? html`<span class="filter-action ${this._getActionClass(rule.action)}">${rule.action}</span>`
            : nothing}
        </div>
        <span class="filter-matches">${this._formatNumber(rule.matches)}</span>

        ${isExpanded
          ? html`
              <div class="filter-details">
                ${rule.rule
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Pattern:</span>
                        <span class="filter-detail-value">${rule.rule}</span>
                      </div>
                    `
                  : nothing}
                ${rule.type
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Type:</span>
                        <span class="filter-detail-value">${rule.type}</span>
                      </div>
                    `
                  : nothing}
                ${rule.enabled !== undefined
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Enabled:</span>
                        <span class="filter-detail-value">${rule.enabled ? 'Yes' : 'No'}</span>
                      </div>
                    `
                  : nothing}
                ${rule.id !== undefined
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">ID:</span>
                        <span class="filter-detail-value">${rule.id}</span>
                      </div>
                    `
                  : nothing}
              </div>
            `
          : nothing}
      </div>
    `;
  }

  private _renderDynamicRuleItem(entityId: string, rule: DynamicRule) {
    const isExpanded = this._expandedDynamic.has(entityId);
    const network = rule.network || this._extractDynamicRuleName(this.hass.states[entityId]);

    return html`
      <div
        class="filter-item ${isExpanded ? 'expanded' : ''}"
        @click=${() => this._toggleDynamicExpand(entityId)}
      >
        <div class="filter-main">
          <span class="filter-name">${network}</span>
          ${rule.action
            ? html`<span class="filter-action ${this._getActionClass(rule.action)}">${rule.action}</span>`
            : nothing}
        </div>
        <span class="filter-matches">${this._formatNumber(rule.blocks)}</span>

        ${isExpanded
          ? html`
              <div class="filter-details">
                ${rule.reason
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Reason:</span>
                        <span class="filter-detail-value">${rule.reason}</span>
                      </div>
                    `
                  : nothing}
                ${rule.seconds !== undefined && rule.seconds > 0
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Time Left:</span>
                        <span class="filter-detail-value">${this._formatTimeRemaining(rule.seconds, rule.last_updated)}</span>
                      </div>
                    `
                  : nothing}
                ${rule.ebpf !== undefined
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">eBPF:</span>
                        <span class="filter-detail-value">${rule.ebpf ? 'Yes' : 'No'}</span>
                      </div>
                    `
                  : nothing}
                ${rule.warning !== undefined && rule.warning
                  ? html`
                      <div class="filter-detail-row">
                        <span class="filter-detail-label">Warning:</span>
                        <span class="filter-detail-value">Yes</span>
                      </div>
                    `
                  : nothing}
              </div>
            `
          : nothing}
      </div>
    `;
  }

  private _renderConfirmDialog() {
    if (!this._showConfirm) return nothing;

    return html`
      <div class="confirm-overlay" @click=${this._hideConfirm}>
        <div class="confirm-dialog" @click=${(e: Event) => e.stopPropagation()}>
          <div class="confirm-title">Clear Cache?</div>
          <div class="confirm-message">
            This will clear the DNS cache on ${this._config.title || this._config.entity_prefix}.
          </div>
          <div class="confirm-buttons">
            <button class="action-button confirm-cancel" @click=${this._hideConfirm}>
              Cancel
            </button>
            <button class="action-button confirm-confirm" @click=${this._confirmDialogAction}>
              Clear
            </button>
          </div>
        </div>
      </div>
    `;
  }

  render() {
    if (!this._config || !this.hass) {
      return html`<ha-card><div class="loading">Loading...</div></ha-card>`;
    }

    if (!this._config.entity_prefix) {
      return html`
        <ha-card>
          <div class="empty-state">
            <ha-icon icon="mdi:dns"></ha-icon>
            <div>Please configure the entity prefix</div>
          </div>
        </ha-card>
      `;
    }

    const title = this._config.title || this._config.entity_prefix;
    const cpu = this._getNumericValue('cpu');
    const cacheHit = this._getNumericValue('cache_hit_rate');
    const filterEntities = this._config.show_filters ? this._getFilterEntities() : [];
    const dynamicRuleEntities = this._config.show_dynamic_rules ? this._getDynamicRuleEntities() : [];

    return html`
      <ha-card>
        <!-- Header -->
        <div class="card-header">
          <div class="card-title">
            <ha-icon icon="mdi:dns"></ha-icon>
            ${title}
          </div>
          <span class="status-badge ${this._getSecurityStatusClass()}">
            ${this._getSecurityLabel()}
          </span>
        </div>

        <!-- Gauges -->
        <div class="gauge-container">
          ${this._renderGaugeGreenToRed(cpu, 'CPU', 'left')}
          ${this._renderGaugeRedToGreen(cacheHit, 'Cache Hit', 'right')}
        </div>

        <!-- Uptime -->
        <div class="uptime-display">
          <ha-icon icon="mdi:timer-outline"></ha-icon>
          <span class="uptime-label">Uptime:</span>
          <span class="uptime-value">${this._getUptimeDisplay()}</span>
        </div>

        <!-- Traffic Counters -->
        <div class="section-header">Traffic Counters</div>
        <div class="counters-grid">
          ${this._renderCounterTile('Queries', 'queries', 'mdi:dns')}
          ${this._renderCounterTile('Responses', 'responses', 'mdi:send')}
          ${this._renderCounterTile('Drops', 'drops', 'mdi:cancel')}
          ${this._renderCounterTile('Rule Drops', 'rule_drop', 'mdi:shield-off-outline')}
          ${this._renderCounterTile('Errors', 'downstream_errors', 'mdi:alert-circle')}
        </div>

        <!-- Request Rates -->
        <div class="section-header">Request Rates</div>
        <div class="stats-grid">
          <div class="stat-tile">
            <ha-icon class="stat-icon" icon="mdi:chart-line"></ha-icon>
            <div class="stat-value">${this._formatNumber(this._getNumericValue('req_per_hour'))}</div>
            <div class="stat-label">Per Hour</div>
          </div>
          <div class="stat-tile">
            <ha-icon class="stat-icon" icon="mdi:chart-areaspline"></ha-icon>
            <div class="stat-value">${this._formatNumber(this._getNumericValue('req_per_day'))}</div>
            <div class="stat-label">Per Day</div>
          </div>
        </div>

        <!-- Filtering Rules (only shown if rules exist) -->
        ${this._config.show_filters && filterEntities.length > 0
          ? html`
              <div class="section-header">Filtering Rules (${filterEntities.length})</div>
              <div class="filters-list">
                ${filterEntities.map(({ entity, rule }) =>
                  this._renderFilterItem(entity.entity_id, rule)
                )}
              </div>
            `
          : nothing}

        <!-- Dynamic Rules (only shown if rules exist) -->
        ${this._config.show_dynamic_rules && dynamicRuleEntities.length > 0
          ? html`
              <div class="section-header">Dynamic Rules (${dynamicRuleEntities.length})</div>
              <div class="filters-list">
                ${dynamicRuleEntities.map(({ entity, rule }) =>
                  this._renderDynamicRuleItem(entity.entity_id, rule)
                )}
              </div>
            `
          : nothing}

        <!-- Actions -->
        ${this._config.show_actions
          ? html`
              <div class="actions-container">
                <button class="action-button" @click=${this._showClearCacheConfirm}>
                  <ha-icon icon="mdi:database-refresh"></ha-icon>
                  Clear Cache
                </button>
                ${this._config.show_dynamic_rules
                  ? html`
                      <button
                        class="action-button ${this._showZeroMatchDynamic ? '' : 'toggle-off'}"
                        @click=${this._toggleShowZeroMatchDynamic}
                      >
                        <ha-icon icon="${this._showZeroMatchDynamic ? 'mdi:eye-off' : 'mdi:eye'}"></ha-icon>
                        ${this._showZeroMatchDynamic ? 'Hide 0 Hits' : 'Show 0 Hits'}
                      </button>
                    `
                  : nothing}
              </div>
            `
          : nothing}

        ${this._renderConfirmDialog()}
      </ha-card>
    `;
  }

  getCardSize(): number {
    let size = 3; // Header + gauges + uptime
    size += 2; // Counters
    size += 2; // Rates
    if (this._config?.show_filters) {
      const filterCount = this._getFilterEntities().length;
      size += Math.min(4, Math.ceil(filterCount / 2) + 1);
    }
    if (this._config?.show_dynamic_rules) {
      const dynamicCount = this._getDynamicRuleEntities().length;
      size += Math.min(4, Math.ceil(dynamicCount / 2) + 1);
    }
    if (this._config?.show_actions) size += 1;
    return size;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'dnsdist-card': DnsdistCard;
  }
}
