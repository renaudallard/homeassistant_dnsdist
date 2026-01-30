/**
 * CSS styles for dnsdist Lovelace card.
 */
import { css } from 'lit';

export const cardStyles = css`
  :host {
    --dnsdist-card-background: var(--ha-card-background, var(--card-background-color, #fff));
    --dnsdist-primary-text: var(--primary-text-color, #212121);
    --dnsdist-secondary-text: var(--secondary-text-color, #727272);
    --dnsdist-accent: var(--primary-color, #03a9f4);
    --dnsdist-success: var(--success-color, #4caf50);
    --dnsdist-warning: var(--warning-color, #ff9800);
    --dnsdist-error: var(--error-color, #f44336);
    --dnsdist-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --dnsdist-border-radius: var(--ha-card-border-radius, 12px);
  }

  ha-card {
    padding: 16px;
    overflow: hidden;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--dnsdist-divider);
  }

  .card-title {
    font-size: 1.2rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
  }

  .status-ok {
    background: rgba(76, 175, 80, 0.2);
    color: var(--dnsdist-success);
  }

  .status-warning {
    background: rgba(255, 152, 0, 0.2);
    color: var(--dnsdist-warning);
  }

  .status-critical {
    background: rgba(244, 67, 54, 0.2);
    color: var(--dnsdist-error);
  }

  .status-unknown {
    background: rgba(158, 158, 158, 0.2);
    color: var(--dnsdist-secondary-text);
  }

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }

  .stat-tile {
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    transition: box-shadow 0.2s ease;
  }

  .stat-tile:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .stat-value {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
  }

  .stat-label {
    font-size: 0.75rem;
    color: var(--dnsdist-secondary-text);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .stat-icon {
    margin-bottom: 4px;
    color: var(--dnsdist-accent);
    --mdc-icon-size: 24px;
  }

  /* Gauge Styles */
  .gauge-container {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }

  .gauge {
    position: relative;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 4px;
  }

  .gauge-svg {
    width: 100px;
    height: 90px;
    overflow: visible;
    flex-shrink: 0;
  }

  .gauge-info {
    display: flex;
    flex-direction: column;
    min-width: 50px;
  }

  .gauge-info-left {
    text-align: right;
  }

  .gauge-info-right {
    text-align: left;
  }

  .gauge-arc-path {
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.15));
  }

  .gauge-needle-group {
    transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .gauge-needle {
    stroke: var(--dnsdist-primary-text, #212121);
    stroke-width: 2.5;
    stroke-linecap: round;
  }

  .gauge-pivot {
    fill: var(--dnsdist-primary-text, #212121);
  }

  .gauge-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
  }

  .gauge-label {
    font-size: 0.7rem;
    color: var(--dnsdist-secondary-text);
    text-transform: uppercase;
  }

  /* Section Headers */
  .section-header {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--dnsdist-secondary-text);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 16px 0 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--dnsdist-divider);
  }

  /* Counters Grid */
  .counters-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }

  .counter-tile {
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    padding: 10px 8px;
    text-align: center;
  }

  .counter-value {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--dnsdist-primary-text);
  }

  .counter-label {
    font-size: 0.65rem;
    color: var(--dnsdist-secondary-text);
    margin-top: 2px;
    text-transform: uppercase;
  }

  /* Filter Rules */
  .filters-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 300px;
    overflow-y: auto;
  }

  .filter-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .filter-item:hover {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.05));
  }

  .filter-item.expanded {
    flex-wrap: wrap;
  }

  .filter-main {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .filter-name {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .filter-matches {
    font-size: 1rem;
    font-weight: 600;
    color: var(--dnsdist-accent);
    min-width: 50px;
    text-align: right;
  }

  .filter-action {
    display: inline-flex;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    background: rgba(3, 169, 244, 0.15);
    color: var(--dnsdist-accent);
  }

  .filter-action.drop {
    background: rgba(244, 67, 54, 0.15);
    color: var(--dnsdist-error);
  }

  .filter-action.allow {
    background: rgba(76, 175, 80, 0.15);
    color: var(--dnsdist-success);
  }

  .filter-details {
    width: 100%;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--dnsdist-divider);
    font-size: 0.8rem;
    color: var(--dnsdist-secondary-text);
  }

  .filter-detail-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
  }

  .filter-detail-label {
    font-weight: 500;
  }

  .filter-detail-value {
    font-family: monospace;
    word-break: break-all;
    text-align: right;
    max-width: 60%;
  }

  /* Action Buttons */
  .actions-container {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 16px;
  }

  .action-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background: var(--dnsdist-accent);
    color: white;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s ease;
  }

  .action-button:hover {
    opacity: 0.9;
  }

  .action-button:active {
    opacity: 0.8;
  }

  .action-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-button ha-icon {
    --mdc-icon-size: 18px;
  }

  .action-button.toggle-off {
    background: var(--dnsdist-divider);
    color: var(--dnsdist-secondary-text);
  }

  /* Compact Mode */
  :host([compact]) .gauge-container {
    gap: 4px;
  }

  :host([compact]) .gauge {
    gap: 2px;
  }

  :host([compact]) .gauge-svg {
    width: 80px;
    height: 72px;
  }

  :host([compact]) .gauge-info {
    min-width: 40px;
  }

  :host([compact]) .gauge-value {
    font-size: 0.95rem;
  }

  :host([compact]) .gauge-label {
    font-size: 0.6rem;
  }

  :host([compact]) .stat-tile {
    padding: 8px;
  }

  :host([compact]) .stat-value {
    font-size: 1.1rem;
  }

  /* Uptime display */
  .uptime-display {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px;
    background: var(--ha-card-background, var(--card-background-color));
    border: 1px solid var(--dnsdist-divider);
    border-radius: 8px;
    margin-bottom: 16px;
  }

  .uptime-value {
    font-size: 1rem;
    font-weight: 500;
    color: var(--dnsdist-primary-text);
  }

  .uptime-label {
    font-size: 0.75rem;
    color: var(--dnsdist-secondary-text);
  }

  /* Empty state */
  .empty-state {
    text-align: center;
    padding: 24px;
    color: var(--dnsdist-secondary-text);
  }

  .empty-state ha-icon {
    --mdc-icon-size: 48px;
    opacity: 0.5;
    margin-bottom: 8px;
  }

  /* Loading state */
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    color: var(--dnsdist-secondary-text);
  }

  /* Confirmation dialog overlay */
  .confirm-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .confirm-dialog {
    background: var(--dnsdist-card-background);
    padding: 24px;
    border-radius: var(--dnsdist-border-radius);
    max-width: 320px;
    text-align: center;
  }

  .confirm-title {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--dnsdist-primary-text);
  }

  .confirm-message {
    font-size: 0.9rem;
    color: var(--dnsdist-secondary-text);
    margin-bottom: 16px;
  }

  .confirm-buttons {
    display: flex;
    gap: 8px;
    justify-content: center;
  }

  .confirm-cancel {
    background: var(--dnsdist-divider);
    color: var(--dnsdist-primary-text);
  }

  .confirm-confirm {
    background: var(--dnsdist-error);
  }
`;

export const editorStyles = css`
  :host {
    display: block;
  }

  .form-group {
    margin-bottom: 16px;
  }

  .form-label {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--primary-text-color);
    margin-bottom: 4px;
  }

  .form-hint {
    font-size: 0.75rem;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }

  ha-textfield,
  ha-select {
    display: block;
    width: 100%;
  }

  ha-formfield {
    display: block;
    margin-bottom: 8px;
  }
`;
