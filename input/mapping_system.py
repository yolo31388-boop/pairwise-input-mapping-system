"""
pairwise-input-mapping-system - InputMappingSystem

A complete input mapping system for games:

- bind_action():   conflict detection, per-device bindings, persistence
- process_input(): key->action mapping, combo keys (Ctrl+Shift+A), analog dead zone
- load_config():   version check, migration, validation
- get_key_hint():  localized hints with icons, always reflects current bindings
- record_input():  timestamps, device filtering, compression
"""

from __future__ import annotations

import json
import os
import time
import zlib

CONFIG_VERSION = 3
DEFAULT_DEAD_ZONE = 0.15
SUPPORTED_DEVICES = ("keyboard", "mouse", "gamepad")
SUPPORTED_LOCALES = ("zh_CN", "en_US")

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")
MODIFIER_ALIASES = {
    "ctrl": "Ctrl", "control": "Ctrl",
    "alt": "Alt", "option": "Alt",
    "shift": "Shift",
    "meta": "Meta", "cmd": "Meta", "command": "Meta", "super": "Meta", "win": "Meta",
}

DEFAULT_BINDINGS = {
    "keyboard": {
        "jump": "Space",
        "crouch": "C",
        "interact": "E",
        "pause": "Escape",
    },
    "mouse": {
        "fire": "mouse_left",
        "aim": "mouse_right",
    },
    "gamepad": {
        "jump": "button_a",
        "fire": "trigger_right",
    },
}

LOCALIZATIONS = {
    "zh_CN": {
        "Space": "空格键",
        "Escape": "Esc 键",
        "mouse_left": "鼠标左键",
        "mouse_right": "鼠标右键",
        "mouse_middle": "鼠标中键",
        "mouse_side": "鼠标侧键",
        "mouse_x1": "鼠标侧键 1",
        "mouse_x2": "鼠标侧键 2",
        "button_a": "手柄 A 键",
        "button_b": "手柄 B 键",
        "trigger_right": "手柄右扳机",
        "trigger_left": "手柄左扳机",
        "Ctrl": "Ctrl",
        "Alt": "Alt",
        "Shift": "Shift",
        "Meta": "Win",
    },
    "en_US": {
        "Space": "Space",
        "Escape": "Esc",
        "mouse_left": "Left Mouse Button",
        "mouse_right": "Right Mouse Button",
        "mouse_middle": "Middle Mouse Button",
        "mouse_side": "Mouse Side Button",
        "mouse_x1": "Mouse Side Button 1",
        "mouse_x2": "Mouse Side Button 2",
        "button_a": "Gamepad A",
        "button_b": "Gamepad B",
        "trigger_right": "Right Trigger",
        "trigger_left": "Left Trigger",
        "Ctrl": "Ctrl",
        "Alt": "Alt",
        "Shift": "Shift",
        "Meta": "Meta",
    },
}

DEVICE_ICONS = {
    "keyboard": "⌨",
    "mouse": "🖱",
    "gamepad": "🎮",
}

KEY_ICONS = {
    "mouse_left": "🖱L",
    "mouse_right": "🖱R",
    "mouse_middle": "🖱M",
    "mouse_side": "🖱⇧",
    "mouse_x1": "🖱X1",
    "mouse_x2": "🖱X2",
    "button_a": "🎮A",
    "button_b": "🎮B",
    "trigger_right": "🎮RT",
    "trigger_left": "🎮LT",
}


class KeyConflictError(ValueError):
    """Raised when a key is already bound to another action on the same device."""


class ConfigVersionError(ValueError):
    """Raised when a config file version is newer than this system supports."""


class ConfigValidationError(ValueError):
    """Raised when a config file is structurally invalid."""


def normalize_combo(key, modifiers=()):
    """Build a canonical combo string like 'Ctrl+Shift+A' from a key and modifiers."""
    parts = []
    if isinstance(key, str) and "+" in key:
        pieces = [p.strip() for p in key.split("+") if p.strip()]
        key = pieces[-1] if pieces else ""
        modifiers = list(modifiers) + pieces[:-1]
    mods = []
    for mod in modifiers or ():
        canonical = MODIFIER_ALIASES.get(str(mod).strip().lower())
        if canonical and canonical not in mods:
            mods.append(canonical)
    mods.sort(key=MODIFIER_ORDER.index)
    parts.extend(mods)
    if key:
        key = str(key)
        if len(key) == 1 and key.isalpha():
            key = key.upper()
        parts.append(key)
    return "+".join(parts)


class InputMappingSystem:
    CONFIG_VERSION = CONFIG_VERSION
    DEFAULT_DEAD_ZONE = DEFAULT_DEAD_ZONE

    def __init__(self, config_path=None, locale="zh_CN", dead_zone=DEFAULT_DEAD_ZONE):
        self.config_path = config_path
        self.locale = locale if locale in SUPPORTED_LOCALES else "zh_CN"
        self.dead_zone = self._clamp_dead_zone(dead_zone)
        # Bindings are stored per device: {device: {action: key}}
        self.bindings = {device: dict(keys) for device, keys in DEFAULT_BINDINGS.items()}
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)

    # ------------------------------------------------------------------
    # Binding
    # ------------------------------------------------------------------
    def bind_action(self, action=None, key=None, device="keyboard", persist=True):
        """Bind an action to a key on a specific device.

        - Conflict detection: raises KeyConflictError if the key is already
          bound to a different action on the same device.
        - Device separation: the same key may be bound on different devices.
        - Persistence: saves the config to disk when a config_path is set.
        """
        if action is None:
            # No-arg introspection: return a snapshot of current bindings.
            return {dev: dict(keys) for dev, keys in self.bindings.items()}
        device = self._check_device(device)
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"invalid key for action {action!r}: {key!r}")
        key = normalize_combo(key)

        device_bindings = self.bindings.setdefault(device, {})
        for other_action, other_key in device_bindings.items():
            if other_key == key and other_action != action:
                raise KeyConflictError(
                    f"key {key!r} on device {device!r} is already bound to "
                    f"action {other_action!r}"
                )
        device_bindings[action] = key
        if persist:
            self.save_config()
        return {"action": action, "key": key, "device": device, "conflict": None}

    def unbind_action(self, action, device="keyboard", persist=True):
        device = self._check_device(device)
        removed = self.bindings.get(device, {}).pop(action, None)
        if removed is not None and persist:
            self.save_config()
        return removed

    def reset_to_defaults(self, persist=True):
        """Restore default bindings (re-enables the greyed-out 'reset' button)."""
        self.bindings = {device: dict(keys) for device, keys in DEFAULT_BINDINGS.items()}
        if persist:
            self.save_config()
        return {dev: dict(keys) for dev, keys in self.bindings.items()}

    def find_conflict(self, key, device="keyboard"):
        """Return the action currently bound to key on device, or None."""
        key = normalize_combo(key)
        for action, bound_key in self.bindings.get(device, {}).items():
            if bound_key == key:
                return action
        return None

    # ------------------------------------------------------------------
    # Input processing
    # ------------------------------------------------------------------
    def process_input(self, raw=None, device="keyboard", modifiers=(), value=None):
        """Map a raw input to the bound action(s).

        - Mapping: raw keys are translated through the device bindings.
        - Combo keys: modifiers + key are normalized (e.g. Ctrl+Shift+A).
        - Dead zone: analog values below the dead zone are ignored.
        Returns a list of triggered action names (empty if none).
        """
        if raw is None:
            return []
        device = self._check_device(device)

        if value is not None:
            try:
                magnitude = abs(float(value))
            except (TypeError, ValueError):
                magnitude = 0.0
            if magnitude < self.dead_zone:
                return []

        combo = normalize_combo(raw, modifiers)
        triggered = []
        for action, bound_key in self.bindings.get(device, {}).items():
            if bound_key == combo:
                triggered.append(action)
        return triggered

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def default_config(self):
        return {
            "version": CONFIG_VERSION,
            "locale": self.locale,
            "dead_zone": self.dead_zone,
            "bindings": {dev: dict(keys) for dev, keys in self.bindings.items()},
        }

    def save_config(self, path=None):
        path = path or self.config_path
        if not path:
            return None
        config = self.default_config()
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
        return config

    def load_config(self, path=None):
        """Load config with version check, migration and validation.

        - Version check: newer configs raise ConfigVersionError.
        - Migration: older configs are upgraded step by step.
        - Validation: illegal values are repaired with defaults.
        """
        path = path or self.config_path
        if not path or not os.path.exists(path):
            return self.default_config()
        with open(path, "r", encoding="utf-8") as fh:
            try:
                config = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ConfigValidationError(f"config is not valid JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise ConfigValidationError("config root must be an object")

        config = self._migrate(config)
        config = self._validate(config)

        self.locale = config["locale"]
        self.dead_zone = config["dead_zone"]
        self.bindings = {dev: dict(keys) for dev, keys in config["bindings"].items()}
        return config

    def _migrate(self, config):
        version = config.get("version", 1)
        if not isinstance(version, int) or version < 1:
            raise ConfigVersionError(f"invalid config version: {version!r}")
        if version > CONFIG_VERSION:
            raise ConfigVersionError(
                f"config version {version} is newer than supported {CONFIG_VERSION}"
            )
        config = dict(config)
        while version < CONFIG_VERSION:
            migrator = getattr(self, f"_migrate_v{version}_to_v{version + 1}")
            config = migrator(config)
            version += 1
        config["version"] = CONFIG_VERSION
        return config

    @staticmethod
    def _migrate_v1_to_v2(config):
        # v1 stored bindings as a flat {action: key} map with no devices.
        bindings = config.get("bindings", {})
        if isinstance(bindings, dict) and not any(
            dev in bindings for dev in SUPPORTED_DEVICES
        ):
            config["bindings"] = {"keyboard": dict(bindings)}
        return config

    @staticmethod
    def _migrate_v2_to_v3(config):
        # v3 introduced locale and dead_zone; fill with defaults.
        config.setdefault("locale", "zh_CN")
        config.setdefault("dead_zone", DEFAULT_DEAD_ZONE)
        return config

    def _validate(self, config):
        validated = self.default_config()
        locale = config.get("locale")
        if locale in SUPPORTED_LOCALES:
            validated["locale"] = locale
        try:
            validated["dead_zone"] = self._clamp_dead_zone(float(config.get("dead_zone")))
        except (TypeError, ValueError):
            validated["dead_zone"] = DEFAULT_DEAD_ZONE
        bindings = config.get("bindings")
        if bindings is not None:
            if not isinstance(bindings, dict):
                raise ConfigValidationError("config 'bindings' must be an object")
            clean = {}
            for device, device_bindings in bindings.items():
                if device not in SUPPORTED_DEVICES:
                    continue  # drop unknown devices instead of crashing
                if not isinstance(device_bindings, dict):
                    continue
                clean[device] = {
                    str(action): normalize_combo(key)
                    for action, key in device_bindings.items()
                    if isinstance(key, str) and key.strip()
                }
            validated["bindings"] = clean
        return validated

    # ------------------------------------------------------------------
    # Key hints
    # ------------------------------------------------------------------
    def get_key_hint(self, action=None, device=None, locale=None):
        """Return a localized hint (text + icon) for an action's binding.

        Hints are computed from the live bindings, so they always reflect
        the latest changes (no stale hints after rebinding).
        """
        locale = locale if locale in SUPPORTED_LOCALES else self.locale
        if action is None:
            # All hints, grouped per device.
            return {
                dev: {
                    act: self._hint_for_key(key, dev, locale)
                    for act, key in keys.items()
                }
                for dev, keys in self.bindings.items()
            }
        devices = [device] if device else list(self.bindings)
        for dev in devices:
            key = self.bindings.get(dev, {}).get(action)
            if key is not None:
                return self._hint_for_key(key, dev, locale)
        return None

    def _hint_for_key(self, key, device, locale):
        table = LOCALIZATIONS.get(locale, LOCALIZATIONS["zh_CN"])
        parts = key.split("+")
        localized = [table.get(part, part) for part in parts]
        text = "+".join(localized)
        main_key = parts[-1] if parts else key
        icon = KEY_ICONS.get(main_key, DEVICE_ICONS.get(device, "⌨"))
        return {"text": text, "icon": icon, "key": key, "device": device, "locale": locale}

    # ------------------------------------------------------------------
    # Input recording
    # ------------------------------------------------------------------
    def record_input(self, events=None, device_filter=None, compress=True):
        """Record input events with timestamps, device filtering and compression.

        - Timestamps: every event gets a relative 'time' offset (seconds)
          from the start of the recording, so replays keep the right pace.
        - Device filter: only events from the given device(s) are kept.
        - Compression: the JSON payload is zlib-compressed.
        Returns the compressed recording as bytes.
        """
        if events is None:
            events = []
        if isinstance(device_filter, str):
            device_filter = {device_filter}
        elif device_filter is not None:
            device_filter = set(device_filter)

        now = time.monotonic()
        recorded = []
        start = None
        for event in events:
            if not isinstance(event, dict):
                continue
            device = event.get("device", "keyboard")
            if device_filter is not None and device not in device_filter:
                continue
            timestamp = event.get("timestamp", now)
            if start is None:
                start = timestamp
            recorded.append({
                "time": round(timestamp - start, 6),
                "device": device,
                "key": event.get("key"),
                "value": event.get("value"),
            })
        payload = json.dumps(
            {"version": CONFIG_VERSION, "events": recorded},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return zlib.compress(payload) if compress else payload

    @staticmethod
    def load_recording(data):
        """Decompress a recording produced by record_input (accepts raw JSON too)."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            payload = zlib.decompress(data)
        except zlib.error:
            payload = data
        return json.loads(payload.decode("utf-8"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _check_device(device):
        if device not in SUPPORTED_DEVICES:
            raise ValueError(
                f"unsupported device {device!r}; expected one of {SUPPORTED_DEVICES}"
            )
        return device

    @staticmethod
    def _clamp_dead_zone(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return DEFAULT_DEAD_ZONE
        return min(max(value, 0.0), 1.0)
