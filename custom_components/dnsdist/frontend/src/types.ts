/**
 * TypeScript interfaces for dnsdist Lovelace card.
 */

export interface DnsdistCardConfig {
  type: string;
  entity_prefix: string;
  title?: string;
  show_graphs?: boolean;
  show_filters?: boolean;
  show_dynamic_rules?: boolean;
  show_actions?: boolean;
  compact?: boolean;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  callService: (
    domain: string,
    service: string,
    serviceData?: Record<string, unknown>
  ) => Promise<void>;
  connection: {
    subscribeEvents: (
      callback: (event: unknown) => void,
      eventType: string
    ) => Promise<() => void>;
  };
  themes: {
    darkMode: boolean;
  };
  locale: {
    language: string;
  };
}

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
  last_changed: string;
  last_updated: string;
}

export interface FilteringRule {
  id?: number;
  uuid?: string;
  name?: string;
  action?: string;
  rule?: string;
  type?: string;
  enabled?: boolean;
  bypass?: boolean;
  matches: number;
  sources?: Record<string, number>;
}

export interface DynamicRule {
  network?: string;
  reason?: string;
  action?: string;
  seconds?: number;
  ebpf?: boolean;
  warning?: boolean;
  blocks: number;
  sources?: Record<string, number>;
  last_updated?: string;  // ISO timestamp for calculating elapsed time
}

export interface LovelaceCardEditor extends HTMLElement {
  setConfig(config: DnsdistCardConfig): void;
}

declare global {
  interface Window {
    customCards?: Array<{
      type: string;
      name: string;
      description: string;
      preview?: boolean;
    }>;
  }
}
