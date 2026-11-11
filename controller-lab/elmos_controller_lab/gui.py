"""Tkinter control surface for the Elmo's Controller Lab."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from .bridge import BridgeClient, BridgeError
from .mapping import ActionLayer, Mapper, MappingProfile, StickTuning
from .model import neutral_state
from .sdl_source import SDLInputSource
from .store import MappingStore

GAMEPAD_BUTTONS = [
    "south", "east", "west", "north", "left_shoulder", "right_shoulder",
    "back", "start", "left_stick", "right_stick",
]
KEY_OPTIONS = "Space, Enter, Escape, Tab, W, A, S, D, E, F, R, Q, LeftShift, LeftControl, LeftAlt, Up, Down, Left, Right"
MOUSE_OPTIONS = ["none", "left", "right", "middle", "back", "forward"]


class ControllerLabApp:
    def __init__(self, bridge_path=None):
        self.root = tk.Tk()
        self.root.title("Elmo's Controller Lab")
        self.root.geometry("1120x820")
        self.root.minsize(940, 700)
        self.bridge = BridgeClient(bridge_path, on_event=self._bridge_event)
        self.source = None
        self.store = MappingStore()
        self.mapping = MappingProfile()
        self.profiles = []
        self.profile_by_label = {}
        self.device_by_label = {}
        self.active = False
        self.active_slots = []
        self.physical_instance = None
        self.device_guid = "unknown"
        self.mapper = None
        self._after_id = None

        self.status_var = tk.StringVar(value="Starting Controller Lab…")
        self.driver_var = tk.StringVar(value="Checking virtual driver…")
        self.game_var = tk.StringVar(value="default")
        self.device_var = tk.StringVar()
        self.profile_var = tk.StringVar()
        self.search_var = tk.StringVar()

        self.button_targets = {}
        self.keyboard_entries = {}
        self.mouse_targets = {}
        self.layer_button_targets = {}
        self.layer_keyboard_entries = {}
        self.left_deadzone = tk.DoubleVar(value=0.12)
        self.right_deadzone = tk.DoubleVar(value=0.12)
        self.left_exponent = tk.DoubleVar(value=1.0)
        self.right_exponent = tk.DoubleVar(value=1.0)
        self.left_sensitivity = tk.DoubleVar(value=1.0)
        self.right_sensitivity = tk.DoubleVar(value=1.0)
        self.left_wasd = tk.BooleanVar(value=False)
        self.right_mouse = tk.BooleanVar(value=False)
        self.mouse_sensitivity = tk.DoubleVar(value=14.0)
        self.touchpad_mode = tk.StringVar(value="off")
        self.touchpad_sensitivity = tk.DoubleVar(value=1.0)
        self.layer_enabled = tk.BooleanVar(value=False)
        self.layer_activator = tk.StringVar(value="left_paddle")
        self.layer_mode = tk.StringVar(value="hold")

        self._build_ui()
        self._connect()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        root = self.root
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        header = ttk.Frame(root, padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="ELMO'S CONTROLLER LAB", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="UNIVERSAL INPUT • VIRTUAL OUTPUT", foreground="#5b9b83").pack(side="left", padx=18)
        ttk.Label(root, textvariable=self.status_var, padding=(18, 2)).pack(fill="x")

        session = ttk.LabelFrame(root, text="Controller session", padding=12, style="Section.TLabelframe")
        session.pack(fill="x", padx=16, pady=8)
        session.columnconfigure(1, weight=1)
        session.columnconfigure(3, weight=2)
        ttk.Label(session, text="Physical controller").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.device_combo = ttk.Combobox(session, textvariable=self.device_var, state="readonly", width=35)
        self.device_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(session, text="Virtual identity").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.profile_combo = ttk.Combobox(session, textvariable=self.profile_var, state="readonly", width=48)
        self.profile_combo.grid(row=0, column=3, sticky="ew", padx=4, pady=4)
        ttk.Label(session, text="Game / profile group").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(session, textvariable=self.game_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(session, text="Refresh devices", command=self.refresh_devices).grid(row=1, column=2, padx=4, pady=4)
        ttk.Button(session, text="Refresh profiles", command=self.refresh_profiles).grid(row=1, column=3, sticky="w", padx=4, pady=4)
        actions = ttk.Frame(session)
        actions.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.start_button = ttk.Button(actions, text="Start virtual controller", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop and release devices", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Label(actions, textvariable=self.driver_var).pack(side="right")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=16, pady=8)
        buttons_tab = ttk.Frame(notebook, padding=14)
        analog_tab = ttk.Frame(notebook, padding=14)
        layer_tab = ttk.Frame(notebook, padding=14)
        notebook.add(buttons_tab, text="Buttons & Actions")
        notebook.add(analog_tab, text="Sticks & Touchpad")
        notebook.add(layer_tab, text="Action Layer")

        face = ttk.LabelFrame(buttons_tab, text="Face-button remapping", padding=10)
        face.pack(fill="x", pady=6)
        headings = ["Physical input", "Virtual gamepad button", "Keyboard keys", "Mouse button"]
        for col, label in enumerate(headings):
            ttk.Label(face, text=label).grid(row=0, column=col, sticky="w", padx=5, pady=3)
        targets = ["default"] + GAMEPAD_BUTTONS
        for row, semantic in enumerate(("south", "east", "west", "north"), start=1):
            label = {"south": "Cross / A", "east": "Circle / B", "west": "Square / X", "north": "Triangle / Y"}[semantic]
            ttk.Label(face, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)
            var = tk.StringVar(value=semantic)
            self.button_targets[semantic] = var
            ttk.Combobox(face, textvariable=var, values=targets, state="readonly", width=20).grid(row=row, column=1, padx=5, pady=4)
            key = tk.StringVar()
            self.keyboard_entries[semantic] = key
            ttk.Entry(face, textvariable=key, width=28).grid(row=row, column=2, padx=5, pady=4)
            mouse = tk.StringVar(value="none")
            self.mouse_targets[semantic] = mouse
            ttk.Combobox(face, textvariable=mouse, values=MOUSE_OPTIONS, state="readonly", width=14).grid(row=row, column=3, padx=5, pady=4)
        ttk.Label(buttons_tab, text="Keyboard examples: Space, E, LeftShift. Separate multiple keys with commas.",
                  foreground="#777").pack(anchor="w", pady=4)

        analog = ttk.LabelFrame(analog_tab, text="Analog shaping", padding=10)
        analog.pack(fill="x", pady=6)
        self._scale_row(analog, 0, "Left stick deadzone", self.left_deadzone, 0, 0.5)
        self._scale_row(analog, 1, "Right stick deadzone", self.right_deadzone, 0, 0.5)
        self._scale_row(analog, 2, "Left stick response exponent", self.left_exponent, 0.3, 3.0)
        self._scale_row(analog, 3, "Right stick response exponent", self.right_exponent, 0.3, 3.0)
        self._scale_row(analog, 4, "Left stick sensitivity", self.left_sensitivity, 0.2, 2.5)
        self._scale_row(analog, 5, "Right stick sensitivity", self.right_sensitivity, 0.2, 2.5)
        ttk.Checkbutton(analog, text="Use left stick as WASD", variable=self.left_wasd).grid(row=6, column=0, sticky="w", pady=6)
        ttk.Checkbutton(analog, text="Use right stick as mouse", variable=self.right_mouse).grid(row=7, column=0, sticky="w", pady=6)
        self._scale_row(analog, 8, "Mouse sensitivity", self.mouse_sensitivity, 1, 80)
        touch = ttk.LabelFrame(analog_tab, text="Touchpad mapping", padding=10)
        touch.pack(fill="x", pady=10)
        ttk.Label(touch, text="Touchpad mode").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Combobox(touch, textvariable=self.touchpad_mode, values=["off", "mouse", "right_stick"],
                     state="readonly", width=20).grid(row=0, column=1, sticky="w", padx=5)
        self._scale_row(touch, 1, "Touchpad sensitivity", self.touchpad_sensitivity, 0.1, 4.0)

        layer = ttk.LabelFrame(layer_tab, text="Hold / toggle action layer", padding=12)
        layer.pack(fill="x", pady=6)
        ttk.Checkbutton(layer, text="Enable a second action layer", variable=self.layer_enabled).grid(row=0, column=0, sticky="w", padx=5, pady=6)
        ttk.Label(layer, text="Activator").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(layer, textvariable=self.layer_activator, values=GAMEPAD_BUTTONS + ["left_paddle", "right_paddle"],
                     state="readonly", width=22).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(layer, text="Activation").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(layer, textvariable=self.layer_mode, values=["hold", "toggle"],
                     state="readonly", width=22).grid(row=2, column=1, sticky="w", padx=5)
        layer_face = ttk.LabelFrame(layer_tab, text="Alternate face-button actions while the layer is active", padding=10)
        layer_face.pack(fill="x", pady=8)
        for col, label in enumerate(("Physical input", "Virtual gamepad button", "Keyboard keys")):
            ttk.Label(layer_face, text=label).grid(row=0, column=col, sticky="w", padx=5, pady=3)
        for row, semantic in enumerate(("south", "east", "west", "north"), start=1):
            ttk.Label(layer_face, text=semantic.title()).grid(row=row, column=0, sticky="w", padx=5, pady=4)
            target = tk.StringVar(value=semantic)
            self.layer_button_targets[semantic] = target
            ttk.Combobox(layer_face, textvariable=target, values=["default"] + GAMEPAD_BUTTONS,
                         state="readonly", width=20).grid(row=row, column=1, padx=5, pady=4)
            keys = tk.StringVar()
            self.layer_keyboard_entries[semantic] = keys
            ttk.Entry(layer_face, textvariable=keys, width=28).grid(row=row, column=2, padx=5, pady=4)
        ttk.Label(layer_tab, text="The activator is reserved for the layer. Hold or toggle it to switch to these alternate actions.",
                  foreground="#777").pack(anchor="w", pady=4)

        footer = ttk.Frame(root, padding=(16, 8))
        footer.pack(fill="x")
        ttk.Button(footer, text="Load saved profile", command=self.load_mapping).pack(side="left")
        ttk.Button(footer, text="Save mapping profile", command=self.save_mapping).pack(side="left", padx=8)
        ttk.Label(footer, text="Profiles are isolated by physical GUID + game + virtual identity.",
                  foreground="#777").pack(side="right")

        self.device_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_mapping())
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_mapping())

    def _scale_row(self, parent, row, label, variable, low, high):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)
        scale = ttk.Scale(parent, variable=variable, from_=low, to=high, orient="horizontal", length=330)
        scale.grid(row=row, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(parent, textvariable=variable, width=7).grid(row=row, column=2, sticky="w", padx=5)

    def _connect(self):
        try:
            status = self.bridge.request("status")
            self.driver_var.set(
                "Driver ready · elevated" if status.get("driverPrepared") and status.get("elevated")
                else "Driver prepared · admin required" if status.get("driverPrepared")
                else "Driver setup required" if not status.get("driverInstalled")
                else "Run explicit driver setup"
            )
            self.refresh_profiles()
        except Exception as exc:
            self.status_var.set(str(exc))
        self.refresh_devices()

    def refresh_devices(self):
        if self.source is None:
            try:
                self.source = SDLInputSource()
            except Exception as exc:
                self.status_var.set(f"SDL controller reader unavailable: {exc}")
                return
        try:
            devices = self.source.refresh()
            self.device_by_label = {}
            labels = []
            for item in devices:
                label = f'{item["index"]} · {item["name"]} · {item["guid"][:8]}'
                self.device_by_label[label] = item
                labels.append(label)
            self.device_combo["values"] = labels
            if labels and self.device_var.get() not in labels:
                self.device_var.set(labels[0])
            self.status_var.set(f"{len(labels)} physical/virtual controller(s) visible through SDL.")
        except Exception as exc:
            self.status_var.set(f"Device refresh failed: {exc}")

    def refresh_profiles(self):
        try:
            result = self.bridge.request("profiles")
            self.profiles = [
                p for p in result.get("profiles", [])
                if p.get("deployable") and not p.get("requiresUsbip")
                and "keyboard" not in str(p.get("type", "")).casefold()
                and "mouse" not in str(p.get("type", "")).casefold()
            ]
            self.profile_by_label = {}
            labels = []
            for profile in self.profiles:
                label = f'{profile.get("displayName") or profile.get("name")}  [{profile.get("id")}]'
                self.profile_by_label[label] = profile
                labels.append(label)
            self.profile_combo["values"] = labels
            if labels and self.profile_var.get() not in labels:
                preferred = next((x for x in labels if "xbox-360-wired" in x), labels[0])
                self.profile_var.set(preferred)
            self.status_var.set(f'{len(self.profiles)} deployable gamepad/joystick/wheel profiles loaded.')
        except Exception as exc:
            self.status_var.set(f"Profile catalogue unavailable: {exc}")

    def _selected_device(self):
        return self.device_by_label.get(self.device_var.get())

    def _selected_profile(self):
        return self.profile_by_label.get(self.profile_var.get())

    def _current_key(self):
        device = self._selected_device()
        profile = self._selected_profile()
        if not device or not profile:
            raise BridgeError("Choose a physical controller and a virtual identity.")
        return device, profile

    def _collect_mapping(self):
        device, target = self._current_key()
        mapping = MappingProfile(
            name=f'{device["name"]} → {target.get("name")}',
            button_map={k: v.get() for k, v in self.button_targets.items() if v.get() not in ("default", k)},
            keyboard_map={k: [x.strip() for x in v.get().split(",") if x.strip()]
                          for k, v in self.keyboard_entries.items() if v.get().strip()},
            mouse_map={k: v.get() for k, v in self.mouse_targets.items() if v.get() != "none"},
            left_stick=StickTuning(deadzone=float(self.left_deadzone.get()), exponent=float(self.left_exponent.get()),
                                   sensitivity=float(self.left_sensitivity.get())),
            right_stick=StickTuning(deadzone=float(self.right_deadzone.get()), exponent=float(self.right_exponent.get()),
                                    sensitivity=float(self.right_sensitivity.get())),
            left_stick_as_wasd=bool(self.left_wasd.get()),
            right_stick_mouse=bool(self.right_mouse.get()),
            mouse_sensitivity=float(self.mouse_sensitivity.get()),
            touchpad_mode=self.touchpad_mode.get(),
            touchpad_sensitivity=float(self.touchpad_sensitivity.get()),
        )
        if self.layer_enabled.get():
            mapping.layer = ActionLayer(
                activator=self.layer_activator.get(),
                mode=self.layer_mode.get(),
                button_map={k: v.get() for k, v in self.layer_button_targets.items()
                            if v.get() not in ("default", k)},
                keyboard_map={k: [x.strip() for x in v.get().split(",") if x.strip()]
                              for k, v in self.layer_keyboard_entries.items() if v.get().strip()},
            )
        return mapping

    def save_mapping(self):
        try:
            device, target = self._current_key()
            mapping = self._collect_mapping()
            self.store.save(device["guid"], self.game_var.get().strip() or "default", target["id"], mapping)
            self.mapping = mapping
            self.status_var.set("Mapping profile saved locally for this controller, game and virtual identity.")
        except Exception as exc:
            messagebox.showerror("Save mapping", str(exc), parent=self.root)

    def load_mapping(self):
        try:
            device, target = self._current_key()
            self.mapping = self.store.get(device["guid"], self.game_var.get().strip() or "default", target["id"])
            p = self.mapping
            for key, var in self.button_targets.items():
                var.set(p.button_map.get(key, key))
            for key, var in self.keyboard_entries.items():
                var.set(", ".join(p.keyboard_map.get(key, [])))
            for key, var in self.mouse_targets.items():
                var.set(p.mouse_map.get(key, "none"))
            self.left_deadzone.set(p.left_stick.deadzone)
            self.right_deadzone.set(p.right_stick.deadzone)
            self.left_exponent.set(p.left_stick.exponent)
            self.right_exponent.set(p.right_stick.exponent)
            self.left_sensitivity.set(p.left_stick.sensitivity)
            self.right_sensitivity.set(p.right_stick.sensitivity)
            self.left_wasd.set(p.left_stick_as_wasd)
            self.right_mouse.set(p.right_stick_mouse)
            self.mouse_sensitivity.set(p.mouse_sensitivity)
            self.touchpad_mode.set(p.touchpad_mode)
            self.touchpad_sensitivity.set(p.touchpad_sensitivity)
            self.layer_enabled.set(p.layer is not None)
            for key, var in self.layer_button_targets.items():
                var.set(p.layer.button_map.get(key, key) if p.layer else key)
            for key, var in self.layer_keyboard_entries.items():
                var.set(", ".join(p.layer.keyboard_map.get(key, [])) if p.layer else "")
            if p.layer:
                self.layer_activator.set(p.layer.activator)
                self.layer_mode.set(p.layer.mode)
            self.status_var.set(f"Loaded mapping: {p.name}")
        except Exception as exc:
            self.status_var.set(f"Could not load mapping: {exc}")

    def start(self):
        if self.active:
            return
        try:
            device, target = self._current_key()
            self.mapping = self._collect_mapping()
            self.store.save(device["guid"], self.game_var.get().strip() or "default", target["id"], self.mapping)
            status = self.bridge.request("status")
            if not status.get("driverInstalled") or not status.get("driverPrepared"):
                raise BridgeError("Install the virtual driver explicitly first using Install-ControllerLab-Driver.ps1.")
            if not status.get("elevated"):
                raise BridgeError("Virtual devices require administrator approval. Start the GUI with Run-ControllerLab-Elevated.ps1 gui.")
            if self.source is None:
                self.refresh_devices()
            self.physical_instance = device["instance_id"]
            self.device_guid = device["guid"]
            self.source.attach_sensor_reader(self.physical_instance)
            self.mapper = Mapper(self.mapping)
            self.active_slots = []
            slot = "gui-gamepad"
            self.bridge.request("create", slot=slot, profile_id=target["id"])
            self.active_slots.append(slot)
            need_keyboard = bool(self.mapping.keyboard_map or self.mapping.trigger_keyboard_map or self.mapping.left_stick_as_wasd or
                                 (self.mapping.layer and (self.mapping.layer.keyboard_map or self.mapping.layer.left_stick_as_wasd)))
            need_mouse = bool(self.mapping.mouse_map or self.mapping.right_stick_mouse or self.mapping.touchpad_mode == "mouse" or
                              (self.mapping.layer and (self.mapping.layer.mouse_map or self.mapping.layer.right_stick_mouse or
                                                       self.mapping.layer.touchpad_mode == "mouse")))
            if need_keyboard:
                self.bridge.request("create", slot="gui-keyboard", profile_id="microsoft-wired-keyboard-600")
                self.active_slots.append("gui-keyboard")
            if need_mouse:
                self.bridge.request("create", slot="gui-mouse", profile_id="microsoft-optical-mouse-tilt-wheel")
                self.active_slots.append("gui-mouse")
            self.active = True
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status_var.set("Live virtual controller active. Move the physical controller to test mappings.")
            self._tick()
        except Exception as exc:
            self.stop()
            messagebox.showerror("Start virtual controller", str(exc), parent=self.root)

    def _tick(self):
        if not self.active:
            return
        try:
            physical = self.source.read_instance(self.physical_instance)
            output = self.mapper.map_actions(physical)
            self.bridge.send_state("gui-gamepad", output.gamepad.to_wire())
            if "gui-keyboard" in self.active_slots:
                self.bridge.send_keyboard("gui-keyboard", sorted(output.keyboard_keys), sorted(output.keyboard_modifiers))
            if "gui-mouse" in self.active_slots:
                self.bridge.send_mouse("gui-mouse", sorted(output.mouse_buttons), output.mouse_dx,
                                       output.mouse_dy, output.mouse_wheel, output.mouse_pan)
            self._after_id = self.root.after(8, self._tick)
        except Exception as exc:
            self.status_var.set(f"Input stream stopped: {exc}")
            self.stop()

    def stop(self):
        self.active = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        for slot in reversed(self.active_slots):
            try:
                if slot.endswith("keyboard"):
                    self.bridge.send_keyboard(slot, [], [])
                elif slot.endswith("mouse"):
                    self.bridge.send_mouse(slot, [], 0, 0, 0, 0)
                else:
                    self.bridge.send_state(slot, neutral_state().to_wire())
                self.bridge.request("destroy", slot=slot, timeout=15)
            except Exception:
                pass
        self.active_slots = []
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set("Virtual output stopped; held keys/buttons released.")

    def _bridge_event(self, event):
        if event.get("event_name") == "error":
            message = event.get("message", "Virtual device error.")
            try:
                self.root.after(0, lambda: self.status_var.set(message))
            except Exception:
                pass

    def close(self):
        self.stop()
        if self.source:
            self.source.close()
        self.bridge.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main(bridge_path=None):
    ControllerLabApp(bridge_path).run()
