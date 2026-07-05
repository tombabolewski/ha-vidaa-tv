const CARD_TYPE = "vidaa-tv-remote-card";
const DEFAULT_REMOTE = "remote.vidaa_tv_remote";

const BUTTONS = [
  [
    { icon: "mdi:power", key: "POWER", action: "power", className: "danger" },
    { icon: "mdi:information", key: "KEY_INFO" },
    { icon: "mdi:home", key: "KEY_HOME" },
  ],
  [{ spacer: true }, { icon: "mdi:arrow-up", key: "KEY_UP" }, { spacer: true }],
  [
    { icon: "mdi:arrow-left", key: "KEY_LEFT" },
    { icon: "mdi:checkbox-blank-circle", key: "KEY_OK", className: "ok" },
    { icon: "mdi:arrow-right", key: "KEY_RIGHT" },
  ],
  [
    { spacer: true },
    { icon: "mdi:arrow-down", key: "KEY_DOWN" },
    { spacer: true },
  ],
  [
    { icon: "mdi:arrow-u-left-top", key: "KEY_RETURNS", label: "Back" },
    { icon: "mdi:menu", key: "KEY_MENU", label: "Menu" },
    { icon: "mdi:close-box", key: "KEY_EXIT", label: "Exit" },
  ],
  [
    { icon: "mdi:volume-minus", key: "KEY_VOLUMEDOWN", label: "VOL-" },
    { icon: "mdi:volume-off", key: "KEY_MUTE", label: "Mute" },
    { icon: "mdi:volume-plus", key: "KEY_VOLUMEUP", label: "VOL+" },
  ],
  [
    { icon: "mdi:arrow-up-bold", key: "KEY_CHANNELUP", label: "CH+" },
    { icon: "mdi:arrow-down-bold", key: "KEY_CHANNELDOWN", label: "CH-" },
  ],
  [
    { icon: "mdi:rewind", key: "KEY_BACK" },
    { icon: "mdi:play", key: "KEY_PLAY" },
    { icon: "mdi:pause", key: "KEY_PAUSE" },
    { icon: "mdi:stop", key: "KEY_STOP" },
    { icon: "mdi:fast-forward", key: "KEY_FORWARDS" },
  ],
];

class VidaaTVRemoteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._lastSelectCall = { key: "", time: 0 };
    this._lastRenderKey = "";
    this._pending = {
      app: { value: "", time: 0 },
      source: { value: "", time: 0 },
    };
    this._selectInteractingUntil = 0;
  }

  setConfig(config) {
    config = config || {};
    this.config = {
      entity: config.entity || config.remote_entity || DEFAULT_REMOTE,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return {
      columns: 6,
      min_columns: 3,
      rows: 8,
      min_rows: 6,
    };
  }

  static getStubConfig() {
    return { entity: DEFAULT_REMOTE };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { domain: "remote" } },
        },
        {
          name: "media_player_entity",
          selector: { entity: { domain: "media_player" } },
        },
        {
          name: "app_sensor_entity",
          selector: { entity: { domain: "sensor" } },
        },
        {
          name: "source_sensor_entity",
          selector: { entity: { domain: "sensor" } },
        },
      ],
    };
  }

  _baseObjectId(entityId) {
    return entityId ? entityId.split(".").slice(1).join(".") : "vidaa_tv";
  }

  _objectIdCandidates(entityId) {
    const base = this._baseObjectId(entityId);
    const candidates = [base];
    for (const suffix of ["_remote", "_current_app", "_current_source"]) {
      if (base.endsWith(suffix)) {
        candidates.push(base.slice(0, -suffix.length));
      }
    }
    return [...new Set(candidates)];
  }

  _remoteEntity() {
    const entityId = this.config.entity || this.config.remote_entity;
    if (this.config.remote_entity) {
      return this.config.remote_entity;
    }
    if (entityId?.startsWith("remote.")) {
      return entityId;
    }
    for (const base of this._objectIdCandidates(entityId)) {
      for (const candidate of [`remote.${base}_remote`, `remote.${base}`]) {
        if (this._hass?.states[candidate]) {
          return candidate;
        }
      }
    }
    return DEFAULT_REMOTE;
  }

  _mediaPlayerEntity() {
    if (this.config.media_player_entity) {
      return this.config.media_player_entity;
    }
    for (const base of this._objectIdCandidates(this._remoteEntity())) {
      const candidate = `media_player.${base}`;
      if (this._hass?.states[candidate]) {
        return candidate;
      }
    }
    return undefined;
  }

  _remoteState() {
    return this._hass?.states[this._remoteEntity()];
  }

  _mediaPlayerState() {
    const mediaPlayer = this._mediaPlayerEntity();
    return mediaPlayer ? this._hass?.states[mediaPlayer] : undefined;
  }

  _sensorEntity(kind) {
    const configKey = kind === "app" ? "app_sensor_entity" : "source_sensor_entity";
    if (this.config[configKey]) {
      return this.config[configKey];
    }
    for (const base of this._objectIdCandidates(this._remoteEntity())) {
      const candidate = `sensor.${base}_current_${kind}`;
      if (this._hass?.states[candidate]) {
        return candidate;
      }
    }
    return undefined;
  }

  _friendlyState(entityId) {
    const stateObj = entityId ? this._hass?.states[entityId] : undefined;
    if (!stateObj) {
      return "Unavailable";
    }
    return stateObj.state || "Unknown";
  }

  _setPending(type, value) {
    this._pending[type] = { value, time: Date.now() };
  }

  _normalize(value) {
    return String(value || "").toLowerCase();
  }

  _displayValue(type, stateValue) {
    const pending = this._pending[type];
    if (!pending?.value) {
      return stateValue;
    }

    const normalizedState = this._normalize(stateValue);
    const normalizedPending = this._normalize(pending.value);
    if (normalizedState === normalizedPending || Date.now() - pending.time > 10000) {
      this._pending[type] = { value: "", time: 0 };
      return stateValue;
    }

    return pending.value;
  }

  _isSelectActive() {
    return (
      this.shadowRoot?.activeElement?.tagName === "SELECT" ||
      Date.now() < this._selectInteractingUntil
    );
  }

  _renderKey(remote, mediaPlayer, appSensor, sourceSensor, appOptions, sourceOptions) {
    const remoteState = this._hass.states[remote];
    const mediaPlayerState = mediaPlayer ? this._hass.states[mediaPlayer] : undefined;
    const appState = appSensor ? this._hass.states[appSensor] : undefined;
    const sourceState = sourceSensor ? this._hass.states[sourceSensor] : undefined;

    return JSON.stringify({
      remote,
      mediaPlayer,
      appSensor,
      sourceSensor,
      remoteState: remoteState?.state,
      remoteName: remoteState?.attributes?.friendly_name,
      mediaPlayerState: mediaPlayerState?.state,
      mediaPlayerName: mediaPlayerState?.attributes?.friendly_name,
      mediaPlayerSource: mediaPlayerState?.attributes?.source,
      mediaPlayerApp: mediaPlayerState?.attributes?.app_name,
      appState: appState?.state,
      sourceState: sourceState?.state,
      appOptions,
      sourceOptions,
      pendingApp: this._pending.app.value,
      pendingSource: this._pending.source.value,
    });
  }

  _escape(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[char]);
  }

  _callRemote(key) {
    const remote = this._remoteEntity();
    this._hass.callService("remote", "send_command", {
      entity_id: remote,
      command: key,
    });
  }

  _selectSource(source) {
    const mediaPlayer = this._mediaPlayerEntity();
    if (!mediaPlayer || !source) {
      return;
    }

    this._hass.callService("media_player", "select_source", {
      entity_id: mediaPlayer,
      source,
    });
  }

  _handleSelectChange(element, value) {
    const type = element.dataset.select;
    if (!type || !value) {
      return;
    }

    const now = Date.now();
    const dedupeKey = `${type}:${value}`;
    if (
      this._lastSelectCall.key === dedupeKey &&
      now - this._lastSelectCall.time < 750
    ) {
      return;
    }
    this._lastSelectCall = { key: dedupeKey, time: now };
    this._setPending(type, value);
    this._selectInteractingUntil = 0;

    if (type === "app") {
      this._setPending("source", "Unknown");
      this._launchApp(value);
      this._render(true);
      return;
    }
    this._setPending("app", "Unknown");
    this._selectSource(value);
    this._render(true);
  }

  _launchApp(app) {
    const mediaPlayer = this._mediaPlayerEntity();
    if (!mediaPlayer || !app) {
      return;
    }

    this._hass.callService("media_player", "play_media", {
      entity_id: mediaPlayer,
      media_content_type: "app",
      media_content_id: app,
    });
  }

  _sourceOptions() {
    const mediaPlayerState = this._mediaPlayerState();
    const sourceList = mediaPlayerState?.attributes?.source_list;
    if (!Array.isArray(sourceList)) {
      return [];
    }

    const appOptions = this._appOptions();
    return sourceList.filter(
      (source) =>
        typeof source === "string" && source && !appOptions.includes(source),
    );
  }

  _appOptions() {
    const remoteState = this._remoteState();
    const activityList = remoteState?.attributes?.activity_list;
    if (Array.isArray(activityList) && activityList.length > 0) {
      return activityList.filter((app) => typeof app === "string" && app);
    }

    const mediaPlayerState = this._mediaPlayerState();
    const appName = mediaPlayerState?.attributes?.app_name;
    return typeof appName === "string" && appName ? [appName] : [];
  }

  _selectTemplate(label, value, options, type) {
    const normalizedValue = this._normalize(value);
    const currentValue =
      normalizedValue === "unavailable"
        ? ""
        : normalizedValue === "unknown"
          ? "Unknown"
          : value;
    const selectOptions =
      currentValue && !options.includes(currentValue)
        ? [currentValue, ...options]
        : options;
    const hasOptions = selectOptions.length > 0;
    return `
      <div class="select-item">
        <label>${label}</label>
        <select
          data-select="${type}"
          data-value="${this._escape(currentValue)}"
          ${hasOptions ? "" : "disabled"}
        >
          ${
            hasOptions
              ? selectOptions
                  .map(
                    (option) => `
                      <option
                        value="${this._escape(option)}"
                        ${option === currentValue ? "selected" : ""}
                      >
                        ${this._escape(option)}
                      </option>
                    `,
                  )
                  .join("")
              : `<option value="">Unavailable</option>`
          }
        </select>
      </div>
    `;
  }

  _togglePower() {
    const mediaPlayer = this._mediaPlayerEntity();
    if (mediaPlayer) {
      this._hass.callService("homeassistant", "toggle", {
        entity_id: mediaPlayer,
      });
      return;
    }
    this._callRemote("KEY_POWER");
  }

  _handleButton(button) {
    if (button.action === "power") {
      this._togglePower();
      return;
    }
    this._callRemote(button.key);
  }

  _buttonTemplate(button) {
    if (button.spacer) {
      return `<div class="spacer"></div>`;
    }
    const label = button.label ? `<span>${button.label}</span>` : "";
    const className = button.className ? ` ${button.className}` : "";
    return `
      <button class="remote-button${className}" data-key="${button.key}">
        <ha-icon icon="${button.icon}"></ha-icon>
        ${label}
      </button>
    `;
  }

  _render(force = false) {
    if (!this._hass || !this.config) {
      return;
    }

    const remote = this._remoteEntity();
    const mediaPlayer = this._mediaPlayerEntity();
    const appSensor = this._sensorEntity("app");
    const sourceSensor = this._sensorEntity("source");
    const appStateValue = this._friendlyState(appSensor);
    const sourceStateValue = this._friendlyState(sourceSensor);
    const appValue = this._displayValue("app", appStateValue);
    const sourceValue = this._displayValue("source", sourceStateValue);
    const appOptions = this._appOptions();
    const sourceOptions = this._sourceOptions();
    const renderKey = this._renderKey(
      remote,
      mediaPlayer,
      appSensor,
      sourceSensor,
      appOptions,
      sourceOptions,
    );

    if (!force && (renderKey === this._lastRenderKey || this._isSelectActive())) {
      return;
    }
    this._lastRenderKey = renderKey;

    const title =
      this._hass.states[mediaPlayer]?.attributes?.friendly_name ||
      this._hass.states[remote]?.attributes?.friendly_name ||
      "Vidaa TV";
    const remoteAvailable = Boolean(this._hass.states[remote]);

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 16px;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 14px;
        }
        .title {
          font-size: 20px;
          font-weight: 500;
          line-height: 1.2;
        }
        .status {
          color: var(--secondary-text-color);
          font-size: 13px;
          text-transform: capitalize;
        }
        .grid {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .row {
          display: grid;
          gap: 8px;
          grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
        }
        .remote-button,
        .spacer {
          min-height: 48px;
          border-radius: 8px;
        }
        .remote-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 7px;
          border: 1px solid var(--divider-color);
          color: var(--primary-text-color);
          background: var(--ha-card-background, var(--card-background-color));
          cursor: pointer;
          font: inherit;
          font-weight: 500;
        }
        .remote-button:hover {
          background: var(--secondary-background-color);
        }
        .remote-button:active {
          transform: translateY(1px);
        }
        .remote-button ha-icon {
          color: var(--primary-color);
        }
        .remote-button.ok ha-icon {
          --mdc-icon-size: 28px;
        }
        .remote-button.danger ha-icon {
          color: var(--error-color);
        }
        .spacer {
          border: 1px solid var(--divider-color);
          opacity: 0.35;
        }
        .selects {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          margin-top: 12px;
        }
        .select-item {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 8px 12px 12px;
          min-width: 0;
        }
        .select-item label {
          display: block;
          color: var(--secondary-text-color);
          font-size: 12px;
          margin-bottom: 6px;
        }
        select {
          width: 100%;
          min-height: 42px;
          border: 0;
          border-bottom: 1px solid var(--secondary-text-color);
          border-radius: 4px 4px 0 0;
          padding: 0 32px 0 12px;
          color: var(--primary-text-color);
          background: var(--secondary-background-color);
          font: inherit;
          outline: none;
        }
        select:focus {
          border-bottom-color: var(--primary-color);
        }
        .missing {
          color: var(--error-color);
          font-size: 13px;
          margin-top: 12px;
        }
      </style>
      <ha-card>
        <div class="header">
          <div>
            <div class="title">${this._escape(title)}</div>
            <div class="status">${this._escape(this._friendlyState(mediaPlayer || remote))}</div>
          </div>
          <ha-icon icon="mdi:remote-tv"></ha-icon>
        </div>
        <div class="grid">
          ${BUTTONS.map(
            (row) => `
              <div class="row" style="--columns: ${row.length}">
                ${row.map((button) => this._buttonTemplate(button)).join("")}
              </div>
            `,
          ).join("")}
        </div>
        <div class="selects">
          ${this._selectTemplate("App", appValue, appOptions, "app")}
          ${this._selectTemplate("Source", sourceValue, sourceOptions, "source")}
        </div>
        ${
          remoteAvailable
            ? ""
            : `<div class="missing">Remote entity ${this._escape(remote)} was not found.</div>`
        }
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".remote-button").forEach((element) => {
      element.addEventListener("click", () => {
        const key = element.dataset.key;
        const button = BUTTONS.flat().find((item) => item.key === key);
        if (button) {
          this._handleButton(button);
        }
      });
    });

    this.shadowRoot.querySelectorAll("select").forEach((element) => {
      element.value = element.dataset.value;
      element.addEventListener("pointerdown", () => {
        this._selectInteractingUntil = Date.now() + 2000;
      });
      element.addEventListener("focus", () => {
        this._selectInteractingUntil = Date.now() + 2000;
      });
      element.addEventListener("change", () => {
        this._handleSelectChange(element, element.value);
      });
      element.addEventListener("blur", () => {
        this._selectInteractingUntil = 0;
        this._render(true);
      });
    });
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, VidaaTVRemoteCard);
}

window.customCards = window.customCards || [];
const cardMetadata = {
  type: CARD_TYPE,
  name: "Vidaa TV Remote",
  description: "Remote control card for Vidaa TV devices.",
  documentationURL: "https://github.com/tombabolewski/ha-vidaa-tv",
  getEntitySuggestion: (hass, entityId) => {
    if (!entityId || !hass?.states) {
      return null;
    }

    const domain = entityId.split(".")[0];
    if (!["remote", "media_player"].includes(domain)) {
      return null;
    }

    const stateObj = hass.states[entityId];
    const friendlyName = stateObj?.attributes?.friendly_name || "";
    const objectId = entityId.split(".").slice(1).join(".");
    const base = objectId.endsWith("_remote")
      ? objectId.slice(0, -"_remote".length)
      : objectId;
    const looksLikeVidaa =
      objectId.includes("vidaa") || friendlyName.toLowerCase().includes("vidaa");
    const relatedVidaaEntities = [
      `button.${base}_power`,
      `sensor.${base}_current_app`,
      `sensor.${base}_current_source`,
      `remote.${base}_remote`,
    ];
    const looksRelated =
      looksLikeVidaa || relatedVidaaEntities.some((candidate) => hass.states[candidate]);

    if (!looksRelated) {
      return null;
    }

    const remoteCandidates =
      domain === "remote"
        ? [entityId]
        : [`remote.${base}_remote`, `remote.${base}`];
    const remote =
      remoteCandidates.find((candidate) => hass.states[candidate]) ||
      remoteCandidates[0];
    const mediaPlayer =
      domain === "media_player" ? entityId : `media_player.${base}`;
    const config = {
      type: `custom:${CARD_TYPE}`,
      entity: remote,
    };

    if (hass.states[mediaPlayer]) {
      config.media_player_entity = mediaPlayer;
    }

    return { config };
  },
};
const existingCardIndex = window.customCards.findIndex(
  (card) => card?.type === CARD_TYPE,
);
if (existingCardIndex === -1) {
  window.customCards.push(cardMetadata);
} else {
  window.customCards[existingCardIndex] = cardMetadata;
}
