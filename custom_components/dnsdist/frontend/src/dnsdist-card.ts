/**
 * dnsdist Custom Lovelace Card
 *
 * Displays dnsdist counters and filtering rules in a dynamic layout.
 */
import { LitElement, html, nothing, PropertyValues } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { cardStyles } from './styles';
import type { DnsdistCardConfig, HomeAssistant, HassEntity, FilteringRule } from './types';

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
  @state() private _showConfirm = false;
  @state() private _confirmAction: (() => void) | null = null;

  static getConfigElement() {
    return document.createElement('dnsdist-card-editor');
  }

  static getStubConfig() {
    return {
      entity_prefix: 'dnsdist',
      show_filters: true,
      show_actions: true,
    };
  }

  setConfig(config: DnsdistCardConfig) {
    // Don't throw during initial setup - let the editor handle validation
    this._config = {
      show_graphs: false,
      show_filters: true,
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

  private _renderGauge(value: number | null, label: string, color?: string) {
    const pct = value !== null ? Math.min(100, Math.max(0, value)) : 0;
    const rotation = 225 + (pct / 100) * 270;

    return html`
      <div class="gauge">
        <div class="gauge-arc">
          <div class="gauge-arc-bg"></div>
          <div
            class="gauge-arc-fill"
            style="transform: rotate(${rotation}deg); ${color ? `border-color: ${color}; border-bottom-color: transparent; border-left-color: transparent;` : ''}"
          ></div>
        </div>
        <div class="gauge-value">${value !== null ? `${value.toFixed(0)}%` : '-'}</div>
        <div class="gauge-label">${label}</div>
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
          ${this._renderGauge(cpu, 'CPU')}
          ${this._renderGauge(cacheHit, 'Cache Hit')}
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

        <!-- Actions -->
        ${this._config.show_actions
          ? html`
              <div class="actions-container">
                <button class="action-button" @click=${this._showClearCacheConfirm}>
                  <ha-icon icon="mdi:database-refresh"></ha-icon>
                  Clear Cache
                </button>
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
    if (this._config?.show_actions) size += 1;
    return size;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'dnsdist-card': DnsdistCard;
  }
}
