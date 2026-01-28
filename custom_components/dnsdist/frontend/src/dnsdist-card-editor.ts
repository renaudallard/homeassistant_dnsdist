/**
 * dnsdist Card Configuration Editor
 *
 * Visual editor for configuring the dnsdist Lovelace card.
 */
import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import type { DnsdistCardConfig, HomeAssistant } from './types';

@customElement('dnsdist-card-editor')
export class DnsdistCardEditor extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    .form-row {
      margin-bottom: 16px;
    }
    .form-row label {
      display: block;
      margin-bottom: 4px;
      font-weight: 500;
    }
    .form-hint {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }
    ha-textfield {
      display: block;
      width: 100%;
    }
    ha-formfield {
      display: block;
      padding: 8px 0;
    }
    .prefix-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .prefix-chip {
      padding: 4px 12px;
      border-radius: 16px;
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      font-size: 12px;
      cursor: pointer;
      border: none;
    }
    .prefix-chip:hover {
      opacity: 0.8;
    }
    input[type="text"] {
      width: 100%;
      padding: 8px 12px;
      border: 1px solid var(--divider-color, #ccc);
      border-radius: 4px;
      font-size: 14px;
      box-sizing: border-box;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color, #000);
    }
    input[type="text"]:focus {
      outline: none;
      border-color: var(--primary-color);
    }
    input[type="checkbox"] {
      margin-right: 8px;
      width: 18px;
      height: 18px;
      cursor: pointer;
    }
    label {
      display: flex;
      align-items: center;
      cursor: pointer;
    }
  `;

  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config!: DnsdistCardConfig;

  setConfig(config: DnsdistCardConfig) {
    this._config = { ...config };
  }

  private _updateConfig(key: string, value: unknown) {
    if (!this._config) return;

    const newConfig = { ...this._config, [key]: value };
    this._config = newConfig;

    this.dispatchEvent(
      new CustomEvent('config-changed', {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }

  private _getAvailablePrefixes(): string[] {
    if (!this.hass?.states) return [];

    const prefixes = new Set<string>();
    // Match various dnsdist sensor patterns
    const patterns = [
      /^sensor\.(.+?)_total_queries$/,
      /^sensor\.(.+?)_uptime$/,
      /^sensor\.(.+?)_cpu_usage$/,
      /^sensor\.(.+?)_responses$/,
      /^sensor\.(.+?)_filter_/,  // Filter sensors
    ];

    for (const entityId of Object.keys(this.hass.states)) {
      for (const pattern of patterns) {
        const match = entityId.match(pattern);
        if (match) {
          prefixes.add(match[1]);
          break;
        }
      }
    }

    return Array.from(prefixes).sort();
  }

  protected render() {
    if (!this.hass || !this._config) {
      return html`<div>Loading...</div>`;
    }

    const prefixes = this._getAvailablePrefixes();

    return html`
      <div class="form-row">
        <label for="entity_prefix">Entity Prefix *</label>
        <input
          type="text"
          id="entity_prefix"
          .value=${this._config.entity_prefix || ''}
          @input=${(e: Event) => {
            const value = (e.target as HTMLInputElement).value;
            this._updateConfig('entity_prefix', value);
          }}
          placeholder="e.g., dns1"
        />
        ${prefixes.length > 0
          ? html`
              <div class="form-hint">Click to select:</div>
              <div class="prefix-chips">
                ${prefixes.map(
                  (prefix) => html`
                    <button
                      type="button"
                      class="prefix-chip"
                      @click=${() => this._updateConfig('entity_prefix', prefix)}
                    >
                      ${prefix}
                    </button>
                  `
                )}
              </div>
            `
          : html`<div class="form-hint">No dnsdist entities detected</div>`}
      </div>

      <div class="form-row">
        <label for="title">Card Title</label>
        <input
          type="text"
          id="title"
          .value=${this._config.title || ''}
          @input=${(e: Event) => {
            const value = (e.target as HTMLInputElement).value;
            this._updateConfig('title', value);
          }}
          placeholder="Optional custom title"
        />
        <div class="form-hint">
          Leave empty to use the entity prefix as title
        </div>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${this._config.show_filters !== false}
            @change=${(e: Event) => {
              const checked = (e.target as HTMLInputElement).checked;
              this._updateConfig('show_filters', checked);
            }}
          />
          Show Filtering Rules
        </label>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${this._config.show_actions !== false}
            @change=${(e: Event) => {
              const checked = (e.target as HTMLInputElement).checked;
              this._updateConfig('show_actions', checked);
            }}
          />
          Show Action Buttons
        </label>
      </div>

      <div class="form-row">
        <label>
          <input
            type="checkbox"
            .checked=${this._config.compact === true}
            @change=${(e: Event) => {
              const checked = (e.target as HTMLInputElement).checked;
              this._updateConfig('compact', checked);
            }}
          />
          Compact Mode
        </label>
        <div class="form-hint">
          Use smaller sizes for sidebar placement
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'dnsdist-card-editor': DnsdistCardEditor;
  }
}
